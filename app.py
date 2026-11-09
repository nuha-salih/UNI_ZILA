"""
ZILAL AI (ظِلال) — نموذج أكاديمي أولي للأداء الحراري وكفاءة الطاقة في القاعات الجامعية.
التشغيل:  python -m streamlit run app.py

ثلاث صفحات فقط، مفتوحة مباشرة دون تسجيل دخول: الرئيسية، المحاكاة، التحليلات والذكاء الاصطناعي.
كل البيانات والنتائج محاكاة اصطناعية؛ لا اتصال بمبانٍ أو أنظمة أو عدّادات فعلية لجامعة نجران.
"""
from __future__ import annotations

import streamlit as st

from zilal.ui import components as ui
from zilal.ui import site
from zilal.ui.theme import css
from zilal.views import home_page, insights_page, sim_page

VIEWS = {"home": home_page.render, "sim": sim_page.render, "insights": insights_page.render}


def main() -> None:
    st.set_page_config(page_title="ظِلال AI | منصة الأداء الحراري وكفاءة الطاقة", page_icon="🌡️", layout="wide",
                       initial_sidebar_state="collapsed")
    ui.md(css())
    ui.md(site.css())
    page = site.current_page()
    site.header(page)
    try:
        VIEWS[page]()
    except Exception as exc:  # noqa: BLE001 — رسالة واضحة بدل تتبع خام أمام الزائر
        st.error(f"حدث خطأ غير متوقع في هذه الصفحة: {exc}")
        with st.expander("تفاصيل تقنية"):
            st.exception(exc)
    site.footer()


main()
