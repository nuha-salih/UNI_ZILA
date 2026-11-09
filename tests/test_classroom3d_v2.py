"""
اختبارات النسخة الثانية من القاعة الافتراضية (مقارنة «التقليدي» مقابل «ظِلال» + التحكم الزمني):
1) الجسر build_compare_state: مدخلات متطابقة، طاقة متراكمة صحيحة (تكامل حصري حتى اللحظة)، تطابق المجموع
   النهائي مع ملخص المحرك، توفير سالب يُعرض كما هو، الراحة حتى الآن، رفض المدخلات غير الصالحة.
2) الصفحة داخل التطبيق عبر بديل Streamlit.
3) متصفح حقيقي (Chromium/WebGL): تسلسل العرض للمحكّم — بدء 08:00، السرعات، الإيقاف يجمّد، الاستئناف يكمل،
   القيم عند 12:00 = Python، نهاية اليوم = النتيجة النهائية، إعادة الضبط، الخطوات، تبديل الحالة المعروضة.
النسخة الأولى (test_classroom3d.py) تبقى كما هي.
"""
import json
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tests import st_stub

st = st_stub.install()
REC = st_stub.REC

from zilal import campus  # noqa: E402
from zilal.engine import evaluation as ev  # noqa: E402
from zilal.engine.weather import generate_weather_profile  # noqa: E402
from zilal.ui import state  # noqa: E402
from zilal.viz import classroom3d_compare as cmp  # noqa: E402
from tests.test_classroom3d import _have_browser  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
APP = str(ROOT / "app.py")


def analysis(**over):
    room = campus.ROOM_BY_ID["ENG-101"]
    p = room.params(occupancy=over.pop("occupancy", 30), **over)
    w = generate_weather_profile("typical", start=campus.CAMPUS_DAY)
    return ev.run_analysis(p, "prelecture", w, pd.Timestamp(campus.CAMPUS_DAY).date(), 24)


A = analysis()


# ---------------------------------------------------------------- bridge
def test_cases_share_identical_inputs_and_differ_only_by_control():
    s = cmp.build_compare_state(A, "R", "D")
    c, z = s["cases"]["conv"], s["cases"]["zilal"]
    assert (c["key"], z["key"]) == ("R", "D") and s["n"] == 96 and s["dt_s"] == 900
    dc, dz = A["results"]["R"], A["results"]["D"]
    for col in cmp.SHARED_COLS:
        np.testing.assert_array_equal(dc[col].to_numpy(), dz[col].to_numpy())
    assert c["t_in"][0] == z["t_in"][0]
    np.testing.assert_allclose(c["t_in"], dc["t_in"], atol=1e-4)
    np.testing.assert_allclose(z["q_cool_kw"], dz["q_cool_w"] / 1000.0, atol=1e-4)
    assert c["q_cool_kw"] != z["q_cool_kw"]  # منطق التحكم مختلف فعلاً


def test_energy_is_exclusive_integral_of_electric_power():
    s = cmp.build_compare_state(A, "R", "D")
    for key, case in s["cases"].items():
        df = A["results"][case["key"]]
        p_h = df["q_cool_w"].to_numpy() / s["cop"] / 1000.0           # تكييف kW كهربائي
        hours, occ = np.asarray(s["hour"]), np.asarray(s["occ"]) > 0
        on = ((hours >= 7) & (hours < 18)) if case["key"] in ("R", "A", "B") else occ   # من المبادئ الأولى
        p_l = on * 12.0 * 60.0 / 1000.0                                  # إنارة kW = LPD·A
        p_el = p_h + p_l
        np.testing.assert_allclose(case["p_light_kw"], p_l, atol=1e-6)
        np.testing.assert_allclose(case["p_total_kw"], p_el, atol=1e-4)
        assert case["light_on"] == [bool(x) for x in on]
        e = np.concatenate([[0.0], np.cumsum(p_el * 900 / 3600.0)])    # kWh عند حدود الخطوات
        eh = np.concatenate([[0.0], np.cumsum(p_h * 900 / 3600.0)])
        np.testing.assert_allclose(case["e_upto_hvac"], eh[:-1], atol=1e-4)
        np.testing.assert_allclose(np.asarray(case["e_upto_hvac"]) + np.asarray(case["e_upto_light"]),
                                   case["e_upto"], atol=1e-4)
        np.testing.assert_allclose(case["e_upto"], e[:-1], atol=1e-4)
        assert case["e_upto"][0] == 0.0
        assert case["e_day"] == pytest.approx(e[-1], abs=1e-4)
        assert case["e_day"] == pytest.approx(A["summary"].loc[case["key"], "energy_kwh"], abs=1e-6)
        assert all(np.diff(case["e_upto"]) >= -1e-12)                  # تراكمي لا يتناقص
        np.testing.assert_allclose(case["p_el_kw"], p_h, atol=1e-4)     # kW منفصلة عن kWh


