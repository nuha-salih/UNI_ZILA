"""اختبارات الإضافات العلمية: الوحدات، الاستراتيجيات الجديدة، الراحة، التوازن الحراري، فترة العرض، الإفراط في التبريد."""
import numpy as np
import pandas as pd
import pytest

from zilal.engine import evaluation as ev
from zilal.engine.scenarios import SCENARIOS, customize
from zilal.engine.strategies import (MeasuredStrategy, PredictiveStrategy, StrategyConfig, make_strategy)
from zilal.engine.thermal_model import DT_S, ClassroomParams, build_sim_inputs, simulate
from zilal.engine.weather import generate_synthetic_weather, generate_variable_weather, generate_weather_profile, slice_weather

DAY = pd.Timestamp("2025-07-14").date()


def day(profile="typical"):
    return slice_weather(generate_weather_profile(profile), DAY, 24)


def inp_for(key="prelecture", **kw):
    sc = SCENARIOS[key]
    return build_sim_inputs(ClassroomParams(**kw), day(), sc.occupancy_blocks, sc.timetable_blocks)


def test_timestep_is_900s_and_96_steps_per_day():
    assert DT_S == 900.0
    inp = inp_for()
    assert inp.n == 96
    ts = pd.to_datetime(pd.Series(inp.timestamps))
    assert (ts.diff().dropna() == pd.Timedelta(seconds=900)).all()


def test_energy_units_kwh():
    # 3 kW حراري لمدة ساعة (4 خطوات) عند COP=3 → 1 kWh كهربائي
    df = simulate(inp_for(), type("K", (), {"reset": lambda s, i: None, "decide": lambda s, k, T, i: 3000.0})())
    first4 = df["e_hvac_kwh"].iloc[:4].sum()
    assert first4 == pytest.approx(1.0)
    assert df["p_hvac_kw"].iloc[0] == pytest.approx(1.0)


def test_numerical_stability_ratio():
    p = ClassroomParams()
    assert p.dt_s * p.ua_w_per_k / p.capacitance_j_per_k < 0.05


def test_no_control_is_zero_energy_and_reference_continuous():
    inp = inp_for()
    n = simulate(inp, make_strategy("N"))
    r = simulate(inp, make_strategy("R"))
    assert n["e_hvac_kwh"].sum() == 0.0
    a = simulate(inp, make_strategy("A"))
    assert r["e_hvac_kwh"].sum() > a["e_hvac_kwh"].sum()  # المستمر يبرّد ليلاً أيضاً
    assert (r["q_cool_w"] > 0).mean() > 0.9


def test_heat_balance_closes_energy_conservation():
    inp = inp_for("solar")
    p = inp.params
    for key in ("N", "C", "D"):
        df = simulate(inp, make_strategy(key))
        net_j = ((df["q_envelope_w"] + df["q_solar_w"] + df["q_internal_w"] - df["q_cool_w"]) * p.dt_s).sum()
        t_end = df["t_in"].iloc[-1] + p.dt_s / p.capacitance_j_per_k * (
            df["q_envelope_w"].iloc[-1] + df["q_solar_w"].iloc[-1] + df["q_internal_w"].iloc[-1] - df["q_cool_w"].iloc[-1])
        assert net_j == pytest.approx(p.capacitance_j_per_k * (t_end - df["t_in"].iloc[0]), rel=1e-9)


def test_comfort_metrics_definitions():
    p = ClassroomParams()
    t = np.array([24.0, 26.5, 27.5, 24.0, 21.5, 24.0])
    occ = np.array([1, 1, 1, 1, 1, 0], bool)
    m = ev.comfort_metrics(t, occ, p)
    assert m["comfort_violation_h"] == pytest.approx(0.75)
    assert m["max_deviation_c"] == pytest.approx(2.0)
    assert m["longest_uncomfortable_h"] == pytest.approx(0.5)
    assert m["degree_hours"] == pytest.approx((1.0 + 2.0 + 1.0) * 0.25)
    assert m["comfort_compliance"] == pytest.approx(2 / 5)
    assert m["mean_t_occupied_c"] == pytest.approx(t[:5].mean())
    empty = ev.comfort_metrics(t, np.zeros(6, bool), p)
    assert not empty["comfort_applicable"] and empty["comfort_compliance"] == 1.0


def test_strategy_comparison_holds_inputs_constant_and_cop():
    a = ev.run_analysis(ClassroomParams(cop=2.7), "solar")
    ref = a["results"]["R"]
    for k, df in a["results"].items():
        for col in ("timestamp", "t_out", "q_solar_w", "occupancy"):
            np.testing.assert_array_equal(df[col].to_numpy(), ref[col].to_numpy())
        # الكسب الداخلي غير المتحكم به (أشخاص + أجهزة) متطابق؛ الإنارة وحدها تختلف بحسب التحكم
        np.testing.assert_allclose(df["q_internal_w"] - df["q_light_w"], ref["q_internal_w"] - ref["q_light_w"])
        np.testing.assert_allclose(df["e_hvac_kwh"], df["q_cool_w"] / 2.7 * 900 / 3.6e6)


def test_baseline_choice_and_assessment():
    a = ev.run_analysis(ClassroomParams(), "prelecture")
    s = a["summary"]
    assert s.loc["R", "saving_pct"] == 0.0 and s.attrs["baseline_key"] == "R"
    assert s.loc["C", "assessment"].startswith("مقيّد")       # يوفر طاقة لكن يخالف الراحة
    assert s.loc["D", "assessment"].startswith("خيار مقبول")
    assert a["best"] == "D"
    b = ev.run_analysis(ClassroomParams(), "prelecture", baseline_key="A")["summary"]
    assert b.loc["A", "saving_pct"] == 0.0
    with pytest.raises(ValueError):
        ev.compare_strategies(inp_for(), keys=("C", "D"), baseline_key="R")


