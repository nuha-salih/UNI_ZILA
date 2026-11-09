"""
check_env.py — فحص بيئة ZILAL AI (يُشغَّل تلقائياً من setup_windows.bat).

يتحقق من: إصدار Python، استيراد المكتبات الأساسية، تشغيل محاكاة قصيرة، بناء رسم، وتوليد PDF عربي.
يعيد رمز خروج 0 عند النجاح و 1 عند الفشل، مع رسالة واضحة بالعربية والإنجليزية.
"""
from __future__ import annotations

import importlib
import os
import sys
import traceback

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

REQUIRED = ("numpy", "pandas", "sklearn", "plotly", "reportlab", "streamlit")
OPTIONAL = ("pyarrow",)  # تستخدمه Streamlit داخلياً؛ المنصة لا تعتمد على st.dataframe


def try_import(name: str):
    try:
        mod = importlib.import_module(name)
        return True, getattr(mod, "__version__", "?")
    except Exception as exc:  # noqa: BLE001 — نعرض أي فشل (بما فيه منع Application Control)
        return False, f"{type(exc).__name__}: {exc}"


def smoke_test() -> list[str]:
    problems = []
    try:
        from zilal.engine.evaluation import run_analysis
        from zilal.engine.thermal_model import ClassroomParams
        a = run_analysis(ClassroomParams(), "prelecture")
        assert a["summary"].loc["D", "energy_kwh"] > 0
    except Exception:  # noqa: BLE001
        problems.append("المحاكاة / simulation:\n" + traceback.format_exc(limit=2))
    try:
        from zilal.ui import charts  # noqa: F401 — يستورد streamlit أيضاً
        import plotly.graph_objects as go
        go.Figure(charts.bar_chart(["أ", "ب"], [1.0, 2.0], "اختبار", "kWh"))
    except Exception:  # noqa: BLE001
        problems.append("الرسوم / charts:\n" + traceback.format_exc(limit=2))
    try:
        from zilal.reports.pdf_report import build_pdf
        from zilal.reports.report_data import room_report
        pdf = build_pdf(room_report("ENG-101"))
        assert pdf[:5] == b"%PDF-"
    except Exception:  # noqa: BLE001
        problems.append("تقرير PDF / PDF report:\n" + traceback.format_exc(limit=2))
    return problems


def main() -> int:
    ok = True
    v = sys.version_info
    print(f"Python {v.major}.{v.minor}.{v.micro}  ({sys.executable})")
    if (v.major, v.minor) != (3, 12):
        print("  تنبيه: الإصدار المُوصى به 3.12 / Note: Python 3.12 is the recommended version.")
    if (v.major, v.minor) < (3, 10):
        print("  خطأ: يلزم Python 3.10 أو أحدث / ERROR: Python >= 3.10 required.")
        return 1
    for name in REQUIRED:
        good, info = try_import(name)
        print(f"  [{'OK' if good else 'FAIL'}] {name:<12} {info}")
        ok &= good
    for name in OPTIONAL:
        good, info = try_import(name)
        print(f"  [{'OK' if good else 'WARN'}] {name:<12} {info}")
    if not ok:
        print("\nفشل استيراد مكتبة مطلوبة. إن ظهر 'DLL load failed' أو 'blocked' فقد تمنع سياسة Windows Application "
              "Control ملفات مترجمة داخل .venv؛ لا تعطّل الحماية — اطلب من قسم تقنية المعلومات السماح بمجلد المشروع، "
              "أو استخدم Streamlit Community Cloud.\nA required import failed (see above).")
        return 1
    problems = smoke_test()
    for p in problems:
        print("\n[FAIL] " + p)
    if problems:
        return 1
    print("\nنجح الفحص: البيئة جاهزة. / Environment OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