def test_savings_at_noon_and_end_of_day():
    s = cmp.build_compare_state(A, "R", "D")
    c, z, k = s["cases"]["conv"], s["cases"]["zilal"], s["compare"]
    i = 48  # 12:00
    assert s["hour"][i] == pytest.approx(12.0)
    assert k["saved_kwh"][i] == pytest.approx(c["e_upto"][i] - z["e_upto"][i], abs=1e-6)
    assert k["saved_pct"][i] == pytest.approx((c["e_upto"][i] - z["e_upto"][i]) / c["e_upto"][i] * 100, abs=1e-2)
    summ = A["summary"]
    assert k["final"]["saved_kwh"] == pytest.approx(summ.loc["R", "energy_kwh"] - summ.loc["D", "energy_kwh"], abs=1e-3)


def test_negative_savings_are_reported_honestly():
    # نعكس الدورين (C مرجعاً و R «ذكياً») لنحصل على حالة تستهلك فيها الحالة الثانية أكثر
    s = cmp.build_compare_state(A, "C", "R")
    sv = np.array(s["compare"]["saved_kwh"])
    assert (sv < -1e-6).any(), "يجب أن تظهر قيم سالبة عندما تستهلك الحالة الثانية أكثر"
    assert s["compare"]["final"]["saved_kwh"] < 0


def test_comfort_so_far_and_compromised_comfort():
    s = cmp.build_compare_state(A, "R", "C")
    occ = np.array(s["occ"]) > 0
    first = int(occ.argmax())
    assert all(v is None for v in s["cases"]["zilal"]["comp_cum"][:first])
    assert s["cases"]["zilal"]["comp_cum"][first] is not None
    assert s["compare"]["final"]["d_comp_pp"] < 0       # C يوفّر لكن على حساب الراحة في هذه الظروف
    assert s["compare"]["final"]["saved_kwh"] > 0
    codes = s["cases"]["zilal"]["comfort"]
    assert all(c == cmp.COMFORT_NONE for c, o in zip(codes, occ) if not o)


def test_decision_events_come_from_engine_results():
    s = cmp.build_compare_state(A, "R", "D")
    z = s["cases"]["zilal"]
    ev_ = {e["kind"]: s["hour"][e["k"]] for e in z["events"]}
    df = A["results"]["D"]
    on = df["q_cool_w"].to_numpy() > 1
    occ = df["occupancy"].to_numpy() > 0
    first, k0 = int(occ.argmax()), next(e["k"] for e in z["events"] if e["kind"] == "precool")
    assert ev_["arrive"] == pytest.approx(12.0) and ev_["leave"] == pytest.approx(14.0)
    assert ev_["precool"] < ev_["arrive"] and on[k0:first].all() and not occ[k0:first].any() and not on[k0 - 1]
    assert ev_["off"] == pytest.approx(14.0) and not on[int(occ.nonzero()[0][-1]) + 1]
    # القواعد (C) لا تبرّد مسبقاً
    c_ev = [e["kind"] for e in cmp.build_compare_state(A, "R", "C")["cases"]["zilal"]["events"]]
    assert "precool" not in c_ev


def test_rejects_invalid_pairs():
    with pytest.raises(ValueError):
        cmp.build_compare_state(A, "D", "D")
    with pytest.raises(ValueError):
        cmp.build_compare_state(A, "R", "X")