def test_energy_alone_never_selects_best():
    a = ev.run_analysis(ClassroomParams(), "prelecture")
    s = a["summary"]
    lowest = s.loc[["R", "A", "B", "C", "D"], "energy_kwh"].idxmin()
    assert not s.loc[lowest, "comfort_ok"]
    assert a["best"] != lowest


def test_reporting_interval_matches_integration_points():
    df = simulate(inp_for(), make_strategy("D"))
    rep = ev.to_reporting_interval(df, 5)
    assert len(rep) == 96 * 3
    on_grid = rep[~rep["interpolated"]].reset_index(drop=True)
    np.testing.assert_allclose(on_grid["t_in"], df["t_in"])
    assert "e_hvac_kwh" not in rep.columns  # الطاقة لا تُحسب من سلسلة العرض
    with pytest.raises(ValueError):
        ev.to_reporting_interval(df, 7)


def test_overcooling_lower_setpoint_costs_energy_and_causes_cold():
    oc = ev.overcooling_analysis(inp_for("overcool"), setpoints=(24.0, 22.5, 21.0))
    e = oc.set_index("setpoint_c")["energy_kwh"]
    assert e[21.0] > e[22.5] > e[24.0]
    assert oc.set_index("setpoint_c").loc[21.0, "cold_violation_h"] > 0
    assert oc.set_index("setpoint_c").loc[24.0, "cold_violation_h"] == 0
    assert oc.set_index("setpoint_c").loc[24.0, "extra_energy_pct"] == 0


def test_target_override_validation():
    with pytest.raises(ValueError):
        StrategyConfig(target_c=10).validate()


def test_predictive_with_forecast_error_differs_and_perfect_forecast_identical():
    inp = inp_for()
    perfect = simulate(inp, PredictiveStrategy(StrategyConfig(), forecast_inp=inp))
    base = simulate(inp, make_strategy("D"))
    np.testing.assert_allclose(perfect["t_in"], base["t_in"])
    w = day().copy()
    w["outdoor_temp_c"] -= 4.0  # توقع متفائل (أبرد من الواقع)
    sc = SCENARIOS["prelecture"]
    fc = build_sim_inputs(ClassroomParams(), w, sc.occupancy_blocks, sc.timetable_blocks)
    biased = simulate(inp, PredictiveStrategy(StrategyConfig(), forecast_inp=fc))
    j = int(np.argmax(inp.occ > 0))
    assert biased["t_in"].iloc[j] > base["t_in"].iloc[j]  # بدأ التبريد المسبق متأخراً


def test_measured_strategy_zero_noise_is_identity():
    inp = inp_for()
    a = simulate(inp, make_strategy("C"))
    b = simulate(inp, MeasuredStrategy(make_strategy("C"), 0.0, 0.0))
    np.testing.assert_allclose(a["q_cool_w"], b["q_cool_w"])
    with pytest.raises(ValueError):
        MeasuredStrategy(make_strategy("C"), -1.0)


def test_weather_profiles_deterministic_and_labelled():
    assert generate_weather_profile("typical").equals(generate_synthetic_weather())
    h1, h2 = generate_weather_profile("high_solar"), generate_weather_profile("high_solar")
    assert h1.equals(h2)
    assert h1["solar_irradiance_wm2"].max() > generate_weather_profile("typical")["solar_irradiance_wm2"].max()
    assert generate_weather_profile("dusty")["solar_irradiance_wm2"].max() < 800
    assert (h1["data_source"].str.contains("SYNTHETIC")).all()
    v = generate_variable_weather(days=10)
    assert len(v) == 960 and v["solar_irradiance_wm2"].between(0, 1150).all()
    with pytest.raises(ValueError):
        generate_weather_profile("nope")


def test_scenario_customize_and_validation():
    sc = customize(SCENARIOS["prelecture"], occupancy_blocks=((9.0, 10.5),))
    assert sc.occupancy_blocks == ((9.0, 10.5),)
    with pytest.raises(ValueError):
        customize(SCENARIOS["prelecture"], occupancy_blocks=((14.0, 12.0),))
    assert set(SCENARIOS) == {"empty", "prelecture", "solar", "overcool"}


def test_occupancy_series_input():
    w = day()
    occ = np.zeros(96)
    occ[40:48] = 20
    inp = build_sim_inputs(ClassroomParams(), w, occupancy_series=occ, timetable_series=occ > 0)
    assert inp.occ.sum() == 160 and inp.timetable_on.sum() == 8
    with pytest.raises(ValueError):
        build_sim_inputs(ClassroomParams(), w, occupancy_series=occ[:10])


def test_empty_room_has_no_internal_gain_and_shading_effect_holds():
    a = ev.run_analysis(ClassroomParams(), "empty")
    # قاعة فارغة: لا كسب من أشخاص/أجهزة؛ الكسب الداخلي الوحيد حرارة الإنارة المجدولة (تقليدي)
    hb = a["heat_balance"]["N"]
    assert hb["internal_kwh"] == pytest.approx(hb["lighting_heat_kwh"])
    assert hb["lighting_heat_kwh"] == pytest.approx(12 * 60 * 11 / 1000)   # 0.72 kW × 07–18
    assert a["heat_balance"]["D"]["internal_kwh"] == 0.0                  # ظِلال: لا إنارة بلا طلاب
    shaded = ev.run_analysis(ClassroomParams(shading_fraction=0.8), "empty")
    assert shaded["summary"].loc["C", "solar_gain_kwh"] < a["summary"].loc["C", "solar_gain_kwh"]
