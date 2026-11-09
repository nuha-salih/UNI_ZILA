"""
ml.py — مقارنة Random Forest و Gradient Boosting (نماذج مدرّبة على بيانات محاكاة اصطناعية).

المهمة: التنبؤ بالقدرة الكهربائية للتكييف P_hvac (kW) لكل فترة 15 دقيقة لقاعة محددة
تحت استراتيجية محددة، باستخدام معلومات متاحة مسبقاً فقط (تخطيط اليوم التالي):
  • توقيت: sin/cos الساعة، يوم دراسي أم لا.
  • الطقس المتوقع: الحرارة الخارجية، إشعاع الواجهة، الحرارة الخارجية قبل ساعتين.
  • الجدول/الإشغال المخطط: عدد الطلاب الآن، وبعد ساعة، والدقائق حتى بداية الإشغال التالي.
  • ذاكرة: القدرة في الوقت نفسه من اليوم السابق (lag 96) — معلومة ماضية متاحة فعلاً.
لا تُستخدم الحرارة الداخلية ولا Q_cool الحالي (لمنع تسرب الهدف).

البيانات: 28 يوماً من الطقس الاصطناعي المتنوع + جدول دراسي اصطناعي (الأحد–الخميس)،
تُحاكى بمحرك RC نفسه. التقسيم زمني: أول 20 يوماً تدريب، آخر 8 أيام اختبار (بلا خلط).
خط أساس ساذج للمقارنة: «قيمة الأمس في الوقت نفسه».

تنبيه: الدقة هنا تقيس قدرة النموذج على تقليد المحاكي فقط، وليست دقة على قاعات حقيقية.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .engine.strategies import StrategyConfig, make_strategy
from .engine.thermal_model import ClassroomParams, build_sim_inputs, simulate
from .engine.weather import generate_variable_weather

SEED = 42
N_DAYS = 28
TRAIN_DAYS = 20
FEATURES = ["hour_sin", "hour_cos", "is_teaching_day", "t_out_c", "g_facade_wm2", "t_out_lag2h_c",
            "occ_now", "occ_next1h", "minutes_to_next_occ", "p_lag24h_kw"]
FEATURES_AR = {
    "hour_sin": "الساعة (sin)", "hour_cos": "الساعة (cos)", "is_teaching_day": "يوم دراسي",
    "t_out_c": "الحرارة الخارجية", "g_facade_wm2": "إشعاع الواجهة", "t_out_lag2h_c": "الحرارة الخارجية قبل ساعتين",
    "occ_now": "عدد الطلاب الآن", "occ_next1h": "عدد الطلاب بعد ساعة",
    "minutes_to_next_occ": "الدقائق حتى الإشغال التالي", "p_lag24h_kw": "قدرة الأمس في الوقت نفسه",
}
TARGET = "p_hvac_kw"
MODEL_NAMES_AR = {"rf": "Random Forest", "gb": "Gradient Boosting", "naive": "خط أساس: قيمة الأمس"}
SLOTS = [(8, 10), (10, 12), (12, 14), (14, 16)]


def synthetic_timetable(timestamps: pd.Series, capacity: int, seed: int = SEED) -> np.ndarray:
    """جدول اصطناعي حتمي: أيام الأحد–الخميس، 2–4 محاضرات يومياً بحضور 50–100٪ من السعة."""
    rng = np.random.default_rng(seed)
    ts = pd.to_datetime(timestamps)
    days = ts.dt.normalize()
    h = (ts.dt.hour + ts.dt.minute / 60.0).to_numpy()
    occ = np.zeros(len(ts), dtype=int)
    for d in days.unique():
        dow = pd.Timestamp(d).dayofweek  # Mon=0 … Sun=6
        if dow in (4, 5):  # الجمعة والسبت
            continue
        n = int(rng.integers(2, 5))
        chosen = rng.choice(len(SLOTS), size=n, replace=False)
        mask_day = (days == d).to_numpy()
        for c in chosen:
            s, e = SLOTS[c]
            att = int(round(capacity * rng.uniform(0.5, 1.0)))
            occ[mask_day & (h >= s) & (h < e)] = att
    return occ


def generate_dataset(params: ClassroomParams | None = None, strategy_key: str = "C",
                     days: int = N_DAYS, seed: int = SEED) -> pd.DataFrame:
    params = (params or ClassroomParams()).validate()
    w = generate_variable_weather(days=days, seed=seed)
    occ = synthetic_timetable(w["timestamp"], params.max_occupancy, seed)
    inp = build_sim_inputs(params, w, occupancy_series=occ, timetable_series=occ > 0)
    df = simulate(inp, make_strategy(strategy_key, StrategyConfig()))
    ts = pd.to_datetime(df["timestamp"])
    h = df["hour"].to_numpy()
    out = pd.DataFrame({"timestamp": ts})
    out["day_index"] = ((ts - ts.iloc[0].normalize()).dt.days).to_numpy()
    out["hour_sin"] = np.sin(2 * np.pi * h / 24)
    out["hour_cos"] = np.cos(2 * np.pi * h / 24)
    out["is_teaching_day"] = (~ts.dt.dayofweek.isin([4, 5])).astype(int).to_numpy()
    out["t_out_c"] = df["t_out"].to_numpy()
    out["g_facade_wm2"] = df["g_facade"].to_numpy()
    out["t_out_lag2h_c"] = pd.Series(df["t_out"].to_numpy()).shift(8).to_numpy()
    out["occ_now"] = occ
    out["occ_next1h"] = pd.Series(occ).shift(-4).fillna(0).to_numpy()  # من الجدول المخطط (معروف مسبقاً)
    nxt = inp.next_occ
    idx = np.arange(len(occ))
    mins = np.where(occ > 0, 0, np.where(nxt >= 0, (nxt - idx) * 15, 24 * 60))
    out["minutes_to_next_occ"] = np.minimum(mins, 24 * 60)
    out[TARGET] = df["p_hvac_kw"].to_numpy()
    out["p_lag24h_kw"] = pd.Series(out[TARGET]).shift(96).to_numpy()
    out["t_in_c"] = df["t_in"].to_numpy()  # للعرض فقط — ليس ميزة
    out["day_type"] = w["day_type"].to_numpy()
    out = out.dropna(subset=FEATURES).reset_index(drop=True)
    out.attrs.update(strategy=strategy_key, seed=seed, days=days)
    return out


def time_split(data: pd.DataFrame, train_days: int = TRAIN_DAYS):
    """تقسيم زمني: كل التدريب قبل أول عيّنة اختبار (لا خلط)."""
    train = data[data["day_index"] < train_days]
    test = data[data["day_index"] >= train_days]
    if train.empty or test.empty:
        raise ValueError("التقسيم الزمني أنتج مجموعة فارغة.")
    return train, test


def _metrics(y, p) -> dict:
    y, p = np.asarray(y, float), np.asarray(p, float)
    err = p - y
    ss_res = float(np.sum(err ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    return {"MAE_kW": float(np.mean(np.abs(err))), "RMSE_kW": float(np.sqrt(np.mean(err ** 2))),
            "R2": 1 - ss_res / ss_tot if ss_tot > 0 else float("nan"),
            "daily_energy_error_pct": float((p.sum() - y.sum()) / y.sum() * 100) if y.sum() > 0 else float("nan")}


def train_and_compare(params: ClassroomParams | None = None, strategy_key: str = "C",
                      seed: int = SEED, rf_trees: int = 200, gb_trees: int = 300) -> dict:
    from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor

    data = generate_dataset(params, strategy_key, seed=seed)
    train, test = time_split(data)
    Xtr, ytr, Xte, yte = train[FEATURES], train[TARGET], test[FEATURES], test[TARGET]
    models = {
        "rf": RandomForestRegressor(n_estimators=rf_trees, min_samples_leaf=2, random_state=seed, n_jobs=1),
        "gb": GradientBoostingRegressor(n_estimators=gb_trees, learning_rate=0.05, max_depth=3,
                                        subsample=0.9, random_state=seed),
    }
    preds, rows, importances = {}, {}, {}
    for k, m in models.items():
        m.fit(Xtr, ytr)
        preds[k] = np.clip(m.predict(Xte), 0, None)
        rows[k] = _metrics(yte, preds[k])
        importances[k] = pd.Series(m.feature_importances_, index=FEATURES)
    preds["naive"] = test["p_lag24h_kw"].to_numpy()
    rows["naive"] = _metrics(yte, preds["naive"])
    metrics = pd.DataFrame(rows).T
    metrics["model_ar"] = [MODEL_NAMES_AR[k] for k in metrics.index]
    pred_df = test[["timestamp", "day_index", "occ_now", "t_out_c", TARGET]].copy()
    for k, v in preds.items():
        pred_df[f"pred_{k}"] = v
    best = metrics.loc[["rf", "gb"], "MAE_kW"].idxmin()
    return {
        "data": data, "train": train, "test": test, "metrics": metrics, "predictions": pred_df,
        "importances": pd.DataFrame(importances).rename(index=FEATURES_AR), "models": models, "best": best,
        "split": {"train_start": train["timestamp"].min(), "train_end": train["timestamp"].max(),
                  "test_start": test["timestamp"].min(), "test_end": test["timestamp"].max(),
                  "n_train": len(train), "n_test": len(test)},
        "label_ar": "نماذج مدرّبة على بيانات محاكاة اصطناعية — ليست قياسات من قاعات الجامعة",
    }


def predict_day(result: dict, day_index: int, model_key: str) -> pd.DataFrame:
    """تنبؤ يوم كامل من فترة الاختبار مقارنة بقيمة المحاكي."""
    pr = result["predictions"]
    d = pr[pr["day_index"] == day_index]
    if d.empty:
        raise ValueError("اليوم المطلوب ليس ضمن فترة الاختبار.")
    return d[["timestamp", TARGET, f"pred_{model_key}", "occ_now", "t_out_c"]].rename(
        columns={TARGET: "simulated_kw", f"pred_{model_key}": "predicted_kw"})
