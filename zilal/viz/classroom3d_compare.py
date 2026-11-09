"""
classroom3d_compare.py — جسر النسخة الثانية من القاعة الافتراضية: «التقليدي» مقابل «ظِلال».

كل الأرقام المعروضة محسوبة هنا في Python لكل خطوة 15 دقيقة، والعرض (classroom3d_v2.js) يقرأها بالفهرس فقط:
• الحالتان تأتيان من compare_strategies على كائن SimInputs واحد ⇒ طقس وقاعة وإشغال واتجاه وتظليل
  وحرارة ابتدائية ومدة و COP متطابقة؛ يختلف منطق التحكم فقط (ونتحقق من ذلك هنا).
• القدرة اللحظية (kW) منفصلة عن الطاقة المتراكمة (kWh)، ولكل منهما ثلاثة أجزاء: تكييف، إنارة، كلي:
  P_hvac = Q_cool/COP ، P_light = LPD·A·on_light ، P_total = P_hvac + P_light
  E_upto[k] = Σ_{j<k} P_j·Δt / 3.6e6  — تكامل القدرة الكهربائية عبر خطوات Δt = 900 s.
  عند الوقت t_k (مثلاً 12:00) تشمل الطاقة الفترة [00:00, t_k) بالضبط؛ ونهاية اليوم (24:00) = المجموع اليومي.
• التوفير = E_cum,التقليدي − E_cum,ظِلال (قد يكون سالباً ويُعرض كما هو)، والنسبة ÷ E_cum,التقليدي.
• الالتزام بالراحة حتى الآن = خطوات الإشغال داخل النطاق ÷ خطوات الإشغال حتى الخطوة k (None قبل أي إشغال).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..engine.strategies import STRATEGY_NAMES_AR
from ..engine.thermal_model import ORIENTATION_AR, ClassroomParams
from .classroom3d import LABELS_AR, _clean, _safe_json, HERE

SHARED_COLS = ("t_out", "q_solar_w", "g_facade", "occupancy", "hour")
COMFORT_NONE, COMFORT_OK, COMFORT_HOT, COMFORT_COLD = 0, 1, 2, 3

LABELS_V2 = dict(LABELS_AR)
LABELS_V2.update({
    "conv": "النظام التقليدي", "zilal": "نظام ظِلال", "view": "المعروض في القاعة",
    "stepBack": "رجوع 15 دقيقة", "stepFwd": "تقدّم 15 دقيقة", "hourBack": "رجوع ساعة", "hourFwd": "تقدّم ساعة",
    "speed": "سرعة العرض", "speedNote": "1× = ساعة محاكاة كل ثانيتين · السرعة تغيّر العرض فقط",
    "startFrom": "ابدأ من", "energyCum": "الطاقة الكلية منذ 00:00", "energyDay": "الطاقة الكلية اليوم",
    "deckTitle": "المقارنة الحية حتى", "indicator": "المؤشر", "diff": "الفرق (ظِلال − التقليدي)",
    "rowCool": "قدرة التبريد الآن (kW حراري)",
    "rowPower": "قدرة التكييف الكهربائية الآن (kW)", "rowLight": "قدرة الإنارة الآن (kW)",
    "rowTotal": "القدرة الكهربائية الكلية الآن (kW)",
    "rowEnergyH": "طاقة التكييف منذ 00:00 (kWh)", "rowEnergyL": "طاقة الإنارة منذ 00:00 (kWh)",
    "rowEnergy": "الطاقة الكلية منذ 00:00 (kWh)", "rowTemp": "الحرارة الداخلية (°م)",
    "rowStatus": "حالة الراحة الآن", "rowComp": "الالتزام بالراحة حتى الآن",
    "saved": "الطاقة الكلية الموفّرة حتى الآن", "savedSplit": "منها: تكييف · إنارة (kWh)",
    "partH": "تكييف", "partL": "إنارة", "partT": "الكلي", "lightsOn": "تعمل", "lightsOff": "مطفأة",
    "lightRow": "الإنارة", "savedPct": "نسبة التوفير", "dCool": "فرق قدرة التبريد الآن (ظِلال − التقليدي)",
    "dComp": "فرق الالتزام بالراحة (ظِلال − التقليدي)", "noOcc": "لا إشغال بعد", "na": "—",
    "vGood": "ظِلال يوفّر مع الحفاظ على الراحة", "vCost": "توفير على حساب الراحة — لا يُعدّ نجاحاً",
    "vMore": "ظِلال يستهلك أكثر حتى هذه اللحظة", "vEqual": "لا فرق في الطاقة حتى الآن",
    "final": "النتيجة اليومية النهائية", "endOfDay": "نهاية اليوم المحاكى",
    "hot": "حارة", "cold": "باردة", "ok": "مريحة", "empty": "فارغة",
    "chartTitle": "الطاقة المتراكمة (kWh)", "comfortPts": "نقطة",
    "powerTitle": "القدرة الكهربائية لحظة بلحظة — تكييف وإنارة", "lectureBand": "محاضرة",
    "evPrecool": "ظِلال يبدأ التبريد المسبق", "evArrive": "وصول الطلاب", "evLeave": "مغادرة الطلاب", "evOff": "إطفاء تلقائي",
})


def _comfort_codes(t_in: np.ndarray, occ: np.ndarray, lo: float, hi: float) -> np.ndarray:
    codes = np.full(len(t_in), COMFORT_NONE, dtype=int)
    o = occ > 0
    codes[o & (t_in >= lo - 1e-9) & (t_in <= hi + 1e-9)] = COMFORT_OK
    codes[o & (t_in > hi + 1e-9)] = COMFORT_HOT
    codes[o & (t_in < lo - 1e-9)] = COMFORT_COLD
    return codes


def _case(df: pd.DataFrame, params: ClassroomParams, key: str, metrics: dict) -> dict:
    t = df["t_in"].to_numpy(dtype=float)
    occ = df["occupancy"].to_numpy()
    codes = _comfort_codes(t, occ, params.comfort_low_c, params.comfort_high_c)
    occ_steps = np.cumsum(occ > 0)
    ok_steps = np.cumsum(codes == COMFORT_OK)
    comp = [None if n == 0 else round(float(k / n), 4) for k, n in zip(ok_steps, occ_steps)]
    e_h = df["e_hvac_kwh"].to_numpy(dtype=float)
    e_l = df["e_light_kwh"].to_numpy(dtype=float)
    e_step = e_h + e_l

    def upto(e):  # تراكم حصري: الطاقة حتى بداية الخطوة k
        return _clean(np.concatenate([[0.0], np.cumsum(e)[:-1]]))
    return {
        "key": key, "label": STRATEGY_NAMES_AR[key],
        "t_in": _clean(t),
        "q_cool_kw": _clean(df["q_cool_w"].to_numpy(dtype=float) / 1000.0),
        "p_el_kw": _clean(df["p_hvac_kw"]),          # تكييف (كهربائي)
        "p_light_kw": _clean(df["p_light_kw"]),
        "p_total_kw": _clean(df["p_total_kw"]),
        "light_on": [bool(x) for x in (df["q_light_w"].to_numpy() > 0)],
        "lighting_mode": df.attrs.get("lighting_mode", "occupancy"),
        "e_step": _clean(e_step),
        "e_upto": upto(e_step),                      # كلي
        "e_upto_hvac": upto(e_h),
        "e_upto_light": upto(e_l),
        "e_day": round(float(e_step.sum()), 6),
        "e_day_hvac": round(float(e_h.sum()), 6),
        "e_day_light": round(float(e_l.sum()), 6),
        "comfort": [int(c) for c in codes],
        "events": _events(df),
        "comp_cum": comp,
        "final": {"energy_kwh": float(metrics["energy_kwh"]), "hvac_kwh": float(metrics["hvac_kwh"]),
                  "lighting_kwh": float(metrics["lighting_kwh"]), "compliance": float(metrics["comfort_compliance"]),
                  "violation_h": float(metrics["comfort_violation_h"]), "comfort_ok": bool(metrics["comfort_ok"]),
                  "applicable": bool(metrics["comfort_applicable"])},
    }


def _events(df: pd.DataFrame) -> list:
    """لحظات القرار للعرض على الرسم (من نتائج المحرك، لا منطق تحكم هنا):
    arrive/leave = بداية ونهاية كل فترة إشغال؛ precool = بداية تبريد متصل والقاعة فارغة ينتهي عند وصول الطلاب؛
    off = أول خطوة بلا تبريد بعد مغادرة الطلاب."""
    occ = df["occupancy"].to_numpy() > 0
    on = df["q_cool_w"].to_numpy() > 1.0
    n, ev = len(df), []
    k = 0
    while k < n:
        if occ[k] and (k == 0 or not occ[k - 1]):
            a = k
            j = a - 1
            while j >= 0 and on[j] and not occ[j]:
                j -= 1
            if j + 1 < a:
                ev.append({"k": j + 1, "kind": "precool"})
            ev.append({"k": a, "kind": "arrive"})
            b = a
            while b + 1 < n and occ[b + 1]:
                b += 1
            if b + 1 < n:
                ev.append({"k": b + 1, "kind": "leave"})
                if not on[b + 1]:
                    ev.append({"k": b + 1, "kind": "off"})
            k = b + 1
        else:
            k += 1
    return ev


def build_compare_state(analysis: dict, conv_key: str = "R", zilal_key: str = "D", start_index: int = 32) -> dict:
    """حالة العرض للمقارنة من مخرجات run_analysis (نفس SimInputs للحالتين)."""
    res, summ, p = analysis["results"], analysis["summary"], analysis["params"]
    if conv_key not in res or zilal_key not in res:
        raise ValueError("الاستراتيجيتان المطلوبتان غير موجودتين في نتائج المقارنة.")
    if conv_key == zilal_key:
        raise ValueError("يجب أن تختلف استراتيجية ظِلال عن النظام التقليدي.")
    dc, dz = res[conv_key], res[zilal_key]
    for col in SHARED_COLS:  # ضمان تطابق الظروف: لا يختلف إلا منطق التحكم
        if not np.array_equal(dc[col].to_numpy(), dz[col].to_numpy()):
            raise ValueError(f"الحالتان لا تشتركان في المدخلات نفسها ({col}).")
    if dc["t_in"].iloc[0] != dz["t_in"].iloc[0]:
        raise ValueError("الحرارة الابتدائية مختلفة بين الحالتين.")
    conv = _case(dc, p, conv_key, summ.loc[conv_key].to_dict())
    zil = _case(dz, p, zilal_key, summ.loc[zilal_key].to_dict())
    ec, ez = np.asarray(conv["e_upto"]), np.asarray(zil["e_upto"])
    saved = ec - ez
    saved_h = np.asarray(conv["e_upto_hvac"]) - np.asarray(zil["e_upto_hvac"])
    saved_l = np.asarray(conv["e_upto_light"]) - np.asarray(zil["e_upto_light"])
    pct = [None if c <= 1e-9 else round(float(s / c * 100.0), 3) for s, c in zip(saved, ec)]
    dcomp = [None if (a is None or b is None) else round((b - a) * 100.0, 2)
             for a, b in zip(conv["comp_cum"], zil["comp_cum"])]
    n = len(dc)
    fc, fz = conv["final"], zil["final"]
    return {
        "version": 2, "n": n, "dt_s": p.dt_s,
        "hour": _clean(dc["hour"]), "t_out": _clean(dc["t_out"]), "q_solar": _clean(dc["q_solar_w"]),
        "g_facade": _clean(dc["g_facade"]),
        "occ": [int(x) for x in np.minimum(dc["occupancy"].to_numpy(dtype=int), p.max_occupancy)],
        "q_max": float(p.hvac_capacity_w), "band": [float(p.comfort_low_c), float(p.comfort_high_c)],
        "capacity": int(p.max_occupancy), "students": int(p.effective_occupancy),
        "shading": float(p.shading_fraction), "orientation": p.orientation,
        "orientation_label": ORIENTATION_AR[p.orientation], "cop": float(p.cop),
        "lighting": {"lpd_w_m2": float(p.lighting_w_per_m2), "area_m2": float(p.area_m2),
                     "full_kw": round(p.lighting_w_per_m2 * p.area_m2 / 1000.0, 4),
                     "on_h": float(p.lighting_on_h), "off_h": float(p.lighting_off_h)},
        "start_index": int(max(0, min(n - 1, start_index))),
        "cases": {"conv": conv, "zilal": zil},
        "compare": {
            "saved_kwh": _clean(saved), "saved_pct": pct,
            "saved_hvac_kwh": _clean(saved_h), "saved_light_kwh": _clean(saved_l),
            "d_total_kw": _clean(np.asarray(zil["p_total_kw"]) - np.asarray(conv["p_total_kw"])),
            "d_cool_kw": _clean(np.asarray(conv["q_cool_kw"]) - np.asarray(zil["q_cool_kw"])),
            "d_comp_pp": dcomp,
            "final": {"saved_kwh": round(fc["energy_kwh"] - fz["energy_kwh"], 4),
                      "saved_hvac_kwh": round(fc["hvac_kwh"] - fz["hvac_kwh"], 4),
                      "saved_light_kwh": round(fc["lighting_kwh"] - fz["lighting_kwh"], 4),
                      "d_comp_pp": (round((fz["compliance"] - fc["compliance"]) * 100.0, 2)
                                    if (fc["applicable"] and fz["applicable"]) else None),
                      "saved_pct": None if fc["energy_kwh"] <= 1e-9 else
                      round((fc["energy_kwh"] - fz["energy_kwh"]) / fc["energy_kwh"] * 100.0, 3)},
        },
        # توافق مع لوحة الحالة في النسخة الأولى (الحالة المعروضة افتراضياً = ظِلال)
        "kpi": {"energy_kwh": fz["energy_kwh"], "compliance": fz["compliance"], "violation_h": fz["violation_h"]},
        "labels": LABELS_V2,
    }


def render_html_v2(state: dict, viewport_px: int = 560) -> str:
    """صفحة ذاتية الاحتواء للنسخة الثانية (CSS + JS مضمّنان، دون موارد خارجية)."""
    css = (HERE / "classroom3d_v2.css").read_text(encoding="utf-8")
    js = (HERE / "classroom3d_v2.js").read_text(encoding="utf-8")
    return (
        "<!doctype html><html lang=\"ar\"><head><meta charset=\"utf-8\">"
        f"<style>{css} #zl3d .zl-vp{{height:{int(viewport_px)}px}}</style></head><body>"
        "<div id=\"zl3d\"></div>"
        f"<script>window.ZILAL_STATE={_safe_json(state)};</script>"
        f"<script>{js}</script></body></html>"
    )
