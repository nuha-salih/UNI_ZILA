"""
state.py — حسابات مخزّنة مؤقتاً تشترك فيها الصفحات الثلاث (مصدر حقيقة واحد).

كل الصفحات تقرأ القاعة بوضعها التشغيلي من campus (الجدول، الحضور، التظليل) والمقارنة بالتشغيل التقليدي
المعتمد campus.CONVENTIONAL_KEY تحت الظروف نفسها؛ لا يوجد مسار حساب ثانٍ للقاعة نفسها.
"""
from __future__ import annotations

import streamlit as st

from .. import campus
from .. import ml
from .. import recommendations as rc


@st.cache_data(show_spinner="جارٍ محاكاة الحرم التجريبي…")
def campus_run() -> dict:
    return campus.simulate_campus()


@st.cache_data(show_spinner="جارٍ حساب المقارنة…")
def room_comparison(room_id: str, zilal_key: str, overrides: tuple = ()) -> dict:
    """overrides: أزواج (اسم المعامل، القيمة) لتعديلات «ماذا لو»؛ فارغة = الوضع التشغيلي كما في بقية الصفحات."""
    return campus.room_comparison(campus.ROOM_BY_ID[room_id], zilal_key, campus_run()["weather"], **dict(overrides))


@st.cache_data(show_spinner="جارٍ حساب التوصيات…")
def campus_recommendations() -> list:
    run = campus_run()
    return rc.campus_recommendations(run["metrics"], run["weather"])


@st.cache_resource(show_spinner="جارٍ تدريب نموذجي Random Forest و Gradient Boosting على بيانات اصطناعية…")
def ml_result(room_id: str, strategy_key: str) -> dict:
    room = campus.ROOM_BY_ID[room_id]
    return ml.train_and_compare(room.params(), strategy_key)