def test_v2_html_self_contained_and_v1_untouched():
    html = cmp.render_html_v2(cmp.build_compare_state(A), 560)
    assert "http://" not in html and "https://" not in html and "<script src" not in html
    js = (ROOT / "zilal/viz/classroom3d_v2.js").read_text(encoding="utf-8")
    for banned in ("/ COP", "/COP", "3.6e6", "dt_s *", "* 900"):
        assert banned not in js, f"لا حسابات طاقة في JS: {banned}"
    for f in ("classroom3d.js", "classroom3d.css", "classroom3d.py"):
        assert (ROOT / "zilal/viz" / f).exists()
    assert "zl-deck" not in (ROOT / "zilal/viz/classroom3d.js").read_text(encoding="utf-8")


# ---------------------------------------------------------------- real browser: judge sequence
ACCEPT_JS = r"""
const { chromium } = require('playwright');
(async () => {
  const exp = JSON.parse(process.argv[3]);
  const b = await chromium.launch({args:['--use-gl=swiftshader','--enable-webgl','--ignore-gpu-blocklist']});
  const p = await b.newPage({viewport:{width:1200,height:900}});
  const errs=[]; p.on('pageerror', e=>errs.push(String(e))); p.on('console', m=>{ if(m.type()==='error') errs.push(m.text()); });
  await p.goto('file://' + process.argv[2]); await p.waitForTimeout(1000);
  const S = () => p.evaluate(()=>({p:window.__zl3d.state.p, playing:window.__zl3d.state.playing, speed:window.__zl3d.state.speed}));
  const txt = sel => p.textContent(sel);
  const out = {errs};
  out.start = await S(); out.startClock = await txt('#zl3d-now'); out.startLabel = await txt('#zl3d-play');
  // 1× ثم 5×: قياس معدل التقدم (خطوات / ثانية عرض)
  await p.click('#zl3d-play'); let t0 = Date.now(), p0 = (await S()).p; await p.waitForTimeout(2000);
  let s1 = await S(); out.rate1 = (s1.p - p0) / ((Date.now() - t0) / 1000);
  await p.click('[data-speed="5"]'); t0 = Date.now(); p0 = (await S()).p; await p.waitForTimeout(1500);
  let s5 = await S(); out.rate5 = (s5.p - p0) / ((Date.now() - t0) / 1000);
  // إيقاف: التجميد
  await p.click('#zl3d-play'); const a = await S(); const tA = await txt('#zl-dk-time');
  await p.waitForTimeout(900); const b2 = await S(); const tB = await txt('#zl-dk-time');
  out.freeze = {a: a.p, b: b2.p, same: tA === tB, playing: b2.playing, label: await txt('#zl3d-play')};
  // الانتقال إلى 12:00 وقراءة لوحة المقارنة
  await p.evaluate(()=>window.__zl3d.setIndex(48));
  out.pwNoon = await txt('#zl-dk-pw'); out.pwPaths = await p.evaluate(()=>document.querySelectorAll('#zl-dk-pw path').length);
  out.noon = {time: await txt('#zl-dk-time'), body: await txt('#zl-dk-body'), kpis: await txt('#zl-dk-kpis'),
              verdict: await txt('#zl-dk-verdict'), ecum: await txt('#zl3d-ecum')};
  // استئناف من النقطة نفسها
  await p.click('#zl3d-play'); await p.waitForTimeout(250); const r = await S();
  out.resume = {p: r.p, playing: r.playing};
  // 10× حتى نهاية اليوم
  await p.click('[data-speed="10"]');
  await p.waitForFunction(()=>window.__zl3d.state.p === window.ZILAL_STATE.n && !window.__zl3d.state.playing, null, {timeout: 60000});
  out.pwEnd = await txt('#zl-dk-pw');
  out.end = {clock: await txt('#zl3d-now'), time: await txt('#zl-dk-time'), kpis: await txt('#zl-dk-kpis'),
             body: await txt('#zl-dk-body'), ecum: await txt('#zl3d-ecum'), label: await txt('#zl3d-play')};
  // إعادة الضبط والخطوات وتبديل العرض
  await p.click('#zl3d-reset'); out.reset = await S(); out.resetLabel = await txt('#zl3d-play');
  await p.click('[data-step="4"]'); const st1 = (await S()).p; await p.click('[data-step="-1"]'); const st2 = (await S()).p;
  out.steps = [st1, st2];
  await p.click('[data-view="conv"]'); out.convTin = await txt('#zl3d-tin');
  await p.click('[data-view="zilal"]'); out.zilTin = await txt('#zl3d-tin');
  out.frames = await p.evaluate(()=>window.__zl3dFrames||0);
  console.log(JSON.stringify(out));
  await b.close();
})();
"""


