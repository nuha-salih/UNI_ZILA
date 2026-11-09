"""
strategies.py — استراتيجيات تشغيل التكييف. كلها تستخدم الآلية نفسها لتحديد قدرة التبريد
(طلب «يوصل الغرفة إلى الهدف خلال الخطوة» ثم يقيّده المحاكي بقدرة المكيّف)، فتختلف
النتائج بسبب *منطق القرار* فقط:

R — مرجعي تقليدي: ترموستات عند الهدف على مدار الساعة دون أي منطق ذكي. **خط الأساس الافتراضي للطاقة.**
A — جدول ثابت: يعمل يومياً (افتراضياً 06:00–18:00) بغض النظر عن الإشغال.
N — بدون تكييف (مرجع فيزيائي فقط): المكيّف مطفأ؛ يبيّن سلوك القاعة الحر وليس خياراً تشغيلياً.
B — حسب الجدول الدراسي: يعمل أثناء فترات الجدول المعلن فقط (بلا تبريد مسبق).
C — ذكي قائم على الإشغال (قواعد): يعمل عند الإشغال الفعلي وتجاوز الحرارة (هدف + هامش)، وعند
    خلو القاعة لا يبرّد إلا إذا تجاوزت الحرارة حداً وقائياً.
D — تنبؤي: يتنبأ بالحرارة بنموذج RC ويبدأ التبريد المسبق في أبعد لحظة تسمح بالوصول إلى الهدف
    عند حضور الطلاب؛ وأثناء الإشغال يستخدم هدفاً أعلى قليلاً داخل نطاق الراحة.
    آلية القرار: حلّ مغلق لقدرة التبريد الثابتة المطلوبة (forecasting.required_cooling_for_arrival).
    يفترض افتراضياً توقعاً مثالياً للطقس والإشغال؛ ويمكن تمرير توقع فيه أخطاء (forecast_inp).

الإنارة: R/A/B/N تستخدم جدول إنارة ثابتاً (تقليدي)، وC/D (ظِلال) تشغّل الإنارة حسب الإشغال.
سجل التعديل: A–D دون تغيير في منطق التكييف. أُضيف R و N، وهدف بديل اختياري (target_c) لتجارب
الإفراط في التبريد (R/A/B/C)، وغلاف قياس حساس مشوَّش (MeasuredStrategy)، ومدخلات توقع اختيارية لـ D.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .forecasting import required_cooling_for_arrival
from .thermal_model import SimInputs, cooling_to_target

STRATEGY_KEYS = ("R", "A", "B", "C", "D", "N")
OPERATIONAL_KEYS = ("R", "A", "B", "C", "D")  # N ليس خياراً تشغيلياً
BASELINE_KEY = "R"
STRATEGY_NAMES_AR = {
    "R": "مرجعي تقليدي (مستمر)",
    "N": "بدون تكييف (مرجع فيزيائي)",
    "A": "جدول ثابت 06–18",
    "B": "حسب الجدول الدراسي",
    "C": "ذكي حسب الإشغال (قواعد)",
    "D": "تنبؤي (نموذج RC)",
}
ZILAL_KEYS = ("C", "D")  # استراتيجيات ظِلال الذكية (تكييف + إنارة حسب الإشغال)
STRATEGY_LIGHTING = {"R": "schedule", "N": "schedule", "A": "schedule", "B": "schedule",
                     "C": "occupancy", "D": "occupancy"}
STRATEGY_SHORT_AR = {"R": "مرجعي", "N": "بدون تكييف", "A": "جدول ثابت", "B": "الجدول الدراسي",
                     "C": "حسب الإشغال", "D": "تنبؤي"}
STRATEGY_DESC_AR = {
    "R": "ترموستات مضبوط عند الهدف على مدار الساعة دون جدولة أو منطق ذكي؛ يمثّل التشغيل التقليدي ويُستخدم أساساً لحساب فروق الطاقة.",
    "N": "المكيّف مطفأ طوال اليوم. ليس خياراً تشغيلياً؛ يوضّح فقط كيف تتصرف القاعة حرارياً دون تبريد.",
    "A": "تشغيل يومي ثابت من بداية الدوام إلى نهايته بغض النظر عن الحضور. يمثّل جدولة زمنية بسيطة دون معرفة الإشغال.",
    "B": "يعمل أثناء فترات الجدول الدراسي المعلن فقط، دون تبريد مسبق ودون معرفة الحضور الفعلي.",
    "C": "يعمل عند وجود طلاب فعلياً وارتفاع الحرارة فوق الهدف + هامش، ويتوقف عند خلو القاعة (مع حد وقائي).",
    "D": "يتنبأ بالحرارة بالنموذج الفيزيائي ويبدأ التبريد المسبق في آخر وقت يضمن جاهزية القاعة عند الوصول.",
}


@dataclass
class StrategyConfig:
    fixed_on_h: float = 6.0
    fixed_off_h: float = 18.0
    deadband_c: float = 0.5  # C: التبريد يبدأ عند الهدف + الهامش
    unocc_limit_c: float = 32.0  # حد وقائي عند خلو القاعة (C و D)
    horizon_h: float = 8.0  # أفق التنبؤ لـ D
    predictive_offset_c: float = 0.5  # D: رفع الهدف أثناء الإشغال (داخل نطاق الراحة)
    start_frac: float = 0.85  # D: يبدأ التبريد المسبق عندما يبلغ المطلوب هذه النسبة من القدرة
    target_c: float | None = None  # هدف بديل لـ R/A/B/C (تجارب الإفراط في التبريد أو رفع الهدف)

    def validate(self) -> "StrategyConfig":
        if not (0 <= self.fixed_on_h < self.fixed_off_h <= 24):
            raise ValueError("ساعات التشغيل الثابت غير صالحة (يجب 0 ≤ بداية < نهاية ≤ 24).")
        if not (0 <= self.deadband_c <= 3):
            raise ValueError("هامش القواعد خارج [0, 3].")
        if not (20 <= self.unocc_limit_c <= 40):
            raise ValueError("الحد الوقائي لخلو القاعة خارج [20, 40].")
        if not (0.5 <= self.horizon_h <= 12):
            raise ValueError("أفق التنبؤ خارج [0.5, 12] ساعة.")
        if not (0 <= self.predictive_offset_c <= 2):
            raise ValueError("إزاحة الهدف التنبؤي خارج [0, 2].")
        if not (0.3 <= self.start_frac <= 1.0):
            raise ValueError("نسبة بدء التبريد المسبق خارج [0.3, 1].")
        if self.target_c is not None and not (16 <= self.target_c <= 30):
            raise ValueError("الهدف البديل خارج [16, 30] °م.")
        return self


def _demand(k: int, T: float, inp: SimInputs, target: float) -> float:
    p = inp.params
    return cooling_to_target(T, target, inp.t_out[k], inp.q_solar[k], inp.q_internal[k],
                             p.capacitance_j_per_k, p.ua_w_per_k, p.dt_s)


class _Base:
    key = "?"
    lighting_mode = "schedule"  # التشغيل التقليدي: جدول إنارة ثابت (ClassroomParams.lighting_on_h/off_h)

    def __init__(self, cfg: StrategyConfig | None = None):
        self.cfg = (cfg or StrategyConfig()).validate()

    def reset(self, inp: SimInputs) -> None:  # noqa: D401
        pass

    def _target(self, inp: SimInputs) -> float:
        return self.cfg.target_c if self.cfg.target_c is not None else inp.params.comfort_setpoint_c


class NoControlStrategy(_Base):
    key = "N"

    def decide(self, k, T, inp):
        return 0.0


class ContinuousStrategy(_Base):
    key = "R"

    def decide(self, k, T, inp):
        return _demand(k, T, inp, self._target(inp))


class FixedStrategy(_Base):
    key = "A"

    def decide(self, k, T, inp):
        if self.cfg.fixed_on_h <= inp.hours[k] < self.cfg.fixed_off_h:
            return _demand(k, T, inp, self._target(inp))
        return 0.0


class TimetableStrategy(_Base):
    key = "B"

    def decide(self, k, T, inp):
        if inp.timetable_on[k]:
            return _demand(k, T, inp, self._target(inp))
        return 0.0


class RuleBasedStrategy(_Base):
    key = "C"
    lighting_mode = "occupancy"  # ظِلال: الإنارة حسب الإشغال

    def reset(self, inp):
        self.active = False

    def decide(self, k, T, inp):
        sp = self._target(inp)
        if inp.occ[k] > 0:
            if T > sp + self.cfg.deadband_c:
                self.active = True
            elif T <= sp + 1e-9:
                self.active = False
            return _demand(k, T, inp, sp) if self.active else 0.0
        self.active = False
        if T > self.cfg.unocc_limit_c:
            return _demand(k, T, inp, self.cfg.unocc_limit_c)
        return 0.0


class PredictiveStrategy(_Base):
    key = "D"
    lighting_mode = "occupancy"  # ظِلال: الإنارة حسب الإشغال

    def __init__(self, cfg: StrategyConfig | None = None, forecast_inp: SimInputs | None = None):
        super().__init__(cfg)
        self.forecast_inp = forecast_inp

    def reset(self, inp):
        self.precooling = False
        if self.forecast_inp is not None and self.forecast_inp.n != inp.n:
            raise ValueError("مدخلات التوقع يجب أن تطابق طول نافذة المحاكاة.")

    def decide(self, k, T, inp):
        p, cfg = inp.params, self.cfg
        offset = min(cfg.predictive_offset_c, 0.8 * p.comfort_tolerance_c)
        target = p.comfort_setpoint_c + offset
        if inp.occ[k] > 0:
            self.precooling = False
            return _demand(k, T, inp, target)
        horizon_steps = int(cfg.horizon_h * 3600 / p.dt_s)
        fc = self.forecast_inp if self.forecast_inp is not None else inp
        j = int(fc.next_occ[k])
        if j != -1 and (j - k) <= horizon_steps:
            q_req = required_cooling_for_arrival(T, k, j, target, fc)
            if q_req >= cfg.start_frac * p.hvac_capacity_w:
                self.precooling = True
            if self.precooling and q_req > 0:
                return q_req
            self.precooling = False
        if T > cfg.unocc_limit_c:
            return _demand(k, T, inp, cfg.unocc_limit_c)
        return 0.0


class MeasuredStrategy:
    """
    غلاف يجعل الاستراتيجية تقرر بناءً على *قراءة حساس افتراضي* بدل الحرارة الحقيقية:
    T_measured = T + bias + N(0, sigma). الفيزياء نفسها تبقى على T الحقيقية.
    يُستخدم لتجربة ضوضاء الحساسات (لا يوجد اتصال بحساسات فعلية).
    """

    def __init__(self, base, sigma_c: float = 0.0, bias_c: float = 0.0, seed: int = 0):
        if sigma_c < 0:
            raise ValueError("الانحراف المعياري للضوضاء لا يمكن أن يكون سالباً.")
        self.base, self.sigma, self.bias, self.seed = base, float(sigma_c), float(bias_c), int(seed)
        self.key = getattr(base, "key", "?")
        self.lighting_mode = getattr(base, "lighting_mode", None)

    def reset(self, inp):
        self.base.reset(inp)
        rng = np.random.default_rng(self.seed)
        self.noise = rng.normal(0.0, self.sigma, inp.n) if self.sigma > 0 else np.zeros(inp.n)
        self.readings = np.full(inp.n, np.nan)

    def decide(self, k, T, inp):
        t_meas = T + self.bias + self.noise[k]
        self.readings[k] = t_meas
        return self.base.decide(k, t_meas, inp)


def make_strategy(key: str, cfg: StrategyConfig | None = None, forecast_inp: SimInputs | None = None):
    cfg = (cfg or StrategyConfig()).validate()
    classes = {"R": ContinuousStrategy, "N": NoControlStrategy, "A": FixedStrategy, "B": TimetableStrategy,
               "C": RuleBasedStrategy}
    if key == "D":
        return PredictiveStrategy(cfg, forecast_inp)
    if key not in classes:
        raise ValueError(f"استراتيجية غير معروفة: {key}")
    return classes[key](cfg)


def make_strategies(cfg: StrategyConfig | None = None, keys=STRATEGY_KEYS) -> dict:
    return {k: make_strategy(k, cfg) for k in keys}
