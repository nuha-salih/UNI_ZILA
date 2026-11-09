"""
evaluation.py — مقاييس الطاقة والراحة، المقارنة العادلة بين الاستراتيجيات، وتحليلات التجارب.

تعريفات (كلها نتائج محاكاة وليست قياسات):
• energy_kwh: الطاقة الكهربائية الكلية = hvac_kwh + lighting_kwh (منذ الإصدار 2.3).
  hvac_kwh = Σ (Q_cool/COP)·dt/3.6e6 ؛ lighting_kwh = Σ P_light·dt/3.6e6 (على خطوات 15 دقيقة).
  التوفير وأفضل استراتيجية والتحدي والتوصيات كلها على الطاقة الكلية؛ حساسية COP تمس جزء التكييف فقط.
• نطاق الراحة الافتراضي: [الهدف − السماحية، الهدف + السماحية] = 22.5–25.5 °م افتراضياً.
  افتراض للنموذج الأولي، وليس معياراً رسمياً للجامعة.
• comfort_violation_h: ساعات الإشغال التي كانت فيها T_in خارج النطاق (يُقيَّم أثناء الإشغال فقط).
• comfort_compliance: ساعات الإشغال داخل النطاق ÷ ساعات الإشغال (1 إن لم يوجد إشغال؛ غير منطبق).
• max_deviation_c: أكبر بُعد (°م) عن حدود النطاق أثناء الإشغال. degree_hours: Σ البُعد × dt.
• longest_uncomfortable_h: أطول فترة متصلة خارج النطاق أثناء الإشغال.
• unoccupied_energy_kwh / unnecessary_energy_kwh: الطاقة الكلية والقاعة فارغة، والجزء غير الضروري منها:
  تكييف خارج نافذة التهيئة المسبقة (precond_window_h قبل أقرب إشغال لاحق، افتراضياً 4 ساعات)
  + كل إنارة القاعة الفارغة (لا تهيئة مسبقة للإنارة).
• saving_pct = (E_base − E)/E_base × 100 ؛ relative_energy_diff_pct = −saving_pct.
• comfort_ok: نسبة المخالفة ≤ 5٪ — التوفير بلا راحة مقبولة لا يُعدّ توفيراً صالحاً.

سجل التعديل: compute_metrics و saving_percent و cop_sensitivity و orientation_shading_sweep
مُعاد استخدامها مع إضافة مقاييس الراحة الموسعة. أُضيف اختيار خط الأساس، وتحليل الإفراط في
التبريد، وتفكيك الكسب الحراري، وفترة العرض 5 دقائق. نُقلت التوصيات إلى recommendations.py
واستُبدل تحدي الكليات (بيانات ثابتة) بوحدة challenge.py محسوبة.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .scenarios import SCENARIOS, Scenario
from .strategies import (BASELINE_KEY, OPERATIONAL_KEYS, STRATEGY_KEYS, STRATEGY_NAMES_AR,
                         StrategyConfig, make_strategy)
from .thermal_model import (ORIENTATIONS, ClassroomParams, SimInputs, build_sim_inputs,
                            hvac_energy_kwh, simulate)
from .weather import generate_weather_profile, slice_weather

COMFORT_OK_FRACTION = 0.05
EPS = 1e-9
J_TO_KWH = 1.0 / 3.6e6


def saving_percent(e_baseline: float, e_strategy: float) -> float:
    """((E_base − E_strat)/E_base)×100 مع معالجة آمنة للأساس الصفري."""
    if e_baseline is None or not np.isfinite(e_baseline) or e_baseline <= EPS:
        return 0.0
    return float((e_baseline - e_strategy) / e_baseline * 100.0)


def _longest_run(mask: np.ndarray) -> int:
    best = cur = 0
    for v in mask:
        cur = cur + 1 if v else 0
        best = max(best, cur)
    return best


def comfort_metrics(t_in: np.ndarray, occupied: np.ndarray, params: ClassroomParams) -> dict:
    """مقاييس الراحة أثناء الإشغال فقط (انظر التعريفات أعلى الملف)."""
    dt_h = params.dt_s / 3600.0
    t = np.asarray(t_in, dtype=float)
    occ = np.asarray(occupied, dtype=bool)
    lo, hi = params.comfort_low_c, params.comfort_high_c
    hot = occ & (t > hi + EPS)
    cold = occ & (t < lo - EPS)
    viol = hot | cold
    dev = np.where(occ, np.maximum(np.maximum(t - hi, lo - t), 0.0), 0.0)
    occ_h = float(occ.sum() * dt_h)
    viol_h = float(viol.sum() * dt_h)
    return {
        "occupied_h": occ_h,
        "comfort_applicable": bool(occ_h > 0),
        "comfort_violation_h": viol_h,
        "hot_violation_h": float(hot.sum() * dt_h),
        "cold_violation_h": float(cold.sum() * dt_h),
        "time_in_band_h": occ_h - viol_h,
        "violation_fraction": viol_h / occ_h if occ_h > 0 else 0.0,
        "comfort_compliance": (occ_h - viol_h) / occ_h if occ_h > 0 else 1.0,
        "comfort_ok": bool(viol_h / occ_h <= COMFORT_OK_FRACTION) if occ_h > 0 else True,
        "max_deviation_c": float(dev.max()) if occ.any() else 0.0,
        "degree_hours": float(dev.sum() * dt_h),
        "longest_uncomfortable_h": float(_longest_run(viol) * dt_h),
        "mean_t_occupied_c": float(t[occ].mean()) if occ.any() else float("nan"),
        "max_t_occupied_c": float(t[occ].max()) if occ.any() else float("nan"),
        "min_t_occupied_c": float(t[occ].min()) if occ.any() else float("nan"),
    }


def compute_metrics(df: pd.DataFrame, params: ClassroomParams, inp: SimInputs,
                    precond_window_h: float = 4.0) -> dict:
    occ = (df["occupancy"].to_numpy() > 0)
    t = df["t_in"].to_numpy()
    e_h = df["e_hvac_kwh"].to_numpy()
    e_l = df["e_light_kwh"].to_numpy() if "e_light_kwh" in df else np.zeros(len(df))
    e = e_h + e_l
    q = df["q_cool_w"].to_numpy()
    p_tot = q / params.cop / 1000.0 + (df["p_light_kw"].to_numpy() if "p_light_kw" in df else 0.0)
    w = int(precond_window_h * 3600 / params.dt_s)
    nxt = inp.next_occ
    near_future = np.array([(nxt[k] != -1 and nxt[k] - k <= w) for k in range(len(df))], dtype=bool)
    unocc = ~occ
    on = q > 1.0
    out = {
        "energy_kwh": float(e.sum()),          # كلي (تكييف + إنارة)
        "hvac_kwh": float(e_h.sum()),
        "lighting_kwh": float(e_l.sum()),
        "lighting_on_h": float((e_l > 0).sum() * params.dt_s / 3600.0),
        "unoccupied_lighting_kwh": float(e_l[unocc].sum()),
        "cooling_thermal_kwh": float((q * params.dt_s * J_TO_KWH).sum()),
        "solar_gain_kwh": float((df["q_solar_w"].to_numpy() * params.dt_s * J_TO_KWH).sum()),
        "unoccupied_energy_kwh": float(e[unocc].sum()),
        "unoccupied_hvac_kwh": float(e_h[unocc].sum()),
        "unnecessary_hvac_kwh": float(e_h[unocc & ~near_future].sum()),
        "unnecessary_energy_kwh": float(e_h[unocc & ~near_future].sum() + e_l[unocc].sum()),
        "max_t_c": float(t.max()),
        "mean_t_c": float(t.mean()),
        "peak_cooling_kw": float(q.max() / 1000.0),  # حراري
        "peak_electric_kw": float(np.max(p_tot)),          # كلي (تكييف + إنارة)
        "peak_hvac_electric_kw": float(q.max() / params.cop / 1000.0),
        "hvac_on_h": float(on.sum() * params.dt_s / 3600.0),
        "switch_count": int(np.count_nonzero(on[1:] != on[:-1])),
        "arrival_temp_c": float(t[int(np.argmax(occ))]) if occ.any() else float("nan"),
        # ساعات-أشخاص (Σ عدد الطلاب × dt) — وزن تجميع الراحة على مستوى المبنى/الجامعة
        "occupant_hours": float(df["occupancy"].to_numpy().sum() * params.dt_s / 3600.0),
    }
    out.update(comfort_metrics(t, occ, params))
    return out


def assessment(key: str, m: dict, saving: float) -> str:
    """تصنيف نوعي يجمع الطاقة والراحة (لا يُكافأ خفض الطاقة على حساب الراحة)."""
    if key == "N":
        return "مرجع فيزيائي فقط"
    if not m["comfort_ok"]:
        return "مقيّد: راحة غير مقبولة"
    if saving > 0.5:
        return "خيار مقبول: توفير مع راحة"
    if saving < -0.5:
        return "استهلاك أعلى من الأساس"
    return "مماثل للأساس"


def compare_strategies(inp: SimInputs, cfg: StrategyConfig | None = None,
                       precond_window_h: float = 4.0, keys=STRATEGY_KEYS,
                       baseline_key: str = BASELINE_KEY):
    """يشغّل الاستراتيجيات على *نفس* SimInputs (طقس/خصائص/إشغال/مدة/حرارة ابتدائية/COP متطابقة)."""
    if baseline_key not in keys:
        raise ValueError("خط الأساس يجب أن يكون ضمن الاستراتيجيات المقارنة.")
    results, rows = {}, {}
    for key in keys:
        df = simulate(inp, make_strategy(key, cfg))
        results[key] = df
        rows[key] = compute_metrics(df, inp.params, inp, precond_window_h)
    summary = pd.DataFrame.from_dict(rows, orient="index")
    base = float(summary.loc[baseline_key, "energy_kwh"])
    summary["saving_pct"] = [saving_percent(base, e) for e in summary["energy_kwh"]]
    summary["relative_energy_diff_pct"] = 0.0 - summary["saving_pct"]
    summary["name_ar"] = [STRATEGY_NAMES_AR[k] for k in summary.index]
    summary["assessment"] = [assessment(k, rows[k], summary.loc[k, "saving_pct"]) for k in summary.index]
    summary.attrs["baseline_key"] = baseline_key
    return results, summary


def best_strategy(summary: pd.DataFrame) -> str | None:
    """أقل طاقة بين الاستراتيجيات التشغيلية ذات الراحة المقبولة (None إن لم توجد)."""
    cand = summary[summary.index.isin(OPERATIONAL_KEYS) & summary["comfort_ok"]]
    if cand.empty:
        return None
    return str(cand["energy_kwh"].idxmin())


def orientation_shading_sweep(params, weather_slice, occ_blocks, tt_blocks, cfg=None,
                              shadings=(0.0, 0.5, 0.8), strategy_key="C") -> pd.DataFrame:
    """يقيس أثر الاتجاه × التظليل على الكسب الشمسي وطاقة استراتيجية واحدة (افتراضياً C)."""
    rows = []
    for o in ORIENTATIONS:
        for s in sorted(set(round(float(x), 3) for x in shadings)):
            p = params.with_(orientation=o, shading_fraction=s)
            inp = build_sim_inputs(p, weather_slice, occ_blocks, tt_blocks)
            df = simulate(inp, make_strategy(strategy_key, cfg))
            m = compute_metrics(df, p, inp)
            k = int(np.argmax(inp.q_solar))
            rows.append({
                "orientation": o, "shading": s,
                "solar_gain_kwh": m["solar_gain_kwh"],
                "peak_solar_w": float(inp.q_solar.max()),
                "peak_hour": float(inp.hours[k]) if inp.q_solar.max() > 0 else float("nan"),
                "t_out_at_peak_c": float(inp.t_out[k]),
                "energy_kwh": m["energy_kwh"],
                "comfort_violation_h": m["comfort_violation_h"],
            })
    return pd.DataFrame(rows)


def cop_sensitivity(df: pd.DataFrame, dt_s: float, cops=(2.5, 3.0, 3.5)) -> pd.DataFrame:
    """نفس الحمل التبريدي بمعاملات أداء مختلفة (تغيّر COP لا يغيّر الحمل الحراري في هذا النموذج).
    COP يمس طاقة التكييف فقط؛ طاقة الإنارة ثابتة وتُضاف للمجموع الكلي."""
    q = df["q_cool_w"].to_numpy()
    light = float(df["e_light_kwh"].sum()) if "e_light_kwh" in df else 0.0
    hv = [float(hvac_energy_kwh(q, c, dt_s).sum()) for c in cops]
    return pd.DataFrame({"cop": list(cops), "hvac_kwh": hv, "lighting_kwh": [light] * len(cops),
                         "energy_kwh": [h + light for h in hv]})


def cop_table(results: dict, dt_s: float, cops=(2.5, 3.0, 3.5)) -> pd.DataFrame:
    """جدول الطاقة (kWh) لكل استراتيجية × COP."""
    rows = {k: cop_sensitivity(df, dt_s, cops).set_index("cop")["energy_kwh"] for k, df in results.items()}
    t = pd.DataFrame(rows).T
    t.columns = [f"COP {c:g}" for c in cops]
    return t


def heat_balance(df: pd.DataFrame, dt_s: float) -> dict:
    """تفكيك الطاقة الحرارية اليومية (kWh حراري): الغلاف (كسب/فقد)، الشمس، الداخلي، التبريد المزال.
    internal_kwh يشمل حرارة الإنارة؛ lighting_heat_kwh هو جزؤها (للعرض فقط، ليس إضافة ثانية)."""
    f = dt_s * J_TO_KWH
    env = df["q_envelope_w"].to_numpy()
    light = float(df["q_light_w"].sum() * f) if "q_light_w" in df else 0.0
    return {
        "envelope_gain_kwh": float(np.clip(env, 0, None).sum() * f),
        "envelope_loss_kwh": float(-np.clip(env, None, 0).sum() * f),
        "solar_kwh": float(df["q_solar_w"].sum() * f),
        "internal_kwh": float(df["q_internal_w"].sum() * f),
        "lighting_heat_kwh": light,
        "cooling_removed_kwh": float(df["q_cool_w"].sum() * f),
    }


def overcooling_analysis(inp: SimInputs, setpoints=(24.0, 22.5, 21.0), strategy_key: str = "B",
                         cfg: StrategyConfig | None = None, reference_c: float | None = None) -> pd.DataFrame:
    """نفس الاستراتيجية بنقاط ضبط مختلفة: الطاقة الإضافية والبرودة الزائدة (cold_violation_h)."""
    cfg = cfg or StrategyConfig()
    rows = []
    for sp in setpoints:
        c = StrategyConfig(**{**cfg.__dict__, "target_c": float(sp)})
        df = simulate(inp, make_strategy(strategy_key, c))
        m = compute_metrics(df, inp.params, inp)
        rows.append({"setpoint_c": float(sp), "energy_kwh": m["energy_kwh"], "hvac_kwh": m["hvac_kwh"],
                     "unoccupied_energy_kwh": m["unoccupied_energy_kwh"],
                     "cold_violation_h": m["cold_violation_h"],
                     "comfort_violation_h": m["comfort_violation_h"],
                     "min_t_occupied_c": m["min_t_occupied_c"]})
    out = pd.DataFrame(rows)
    ref_sp = inp.params.comfort_setpoint_c if reference_c is None else reference_c
    match = out[np.isclose(out["setpoint_c"], ref_sp)]
    ref = (match if len(match) else out.loc[[out["setpoint_c"].idxmax()]])["energy_kwh"].iloc[0]
    out["extra_energy_pct"] = [-saving_percent(ref, e) for e in out["energy_kwh"]]
    return out


def to_reporting_interval(df: pd.DataFrame, minutes: int = 5) -> pd.DataFrame:
    """
    سلسلة عرض كل `minutes` دقيقة من نتائج التكامل (15 دقيقة):
    • الحرارة الداخلية والخارجية: استيفاء خطي بين نقاط التكامل (تقريب للعرض فقط).
    • القدرات (Q): ثابتة داخل خطوة أويلر (هذا هو افتراض النموذج نفسه).
    لا تُحسب الطاقة من هذه السلسلة أبداً؛ المجاميع تأتي من خطوات التكامل.
    """
    if minutes <= 0 or 15 % minutes:
        raise ValueError("فترة العرض يجب أن تقسم 15 دقيقة (1، 3، 5، 15).")
    base = df.set_index("timestamp")
    idx = pd.date_range(base.index[0], base.index[-1] + pd.Timedelta(minutes=15 - minutes),
                        freq=f"{minutes}min")
    out = pd.DataFrame(index=idx)
    for col in ("t_in", "t_out"):
        out[col] = base[col].reindex(base.index.union(idx)).interpolate("time").ffill().reindex(idx)
    for col in ("q_cool_w", "q_solar_w", "q_internal_w", "q_light_w", "occupancy"):
        if col in base:
            out[col] = base[col].reindex(idx, method="ffill")
    out["interpolated"] = ~out.index.isin(base.index)
    return out.reset_index(names="timestamp")


def resolve_scenario(scenario) -> Scenario:
    if isinstance(scenario, Scenario):
        return scenario
    if scenario not in SCENARIOS:
        raise ValueError("سيناريو غير معروف.")
    return SCENARIOS[scenario]


def run_analysis(params: ClassroomParams, scenario, weather_df: pd.DataFrame | None = None,
                 start_date=None, duration_h: int = 24, cfg: StrategyConfig | None = None,
                 baseline_key: str = BASELINE_KEY) -> dict:
    """خط معالجة كامل (بلا واجهة): تحقق → مقارنة عادلة → حساسية → تفكيك الكسب → إفراط التبريد."""
    params.validate()
    cfg = (cfg or StrategyConfig()).validate()
    sc = resolve_scenario(scenario)
    if weather_df is None:
        weather_df = generate_weather_profile(sc.weather_profile)
    if start_date is None:
        start_date = weather_df["timestamp"].iloc[0].normalize().date()
    wslice = slice_weather(weather_df, start_date, duration_h)
    inp = build_sim_inputs(params, wslice, sc.occupancy_blocks, sc.timetable_blocks)
    results, summary = compare_strategies(inp, cfg, baseline_key=baseline_key)
    sweep = orientation_shading_sweep(params, wslice, sc.occupancy_blocks, sc.timetable_blocks, cfg,
                                      shadings=(0.0, 0.25, 0.5, 0.75, params.shading_fraction))
    inp0 = build_sim_inputs(params.with_(shading_fraction=0.0), wslice, sc.occupancy_blocks, sc.timetable_blocks)
    return {
        "params": params, "cfg": cfg, "inputs": inp, "results": results, "summary": summary,
        "sweep": sweep, "cop": cop_table(results, params.dt_s),
        "heat_balance": {k: heat_balance(df, params.dt_s) for k, df in results.items()},
        "overcooling": overcooling_analysis(
            inp, setpoints=sorted({params.comfort_setpoint_c, 22.5, 21.0}, reverse=True), cfg=cfg),
        "q_solar_unshaded": inp0.q_solar, "scenario": sc, "weather_slice": wslice,
        "best": best_strategy(summary), "baseline_key": baseline_key,
    }


def hhmm(h: float) -> str:
    m = int(round(h * 60))
    return f"{(m // 60) % 24:02d}:{m % 60:02d}"
