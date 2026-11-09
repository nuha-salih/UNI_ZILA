"""
challenge.py — تحدي ظِلال للاستدامة (مسابقة تجريبية مقترحة؛ بيانات محاكاة فقط).

منهجية النقاط (شفافة وقابلة للتتبع، 0–100):

1) مؤشر كفاءة الطاقة المُطبَّع:  EEI = (E_ref − E) / E_ref
   E_ref = طاقة «التشغيل التقليدي للقاعة نفسها» (جدول ثابت 06:00–18:00 عند 24 °م + إنارة بجدول، بتظليلها نفسه)
   محسوبة بالمحرك تحت *نفس* الطقس والإشغال والخصائص و COP. هذا يُحيّد فروق المساحة والإشغال
   والاتجاه والطقس بين المشاركين: كل مشارك يُقارن بنفسه، لا بالآخرين بالطاقة الخام.
   نقاط الطاقة  S_E = 100 · clip(EEI / 0.5, 0, 1)   (توفير 50٪ عن المرجع = العلامة الكاملة؛ افتراض).

2) الالتزام بالراحة:  c = ساعات الإشغال داخل نطاق الراحة ÷ ساعات الإشغال.
   نقاط الراحة  S_C = 100 · c.

3) بوابة الراحة:  g = 1 إذا c ≥ 0.95، وإلا 0
   تُضرب بها نقاط الطاقة: لا تُحتسب أي نقاط طاقة إذا قلّ الالتزام بالراحة عن 95٪ (الحد الموحّد في المنصة).
   بذلك لا يُكافأ إطفاء التكييف أو رفع الهدف على حساب الراحة.

النتيجة:  Score = 0.5 · g · S_E + 0.5 · S_C

مثال: قاعة وفّرت 40٪ بالتزام 100٪ → 0.5·1·80 + 0.5·100 = 90. قاعة وفّرت 50٪ بالتزام 0٪ → 0.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .campus import BUILDING_BY_ID, ROOM_BY_ID, simulate_room
from .engine.evaluation import saving_percent
from .engine.strategies import OPERATIONAL_KEYS, STRATEGY_SHORT_AR

EEI_FULL_MARKS = 0.5
GATE_LOW = GATE_HIGH = 0.95
W_ENERGY, W_COMFORT = 0.5, 0.5
DEMO_LABEL_AR = "بيانات محاكاة لأغراض العرض — ليست ترتيباً فعلياً لمباني الجامعة"


def score_components(energy_kwh: float, reference_kwh: float, compliance: float) -> dict:
    eei = saving_percent(reference_kwh, energy_kwh) / 100.0
    s_e = 100.0 * float(np.clip(eei / EEI_FULL_MARKS, 0.0, 1.0))
    c = float(np.clip(compliance, 0.0, 1.0))
    s_c = 100.0 * c
    g = 1.0 if c >= GATE_HIGH - 1e-9 else 0.0
    score = W_ENERGY * g * s_e + W_COMFORT * s_c
    return {"eei": eei, "energy_points": s_e, "comfort_points": s_c, "comfort_gate": g,
            "energy_points_counted": W_ENERGY * g * s_e, "comfort_points_counted": W_COMFORT * s_c,
            "score": score}


def _verdict(row) -> str:
    if row["comfort_gate"] < 1e-9 and row["eei"] > 0.05:
        return "توفير على حساب الراحة — نقاط الطاقة لم تُحتسب"
    if row["eei"] < 0.05:
        return "راحة جيدة مع فرصة كبيرة لخفض الطاقة"
    return "أداء متوازن: توفير مع راحة"


def room_leaderboard(campus_metrics: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for rid, m in campus_metrics.iterrows():
        r = ROOM_BY_ID[rid]
        sc = score_components(m["energy_kwh"], m["reference_energy_kwh"], m["comfort_compliance"])
        rows.append({"room_id": rid, "participant_ar": f"{BUILDING_BY_ID[r.building_id].name_ar} — {r.name_ar}",
                     "building_id": r.building_id, "mode_ar": r.mode.note_ar,
                     "energy_kwh": m["energy_kwh"], "reference_energy_kwh": m["reference_energy_kwh"],
                     "comfort_compliance": m["comfort_compliance"],
                     "comfort_violation_h": m["comfort_violation_h"], **sc})
    d = pd.DataFrame(rows)
    d["verdict_ar"] = d.apply(_verdict, axis=1)
    d = d.sort_values(["score", "comfort_compliance"], ascending=False).reset_index(drop=True)
    d["rank"] = np.arange(1, len(d) + 1)
    return d


def building_leaderboard(campus_metrics: pd.DataFrame) -> pd.DataFrame:
    """المباني: طاقة ومرجع مجمّعان، والتزام موزون بساعات-الأشخاص (aggregation.py)."""
    from .aggregation import aggregate
    agg = aggregate(campus_metrics, "building")
    rows = []
    for bid, a in agg.iterrows():
        sc = score_components(a["energy_kwh"], a["reference_energy_kwh"], a["comfort_compliance"])
        rows.append({"building_id": bid, "participant_ar": BUILDING_BY_ID[bid].name_ar,
                     "energy_kwh": a["energy_kwh"], "reference_energy_kwh": a["reference_energy_kwh"],
                     "comfort_compliance": a["comfort_compliance"], "rooms": a["rooms"], **sc})
    d = pd.DataFrame(rows)
    d["verdict_ar"] = d.apply(_verdict, axis=1)
    d = d.sort_values("score", ascending=False).reset_index(drop=True)
    d["rank"] = np.arange(1, len(d) + 1)
    return d


def improvement_options(room_id: str, reference_kwh: float, weather_day=None,
                        shadings=(0.0, 0.5, 0.75)) -> pd.DataFrame:
    """كل التوليفات التشغيلية المعقولة (استراتيجية × تظليل، عند هدف الراحة) مع نقاطها المحسوبة."""
    room = ROOM_BY_ID[room_id]
    rows = []
    for k in OPERATIONAL_KEYS:
        for s in sorted(set(shadings) | {room.mode.shading}):
            _, m = simulate_room(room, strategy=k, shading=s, target_c=None, weather_day=weather_day)
            sc = score_components(m["energy_kwh"], reference_kwh, m["comfort_compliance"])
            rows.append({"strategy": k, "strategy_ar": STRATEGY_SHORT_AR[k], "shading": s,
                         "energy_kwh": m["energy_kwh"], "comfort_compliance": m["comfort_compliance"], **sc})
    return pd.DataFrame(rows).sort_values("score", ascending=False).reset_index(drop=True)


def best_improvement(room_id: str, current_score: float, reference_kwh: float, weather_day=None) -> dict:
    opts = improvement_options(room_id, reference_kwh, weather_day)
    top = opts.iloc[0]
    return {"strategy": top["strategy"], "strategy_ar": top["strategy_ar"], "shading": float(top["shading"]),
            "score": float(top["score"]), "gain": float(top["score"] - current_score),
            "energy_kwh": float(top["energy_kwh"]), "comfort_compliance": float(top["comfort_compliance"]),
            "options": opts}


def all_improvements(board: pd.DataFrame, weather_day=None) -> pd.DataFrame:
    rows = []
    for _, r in board.iterrows():
        b = best_improvement(r["room_id"], r["score"], r["reference_energy_kwh"], weather_day)
        rows.append({"room_id": r["room_id"], **{k: v for k, v in b.items() if k != "options"}})
    return pd.DataFrame(rows).set_index("room_id")


