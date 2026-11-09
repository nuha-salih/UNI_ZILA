"""
forecasting.py — التنبؤ الحراري الفيزيائي (يستخدمه التحكم التنبؤي D).

دحرجة نموذج RC للأمام بتوقعات الطقس والإشغال. افتراضياً تكون التوقعات مطابقة لبيانات
المحاكاة (توقع مثالي) — وهذا قيد موثّق. يمكن تمرير مدخلات توقع مختلفة (forecast_inp)
لمحاكاة أخطاء التوقع (انظر strategies.PredictiveStrategy و data_quality).

سجل التعديل: الدالتان الفيزيائيتان دون تغيير في المعادلات. أُزيل نموذج Random Forest
الأحادي (كان يستخدم تقسيماً عشوائياً) واستُبدل بوحدة zilal/ml.py (مقارنة RF و GB بتقسيم زمني).
"""
from __future__ import annotations

from .thermal_model import SimInputs, step_temperature


def free_float_forecast(t0: float, k: int, j: int, inp: SimInputs) -> float:
    """درجة الحرارة المتوقعة في بداية الخطوة j لو لم يعمل التبريد من الخطوة k (فيزيائي)."""
    p = inp.params
    c, ua, dt = p.capacitance_j_per_k, p.ua_w_per_k, p.dt_s
    t = t0
    for i in range(k, j):
        t = step_temperature(t, inp.t_out[i], inp.q_solar[i], inp.q_internal[i], 0.0, c, ua, dt)
    return t


def required_cooling_for_arrival(t0: float, k: int, j: int, target: float, inp: SimInputs) -> float:
    """
    قدرة تبريد ثابتة Q (W) من الخطوة k حتى j−1 تجعل T_j = target.
    النموذج خطي، لذا: T_j = T_free_j − (dt/C)·Q·Σ_{m=0}^{n−1}(1−a)^m ، a = dt·UA/C.
    قيمة موجبة = يلزم تبريد؛ سالبة/صفر = القاعة ستبقى ضمن الهدف دون تبريد.
    """
    p = inp.params
    c, ua, dt = p.capacitance_j_per_k, p.ua_w_per_k, p.dt_s
    n = j - k
    if n <= 0:
        return 0.0
    a = dt * ua / c
    s = (1.0 - (1.0 - a) ** n) / a
    t_free = free_float_forecast(t0, k, j, inp)
    return (t_free - target) * c / (dt * s)
