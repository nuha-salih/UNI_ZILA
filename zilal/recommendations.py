"""
recommendations.py — توصيات قابلة للتفسير مبنية على مؤشرات محسوبة فقط (منطق قرار منفصل عن
الفيزياء وعن تعلّم الآلة).

كل توصية تحمل: سبب التوليد (المؤشر والعتبة)، والأدلة الرقمية، والأثر المتوقع على الطاقة والراحة
*في المحاكاة* — دون أي وعد بتوفير مضمون. إن لم تتحقق شروط أي قاعدة لا تُولَّد توصية عامة.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .engine.evaluation import hhmm, saving_percent
from .engine.sensitivity import cop_energy_band
from .engine.evaluation import compute_metrics
from .engine.strategies import STRATEGY_NAMES_AR, make_strategy
from .engine.thermal_model import ORIENTATION_AR, simulate

# عتبات القواعد (افتراضات موثّقة)
UNOCC_SHARE_MIN = 0.20      # حصة طاقة تكييف الخلو من طاقة تكييف الاستراتيجية الحالية
LIGHT_UNOCC_MIN_KWH = 0.10  # أقل طاقة إنارة في قاعة فارغة تستدعي توصية الإنارة
SHADING_GAIN_MIN_PCT = 5.0  # أقل خفض طاقة يبرر توصية التظليل
HIGH_SOLAR_PEAK_W = 3000.0  # ذروة كسب شمسي تستدعي الفحص
OVERCOOL_EXTRA_MIN_PCT = 5.0
PRIORITY_AR = {1: "عالية", 2: "متوسطة", 3: "منخفضة"}


@dataclass
class Recommendation:
    rec_id: str
    category_ar: str
    title_ar: str
    why_ar: str
    evidence: dict = field(default_factory=dict)
    energy_impact_ar: str = ""
    comfort_impact_ar: str = ""
    priority: int = 2

    def as_row(self) -> dict:
        return {"id": self.rec_id, "category": self.category_ar, "title": self.title_ar, "why": self.why_ar,
                "energy_impact": self.energy_impact_ar, "comfort_impact": self.comfort_impact_ar,
                "priority": PRIORITY_AR[self.priority]}


def _precool_start(df: pd.DataFrame) -> float | None:
    occ = df["occupancy"].to_numpy() > 0
    if not occ.any():
        return None
    j = int(np.argmax(occ))
    q = df["q_cool_w"].to_numpy()
    k = j
    while k > 0 and q[k - 1] > 1.0:
        k -= 1
    return float(df["hour"].iloc[k]) if k < j else None


def generate(analysis: dict, current_key: str = "A", data_quality: dict | None = None) -> list[Recommendation]:
    s: pd.DataFrame = analysis["summary"]
    p = analysis["params"]
    res = analysis["results"]
    recs: list[Recommendation] = []
    if current_key not in s.index:
        raise ValueError("الاستراتيجية الحالية غير موجودة في المقارنة.")
    cur = s.loc[current_key]
    best = analysis.get("best")

    # 1) طاقة تكييف وقت الخلو (التكييف وحده؛ الإنارة في القاعدة 10)
    if cur["hvac_kwh"] > 0.1:
        share = cur["unoccupied_hvac_kwh"] / cur["hvac_kwh"]
        if share >= UNOCC_SHARE_MIN:
            recs.append(Recommendation(
                "R1", "جدولة التكييف", "مراجعة جدول تشغيل التكييف",
                f"{share:.0%} من طاقة تكييف الاستراتيجية الحالية ({STRATEGY_NAMES_AR[current_key]}) استُهلكت والقاعة خالية "
                f"(العتبة {UNOCC_SHARE_MIN:.0%})، منها {cur['unnecessary_hvac_kwh']:.1f} kWh خارج نافذة التهيئة المسبقة (4 ساعات).",
                {"unoccupied_kwh": cur["unoccupied_hvac_kwh"], "unnecessary_kwh": cur["unnecessary_hvac_kwh"],
                 "share": share},
                f"حتى {cur['unnecessary_hvac_kwh']:.1f} kWh/يوم من طاقة التكييف في هذه المحاكاة يمكن تجنبها دون أثر على فترات الإشغال.",
                "لا أثر مباشر على الراحة لأن الطاقة المعنية خارج فترات الإشغال.", 1 if share > 0.4 else 2))

    # 10) الإنارة في قاعة فارغة → ربطها بالإشغال (الأثر محسوب بإعادة المحاكاة، لا تقدير)
    if cur.get("unoccupied_lighting_kwh", 0.0) >= LIGHT_UNOCC_MIN_KWH and "inputs" in analysis:
        strat = make_strategy(current_key, analysis.get("cfg"))
        strat.lighting_mode = "occupancy"   # الاستراتيجية نفسها للتكييف؛ يتغير التحكم بالإنارة فقط
        inp = analysis["inputs"]
        alt = compute_metrics(simulate(inp, strat), p, inp)
        d_tot = cur["energy_kwh"] - alt["energy_kwh"]
        d_light = cur["lighting_kwh"] - alt["lighting_kwh"]
        d_hvac = cur["hvac_kwh"] - alt["hvac_kwh"]
        recs.append(Recommendation(
            "R10", "الإنارة", "ربط الإنارة بإشغال القاعة",
            f"الإنارة تعمل وفق جدول ثابت {hhmm(p.lighting_on_h)}–{hhmm(p.lighting_off_h)} (افتراض عرض) واستهلكت "
            f"{cur['unoccupied_lighting_kwh']:.2f} kWh والقاعة فارغة (كثافة إنارة {p.lighting_w_per_m2:g} W/m² — افتراض نموذج أولي). "
            "حرارة هذه الإنارة تضاف أيضاً إلى حمل التبريد.",
            {"unoccupied_lighting_kwh": cur["unoccupied_lighting_kwh"], "saved_total_kwh": d_tot,
             "saved_lighting_kwh": d_light, "saved_hvac_kwh": d_hvac},
            f"إعادة المحاكاة بالاستراتيجية نفسها مع إنارة حسب الإشغال: {cur['energy_kwh']:.1f} → {alt['energy_kwh']:.1f} kWh/يوم "
            f"(إنارة {d_light:+.1f}، تكييف {d_hvac:+.1f} kWh) في المحاكاة.",
            f"مخالفة الراحة {alt['comfort_violation_h']:.2f} ساعة مقابل {cur['comfort_violation_h']:.2f} ساعة حالياً.",
            1 if d_tot > 0.1 * max(cur["energy_kwh"], 1e-9) else 2))

    # 2) أفضل استراتيجية مع راحة مقبولة
    if best and best != current_key:
        b = s.loc[best]
        d = saving_percent(cur["energy_kwh"], b["energy_kwh"])
        if d > 0.5:
            recs.append(Recommendation(
                "R2", "استراتيجية التحكم", f"اعتماد «{STRATEGY_NAMES_AR[best]}» بدل الاستراتيجية الحالية",
                f"أقل استهلاك بين الاستراتيجيات التي أبقت المخالفة ≤ 5٪ من وقت الإشغال، تحت الظروف نفسها تماماً.",
                {"current_kwh": cur["energy_kwh"], "best_kwh": b["energy_kwh"], "diff_pct": d},
                f"{cur['energy_kwh']:.1f} → {b['energy_kwh']:.1f} kWh/يوم كهرباء كلية (تكييف + إنارة، {d:.0f}٪ أقل) في المحاكاة.",
                f"مخالفة الراحة {b['comfort_violation_h']:.2f} ساعة مقابل {cur['comfort_violation_h']:.2f} ساعة حالياً.", 1))

    # 3) تحذير: توفير على حساب الراحة
    for k, r in s.iterrows():
        if k == "N" or r["comfort_ok"] or r["saving_pct"] <= 0.5:
            continue
        recs.append(Recommendation(
            f"R3-{k}", "الراحة الحرارية", f"عدم اعتماد «{STRATEGY_NAMES_AR[k]}» بإعداداتها الحالية",
            f"تخفض الطاقة {r['saving_pct']:.0f}٪ عن الأساس لكن الحرارة خرجت عن نطاق الراحة "
            f"{r['comfort_violation_h']:.2f} ساعة من {r['occupied_h']:.2f} ساعة إشغال (العتبة 5٪).",
            {"saving_pct": r["saving_pct"], "violation_h": r["comfort_violation_h"],
             "max_deviation_c": r["max_deviation_c"]},
            "التوفير هنا لا يُعدّ توفيراً مقبولاً.",
            f"أقصى ابتعاد عن النطاق {r['max_deviation_c']:.1f} °م، وأطول فترة متصلة {r['longest_uncomfortable_h']:.2f} ساعة.", 2))

    # 4) توقيت التبريد المسبق
    if "D" in s.index and s.loc["D", "comfort_applicable"]:
        late = [k for k in ("B", "C") if k in s.index and s.loc[k, "arrival_temp_c"] > p.comfort_high_c + 1e-6]
        if late and s.loc["D", "arrival_temp_c"] <= p.comfort_high_c + 1e-6:
            start = _precool_start(res["D"])
            arr = "، ".join(f"{STRATEGY_NAMES_AR[k]}: {s.loc[k, 'arrival_temp_c']:.1f} °م" for k in late)
            recs.append(Recommendation(
                "R4", "ما قبل المحاضرة", "تحسين توقيت التبريد المسبق قبل المحاضرة",
                f"عند وصول الطلاب كانت الحرارة فوق الحد الأعلى للراحة ({p.comfort_high_c:.1f} °م) في: {arr}؛ "
                f"بينما وصل التحكم التنبؤي إلى {s.loc['D', 'arrival_temp_c']:.1f} °م"
                + (f" ببدء التبريد عند {hhmm(start)}." if start is not None else "."),
                {"precool_start_h": start, "arrival_D_c": s.loc["D", "arrival_temp_c"]},
                f"طاقة التنبؤي {s.loc['D', 'energy_kwh']:.1f} kWh/يوم مقارنة بـ {s.loc[late[0], 'energy_kwh']:.1f} kWh/يوم.",
                "قاعة جاهزة عند الوصول بدل دقائق أولى حارة.", 1))

    # 5) التظليل
    sw = analysis.get("sweep")
    if sw is not None and len(sw):
        sub = sw[sw["orientation"] == p.orientation].drop_duplicates("shading").set_index("shading").sort_index()
        cur_s = float(p.shading_fraction)
        higher = sub[sub.index > cur_s + 1e-9]
        if len(higher) and cur_s in sub.index:
            tgt = float(higher.index.max())
            e0, e1 = sub.loc[cur_s, "energy_kwh"], sub.loc[tgt, "energy_kwh"]
            g0, g1 = sub.loc[cur_s, "solar_gain_kwh"], sub.loc[tgt, "solar_gain_kwh"]
            d = saving_percent(e0, e1)
            if d >= SHADING_GAIN_MIN_PCT:
                recs.append(Recommendation(
                    "R5", "التظليل", f"رفع فعالية التظليل من {cur_s:.0%} إلى {tgt:.0%}",
                    f"في مسح التظليل للنافذة ({ORIENTATION_AR[p.orientation]}) انخفض الكسب الشمسي اليومي "
                    f"{g0:.1f} → {g1:.1f} kWh، وطاقة الاستراتيجية C {d:.0f}٪ (العتبة {SHADING_GAIN_MIN_PCT:.0f}٪).",
                    {"solar_from": g0, "solar_to": g1, "energy_from": e0, "energy_to": e1},
                    f"{e0:.1f} → {e1:.1f} kWh/يوم (الاستراتيجية C، محاكاة).",
                    f"مخالفة الراحة {sub.loc[cur_s, 'comfort_violation_h']:.2f} → {sub.loc[tgt, 'comfort_violation_h']:.2f} ساعة.",
                    1 if d >= 15 else 2))

    # 6) كسب شمسي مرتفع
    inp = analysis["inputs"]
    peak = float(inp.q_solar.max())
    if peak >= HIGH_SOLAR_PEAK_W:
        k = int(np.argmax(inp.q_solar))
        recs.append(Recommendation(
            "R6", "الكسب الشمسي", "فحص حالة الكسب الشمسي المرتفع",
            f"ذروة الكسب الشمسي {peak / 1000:.1f} kW عند {hhmm(inp.hours[k])} (العتبة {HIGH_SOLAR_PEAK_W / 1000:.0f} kW) "
            f"لنافذة {ORIENTATION_AR[p.orientation]} مساحتها {p.window_area_m2:.0f} م² و SHGC = {p.shgc:.2f}.",
            {"peak_solar_w": peak, "peak_hour": float(inp.hours[k])},
            "يمكن تقدير الأثر بتغيير SHGC أو التظليل في صفحة المحاكاة.",
            "الكسب الشمسي المرتفع يرفع خطر تجاوز الحد الأعلى للراحة عند محدودية قدرة المكيّف.", 2))

    # 7) الإفراط في التبريد
    oc = analysis.get("overcooling")
    if oc is not None and len(oc) > 1:
        low = oc.loc[oc["setpoint_c"].idxmin()]
        if low["extra_energy_pct"] >= OVERCOOL_EXTRA_MIN_PCT:
            recs.append(Recommendation(
                "R7", "الإفراط في التبريد", f"تجنّب نقاط ضبط أدنى من نطاق الراحة (مثل {low['setpoint_c']:.1f} °م)",
                f"خفض الهدف إلى {low['setpoint_c']:.1f} °م رفع طاقة التشغيل حسب الجدول {low['extra_energy_pct']:.0f}٪ "
                f"مقارنة بالهدف {p.comfort_setpoint_c:.1f} °م (العتبة {OVERCOOL_EXTRA_MIN_PCT:.0f}٪).",
                {"setpoint": low["setpoint_c"], "extra_pct": low["extra_energy_pct"]},
                f"+{low['extra_energy_pct']:.0f}٪ طاقة دون فائدة في المحاكاة.",
                f"برودة زائدة {low['cold_violation_h']:.2f} ساعة خلال الإشغال (أدنى حرارة {low['min_t_occupied_c']:.1f} °م).", 2))

    # 8) جودة البيانات
    if data_quality:
        cs = data_quality.get("clean_summary", {})
        replaced = sum(v.get("replaced", 0) for k, v in cs.items() if isinstance(v, dict))
        long_gap = any(v.get("long_gap") for v in cs.values() if isinstance(v, dict))
        tbl = data_quality.get("table")
        if replaced > 0 or long_gap:
            err = ""
            if tbl is not None and "naive" in tbl.index:
                err = (f" خطأ الطاقة مع المعالجة الساذجة {tbl.loc['naive', 'energy_error_pct']:+.1f}٪، "
                       f"ومع المعالجة الموثّقة {tbl.loc['cleaned', 'energy_error_pct']:+.1f}٪ مقارنة بالبيانات السليمة.")
            recs.append(Recommendation(
                "R8", "جودة البيانات", "مراجعة جودة بيانات الحساسات قبل اعتماد النتائج",
                f"اكتُشفت واستُبدلت {replaced} قراءة طقس (مفقودة/شاذة)" + (" مع فجوة طويلة" if long_gap else "") + "." + err,
                {"replaced": replaced, "long_gap": long_gap},
                "النتائج المبنية على بيانات معالجة أقل يقيناً.", "", 2 if not long_gap else 1))

    # 9) حساسية COP
    if cur["hvac_kwh"] > 0.1:
        lo_h, hi_h = cop_energy_band(cur["hvac_kwh"], p.cop)   # COP يمس التكييف فقط
        lo, hi = lo_h + cur["lighting_kwh"], hi_h + cur["lighting_kwh"]
        recs.append(Recommendation(
            "R9", "افتراضات النموذج", "التحقق من معامل الأداء الفعلي للمكيّف (COP)",
            f"طاقة التكييف المحسوبة تعتمد على COP = {p.cop:.1f} (افتراض). ضمن المدى المعتمد 2.5–3.5 تتراوح الطاقة الكلية "
            f"للاستراتيجية الحالية (تكييف + إنارة ثابتة {cur['lighting_kwh']:.1f} kWh) بين {lo:.1f} و {hi:.1f} kWh/يوم.",
            {"low": lo, "high": hi},
            f"عدم يقين ±{(hi - lo) / 2:.1f} kWh/يوم بسبب COP وحده.", "لا أثر على الراحة (COP لا يغيّر الحمل الحراري).", 3))
    return sorted(recs, key=lambda r: r.priority)


def to_frame(recs: list[Recommendation]) -> pd.DataFrame:
    return pd.DataFrame([r.as_row() for r in recs])



# ---------------------------------------------------------------------------
# توصيات على مستوى الحرم (من الوضع التشغيلي لكل قاعة؛ الأثر محسوب بإعادة محاكاة القاعة نفسها)
# ---------------------------------------------------------------------------
def campus_recommendations(metrics, weather_day=None, threshold: float = 0.95) -> list[dict]:
    """
    لكل قاعة: إن كانت راحتها دون الحد → اقتراح التشغيل التنبؤي عند هدف الراحة (استعادة الراحة، قد يزيد الكهرباء).
    إن كانت مريحة وتعمل بغير ظِلال → اقتراح التنبؤي إن وفّر كهرباء مع بقاء الراحة ≥ الحد.
    الأثر = فرق المحاكاة للقاعة نفسها بالظروف نفسها (لا تقدير).
    """
    from . import campus
    out = []
    for rid, m in metrics.iterrows():
        room = campus.ROOM_BY_ID[rid]
        comfort_bad = m["comfort_compliance"] < threshold - 1e-9
        if not comfort_bad and room.mode.strategy in ("C", "D"):
            continue
        _, alt = campus.simulate_room(room, strategy="D", target_c=None, weather_day=weather_day)
        if alt["comfort_compliance"] < threshold - 1e-9:
            continue
        d = alt["energy_kwh"] - m["energy_kwh"]
        if comfort_bad:
            kind, title = "comfort", ("إعادة الهدف إلى 24 °م مع التشغيل التنبؤي" if room.mode.target_c is not None
                                      else "التشغيل التنبؤي بدل الوضع الحالي")
        elif d < -0.5:
            kind, title = "saving", "التشغيل التنبؤي بدل الوضع الحالي"
        else:
            continue
        out.append({"room_id": rid, "kind": kind, "title": title, "delta_kwh": float(d),
                    "energy_now": float(m["energy_kwh"]), "energy_new": float(alt["energy_kwh"]),
                    "comfort_now": float(m["comfort_compliance"]), "comfort_new": float(alt["comfort_compliance"])})
    out.sort(key=lambda r: (r["kind"] != "saving", r["delta_kwh"] if r["kind"] == "saving" else -abs(r["comfort_new"] - r["comfort_now"])))
    return out