@pytest.mark.skipif(not _have_browser(), reason="Node + Playwright غير متوفرين — اختبار المتصفح متجاوز")
def test_judge_sequence_in_real_browser():
    s = cmp.build_compare_state(A, "R", "D", 32)
    c, z, k = s["cases"]["conv"], s["cases"]["zilal"], s["compare"]
    with tempfile.TemporaryDirectory() as d:
        page = Path(d) / "v2.html"
        page.write_text(cmp.render_html_v2(s, 560), encoding="utf-8")
        script = Path(d) / "accept.js"
        script.write_text(ACCEPT_JS, encoding="utf-8")
        out = subprocess.run(["node", str(script), str(page), "{}"], capture_output=True, text=True, timeout=180)
    assert out.returncode == 0, out.stderr[-2000:]
    r = json.loads(out.stdout.strip().splitlines()[-1])
    assert r["errs"] == [] and r["frames"] > 0
    # البدء من 08:00
    assert r["start"]["p"] == 32 and r["startClock"] == "08:00" and not r["start"]["playing"]
    # السرعة تغيّر العرض فقط (≈ 2 خطوة/ث عند 1×، أسرع بوضوح عند 5×)
    assert r["rate1"] > 0.5 and r["rate5"] > 2.5 * r["rate1"]
    # الإيقاف يجمّد الزمن والقيم
    assert r["freeze"]["a"] == r["freeze"]["b"] and r["freeze"]["same"] and not r["freeze"]["playing"]
    # 12:00: القيم = Python (حتى 12:00 حصرياً)
    noon = r["noon"]
    assert noon["time"] == "12:00"
    assert f"{c['e_upto'][48]:.2f}" in noon["body"] and f"{z['e_upto'][48]:.2f}" in noon["body"]
    assert f"{k['saved_kwh'][48]:.2f}" in noon["kpis"] and f"{k['saved_pct'][48]:.1f}%" in noon["kpis"]
    assert f"{c['q_cool_kw'][48]:.2f}" in noon["body"] and f"{z['t_in'][48]:.1f}" in noon["body"]
    assert noon["ecum"].startswith(f"{z['e_upto'][48]:.2f}")
    # رسم القدرة: يظهر قرار التبريد المسبق عند 12:00، والإطفاء التلقائي فقط بعد بلوغه
    assert r["pwPaths"] == 6 and "11:00" in r["pwNoon"] and "14:00" not in r["pwNoon"].split("محاضرة")[-1]
    assert "14:00" in r["pwEnd"]
    # الاستئناف يكمل من النقطة نفسها
    assert r["resume"]["playing"] and 48 <= r["resume"]["p"] <= 52
    # نهاية اليوم = النتيجة النهائية
    e = r["end"]
    assert e["clock"] == "24:00" and e["time"].startswith("24:00")
    assert f"{k['final']['saved_kwh']:.2f}" in e["kpis"] and f"{k['final']['saved_pct']:.1f}%" in e["kpis"]
    assert f"{c['e_day']:.2f}" in e["body"] and f"{z['e_day']:.2f}" in e["body"]
    assert e["ecum"].startswith(f"{z['e_day']:.2f}")
    # إعادة الضبط والخطوات وتبديل الحالة المعروضة
    assert r["reset"]["p"] == 32 and not r["reset"]["playing"]
    assert r["steps"] == [36, 35]
    assert r["convTin"].startswith(f"{c['t_in'][35]:.1f}") and r["zilTin"].startswith(f"{z['t_in'][35]:.1f}")

