"""
اختبارات القاعة الافتراضية ثلاثية الأبعاد:
1) الجسر (build_state): كل قيمة معروضة = مخرجات المحرك نفسها.
2) الصفحة داخل التطبيق (عبر بديل Streamlit): المدخلات تغيّر الحالة المرسلة للعرض.
3) اختبار متصفح حقيقي (Chromium/WebGL) — يُتجاوز تلقائياً إن لم تتوفر Node و Playwright.
"""
import json
import re
import shutil
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
from zilal.viz import classroom3d as c3  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
APP = str(ROOT / "app.py")


def run_case(strategy="C", **over):
    room = campus.ROOM_BY_ID["ENG-101"]
    p = room.params(occupancy=30, **over)
    w = generate_weather_profile("typical", start=campus.CAMPUS_DAY)
    a = ev.run_analysis(p, "prelecture", w, pd.Timestamp(campus.CAMPUS_DAY).date(), 24)
    return a, p, a["results"][strategy], a["summary"].loc[strategy].to_dict()


def test_state_mirrors_engine_exactly():
    a, p, df, m = run_case("D")
    s = c3.build_state(df, p, "D", m, 40)
    assert s["n"] == 96 and s["dt_s"] == 900
    np.testing.assert_allclose(s["t_in"], df["t_in"], atol=1e-4)
    np.testing.assert_allclose(s["q_cool"], df["q_cool_w"], atol=1e-4)
    np.testing.assert_allclose(s["g_facade"], df["g_facade"], atol=1e-4)
    assert s["occ"] == [int(x) for x in df["occupancy"]]
    assert s["e_cum"][-1] == pytest.approx(m["hvac_kwh"], abs=1e-3)   # الصفحة الأولى: طاقة التكييف
    assert s["kpi"]["energy_kwh"] == pytest.approx(m["hvac_kwh"])
    assert all(b >= a_ for a_, b in zip(s["e_cum"], s["e_cum"][1:]))
    assert s["kpi"]["compliance"] == pytest.approx(m["comfort_compliance"])
    assert s["q_max"] == p.hvac_capacity_w and s["band"] == [22.5, 25.5]
    assert s["start_index"] == 40 and s["orientation_label"] == "غرب"


def test_occupancy_capped_and_inputs_validated():
    a, p, df, m = run_case()
    bad = df.copy()
    bad.loc[50, "occupancy"] = 99
    assert max(c3.build_state(bad, p, "C", m)["occ"]) == p.max_occupancy
    nan = df.copy()
    nan.loc[3, "t_in"] = np.nan
    with pytest.raises(ValueError):
        c3.build_state(nan, p, "C", m)
    with pytest.raises(ValueError):
        c3.build_state(df.drop(columns=["g_facade"]), p, "C", m)


def test_shading_and_orientation_reach_the_view():
    _, p0, d0, m0 = run_case(shading_fraction=0.0)
    _, p8, d8, m8 = run_case(shading_fraction=0.8)
    s0, s8 = c3.build_state(d0, p0, "C", m0), c3.build_state(d8, p8, "C", m8)
    assert s8["shading"] == 0.8 and sum(s8["q_solar"]) < sum(s0["q_solar"])
    _, pe, de, me = run_case(orientation="East")
    se = c3.build_state(de, pe, "C", me)
    assert se["orientation"] == "East" and se["hour"][int(np.argmax(se["g_facade"]))] < 11


def test_html_is_self_contained_and_safe():
    a, p, df, m = run_case()
    html = c3.render_html(c3.build_state(df, p, "C", m), 600)
    assert "window.ZILAL_STATE=" in html and "#zl3d{height:600px}" in html
    assert not re.search(r'<script[^>]+src=|<link[^>]+href=|https?://', html)  # لا موارد خارجية
    payload = html.split("window.ZILAL_STATE=", 1)[1].split(";</script>", 1)[0]
    assert "</" not in payload
    assert json.loads(payload.replace("<\\/", "</"))["n"] == 96


def test_js_is_visualisation_only():
    js = (ROOT / "zilal" / "viz" / "classroom3d.js").read_text(encoding="utf-8")
    for forbidden in ("fetch(", "XMLHttpRequest", "import ", "capacitance", "ua_w_per_k", "COP"):
        assert forbidden not in js, forbidden
    for needed in ("S.t_in[", "S.q_cool[", "S.occ[", "S.g_facade[", "S.e_cum["):
        assert needed in js


# ---------------------------------------------------------------- real browser (optional)
BROWSER_JS = r"""
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({args:['--use-gl=swiftshader','--enable-webgl','--ignore-gpu-blocklist']});
  const p = await b.newPage({viewport:{width:1000,height:620}});
  const errs=[]; p.on('pageerror', e=>errs.push(String(e))); p.on('console', m=>{ if(m.type()==='error') errs.push(m.text()); });
  await p.goto('file://' + process.argv[2]); await p.waitForTimeout(1200);
  const frames = await p.evaluate(()=>window.__zl3dFrames||0);
  const fallback = await p.evaluate(()=>!document.getElementById('zl3d-fallback').hidden);
  const y0 = await p.evaluate(()=>window.__zl3d.cam.yaw);
  await p.mouse.move(500,330); await p.mouse.down(); await p.mouse.move(640,320,{steps:6}); await p.mouse.up();
  const y1 = await p.evaluate(()=>window.__zl3d.cam.yaw);
  await p.evaluate(()=>window.__zl3d.setIndex(0)); await p.click('#zl3d-play'); await p.waitForTimeout(1200);
  const moved = await p.evaluate(()=>window.__zl3d.state.i);
  await p.click('#zl3d-play'); await p.click('#zl3d-reset');
  const reset = await p.evaluate(()=>window.__zl3d.state.i);
  const tin = await p.textContent('#zl3d-tin');
  const shot = await p.screenshot();
  const nonBlank = shot.length > 20000;
  console.log(JSON.stringify({frames, fallback, rotated: y0!==y1, moved, reset, tin, nonBlank, errs}));
  await b.close();
})();
"""


def _have_browser():
    if not shutil.which("node"):
        return False
    r = subprocess.run(["node", "-e", "require('playwright')"], capture_output=True)
    return r.returncode == 0


@pytest.mark.skipif(not _have_browser(), reason="Node + Playwright غير متوفرين — اختبار المتصفح متجاوز")
def test_webgl_renders_and_interacts_in_real_browser():
    a, p, df, m = run_case("C")
    with tempfile.TemporaryDirectory() as d:
        page = Path(d) / "c3d.html"
        page.write_text(c3.render_html(c3.build_state(df, p, "C", m, 48), 600), encoding="utf-8")
        script = Path(d) / "check.js"
        script.write_text(BROWSER_JS, encoding="utf-8")
        out = subprocess.run(["node", str(script), str(page)], capture_output=True, text=True, timeout=120)
    res = json.loads(out.stdout.strip().splitlines()[-1])
    assert res["errs"] == [] and res["frames"] > 0 and not res["fallback"]
    assert res["rotated"] and res["moved"] > 0 and res["reset"] == 0 and res["nonBlank"]
    assert res["tin"].startswith(f"{df['t_in'].iloc[0]:.1f}")
