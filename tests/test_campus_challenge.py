"""اختبارات الحرم التجريبي، التجميع الموزون، تحدي ظِلال، والتوصيات."""
import numpy as np
import pytest

from zilal import campus, challenge as ch, recommendations as rc
from zilal.aggregation import aggregate, naive_average_compliance
from zilal.engine import evaluation as ev
from zilal.engine.thermal_model import ClassroomParams


@pytest.fixture(scope="module")
def run():
    return campus.simulate_campus()


def test_hierarchy_consistent():
    assert 2 <= len(campus.BUILDINGS) <= 3
    for b in campus.BUILDINGS:
        rooms = campus.rooms_of(b.building_id)
        assert 2 <= len(rooms) <= 3
        assert len(campus.floors_of(b.building_id)) >= 2
        assert b.floors_total >= len(campus.floors_of(b.building_id))
        for r in rooms:
            assert r.room_id in b.rooms
            r.params().validate()
    ref = campus.ROOM_BY_ID[campus.REFERENCE_ROOM]
    assert ref.area_m2 == 60 and ref.capacity == 30
    assert {r.orientation for r in campus.ROOMS} == {"East", "West", "South"}


def test_cascading_helpers_update():
    for b in campus.BUILDINGS:
        for f in campus.floors_of(b.building_id):
            rooms = campus.rooms_of(b.building_id, f)
            assert rooms and all(r.floor == f and r.building_id == b.building_id for r in rooms)


def test_room_selection_changes_results(run):
    m = run["metrics"]
    assert m["energy_kwh"].nunique() == len(m)


def test_aggregation_weighted_not_average_of_averages(run):
    m = run["metrics"]
    u = aggregate(m, "university", run["series"]).iloc[0]
    assert u["energy_kwh"] == pytest.approx(m["energy_kwh"].sum())
    assert u["energy_intensity_kwh_m2"] == pytest.approx(m["energy_kwh"].sum() / m["area_m2"].sum())
    w = (m["comfort_compliance"] * m["occupant_hours"]).sum() / m["occupant_hours"].sum()
    assert u["comfort_compliance"] == pytest.approx(w)
    assert abs(u["comfort_compliance"] - naive_average_compliance(m).iloc[0]) > 1e-6  # الطريقتان تختلفان فعلاً
    assert u["coincident_peak_electric_kw"] <= u["sum_of_peaks_electric_kw"] + 1e-9
    b = aggregate(m, "building", run["series"])
    assert b["energy_kwh"].sum() == pytest.approx(u["energy_kwh"])
    f = aggregate(m, "floor")
    assert f["rooms"].sum() == len(m)
    with pytest.raises(ValueError):
        aggregate(m, "galaxy")


def test_score_formula_examples():
    s = ch.score_components(60.0, 100.0, 1.0)          # توفير 40٪ والتزام كامل
    assert s["score"] == pytest.approx(0.5 * 80 + 0.5 * 100)
    off = ch.score_components(0.0, 100.0, 0.0)          # إطفاء كامل وراحة منعدمة
    assert off["score"] == 0.0 and off["comfort_gate"] == 0.0
    mid = ch.score_components(50.0, 100.0, 0.94)        # دون حد الراحة الموحّد 95٪ → لا نقاط طاقة
    assert mid["comfort_gate"] == 0.0 and mid["energy_points_counted"] == 0.0
    edge = ch.score_components(50.0, 100.0, 0.95)       # عند الحد تماماً → نقاط الطاقة كاملة
    assert edge["comfort_gate"] == 1.0
    worse = ch.score_components(120.0, 100.0, 1.0)      # استهلاك أعلى من المرجع → صفر نقاط طاقة
    assert worse["energy_points"] == 0.0


def test_low_energy_poor_comfort_not_first(run):
    board = ch.room_leaderboard(run["metrics"])
    lowest_energy = board.loc[board["energy_kwh"].idxmin()]
    poor = board[board["comfort_compliance"] < 0.8]
    assert len(poor) >= 1
    assert board.iloc[0]["comfort_compliance"] >= 0.95
    assert (poor["rank"] > board[board["comfort_compliance"] >= 0.95]["rank"].min()).all()
    sci = board.set_index("room_id").loc["SCI-G01"]           # ترشيد صارم بهدف 27 °م
    assert sci["eei"] > 0.3 and sci["energy_points_counted"] == 0.0
    assert list(board["rank"]) == list(range(1, len(board) + 1))
    assert lowest_energy["room_id"] != board.iloc[0]["room_id"] or lowest_energy["comfort_compliance"] >= 0.95


def test_shutdown_not_rewarded(run):
    rid = "ENG-101"
    ref = run["metrics"].loc[rid, "reference_energy_kwh"]
    _, m_off = campus.simulate_room(campus.ROOM_BY_ID[rid], strategy="N", target_c=None, weather_day=run["weather"])
    _, m_d = campus.simulate_room(campus.ROOM_BY_ID[rid], strategy="D", target_c=None, weather_day=run["weather"])
    s_off = ch.score_components(m_off["energy_kwh"], ref, m_off["comfort_compliance"])
    s_d = ch.score_components(m_d["energy_kwh"], ref, m_d["comfort_compliance"])
    assert s_off["score"] < s_d["score"]


def test_challenge_does_not_modify_simulation(run):
    before = campus.simulate_campus()["metrics"]["energy_kwh"].to_numpy().copy()
    ch.room_leaderboard(run["metrics"])
    ch.building_leaderboard(run["metrics"])
    after = campus.simulate_campus()["metrics"]["energy_kwh"].to_numpy()
    np.testing.assert_array_equal(before, after)


def test_improvement_options_computed(run):
    board = ch.room_leaderboard(run["metrics"])
    row = board.set_index("room_id").loc["SCI-G01"]
    b = ch.best_improvement("SCI-G01", row["score"], row["reference_energy_kwh"], run["weather"])
    assert b["gain"] > 0 and b["comfort_compliance"] >= 0.8
    assert len(b["options"]) >= 5 * 3


def test_recommendations_are_evidence_based():
    a = ev.run_analysis(ClassroomParams(shading_fraction=0.0, orientation="West"), "prelecture")
    recs = rc.generate(a, "A")
    ids = {r.rec_id for r in recs}
    assert {"R1", "R2", "R4", "R5"} <= ids
    for r in recs:
        assert r.why_ar and any(ch_.isdigit() for ch_ in r.why_ar)
        assert "مضمون" not in r.why_ar + r.energy_impact_ar
    r2 = next(r for r in recs if r.rec_id == "R2")
    assert r2.evidence["best_kwh"] == pytest.approx(a["summary"].loc["D", "energy_kwh"])
    # قاعة فارغة: لا توصية توقيت تبريد مسبق
    e = ev.run_analysis(ClassroomParams(), "empty")
    assert "R4" not in {r.rec_id for r in rc.generate(e, "A")}
    # تظليل كامل مسبقاً: لا توصية تظليل
    full = ev.run_analysis(ClassroomParams(shading_fraction=1.0), "solar")
    assert "R5" not in {r.rec_id for r in rc.generate(full, "A")}
    with pytest.raises(ValueError):
        rc.generate(a, "Z")


