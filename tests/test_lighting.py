"""
اختبارات التحكم بالإنارة (الإصدار 2.3):
• الإنارة تدخل المحاكاة بطريقتين منفصلتين: كهرباء مباشرة + كسب حراري داخلي — دون ازدواج.
• التقليدي: جدول ثابت قابل للضبط (افتراضياً 07:00–18:00) حتى والقاعة فارغة؛ ظِلال: حسب الإشغال.
• عدالة المقارنة: كل ما عدا التحكم متطابق.
• الطاقة الكلية = تكييف + إنارة في الملخص والتقارير؛ COP يمس التكييف فقط.
"""
import numpy as np
import pandas as pd
import pytest

from zilal import recommendations as rc
from zilal.engine import evaluation as ev
from zilal.engine.strategies import STRATEGY_LIGHTING, make_strategy
from zilal.engine.thermal_model import (ClassroomParams, build_sim_inputs, internal_gain, lighting_power_w,
                                        simulate, with_lighting)
from zilal.engine.weather import generate_weather_profile, slice_weather

W = slice_weather(generate_weather_profile("typical"), generate_weather_profile("typical")["timestamp"].iloc[0].date(), 24)
LEC = ((12.0, 14.0),)


def inp_for(p=None):
    return build_sim_inputs(p or ClassroomParams(), W, LEC, LEC)


def test_lighting_power_modes_and_schedule_is_configurable():
    p = ClassroomParams()
    inp = inp_for(p)
    sched = lighting_power_w(p, inp.hours, inp.occ, "schedule")
    occ = lighting_power_w(p, inp.hours, inp.occ, "occupancy")
    assert sched.max() == pytest.approx(12 * 60) and occ.max() == pytest.approx(720)
    assert (sched > 0).sum() * 0.25 == pytest.approx(11.0)        # 07–18
    assert (occ > 0).sum() * 0.25 == pytest.approx(2.0)           # المحاضرة فقط
    p2 = p.with_(lighting_on_h=8.0, lighting_off_h=16.0, lighting_w_per_m2=8.0)
    s2 = lighting_power_w(p2, inp.hours, inp.occ, "schedule")
    assert (s2 > 0).sum() * 0.25 == pytest.approx(8.0) and s2.max() == pytest.approx(480)
    with pytest.raises(ValueError):
        ClassroomParams(lighting_on_h=18, lighting_off_h=7).validate()
    with pytest.raises(ValueError):
        lighting_power_w(p, inp.hours, inp.occ, "daylight")


def test_heat_counted_once_and_electricity_separately():
    inp = inp_for()
    for k in ("R", "D"):
        df = simulate(inp, make_strategy(k))
        base = internal_gain(inp.params, inp.occ, np.zeros(inp.n))     # أشخاص + أجهزة فقط
        # الكسب الداخلي = غير المتحكم به + الإنارة مرة واحدة
        np.testing.assert_allclose(df["q_internal_w"], base + df["q_light_w"])
        np.testing.assert_allclose(df["e_light_kwh"], df["q_light_w"] * 900 / 3.6e6)
        np.testing.assert_allclose(df["e_total_kwh"], df["e_hvac_kwh"] + df["e_light_kwh"])
        np.testing.assert_allclose(df["p_total_kw"], df["p_hvac_kw"] + df["p_light_kw"])
        assert df.attrs["lighting_mode"] == STRATEGY_LIGHTING[k]
    # with_lighting يعيد البناء من المكونات: التبديل ذهاباً وإياباً لا يراكم شيئاً
    back = with_lighting(with_lighting(inp, "schedule"), "occupancy")
    np.testing.assert_allclose(back.q_internal, inp.q_internal)


def test_lighting_heat_raises_cooling_load():
    """نفس منطق التكييف (R) مع إنارة مجدولة مقابل حسب الإشغال: الحرارة الإضافية تزيد طاقة التكييف."""
    inp = inp_for()
    sched = make_strategy("R")
    occ = make_strategy("R"); occ.lighting_mode = "occupancy"
    a, b = simulate(inp, sched), simulate(inp, occ)
    assert a["e_hvac_kwh"].sum() > b["e_hvac_kwh"].sum()
    assert a["e_light_kwh"].sum() == pytest.approx(0.72 * 11)
    assert b["e_light_kwh"].sum() == pytest.approx(0.72 * 2)


def test_fair_comparison_only_control_differs():
    a = ev.run_analysis(ClassroomParams(), "prelecture")
    ref = a["results"]["R"]
    for k, df in a["results"].items():
        for col in ("timestamp", "t_out", "g_facade", "q_solar_w", "occupancy"):
            np.testing.assert_array_equal(df[col].to_numpy(), ref[col].to_numpy())
        assert df["t_in"].iloc[0] == ref["t_in"].iloc[0]
        np.testing.assert_allclose(df["q_internal_w"] - df["q_light_w"], ref["q_internal_w"] - ref["q_light_w"])


def test_summary_reports_hvac_lighting_total_and_cop_hits_hvac_only():
    a = ev.run_analysis(ClassroomParams(), "prelecture")
    s = a["summary"]
    np.testing.assert_allclose(s["energy_kwh"], s["hvac_kwh"] + s["lighting_kwh"])
    assert s.loc["R", "lighting_kwh"] == pytest.approx(7.92) and s.loc["D", "lighting_kwh"] == pytest.approx(1.44)
    assert s.loc["R", "unoccupied_lighting_kwh"] == pytest.approx(7.92 - 1.44)
    assert s.loc["D", "unoccupied_lighting_kwh"] == 0.0
    cop = ev.cop_sensitivity(a["results"]["R"], 900, (2.5, 3.5))
    assert cop["hvac_kwh"].iloc[0] / cop["hvac_kwh"].iloc[1] == pytest.approx(3.5 / 2.5)
    assert cop["lighting_kwh"].iloc[0] == cop["lighting_kwh"].iloc[1]
    # التوفير على الطاقة الكلية، والراحة ما زالت شرطاً
    assert s.loc["D", "saving_pct"] == pytest.approx((s.loc["R", "energy_kwh"] - s.loc["D", "energy_kwh"])
                                                     / s.loc["R", "energy_kwh"] * 100)
    assert not s.loc["C", "comfort_ok"] and s.loc["C", "assessment"].startswith("مقيّد")


def test_lighting_recommendation_is_recomputed_not_estimated():
    a = ev.run_analysis(ClassroomParams(), "prelecture")
    recs = {r.rec_id: r for r in rc.generate(a, "R")}
    r10 = recs["R10"]
    alt = make_strategy("R"); alt.lighting_mode = "occupancy"
    m = ev.compute_metrics(simulate(a["inputs"], alt), a["params"], a["inputs"])
    assert r10.evidence["saved_total_kwh"] == pytest.approx(a["summary"].loc["R", "energy_kwh"] - m["energy_kwh"])
    assert r10.evidence["saved_hvac_kwh"] > 0          # أثر الحرارة محسوب لا مُقدّر
    assert "R10" not in {r.rec_id for r in rc.generate(a, "D")}   # ظِلال لا يترك الإنارة في قاعة فارغة
