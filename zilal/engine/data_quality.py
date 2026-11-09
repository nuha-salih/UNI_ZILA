"""
data_quality.py — تجارب جودة البيانات (جديد).

1) أعطال طقس محكومة: قراءات مفقودة، قراءات شاذة (قفزات)، خطأ قياس منهجي (انحياز)، ضوضاء.
2) كشف ومعالجة موثّقة: فحص المدى، كشف القفزات بالوسيط المتحرك، فحص الإشعاع الليلي،
   ثم استيفاء زمني للقيم المعلَّمة — مع سجل لكل قيمة استُبدلت. لا استبدال صامت.
3) مقارنة الأثر: نفس الاستراتيجية على (طقس سليم = الحقيقة) و(معالجة ساذجة) و(معالجة موثّقة).
4) ضوضاء حساس الحرارة الداخلية: التحكم يقرر بقراءة مشوّشة بينما الفيزياء على الحرارة الحقيقية.

كل البيانات اصطناعية؛ لا يوجد اتصال بحساسات أو محطات طقس فعلية.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .evaluation import compute_metrics, saving_percent, to_reporting_interval
from .strategies import MeasuredStrategy, StrategyConfig, make_strategy
from .thermal_model import ClassroomParams, build_sim_inputs, simulate

COLS = ("outdoor_temp_c", "solar_irradiance_wm2")
SPIKE_THRESH = {"outdoor_temp_c": 4.0, "solar_irradiance_wm2": 250.0}  # افتراضات موثّقة
VALID_RANGE = {"outdoor_temp_c": (-40.0, 65.0), "solar_irradiance_wm2": (0.0, 1500.0)}
NIGHT_HOURS = (19.5, 5.0)  # GHI > 20 W/m² بين 19:30 و05:00 يُعدّ غير معقول عند خط عرض نجران صيفاً
MAX_RELIABLE_GAP_STEPS = 8  # فجوة > ساعتين تُعلَّم «أقل موثوقية»


def inject_faults(df: pd.DataFrame, missing_frac: float = 0.0, spike_frac: float = 0.0,
                  temp_bias_c: float = 0.0, temp_noise_c: float = 0.0, ghi_noise_wm2: float = 0.0,
                  seed: int = 11) -> tuple[pd.DataFrame, pd.DataFrame]:
    """يُفسد نسخة من بيانات الطقس بأعطال محكومة. يعيد (البيانات المُفسدة، سجل الأعطال)."""
    for name, v, hi in (("missing_frac", missing_frac, 0.5), ("spike_frac", spike_frac, 0.2)):
        if not (0 <= v <= hi):
            raise ValueError(f"{name} خارج المدى [0, {hi}].")
    if temp_noise_c < 0 or ghi_noise_wm2 < 0:
        raise ValueError("انحراف الضوضاء لا يمكن أن يكون سالباً.")
    rng = np.random.default_rng(seed)
    out = df.copy()
    n = len(out)
    log = []
    t = out["outdoor_temp_c"].to_numpy(dtype=float, copy=True) + temp_bias_c
    g = out["solar_irradiance_wm2"].to_numpy(dtype=float, copy=True)
    if temp_noise_c > 0:
        t = t + rng.normal(0, temp_noise_c, n)
    if ghi_noise_wm2 > 0:
        g = np.clip(g + rng.normal(0, ghi_noise_wm2, n) * (g > 0), 0, None)
    n_sp = int(round(spike_frac * n))
    if n_sp:
        idx = rng.choice(n, n_sp, replace=False)
        for i in idx:
            if rng.random() < 0.5:
                t[i] += rng.choice([-1, 1]) * rng.uniform(8, 25)
                log.append((i, "outdoor_temp_c", "قراءة شاذة"))
            else:
                g[i] = rng.uniform(1200, 1600) if g[i] < 600 else rng.uniform(0, 50)
                log.append((i, "solar_irradiance_wm2", "قراءة شاذة"))
    n_miss = int(round(missing_frac * n))
    if n_miss:
        # فجوات متتالية قصيرة (1–4 خطوات) لمحاكاة انقطاع الإرسال
        remaining, guard = n_miss, 0
        while remaining > 0 and guard < 10 * n:
            guard += 1
            L = int(min(remaining, rng.integers(1, 5)))
            s = int(rng.integers(1, n - L - 1))
            col = COLS[int(rng.integers(0, 2))]
            arr = t if col == "outdoor_temp_c" else g
            if np.isnan(arr[s:s + L]).any():
                continue
            arr[s:s + L] = np.nan
            log.extend((i, col, "قراءة مفقودة") for i in range(s, s + L))
            remaining -= L
    out["outdoor_temp_c"] = t
    out["solar_irradiance_wm2"] = g
    if temp_bias_c:
        log.append((-1, "outdoor_temp_c", f"انحياز منهجي {temp_bias_c:+.1f} °م على كل القراءات"))
    flog = pd.DataFrame(log, columns=["index", "column", "fault"])
    return out, flog


def detect_and_clean(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """
    يكشف القيم المفقودة/خارج المدى/القفزات/الإشعاع الليلي ويستبدلها باستيفاء زمني.
    يعيد (بيانات منظّفة، سجل التعديلات لكل قيمة، ملخص). الانحياز المنهجي لا يُكتشف بهذه الفحوص.
    """
    clean = df.copy()
    h = (clean["timestamp"].dt.hour + clean["timestamp"].dt.minute / 60.0).to_numpy()
    rows, summary = [], {}
    for col in COLS:
        x = clean[col].to_numpy(dtype=float).copy()
        missing = np.isnan(x)
        lo, hi = VALID_RANGE[col]
        out_range = ~missing & ((x < lo) | (x > hi))
        med = pd.Series(np.where(missing | out_range, np.nan, x)).rolling(9, center=True, min_periods=3).median()
        spike = ~missing & ~out_range & (np.abs(x - med.to_numpy()) > SPIKE_THRESH[col])
        night = np.zeros_like(missing)
        if col == "solar_irradiance_wm2":
            night = ~missing & ~out_range & ((h >= NIGHT_HOURS[0]) | (h < NIGHT_HOURS[1])) & (x > 20)
        flagged = missing | out_range | spike | night
        for i in np.where(flagged)[0]:
            reason = ("مفقودة" if missing[i] else "خارج المدى" if out_range[i]
                      else "إشعاع ليلي غير معقول" if night[i] else "قفزة شاذة")
            rows.append({"index": int(i), "timestamp": clean["timestamp"].iloc[i], "column": col,
                         "reason": reason, "original": None if missing[i] else float(x[i])})
        x[flagged] = np.nan
        s = pd.Series(x, index=clean["timestamp"]).interpolate("time", limit_direction="both")
        clean[col] = s.to_numpy()
        # أطول فجوة معالجة
        run = best = 0
        for f in flagged:
            run = run + 1 if f else 0
            best = max(best, run)
        summary[col] = {"missing": int(missing.sum()), "out_of_range": int(out_range.sum()),
                        "spikes": int(spike.sum()), "night_solar": int(night.sum()),
                        "replaced": int(flagged.sum()), "longest_gap_steps": int(best),
                        "long_gap": bool(best > MAX_RELIABLE_GAP_STEPS)}
    clean["solar_irradiance_wm2"] = clean["solar_irradiance_wm2"].clip(lower=0)
    log = pd.DataFrame(rows, columns=["index", "timestamp", "column", "reason", "original"])
    for i, r in log.iterrows():
        log.loc[i, "replacement"] = float(clean[r["column"]].iloc[int(r["index"])])
    summary["method_ar"] = ("فحص المدى الفيزيائي، كشف القفزات بالوسيط المتحرك (9 خطوات؛ عتبة 4 °م و250 W/m²)، "
                            "فحص الإشعاع الليلي، ثم استيفاء زمني خطي للقيم المعلَّمة.")
    return clean, log, summary


def naive_fill(df: pd.DataFrame) -> pd.DataFrame:
    """معالجة ساذجة للمقارنة: ملء المفقود بآخر قيمة، وإبقاء القيم الشاذة كما هي (مع قص الإشعاع ≥ 0)."""
    out = df.copy()
    for col in COLS:
        out[col] = out[col].ffill().bfill()
    out["solar_irradiance_wm2"] = out["solar_irradiance_wm2"].clip(lower=0)
    return out


def weather_quality_experiment(params: ClassroomParams, weather_slice: pd.DataFrame, occ_blocks, tt_blocks,
                               strategy_key: str = "C", cfg: StrategyConfig | None = None,
                               **fault_kw) -> dict:
    """يقارن نتائج المحاكاة على الطقس السليم (الحقيقة) مقابل الطقس المُفسد بعد معالجتين."""
    corrupt, fault_log = inject_faults(weather_slice, **fault_kw)
    cleaned, clean_log, clean_summary = detect_and_clean(corrupt)
    variants = {"truth": weather_slice, "naive": naive_fill(corrupt), "cleaned": cleaned}
    runs, rows = {}, {}
    for name, w in variants.items():
        inp = build_sim_inputs(params, w, occ_blocks, tt_blocks)
        df = simulate(inp, make_strategy(strategy_key, cfg))
        runs[name] = df
        rows[name] = compute_metrics(df, params, inp)
    tbl = pd.DataFrame(rows).T[["energy_kwh", "comfort_violation_h", "max_t_c", "peak_cooling_kw"]]
    e_true = tbl.loc["truth", "energy_kwh"]
    tbl["energy_error_pct"] = [-saving_percent(e_true, e) if e_true > 0 else 0.0 for e in tbl["energy_kwh"]]
    tbl["max_abs_tin_error_c"] = [float(np.max(np.abs(runs[k]["t_in"].to_numpy() - runs["truth"]["t_in"].to_numpy())))
                                  for k in tbl.index]
    return {"corrupt": corrupt, "cleaned": cleaned, "naive": variants["naive"], "fault_log": fault_log,
            "clean_log": clean_log, "clean_summary": clean_summary, "table": tbl, "runs": runs}


def sensor_noise_experiment(inp, strategy_key: str = "C", sigma_c: float = 0.5, bias_c: float = 0.0,
                            cfg: StrategyConfig | None = None, seed: int = 3, report_minutes: int = 5) -> dict:
    """
    حساس داخلي افتراضي: (أ) التحكم بقراءة مثالية، (ب) التحكم بقراءة مشوّشة (σ، انحياز).
    يعيد المقاييس، وسلسلة قراءات العرض كل 5 دقائق (مثالية مقابل مشوّشة) للحالة (ب).
    """
    ideal_df = simulate(inp, make_strategy(strategy_key, cfg))
    noisy_strat = MeasuredStrategy(make_strategy(strategy_key, cfg), sigma_c=sigma_c, bias_c=bias_c, seed=seed)
    noisy_df = simulate(inp, noisy_strat)
    m_ideal = compute_metrics(ideal_df, inp.params, inp)
    m_noisy = compute_metrics(noisy_df, inp.params, inp)
    rep = to_reporting_interval(noisy_df, report_minutes)
    rng = np.random.default_rng(seed + 1000)
    rep["sensor_reading_c"] = rep["t_in"] + bias_c + (rng.normal(0, sigma_c, len(rep)) if sigma_c > 0 else 0.0)
    keys = ["energy_kwh", "comfort_violation_h", "switch_count", "max_deviation_c", "hvac_on_h"]
    tbl = pd.DataFrame({"ideal": {k: m_ideal[k] for k in keys}, "noisy": {k: m_noisy[k] for k in keys}}).T
    return {"ideal": ideal_df, "noisy": noisy_df, "table": tbl, "readings": rep,
            "measured_at_decisions": noisy_strat.readings}
