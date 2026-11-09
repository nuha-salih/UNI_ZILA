"""
campus.py — الحرم الجامعي التجريبي: جامعة → مبانٍ → أدوار → قاعات (بيانات اصطناعية بالكامل).

كل المباني والقاعات وأوضاع التشغيل هنا *افتراضية لأغراض العرض*، ولا تمثّل مباني أو قاعات
حقيقية في جامعة نجران. القاعة المرجعية المعتمدة: 60 م²، 30 طالباً.

«الوضع التشغيلي التجريبي» لكل قاعة (استراتيجية + تظليل + هدف) حالة اصطناعية تُستخدم بشكل
موحّد في لوحة المعلومات والتحليلات وتحدي ظِلال والتقارير، وكلها تُحسب بالمحرك نفسه.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .engine.evaluation import compute_metrics
from .engine.strategies import StrategyConfig, make_strategy
from .engine.thermal_model import ClassroomParams, build_sim_inputs, simulate
from .engine.weather import generate_weather_profile, slice_weather

CAMPUS_NAME_AR = "الحرم الجامعي التجريبي"
CAMPUS_DAY = "2025-07-14"  # يوم دراسي صيفي اصطناعي (ملف «typical»)
REFERENCE_ROOM = "ENG-101"
# التشغيل التقليدي المعتمد في كل صفحات المنصة: تكييف بجدول ثابت 06:00–18:00 عند هدف 24 °م،
# وإنارة بجدول ثابت (افتراضياً 07:00–18:00)، بتظليل القاعة نفسه وظروفها نفسها.
CONVENTIONAL_KEY = "A"
COMFORT_THRESHOLD = 0.95  # حد الراحة المقبولة الموحّد (نسبة ساعات الإشغال داخل النطاق)
FLOOR_AR = {0: "الدور الأرضي", 1: "الدور الأول", 2: "الدور الثاني", 3: "الدور الثالث"}


@dataclass(frozen=True)
class OperatingMode:
    strategy: str
    shading: float
    target_c: float | None = None  # None = هدف الراحة الافتراضي (24 °م)
    note_ar: str = ""


@dataclass(frozen=True)
class Classroom:
    room_id: str
    name_ar: str
    building_id: str
    floor: int
    area_m2: float
    capacity: int
    window_area_m2: float
    orientation: str
    ua_w_per_k_m2: float
    capacitance_j_per_k_m2: float
    equipment_w: float
    occupancy_blocks: tuple
    timetable_blocks: tuple
    attendance: float  # نسبة الحضور الفعلي من السعة أثناء المحاضرات (افتراض)
    mode: OperatingMode
    shgc: float = 0.60

    def params(self, **overrides) -> ClassroomParams:
        base = dict(
            area_m2=self.area_m2, max_occupancy=self.capacity,
            occupancy=int(round(self.capacity * self.attendance)),
            window_area_m2=self.window_area_m2, orientation=self.orientation,
            shading_fraction=self.mode.shading, shgc=self.shgc,
            ua_w_per_k_m2=self.ua_w_per_k_m2, capacitance_j_per_k_m2=self.capacitance_j_per_k_m2,
            equipment_w=self.equipment_w, hvac_capacity_w=250.0 * self.area_m2,
        )
        base.update(overrides)
        return ClassroomParams(**base).validate()

    @property
    def floor_ar(self) -> str:
        return FLOOR_AR.get(self.floor, f"الدور {self.floor}")


@dataclass(frozen=True)
class Building:
    building_id: str
    name_ar: str
    use_ar: str
    floors_total: int
    rooms: tuple = field(default_factory=tuple)


def _room(room_id, name, b, floor, area, cap, win, ori, ua, cap_j, eq, occ, tt, att, mode, shgc=0.60):
    return Classroom(room_id, name, b, floor, area, cap, win, ori, ua, cap_j, eq, tuple(occ), tuple(tt), att, mode, shgc)


# ملاحظات الافتراضات: الدور العلوي له UA أعلى (سقف معرّض للشمس)، الأرضي سعة حرارية أعلى قليلاً.
ROOMS = (
    _room("ENG-G01", "قاعة G01", "B1", 0, 60, 30, 10.0, "East", 3.0, 165_000, 300,
          [(8, 10), (10, 12)], [(8, 12)], 0.9,
          OperatingMode("A", 0.0, note_ar="جدول ثابت دون تظليل")),
    _room("ENG-101", "قاعة 101 (المرجعية)", "B1", 1, 60, 30, 12.0, "West", 3.4, 150_000, 300,
          [(9, 11), (13, 15)], [(9, 11), (13, 15)], 1.0,
          OperatingMode("D", 0.5, note_ar="تحكم تنبؤي + تظليل 50٪")),
    _room("ENG-201", "قاعة 201", "B1", 2, 72, 36, 14.0, "South", 4.2, 140_000, 400,
          [(8, 10), (12, 14)], [(8, 10), (12, 16)], 0.85,
          OperatingMode("D", 0.3, note_ar="تحكم تنبؤي + تظليل 30٪")),
    _room("CS-101", "قاعة 101", "B2", 1, 48, 24, 9.0, "West", 3.4, 150_000, 1200,
          [(10, 12)], [(8, 14)], 0.9,
          OperatingMode("B", 0.0, note_ar="حسب الجدول؛ معمل حاسب بأجهزة أكثر")),
    _room("CS-102", "قاعة 102", "B2", 1, 60, 30, 12.0, "South", 3.4, 150_000, 300,
          [(8, 10), (11, 13), (14, 16)], [(8, 16)], 0.8,
          OperatingMode("D", 0.6, note_ar="تحكم تنبؤي + تظليل 60٪")),
    _room("CS-201", "قاعة 201", "B2", 2, 90, 45, 16.0, "East", 4.0, 140_000, 450,
          [(8, 11), (12, 14)], [(8, 11), (12, 14)], 0.75,
          OperatingMode("C", 0.0, note_ar="تحكم حسب الإشغال دون تظليل")),
    _room("SCI-G01", "قاعة G01", "B3", 0, 60, 30, 12.0, "East", 3.0, 165_000, 300,
          [(9, 12), (13, 15)], [(9, 12), (13, 15)], 1.0,
          OperatingMode("C", 0.0, target_c=27.0, note_ar="ترشيد صارم: هدف 27 °م (خارج نطاق الراحة)")),
    _room("SCI-104", "قاعة 104", "B3", 1, 72, 36, 18.0, "West", 3.4, 150_000, 300,
          [(8, 10), (12, 15)], [(8, 16)], 0.9,
          OperatingMode("R", 0.0, note_ar="تشغيل تقليدي مستمر، نافذة غربية كبيرة")),
)

BUILDINGS = (
    Building("B1", "المبنى التجريبي (أ)", "قاعات دراسية — نمط كليات هندسية", 3,
             tuple(r.room_id for r in ROOMS if r.building_id == "B1")),
    Building("B2", "المبنى التجريبي (ب)", "قاعات ومعامل حاسب", 3,
             tuple(r.room_id for r in ROOMS if r.building_id == "B2")),
    Building("B3", "المبنى التجريبي (ج)", "قاعات علوم", 2,
             tuple(r.room_id for r in ROOMS if r.building_id == "B3")),
)

ROOM_BY_ID = {r.room_id: r for r in ROOMS}
BUILDING_BY_ID = {b.building_id: b for b in BUILDINGS}


# ---------------------------------------------------------------------------
# Cascading selection helpers
# ---------------------------------------------------------------------------
def floors_of(building_id: str) -> list[int]:
    return sorted({r.floor for r in ROOMS if r.building_id == building_id})


def rooms_of(building_id: str, floor: int | None = None) -> list[Classroom]:
    return [r for r in ROOMS if r.building_id == building_id and (floor is None or r.floor == floor)]


def campus_table() -> pd.DataFrame:
    rows = []
    for r in ROOMS:
        b = BUILDING_BY_ID[r.building_id]
        rows.append({"room_id": r.room_id, "room": r.name_ar, "building_id": b.building_id, "building": b.name_ar,
                     "floor": r.floor, "floor_ar": r.floor_ar, "area_m2": r.area_m2, "capacity": r.capacity,
                     "window_m2": r.window_area_m2, "orientation": r.orientation,
                     "strategy": r.mode.strategy, "shading": r.mode.shading,
                     "target_c": r.mode.target_c, "mode_note": r.mode.note_ar})
    return pd.DataFrame(rows)


def campus_counts() -> dict:
    return {"buildings": len(BUILDINGS),
            "floors": sum(b.floors_total for b in BUILDINGS),
            "floors_modeled": sum(len(floors_of(b.building_id)) for b in BUILDINGS),
            "classrooms": len(ROOMS),
            "area_m2": float(sum(r.area_m2 for r in ROOMS)),
            "seats": int(sum(r.capacity for r in ROOMS))}


# ---------------------------------------------------------------------------
# Simulation of the demonstration campus day
# ---------------------------------------------------------------------------
def campus_weather_day(profile: str = "typical") -> pd.DataFrame:
    w = generate_weather_profile(profile, start=CAMPUS_DAY)
    return slice_weather(w, pd.Timestamp(CAMPUS_DAY).date(), 24)


def simulate_room(room: Classroom, strategy: str | None = None, shading: float | None = None,
                  target_c: float | None = "mode", weather_day: pd.DataFrame | None = None,
                  cop: float | None = None):
    """
    يحاكي القاعة يوماً كاملاً. القيم الافتراضية = الوضع التشغيلي التجريبي للقاعة.
    target_c="mode" يعني هدف الوضع (قد يكون None = هدف الراحة).
    """
    key = strategy or room.mode.strategy
    over = {}
    if shading is not None:
        over["shading_fraction"] = float(shading)
    if cop is not None:
        over["cop"] = float(cop)
    p = room.params(**over)
    tgt = room.mode.target_c if target_c == "mode" else target_c
    cfg = StrategyConfig(target_c=tgt)
    w = weather_day if weather_day is not None else campus_weather_day()
    inp = build_sim_inputs(p, w, room.occupancy_blocks, room.timetable_blocks)
    df = simulate(inp, make_strategy(key, cfg))
    m = compute_metrics(df, p, inp)
    m.update({"room_id": room.room_id, "building_id": room.building_id, "floor": room.floor,
              "area_m2": room.area_m2, "capacity": room.capacity, "strategy": key})
    return df, m


def simulate_campus(strategy_override: str | None = None, weather_profile: str = "typical",
                    cop: float | None = None, include_reference: bool = True) -> dict:
    """
    يحاكي كل القاعات بوضعها التجريبي (أو باستراتيجية موحّدة). يضيف لكل قاعة طاقة التشغيل التقليدي
    (CONVENTIONAL_KEY) تحت الظروف نفسها (للتطبيع العادل في التحدي والتحليلات). يعيد {'metrics': DataFrame, 'series': dict}.
    """
    w = campus_weather_day(weather_profile)
    rows, series = [], {}
    for r in ROOMS:
        tgt = "mode" if strategy_override is None else None
        df, m = simulate_room(r, strategy=strategy_override, target_c=tgt, weather_day=w, cop=cop)
        if include_reference:
            # المرجع: التشغيل التقليدي للقاعة نفسها (جدول ثابت عند 24 °م، إنارة بجدول) بتظليلها نفسه
            # وبنفس الطقس والإشغال والخصائص و COP — يختلف التحكم فقط
            _, mref = simulate_room(r, strategy=CONVENTIONAL_KEY, target_c=None, weather_day=w, cop=cop)
            m["reference_energy_kwh"] = mref["energy_kwh"]
            m["reference_hvac_kwh"] = mref["hvac_kwh"]
            m["reference_lighting_kwh"] = mref["lighting_kwh"]
            m["reference_compliance"] = mref["comfort_compliance"]
        rows.append(m)
        series[r.room_id] = df
    return {"metrics": pd.DataFrame(rows).set_index("room_id"), "series": series, "weather": w}


def room_inputs(room: Classroom, weather_day: pd.DataFrame | None = None, **overrides):
    """مدخلات المحاكاة للقاعة بوضعها التشغيلي (الجدول والحضور والتظليل) — المصدر نفسه للوحة والقاعة 3D."""
    p = room.params(**overrides)
    w = weather_day if weather_day is not None else campus_weather_day()
    return p, build_sim_inputs(p, w, room.occupancy_blocks, room.timetable_blocks)


def room_comparison(room: Classroom, zilal_key: str = "D", weather_day: pd.DataFrame | None = None, **overrides) -> dict:
    """التقليدي (CONVENTIONAL_KEY) مقابل استراتيجية ظِلال على SimInputs واحد، بشكل يقبله جسر القاعة 3D."""
    from .engine.evaluation import compare_strategies
    p, inp = room_inputs(room, weather_day, **overrides)
    keys = tuple(dict.fromkeys((CONVENTIONAL_KEY, "C", "D", zilal_key)))
    results, summary = compare_strategies(inp, StrategyConfig(), keys=keys, baseline_key=CONVENTIONAL_KEY)
    return {"results": results, "summary": summary, "params": p, "inputs": inp}


def default_zilal_key(room: Classroom) -> str:
    """استراتيجية ظِلال المعروضة افتراضياً: وضع القاعة إن كان ظِلال بهدف الراحة، وإلا التنبؤي."""
    return room.mode.strategy if room.mode.strategy in ("C", "D") and room.mode.target_c is None else "D"
