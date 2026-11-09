"""سلامة المشروع: الاستيراد، استقلالية المسارات، الإعدادات الآمنة، التقارير والتشكيل العربي."""
import importlib
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_core_modules_import():
    for m in ("zilal.engine.thermal_model", "zilal.engine.weather", "zilal.engine.scenarios",
              "zilal.engine.forecasting", "zilal.engine.strategies", "zilal.engine.evaluation",
              "zilal.engine.data_quality", "zilal.engine.sensitivity", "zilal.campus", "zilal.aggregation",
              "zilal.challenge", "zilal.recommendations", "zilal.ml",
              "zilal.reports.report_data", "zilal.reports.pdf_report", "zilal.reports.csv_export", "check_env"):
        importlib.import_module(m)


def test_check_env_try_import():
    import check_env
    assert check_env.try_import("numpy")[0]
    assert not check_env.try_import("definitely_missing_pkg")[0]


def test_no_absolute_or_machine_paths():
    pat = re.compile(r"(/home/|/mnt/|/tmp/|C:\\\\Users|C:/Users)")
    for f in ROOT.rglob("*"):
        if (f.suffix in {".py", ".md", ".txt", ".toml", ".bat"} and ".venv" not in f.parts
                and f.name not in (Path(__file__).name, "test_results.txt")):
            assert not pat.search(f.read_text(encoding="utf-8", errors="ignore")), f


def test_streamlit_config_is_safe_and_no_secrets():
    cfg = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    assert "enableCORS" not in cfg and "enableXsrfProtection" not in cfg
    assert not (ROOT / ".streamlit" / "secrets.toml").exists()


def test_requirements_cover_imports():
    req = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    for pkg in ("streamlit", "plotly", "numpy", "pandas", "scikit-learn", "reportlab"):
        assert pkg in req


def test_no_pages_directory_and_assets_present():
    assert not (ROOT / "pages").exists()  # يمنع تفعيل التنقل التلقائي في Streamlit
    for p in ("brand/nu_logo.png", "assets/fonts/DejaVuSans.ttf", "assets/fonts/DejaVuSans-Bold.ttf",
              "data/sample_weather.csv", "app.py", "setup_windows.bat", "run_windows.bat", "README.md"):
        assert (ROOT / p).exists(), p


def test_bat_scripts_use_venv_interpreter_explicitly():
    run = (ROOT / "run_windows.bat").read_text(encoding="utf-8")
    assert r'".venv\Scripts\python.exe" -m streamlit run app.py' in run
    setup = (ROOT / "setup_windows.bat").read_text(encoding="utf-8")
    assert "check_env.py" in setup and "-m venv .venv" in setup
    assert b"\r\n" in (ROOT / "run_windows.bat").read_bytes()


# ---- Arabic shaping for PDF -------------------------------------------------
def test_arabic_shaping_forms_and_lam_alef():
    from zilal.reports.arabic_text import shape, visual
    assert shape("لا") == "\uFEFB"
    assert shape("سلام") == "\uFEB3\uFEFC\uFEE1"
    s = shape("بيت")
    assert s == "\uFE91\uFEF4\uFE96"
    assert visual("ABC 12") == "ABC 12"
    v = visual("الطاقة 25 kWh")
    assert v.startswith("25 kWh") and v.endswith(shape("الطاقة")[::-1][-1])
    assert visual("قاعة (ENG-101)") .startswith("(ENG-101)")


def test_pdf_and_csv_from_computed_values():
    from zilal.engine.evaluation import run_analysis
    from zilal.engine.thermal_model import ClassroomParams
    from zilal import campus
    from zilal.reports import csv_export, pdf_report, report_data
    rep = report_data.room_report("ENG-101")
    room = campus.ROOM_BY_ID["ENG-101"]
    a = run_analysis(room.params(occupancy=room.capacity), "prelecture")
    m = a["summary"].loc[room.mode.strategy]
    e = m["energy_kwh"]
    assert dict(rep.kpis)["الطاقة الكلية (kWh/يوم)"] == f"{e:.2f}"
    assert dict(rep.kpis)["منها تكييف / إنارة (kWh)"] == f"{m['hvac_kwh']:.2f} / {m['lighting_kwh']:.2f}"
    assert e == pytest.approx(m["hvac_kwh"] + m["lighting_kwh"])
    assert dict(rep.config)["كثافة الإنارة (افتراض نموذج أولي)"] == "12 W/m²"
    csv = csv_export.summary_csv(rep).decode("utf-8-sig")
    assert f"{e:.2f}" in csv and "SIMULATED" in csv and "تنبيه" in csv
    ts = csv_export.timeseries_csv(rep).decode("utf-8-sig")
    assert ts.count("\n") == 96 * 6 + 1
    assert "e_light_kwh" in ts.splitlines()[0] and "e_total_kwh" in ts.splitlines()[0]
    pdf = pdf_report.build_pdf(rep)
    assert pdf[:5] == b"%PDF-" and pdf.count(b"/Type /Page") >= 2
    with pytest.raises(ValueError):
        report_data.unit_report("galaxy")
