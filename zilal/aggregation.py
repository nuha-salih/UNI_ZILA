"""
aggregation.py — تجميع النتائج على مستويات: قاعة → دور → مبنى → جامعة (جديد).

منهجية التجميع (لا متوسط للمتوسطات):
• الطاقة والطاقة المرجعية والمساحة وساعات المخالفة: مجاميع.
• كثافة الطاقة kWh/m² = ΣE ÷ ΣA (موزونة بالمساحة ضمنياً).
• التوفير ٪ = (ΣE_ref − ΣE) ÷ ΣE_ref (موزون بالطاقة المرجعية ضمنياً).
• الالتزام بالراحة = Σ(الالتزام_i × ساعات-أشخاص_i) ÷ Σ ساعات-أشخاص (موزون بالتعرّض البشري).
• ذروة الحمل الكهربائي المتزامن = max_t Σ_i P_i(t) من السلاسل الزمنية (وليس مجموع الذُّرى).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .campus import BUILDING_BY_ID, FLOOR_AR, ROOM_BY_ID
from .engine.evaluation import saving_percent

LEVELS_AR = {"room": "قاعة", "floor": "دور", "building": "مبنى", "university": "جامعة"}


QUALIFY_COMFORT = 0.95

def _agg(m: pd.DataFrame, series: dict | None) -> dict:
    e, a = float(m["energy_kwh"].sum()), float(m["area_m2"].sum())
    ph = float(m["occupant_hours"].sum())
    out = {
        "rooms": int(len(m)),
        "area_m2": a,
        "energy_kwh": e,   # كلي: تكييف + إنارة
        "hvac_kwh": float(m["hvac_kwh"].sum()) if "hvac_kwh" in m else e,
        "lighting_kwh": float(m["lighting_kwh"].sum()) if "lighting_kwh" in m else 0.0,
        "energy_intensity_kwh_m2": e / a if a > 0 else float("nan"),
        "comfort_violation_h": float(m["comfort_violation_h"].sum()),
        "occupied_room_h": float(m["occupied_h"].sum()),
        "occupant_hours": ph,
        "comfort_compliance": float((m["comfort_compliance"] * m["occupant_hours"]).sum() / ph) if ph > 0 else 1.0,
        "unoccupied_energy_kwh": float(m["unoccupied_energy_kwh"].sum()),
        "sum_of_peaks_electric_kw": float(m["peak_electric_kw"].sum()),
    }
    if "reference_energy_kwh" in m:
        ref = float(m["reference_energy_kwh"].sum())
        out["reference_energy_kwh"] = ref
        out["saving_vs_reference_pct"] = saving_percent(ref, e)   # الفرق الخام
        if "reference_hvac_kwh" in m:
            out["reference_hvac_kwh"] = float(m["reference_hvac_kwh"].sum())
            out["reference_lighting_kwh"] = float(m["reference_lighting_kwh"].sum())
        # التوفير المؤهَّل: فرق القاعات التي التزمت بالراحة ≥ 95٪ فقط، كنسبة من استهلاك الوحدة التقليدي
        ok = m["comfort_compliance"] >= QUALIFY_COMFORT - 1e-9
        q = float((m.loc[ok, "reference_energy_kwh"] - m.loc[ok, "energy_kwh"]).sum())
        out["qualified_saving_kwh"] = q
        out["qualified_saving_pct"] = q / ref * 100.0 if ref > 1e-9 else 0.0
        out["qualified_rooms"] = int(ok.sum())
    if series:
        col = "p_total_kw" if all("p_total_kw" in series[r] for r in m.index) else "p_hvac_kw"
        p = np.sum([series[r][col].to_numpy() for r in m.index], axis=0)   # ذروة متزامنة كلية (تكييف + إنارة)
        out["coincident_peak_electric_kw"] = float(p.max())
    return out


def aggregate(metrics: pd.DataFrame, level: str, series: dict | None = None) -> pd.DataFrame:
    """يعيد جدولاً بصف لكل وحدة في المستوى المطلوب."""
    m = metrics.copy()
    if level == "room":
        groups = [((rid,), m.loc[[rid]]) for rid in m.index]
    elif level == "floor":
        groups = list(m.groupby(["building_id", "floor"]))
    elif level == "building":
        groups = list(m.groupby(["building_id"]))
    elif level == "university":
        groups = [(("ALL",), m)]
    else:
        raise ValueError("مستوى تجميع غير معروف.")
    rows = []
    for key, g in groups:
        key = key if isinstance(key, tuple) else (key,)
        row = _agg(g, series)
        if level == "room":
            r = ROOM_BY_ID[key[0]]
            row.update(unit_id=r.room_id, unit_ar=f"{BUILDING_BY_ID[r.building_id].name_ar} — {r.name_ar}")
        elif level == "floor":
            row.update(unit_id=f"{key[0]}-F{key[1]}",
                       unit_ar=f"{BUILDING_BY_ID[key[0]].name_ar} — {FLOOR_AR.get(int(key[1]), key[1])}")
        elif level == "building":
            row.update(unit_id=key[0], unit_ar=BUILDING_BY_ID[key[0]].name_ar)
        else:
            row.update(unit_id="ALL", unit_ar="الجامعة (الحرم التجريبي)")
        rows.append(row)
    return pd.DataFrame(rows).set_index("unit_id")


def naive_average_compliance(metrics: pd.DataFrame, by: str = "building_id") -> pd.Series:
    """للمقارنة في الاختبارات/التوثيق فقط: متوسط بسيط للمتوسطات (طريقة غير صحيحة)."""
    return metrics.groupby(by)["comfort_compliance"].mean().groupby(lambda _: "ALL").mean()
