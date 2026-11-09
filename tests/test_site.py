"""
اختبارات الموقع بثلاث صفحات (عبر بديل Streamlit): الصفحات تُعرض دون تسجيل دخول، التنقل ثلاثة روابط فقط،
والقاعة نفسها تعرض الأرقام نفسها في الرئيسية والمحاكاة 3D والتحليلات والتقارير (مصدر حقيقة واحد).
"""
import json
import runpy
from pathlib import Path

import numpy as np
import pytest

from tests import st_stub

st = st_stub.install()
REC = st_stub.REC

from zilal import campus, challenge  # noqa: E402
from zilal.aggregation import aggregate  # noqa: E402
from zilal.reports.report_data import unit_report  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
APP = str(ROOT / "app.py")


def run_page(p, **ss):
    REC.reset()
    st.session_state.clear()
    st.session_state.update(ss)
    st.query_params.clear()
    if p is not None:
        st.query_params["p"] = p
    runpy.run_path(APP)
    assert not REC.errors, REC.errors
    assert not REC.exceptions, REC.exceptions
    return "\n".join(REC.markdown)


def component_state():
    html = REC.components[-1]["html"]
    return json.loads(html.split("window.ZILAL_STATE=", 1)[1].split(";</script>", 1)[0].replace("<\\/", "</"))


@pytest.fixture(scope="module")
def run():
    return campus.simulate_campus()


@pytest.mark.parametrize("p", [None, "home", "sim", "insights", "unknown"])
def test_pages_render_without_login(p):
    html = run_page(p)
    head = next(h for h in REC.markdown if 'class="z-head"' in h)
    assert head.count('class="z-nav-a') == 3
    for k in ("?p=home", "?p=sim", "?p=insights"):
        assert k in head
    low = html.lower()
    for word in ("تسجيل الدخول", "كلمة المرور", "اختر دوراً", "password", "login"):
        assert word not in low
    assert "غير مرتبط رسمياً بأنظمة جامعة نجران" in html


def test_home_numbers_come_from_engine(run):
    html = run_page("home")
    r = run["metrics"].loc[campus.REFERENCE_ROOM]
    uni = aggregate(run["metrics"], "university", run["series"]).iloc[0]
    assert f"{r['energy_kwh']:.1f}" in html and f"{r['reference_energy_kwh']:.1f}" in html
    assert f"{uni['qualified_saving_pct']:.1f}%" in html and f"{uni['saving_vs_reference_pct']:.1f}%" in html
    assert "?p=sim" in html and not REC.components   # لا محاكاة تفاعلية في الرئيسية


def test_same_room_same_numbers_everywhere(run):
    """الرئيسية/التحليلات (محاكاة الحرم) = القاعة 3D (الوضع التشغيلي) = تقرير القاعة."""
    rid = campus.REFERENCE_ROOM
    m = run["metrics"].loc[rid]
    run_page("sim")
    s = component_state()
    z, c = s["cases"]["zilal"], s["cases"]["conv"]
    assert z["key"] == campus.ROOM_BY_ID[rid].mode.strategy and c["key"] == campus.CONVENTIONAL_KEY
    assert z["e_day"] == pytest.approx(m["energy_kwh"], abs=1e-4)
    assert z["e_day_hvac"] == pytest.approx(m["hvac_kwh"], abs=1e-4)
    assert z["e_day_light"] == pytest.approx(m["lighting_kwh"], abs=1e-4)
    assert z["final"]["compliance"] == pytest.approx(m["comfort_compliance"])
    assert c["e_day"] == pytest.approx(m["reference_energy_kwh"], abs=1e-4)
    rep = unit_report("room", rid)
    assert dict(rep.kpis)["الطاقة الكلية — تكييف + إنارة (kWh/يوم)"] == f"{m['energy_kwh']:.1f}"
    assert dict(rep.kpis)["التشغيل التقليدي (kWh/يوم)"] == f"{m['reference_energy_kwh']:.1f}"


@pytest.mark.parametrize("rid", [r.room_id for r in campus.ROOMS])
def test_every_room_conventional_matches_campus_reference(run, rid):
    run_page("sim", sim_room=rid)
    s = component_state()
    assert s["cases"]["conv"]["e_day"] == pytest.approx(run["metrics"].loc[rid, "reference_energy_kwh"], abs=1e-4)
    room = campus.ROOM_BY_ID[rid]
    if campus.default_zilal_key(room) == room.mode.strategy:
        assert s["cases"]["zilal"]["e_day"] == pytest.approx(run["metrics"].loc[rid, "energy_kwh"], abs=1e-4)


def test_sim_what_if_is_labelled_and_recomputes(run):
    run_page("sim")
    base = component_state()
    html = run_page("sim", sim_room=campus.REFERENCE_ROOM, sim_zilal="D", sim_students=10, sim_shading=50,
                    sim_orientation="West", sim_cop=3.0, sim_lpd=8.0, sim_light=(8.0, 16.0))
    s = component_state()
    assert "ماذا لو" in html
    assert s["students"] == 10 and s["lighting"]["lpd_w_m2"] == 8.0 and s["lighting"]["on_h"] == 8.0
    assert s["cases"]["conv"]["e_day_light"] == pytest.approx(0.48 * 8)
    assert s["cases"]["zilal"]["e_day"] != base["cases"]["zilal"]["e_day"]


def test_insights_scopes_and_honest_savings(run):
    m = run["metrics"]
    uni = aggregate(m, "university", run["series"]).iloc[0]
    html = run_page("insights")
    assert f"{uni['energy_kwh']:.1f}" in html and f"{uni['qualified_saving_pct']:.1f}%" in html
    assert f"{uni['hvac_kwh']:.1f}" in html and f"{uni['lighting_kwh']:.1f}" in html
    bad = m[m["comfort_compliance"] < 0.95]
    assert html.count("لا يُحتسب — الراحة دون 95%") == len(bad) and len(bad) > 0
    assert "لا يتحكم" in html and "Random Forest" in html          # دور الذكاء الاصطناعي بصراحة
    for scope, extra in (("building", {"ins_bld": "B2"}), ("room", {"ins_room": "SCI-104"})):
        html = run_page("insights", ins_scope=scope, **extra)
        sub = m[m["building_id"] == "B2"] if scope == "building" else m.loc[["SCI-104"]]
        a = aggregate(sub, "university", run["series"]).iloc[0]
        assert f"{a['energy_kwh']:.1f}" in html


def test_report_download_from_insights():
    run_page("insights", ins_scope="university", ins_rep_ready=("university", None))
    names = [d["file_name"] for d in REC.downloads]
    assert names == ["zilal_university_ALL.pdf", "zilal_university_ALL_summary.csv", "zilal_university_ALL_timeseries.csv"]
    assert REC.downloads[0]["data"][:4] == b"%PDF"


def test_comfort_threshold_unified(run):
    board = challenge.room_leaderboard(run["metrics"])
    for _, r in board.iterrows():
        assert (r["comfort_gate"] == 1.0) == (r["comfort_compliance"] >= 0.95)
        if r["comfort_compliance"] < 0.95:
            assert r["energy_points_counted"] == 0.0
    js = (ROOT / "zilal/viz/classroom3d_v2.js").read_text(encoding="utf-8")
    assert "cZ < 0.95" in js and "cZ < 0.8" not in js
    np.testing.assert_allclose(campus.COMFORT_THRESHOLD, 0.95)
