"""
sensitivity.py — تحليل الحساسية «متغير واحد في كل مرة» (جديد).

لكل متغير تُعاد المحاكاة كاملة بقيم مختلفة مع تثبيت كل شيء آخر (الطقس، الإشغال، القاعة،
الاستراتيجية، COP). الاستثناء: COP يُطبَّق على نفس الحمل التبريدي لأنه لا يغيّر الحمل الحراري
في هذا النموذج (E = Q·dt/COP)، وهذا مطابق رياضياً لإعادة المحاكاة.

مخرجات الجدول: مدخل افتراضي (variable, value) → نتائج محاكاة (energy_kwh, ...).
"""
from __future__ import annotations

import pandas as pd

from .evaluation import compute_metrics, cop_sensitivity, saving_percent
from .strategies import OPERATIONAL_KEYS, STRATEGY_SHORT_AR, StrategyConfig, make_strategy
from .thermal_model import ORIENTATION_AR, ORIENTATIONS, ClassroomParams, build_sim_inputs, simulate

VARIABLE_AR = {
    "cop": "معامل الأداء COP",
    "shading": "فعالية التظليل",
    "orientation": "اتجاه النافذة",
    "occupancy": "عدد الطلاب",
    "solar_scale": "شدة الإشعاع الشمسي (× الملف)",
    "strategy": "استراتيجية التكييف",
}


def _run(params, weather_slice, occ_blocks, tt_blocks, key, cfg):
    inp = build_sim_inputs(params, weather_slice, occ_blocks, tt_blocks)
    df = simulate(inp, make_strategy(key, cfg))
    return df, compute_metrics(df, params, inp)


def one_at_a_time(params: ClassroomParams, weather_slice: pd.DataFrame, occ_blocks, tt_blocks,
                  strategy_key: str = "C", cfg: StrategyConfig | None = None,
                  cops=(2.5, 3.0, 3.5), shadings=(0.0, 0.25, 0.5, 0.75, 1.0),
                  occupancy_fracs=(0.0, 1 / 3, 2 / 3, 1.0), solar_scales=(0.6, 0.8, 1.0, 1.2)) -> pd.DataFrame:
    rows = []
    base_df, base_m = _run(params, weather_slice, occ_blocks, tt_blocks, strategy_key, cfg)

    def add(var, value, label, m, energy=None, hvac=None):
        rows.append({"variable": var, "variable_ar": VARIABLE_AR[var], "value": value, "label": label,
                     "energy_kwh": float(m["energy_kwh"] if energy is None else energy),   # كلي
                     "hvac_kwh": float(m["hvac_kwh"] if hvac is None else hvac),
                     "lighting_kwh": float(m["lighting_kwh"]),
                     "comfort_violation_h": float(m["comfort_violation_h"]),
                     "solar_gain_kwh": float(m["solar_gain_kwh"]),
                     "peak_cooling_kw": float(m["peak_cooling_kw"])})

    for _, r in cop_sensitivity(base_df, params.dt_s, cops).iterrows():
        add("cop", float(r["cop"]), f"{r['cop']:g}", base_m, r["energy_kwh"], r["hvac_kwh"])
    for s in shadings:
        _, m = _run(params.with_(shading_fraction=float(s)), weather_slice, occ_blocks, tt_blocks, strategy_key, cfg)
        add("shading", float(s), f"{s:.0%}", m)
    for o in ORIENTATIONS:
        _, m = _run(params.with_(orientation=o), weather_slice, occ_blocks, tt_blocks, strategy_key, cfg)
        add("orientation", o, ORIENTATION_AR[o], m)
    for f in occupancy_fracs:
        n = int(round(f * params.max_occupancy))
        _, m = _run(params.with_(occupancy=n), weather_slice, occ_blocks, tt_blocks, strategy_key, cfg)
        add("occupancy", n, str(n), m)
    for sc in solar_scales:
        w = weather_slice.copy()
        w["solar_irradiance_wm2"] = w["solar_irradiance_wm2"] * sc
        _, m = _run(params, w, occ_blocks, tt_blocks, strategy_key, cfg)
        add("solar_scale", float(sc), f"×{sc:g}", m)
    for k in OPERATIONAL_KEYS:
        _, m = _run(params, weather_slice, occ_blocks, tt_blocks, k, cfg)
        add("strategy", k, STRATEGY_SHORT_AR[k], m)
    out = pd.DataFrame(rows)
    out["energy_change_pct"] = [-saving_percent(base_m["energy_kwh"], e) for e in out["energy_kwh"]]
    out.attrs["base_energy_kwh"] = base_m["energy_kwh"]
    return out


def tornado(table: pd.DataFrame) -> pd.DataFrame:
    """مدى تغيّر الطاقة (kWh) لكل متغير — للترتيب حسب الأثر."""
    g = table.groupby("variable_ar")["energy_kwh"].agg(["min", "max"])
    g["range_kwh"] = g["max"] - g["min"]
    return g.sort_values("range_kwh", ascending=False).reset_index()


def cop_energy_band(energy_kwh: float, cop: float, cops=(2.5, 3.5)) -> tuple[float, float]:
    """نطاق الطاقة عند COP ∈ [2.5, 3.5] لطاقة محسوبة عند `cop` (E ∝ 1/COP)."""
    q = energy_kwh * cop
    return float(q / max(cops)), float(q / min(cops))


__all__ = ["one_at_a_time", "tornado", "cop_energy_band", "VARIABLE_AR"]
