"""
report_data.py — بناء محتوى التقرير من النتائج المحسوبة (بلا قيم ثابتة) على أربعة مستويات.

البنية الناتجة مستقلة عن الصيغة: عناوين، أزواج (مفتاح، قيمة)، جداول، وقوائم نصية —
يُصدَّرها pdf_report.py و csv_export.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from .. import campus, challenge, recommendations as rc
from ..aggregation import LEVELS_AR, aggregate
from ..engine.evaluation import hhmm, run_analysis
from ..engine.scenarios import SCENARIOS, Scenario
from ..engine.strategies import STRATEGY_KEYS, STRATEGY_NAMES_AR, StrategyConfig
from ..engine.thermal_model import ORIENTATION_AR, ClassroomParams
from ..engine.weather import WEATHER_PROFILES_AR, generate_weather_profile

DISCLAIMER = ("تنبيه: هذا تقرير من نموذج أولي تجريبي مقترح. جميع المباني والقاعات والطقس والنتائج بيانات محاكاة "
              "افتراضية، وليست قياسات أو وفورات فعلية في مباني جامعة نجران، ولا تعني اعتماد الجامعة للمنصة. "
              "الطقس اصطناعي شبيه بظروف نجران الصيفية وليس من محطة رصد.")
ASSUMPTIONS = [
    "نموذج RC أحادي المنطقة: C·dT/dt = UA(T_out − T_in) + Q_solar + Q_internal − Q_cool، تكامل أويلر بخطوة 900 ثانية.",
    "Q_solar = A_w · G_orientation · SHGC · (1 − f_shade)؛ G_orientation تقريب مبسّط من الإشعاع الأفقي.",
    "Q_internal = N · 75 W + 12 W/m² إضاءة + أجهزة (تعمل عند الإشغال فقط).",
    "E = Q_cool / COP · Δt / 3.6×10⁶ kWh؛ COP افتراضي 3.0 بمدى حساسية 2.5–3.5.",
    "نطاق الراحة الافتراضي: الهدف ± 1.5 °م (22.5–25.5 °م افتراضياً) — افتراض للنموذج وليس معياراً رسمياً.",
    "قدرة التبريد القصوى 250 W/m² من مساحة الأرضية؛ السعة الحرارية والـ UA افتراضات هندسية.",
]


@dataclass
class Report:
    title: str
    level: str
    unit_ar: str
    generated: str
    context: list = field(default_factory=list)       # [(مفتاح، قيمة)]
    config: list = field(default_factory=list)
    kpis: list = field(default_factory=list)
    tables: list = field(default_factory=list)        # [(عنوان، DataFrame، {عمود: عنوان}، {عمود: صيغة})]
    recommendations: list = field(default_factory=list)  # [(عنوان، لماذا، أثر)]
    assumptions: list = field(default_factory=lambda: list(ASSUMPTIONS))
    disclaimer: str = DISCLAIMER
    timeseries: pd.DataFrame | None = None


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def room_report(room_id: str, params: ClassroomParams | None = None, scenario: Scenario | str = "prelecture",
                current_key: str | None = None, baseline_key: str = "R") -> Report:
    room = campus.ROOM_BY_ID[room_id]
    p = params or room.params(occupancy=room.capacity)
    sc = SCENARIOS[scenario] if isinstance(scenario, str) else scenario
    w = generate_weather_profile(sc.weather_profile, start=campus.CAMPUS_DAY)
    a = run_analysis(p, sc, w, pd.Timestamp(campus.CAMPUS_DAY).date(), 24, StrategyConfig(), baseline_key=baseline_key)
    cur = current_key or room.mode.strategy
    s = a["summary"]
    b = campus.BUILDING_BY_ID[room.building_id]
    rep = Report(f"تقرير القاعة {room.room_id}", "room", f"{b.name_ar} — {room.floor_ar} — {room.name_ar}", _now())
    rep.context = [("الجامعة", campus.CAMPUS_NAME_AR), ("المبنى", b.name_ar), ("الدور", room.floor_ar),
                   ("القاعة", f"{room.name_ar} ({room.room_id})")]
    rep.config = [("التجربة", sc.name_ar), ("ملف الطقس", WEATHER_PROFILES_AR[sc.weather_profile]),
                  ("التاريخ المحاكى", campus.CAMPUS_DAY), ("المساحة", f"{p.area_m2:.0f} m²"),
                  ("عدد الطلاب أثناء الإشغال", f"{p.occupancy}"),
                  ("النافذة", f"{p.window_area_m2:.1f} m² — {ORIENTATION_AR[p.orientation]}"),
                  ("SHGC / التظليل", f"{p.shgc:.2f} / {p.shading_fraction:.0%}"),
                  ("COP", f"{p.cop:.1f}"), ("نطاق الراحة", f"{p.comfort_low_c:.1f}–{p.comfort_high_c:.1f} °C"),
                  ("كثافة الإنارة (افتراض نموذج أولي)", f"{p.lighting_w_per_m2:g} W/m²"),
                  ("جدول الإنارة التقليدي (افتراض عرض)", f"{hhmm(p.lighting_on_h)}–{hhmm(p.lighting_off_h)}"),
                  ("إنارة ظِلال", "حسب الإشغال"),
                  ("الاستراتيجية الحالية", STRATEGY_NAMES_AR[cur]), ("خط الأساس", STRATEGY_NAMES_AR[baseline_key])]
    m = s.loc[cur]
    rep.kpis = [("الطاقة الكلية (kWh/يوم)", f"{m['energy_kwh']:.2f}"),
                ("منها تكييف / إنارة (kWh)", f"{m['hvac_kwh']:.2f} / {m['lighting_kwh']:.2f}"),
                ("الوقت خارج نطاق الراحة (ساعة)", f"{m['comfort_violation_h']:.2f}"),
                ("الالتزام بالراحة", f"{m['comfort_compliance'] * 100:.0f}%"),
                ("أقصى ابتعاد عن النطاق (°C)", f"{m['max_deviation_c']:.2f}"),
                ("الكسب الشمسي (kWh حراري)", f"{m['solar_gain_kwh']:.1f}"),
                ("أفضل خيار متوازن", STRATEGY_NAMES_AR[a["best"]] if a["best"] else "—")]
    t = s.loc[list(STRATEGY_KEYS)].copy()
    rep.tables.append(("مقارنة الاستراتيجيات (ظروف متطابقة)", t,
                       {"name_ar": "الاستراتيجية", "hvac_kwh": "تكييف kWh", "lighting_kwh": "إنارة kWh",
                        "energy_kwh": "الكلي kWh", "relative_energy_diff_pct": "الفرق %",
                        "comfort_violation_h": "خارج النطاق h", "comfort_compliance": "الالتزام",
                        "assessment": "التقييم"},
                       {"energy_kwh": "{:.2f}", "hvac_kwh": "{:.2f}", "lighting_kwh": "{:.2f}",
                        "relative_energy_diff_pct": "{:+.1f}%", "comfort_violation_h": "{:.2f}",
                        "comfort_compliance": "{:.0%}"}))
    cop = a["cop"].copy()
    cop.insert(0, "name_ar", [STRATEGY_NAMES_AR[k] for k in cop.index])
    rep.tables.append(("حساسية COP — الطاقة الكلية (kWh/يوم؛ COP يغيّر التكييف فقط)", cop, {"name_ar": "الاستراتيجية", **{c: c for c in a["cop"].columns}},
                       {c: "{:.2f}" for c in a["cop"].columns}))
    rep.recommendations = [(x.title_ar, x.why_ar, f"{x.energy_impact_ar} {x.comfort_impact_ar}".strip())
                           for x in rc.generate(a, cur if cur != "N" else "R")]
    ts = []
    for k, df in a["results"].items():
        d = df[["timestamp", "t_out", "t_in", "occupancy", "q_solar_w", "q_internal_w", "q_envelope_w", "q_cool_w",
                "p_hvac_kw", "e_hvac_kwh", "q_light_w", "p_light_kw", "e_light_kwh", "p_total_kw", "e_total_kwh"]].copy()
        d.insert(0, "strategy", k)
        ts.append(d)
    rep.timeseries = pd.concat(ts, ignore_index=True)
    return rep


def unit_report(level: str, unit_id: str | None = None) -> Report:
    """تقارير الدور/المبنى/الجامعة من محاكاة الحرم التجريبي بالأوضاع التشغيلية."""
    if level not in ("room", "floor", "building", "university"):
        raise ValueError("المستوى يجب أن يكون room أو floor أو building أو university.")
    run = campus.simulate_campus()
    m = run["metrics"]
    if level == "room":
        sub = m.loc[[unit_id]]
        r = campus.ROOM_BY_ID[unit_id]
        unit_ar = f"{campus.BUILDING_BY_ID[r.building_id].name_ar} — {r.name_ar}"
    elif level == "floor":
        bid, fl = unit_id.split("-F")
        sub = m[(m["building_id"] == bid) & (m["floor"] == int(fl))]
        unit_ar = f"{campus.BUILDING_BY_ID[bid].name_ar} — {campus.FLOOR_AR.get(int(fl), fl)}"
    elif level == "building":
        sub = m[m["building_id"] == unit_id]
        unit_ar = campus.BUILDING_BY_ID[unit_id].name_ar
    else:
        sub = m
        unit_ar = "الجامعة (الحرم التجريبي)"
    if sub.empty:
        raise ValueError("لا توجد قاعات في الوحدة المطلوبة.")
    agg = aggregate(sub, "university", run["series"]).iloc[0]
    rep = Report(f"تقرير {LEVELS_AR[level]}", level, unit_ar, _now())
    rep.context = [("الجامعة", campus.CAMPUS_NAME_AR), ("الوحدة", unit_ar), ("عدد القاعات", str(len(sub)))]
    rep.config = [("اليوم المحاكى", campus.CAMPUS_DAY), ("ملف الطقس", WEATHER_PROFILES_AR["typical"]),
                  ("التشغيل", "الوضع التشغيلي التجريبي لكل قاعة"),
                  ("التشغيل التقليدي (المرجع)", "تكييف بجدول ثابت 06:00–18:00 عند 24 °C + إنارة 07:00–18:00 (افتراض)، بتظليل القاعة نفسه وبنفس الظروف"),
                  ("حد الراحة المقبولة", "التزام ≥ 95% من ساعات الإشغال"),
                  ("كثافة الإنارة (افتراض نموذج أولي)", "12 W/m²"),
                  ("التجميع", "مجاميع للطاقة؛ ΣE/ΣA للكثافة؛ التزام موزون بساعات-الأشخاص")]
    rep.kpis = [("الطاقة الكلية — تكييف + إنارة (kWh/يوم)", f"{agg['energy_kwh']:.1f}"),
                ("منها تكييف / إنارة (kWh)", f"{agg['hvac_kwh']:.1f} / {agg['lighting_kwh']:.1f}"),
                ("التشغيل التقليدي (kWh/يوم)", f"{agg['reference_energy_kwh']:.1f}"),
                ("الفرق الخام عن التقليدي", f"{agg['saving_vs_reference_pct']:.1f}%"),
                ("التوفير المؤهَّل (راحة ≥ 95%)", f"{agg['qualified_saving_pct']:.1f}% ({agg['qualified_saving_kwh']:.1f} kWh)"),
                ("كثافة الطاقة (kWh/m²)", f"{agg['energy_intensity_kwh_m2']:.3f}"),
                ("الالتزام بالراحة (موزون)", f"{agg['comfort_compliance'] * 100:.1f}%"),
                ("الذروة الكهربائية المتزامنة (kW)", f"{agg['coincident_peak_electric_kw']:.1f}")]
    rows = aggregate(sub, "room")
    rows["strategy_ar"] = [STRATEGY_NAMES_AR[campus.ROOM_BY_ID[i].mode.strategy] for i in rows.index]
    rep.tables.append(("القاعات", rows, {"unit_ar": "القاعة", "strategy_ar": "الوضع", "hvac_kwh": "تكييف kWh",
                                         "lighting_kwh": "إنارة kWh", "energy_kwh": "الكلي kWh",
                                         "reference_energy_kwh": "التقليدي kWh", "energy_intensity_kwh_m2": "kWh/m²",
                                         "comfort_compliance": "الالتزام"},
                       {"energy_kwh": "{:.2f}", "hvac_kwh": "{:.2f}", "lighting_kwh": "{:.2f}",
                        "reference_energy_kwh": "{:.2f}", "energy_intensity_kwh_m2": "{:.3f}",
                        "comfort_compliance": "{:.0%}"}))
    if level in ("building", "university"):
        lv = "floor" if level == "building" else "building"
        a2 = aggregate(sub, lv, run["series"])
        rep.tables.append((f"التجميع حسب {LEVELS_AR[lv]}", a2,
                           {"unit_ar": LEVELS_AR[lv], "energy_kwh": "الكلي kWh", "saving_vs_reference_pct": "التوفير %",
                            "comfort_compliance": "الالتزام", "coincident_peak_electric_kw": "الذروة kW"},
                           {"energy_kwh": "{:.2f}", "saving_vs_reference_pct": "{:.1f}%", "comfort_compliance": "{:.0%}",
                            "coincident_peak_electric_kw": "{:.1f}"}))
    board = challenge.room_leaderboard(m)
    bsub = board[board["room_id"].isin(sub.index)]
    rep.tables.append(("تحدي ظِلال (ترتيب تجريبي على مستوى الحرم)", bsub,
                       {"rank": "الترتيب", "room_id": "القاعة", "eei": "التوفير", "comfort_compliance": "الالتزام",
                        "score": "النقاط"},
                       {"rank": "{:.0f}", "eei": "{:.0%}", "comfort_compliance": "{:.0%}", "score": "{:.1f}"}))
    for _, r in bsub.iterrows():
        b = challenge.best_improvement(r["room_id"], r["score"], r["reference_energy_kwh"], run["weather"])
        if b["gain"] > 1.0:
            rep.recommendations.append((
                f"{r['room_id']}: {STRATEGY_NAMES_AR[b['strategy']]} مع تظليل {b['shading']:.0%}",
                f"أعلى نقاط بين البدائل المحاكاة للقاعة ({r['score']:.1f} → {b['score']:.1f}). الوضع الحالي: "
                f"{campus.ROOM_BY_ID[r['room_id']].mode.note_ar}.",
                f"طاقة {b['energy_kwh']:.1f} kWh/يوم والتزام بالراحة {b['comfort_compliance'] * 100:.0f}% في المحاكاة."))
    ts = []
    for rid in sub.index:
        d = run["series"][rid][["timestamp", "t_out", "t_in", "occupancy", "q_cool_w", "p_hvac_kw", "e_hvac_kwh",
                                 "p_light_kw", "e_light_kwh", "p_total_kw", "e_total_kwh"]].copy()
        d.insert(0, "room_id", rid)
        ts.append(d)
    rep.timeseries = pd.concat(ts, ignore_index=True)
    return rep
