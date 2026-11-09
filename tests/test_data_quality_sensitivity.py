"""اختبارات جودة بيانات الطقس، ضوضاء الحساسات، وتحليل الحساسية."""
import numpy as np
import pandas as pd
import pytest

from zilal.engine import data_quality as dq
from zilal.engine.scenarios import SCENARIOS
from zilal.engine.sensitivity import cop_energy_band, one_at_a_time, tornado
from zilal.engine.thermal_model import ClassroomParams, build_sim_inputs
from zilal.engine.weather import generate_weather_profile, slice_weather

DAY = pd.Timestamp("2025-07-14").date()
W = slice_weather(generate_weather_profile("typical"), DAY, 24)
SC = SCENARIOS["solar"]


def test_inject_faults_counts_and_determinism():
    c1, log1 = dq.inject_faults(W, missing_frac=0.1, spike_frac=0.05, seed=4)
    c2, _ = dq.inject_faults(W, missing_frac=0.1, spike_frac=0.05, seed=4)
    pd.testing.assert_frame_equal(c1, c2)
    n_missing = int(c1[["outdoor_temp_c", "solar_irradiance_wm2"]].isna().sum().sum())
    assert n_missing == round(0.1 * len(W))
    assert (log1["fault"] == "قراءة شاذة").sum() == round(0.05 * len(W))
    assert W["outdoor_temp_c"].notna().all()  # الأصل لم يُعدَّل
    with pytest.raises(ValueError):
        dq.inject_faults(W, missing_frac=0.9)


def test_detect_and_clean_documents_every_replacement():
    corrupt, _ = dq.inject_faults(W, missing_frac=0.1, spike_frac=0.04, seed=2)
    clean, log, summary = dq.detect_and_clean(corrupt)
    assert clean[["outdoor_temp_c", "solar_irradiance_wm2"]].notna().all().all()
    n_missing = int(corrupt[["outdoor_temp_c", "solar_irradiance_wm2"]].isna().sum().sum())
    assert (log["reason"] == "مفقودة").sum() == n_missing
    assert summary["outdoor_temp_c"]["replaced"] + summary["solar_irradiance_wm2"]["replaced"] == len(log)
    assert log["replacement"].notna().all()
    # كل قيمة لم تُعلَّم بقيت كما هي
    flagged = set(zip(log["index"], log["column"]))
    for col in ("outdoor_temp_c", "solar_irradiance_wm2"):
        for i in range(len(clean)):
            if (i, col) not in flagged:
                assert clean[col].iloc[i] == pytest.approx(corrupt[col].iloc[i])


def test_spikes_detected():
    corrupt = W.copy()
    corrupt.loc[40, "outdoor_temp_c"] += 15
    corrupt.loc[2, "solar_irradiance_wm2"] = 900  # إشعاع ليلي
    _, log, s = dq.detect_and_clean(corrupt)
    assert s["outdoor_temp_c"]["spikes"] >= 1
    assert s["solar_irradiance_wm2"]["night_solar"] == 1
    assert 40 in set(log[log["column"] == "outdoor_temp_c"]["index"])


def test_cleaning_beats_naive_and_bias_undetected():
    p = ClassroomParams()
    r = dq.weather_quality_experiment(p, W, SC.occupancy_blocks, SC.timetable_blocks, "C",
                                      missing_frac=0.05, spike_frac=0.06, seed=5)
    t = r["table"]
    assert t.loc["truth", "energy_error_pct"] == 0
    assert abs(t.loc["cleaned", "energy_error_pct"]) < abs(t.loc["naive", "energy_error_pct"])
    rb = dq.weather_quality_experiment(p, W, SC.occupancy_blocks, SC.timetable_blocks, "C", temp_bias_c=2.0, seed=5)
    assert rb["clean_summary"]["outdoor_temp_c"]["replaced"] == 0  # الانحياز لا يُكتشف
    assert rb["table"].loc["cleaned", "energy_error_pct"] > 1.0


def test_sensor_noise_experiment():
    inp = build_sim_inputs(ClassroomParams(), W, SC.occupancy_blocks, SC.timetable_blocks)
    zero = dq.sensor_noise_experiment(inp, "C", 0.0, 0.0)
    assert zero["table"].loc["ideal", "energy_kwh"] == pytest.approx(zero["table"].loc["noisy", "energy_kwh"])
    noisy = dq.sensor_noise_experiment(inp, "C", 0.8, 0.0, seed=1)
    assert noisy["table"].loc["noisy", "switch_count"] >= noisy["table"].loc["ideal", "switch_count"]
    rd = noisy["readings"]
    assert len(rd) == 96 * 3  # قراءات كل 5 دقائق
    resid = rd["sensor_reading_c"] - rd["t_in"]
    assert 0.5 < resid.std() < 1.1
    biased = dq.sensor_noise_experiment(inp, "C", 0.0, 1.0)
    # حساس يقرأ أعلى بدرجة → تبريد أكثر
    assert biased["table"].loc["noisy", "energy_kwh"] > biased["table"].loc["ideal", "energy_kwh"]


def test_one_at_a_time_sensitivity_directions():
    t = one_at_a_time(ClassroomParams(orientation="West"), W, SC.occupancy_blocks, SC.timetable_blocks, "C")
    cop = t[t["variable"] == "cop"].sort_values("value")
    assert list(cop["value"]) == [2.5, 3.0, 3.5]
    assert cop["energy_kwh"].is_monotonic_decreasing
    # COP يمس جزء التكييف فقط؛ طاقة الإنارة ثابتة
    assert cop["hvac_kwh"].iloc[0] / cop["hvac_kwh"].iloc[-1] == pytest.approx(3.5 / 2.5)
    assert cop["lighting_kwh"].nunique() == 1
    np.testing.assert_allclose(cop["energy_kwh"], cop["hvac_kwh"] + cop["lighting_kwh"])
    sh = t[t["variable"] == "shading"].sort_values("value")
    assert sh["solar_gain_kwh"].is_monotonic_decreasing and sh["energy_kwh"].is_monotonic_decreasing
    oc = t[t["variable"] == "occupancy"].sort_values("value")
    assert oc["energy_kwh"].is_monotonic_increasing
    so = t[t["variable"] == "solar_scale"].sort_values("value")
    assert so["energy_kwh"].is_monotonic_increasing
    assert set(t[t["variable"] == "orientation"]["value"]) == {"East", "West", "South"}
    assert len(tornado(t)) == 6


def test_cop_energy_band():
    lo, hi = cop_energy_band(10.0, 3.0)
    assert lo == pytest.approx(30 / 3.5) and hi == pytest.approx(12.0)
    assert np.isfinite(lo)
