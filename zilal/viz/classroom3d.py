"""
classroom3d.py — الجسر بين محرك المحاكاة (Python) وطبقة العرض ثلاثية الأبعاد (WebGL).

القاعدة المعمارية: Python هو المصدر الوحيد للأرقام. هذه الوحدة تأخذ نتائج المحاكاة الجاهزة
(DataFrame من thermal_model.simulate لكل خطوة 15 دقيقة) وتحوّلها إلى «حالة عرض» JSON تقرأها
classroom3d.js بالفهرس الزمني فقط. لا تُكرَّر أي معادلة حرارية في JavaScript.

المكوّن ذاتي الاحتواء: JS و CSS يُضمَّنان في صفحة HTML واحدة تُعرض عبر
streamlit.components.v1.html — دون مكتبات خارجية أو CDN أو اتصال بالإنترنت.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from ..engine.strategies import STRATEGY_NAMES_AR
from ..engine.thermal_model import ORIENTATION_AR, ClassroomParams

HERE = Path(__file__).resolve().parent
LABELS_AR = {
    "canvas": "القاعة الافتراضية ثلاثية الأبعاد", "camReset": "إعادة ضبط الكاميرا", "camTop": "منظر علوي",
    "camInside": "من داخل القاعة", "hint": "اسحب للتدوير · العجلة للتكبير · Shift+سحب أو زر الفأرة الأيمن للتحريك",
    "status": "حالة القاعة", "indoor": "داخل القاعة", "outdoor": "الحرارة الخارجية", "students": "الطلاب",
    "solar": "الكسب الشمسي", "cooling": "قدرة التبريد", "hvac": "المكيّف", "on": "يعمل", "off": "متوقف",
    "energyCum": "الطاقة منذ 00:00", "compliance": "الالتزام بالراحة (اليوم)", "energyDay": "طاقة التكييف اليوم",
    "start": "ابدأ المحاكاة", "pause": "إيقاف مؤقت", "resume": "استئناف", "reset": "إعادة المحاكاة إلى 00:00",
    "timeline": "الشريط الزمني لليوم المحاكى", "empty": "القاعة فارغة", "comfortOk": "مريحة",
    "tooHot": "أحرّ من نطاق الراحة", "tooCold": "أبرد من نطاق الراحة", "windowFaces": "النافذة تواجه",
    "note": "تمثيل مرئي لنتائج محاكاة RC أحادية المنطقة وطقس اصطناعي. لون هواء القاعة تمثيل مفهومي لحالتها "
            "الحرارية المحسوبة، وليس توزيعاً مكانياً للحرارة.",
    "noWebgl": "المتصفح لا يدعم WebGL؛ استخدم صفحة «المحاكاة الحرارية» لعرض النتائج نفسها.",
}


def _clean(a) -> list:
    arr = np.asarray(a, dtype=float)
    if not np.all(np.isfinite(arr)):
        raise ValueError("نتائج المحاكاة تحتوي قيماً غير صالحة؛ لا يمكن عرضها.")
    return [round(float(x), 4) for x in arr]


def build_state(df: pd.DataFrame, params: ClassroomParams, strategy_key: str, metrics: dict,
                start_index: int = 0) -> dict:
    """
    حالة العرض من نتائج محاكاة استراتيجية واحدة.
    df: مخرجات simulate (أعمدة t_in, t_out, q_cool_w, q_solar_w, g_facade, occupancy, e_hvac_kwh, hour).
    metrics: مخرجات compute_metrics لنفس التشغيل (للمؤشرات اليومية).
    """
    need = ("hour", "t_in", "t_out", "q_cool_w", "q_solar_w", "g_facade", "occupancy", "e_hvac_kwh")
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise ValueError(f"أعمدة مفقودة في نتائج المحاكاة: {missing}")
    occ = np.minimum(df["occupancy"].to_numpy(dtype=int), params.max_occupancy)
    n = len(df)
    return {
        "version": 1,
        "n": n,
        "dt_s": params.dt_s,
        "hour": _clean(df["hour"]),
        "t_in": _clean(df["t_in"]),
        "t_out": _clean(df["t_out"]),
        "q_cool": _clean(df["q_cool_w"]),
        "q_solar": _clean(df["q_solar_w"]),
        "g_facade": _clean(df["g_facade"]),
        "occ": [int(x) for x in occ],
        "e_cum": _clean(np.cumsum(df["e_hvac_kwh"].to_numpy(dtype=float))),
        "q_max": float(params.hvac_capacity_w),
        "band": [float(params.comfort_low_c), float(params.comfort_high_c)],
        "capacity": int(params.max_occupancy),
        "students": int(params.effective_occupancy),
        "shading": float(params.shading_fraction),
        "orientation": params.orientation,
        "orientation_label": ORIENTATION_AR[params.orientation],
        "strategy": strategy_key,
        "strategy_label": STRATEGY_NAMES_AR[strategy_key],
        "start_index": int(max(0, min(n - 1, start_index))),
        "kpi": {
            "energy_kwh": float(metrics.get("hvac_kwh", metrics["energy_kwh"])),  # الصفحة الأولى: طاقة التكييف
            "compliance": float(metrics["comfort_compliance"]),
            "violation_h": float(metrics["comfort_violation_h"]),
        },
        "labels": LABELS_AR,
    }


def _safe_json(obj) -> str:
    # يمنع إغلاق وسم <script> من داخل البيانات
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def render_html(state: dict, height_px: int = 640) -> str:
    """صفحة HTML ذاتية الاحتواء (CSS + JS مضمّنان، دون أي مورد خارجي)."""
    css = (HERE / "classroom3d.css").read_text(encoding="utf-8")
    js = (HERE / "classroom3d.js").read_text(encoding="utf-8")
    return (
        "<!doctype html><html lang=\"ar\"><head><meta charset=\"utf-8\">"
        f"<style>{css} #zl3d{{height:{int(height_px)}px}}</style></head><body>"
        "<div id=\"zl3d\"></div>"
        f"<script>window.ZILAL_STATE={_safe_json(state)};</script>"
        f"<script>{js}</script></body></html>"
    )
