"""اختبارات تعلّم الآلة: التوليد الحتمي، التقسيم الزمني ومنع التسرب، التقييم المحسوب، المقارنة."""
import numpy as np
import pytest

from zilal import ml


@pytest.fixture(scope="module")
def result():
    return ml.train_and_compare(rf_trees=60, gb_trees=120)


def test_dataset_deterministic_and_synthetic():
    a = ml.generate_dataset(days=8)
    b = ml.generate_dataset(days=8)
    assert a[ml.FEATURES + [ml.TARGET]].equals(b[ml.FEATURES + [ml.TARGET]])
    assert a["occ_now"].max() <= 30
    weekend = a[a["is_teaching_day"] == 0]
    assert (weekend["occ_now"] == 0).all()


def test_features_exclude_target_and_indoor_state():
    for f in ml.FEATURES:
        assert f not in ("p_hvac_kw", "t_in_c", "q_cool_w")
    # الميزة الماضية الوحيدة المشتقة من الهدف متأخرة 96 خطوة (يوم كامل)
    d = ml.generate_dataset(days=6)
    full = d[ml.TARGET].to_numpy()
    lag = d["p_lag24h_kw"].to_numpy()
    np.testing.assert_allclose(lag[96:], full[:-96])


def test_time_split_no_leakage(result):
    tr, te = result["train"], result["test"]
    assert tr["timestamp"].max() < te["timestamp"].min()
    assert set(tr["day_index"]).isdisjoint(set(te["day_index"]))
    assert result["split"]["n_train"] + result["split"]["n_test"] == len(result["data"])


def test_metrics_are_computed_from_predictions(result):
    pr = result["predictions"]
    for k in ("rf", "gb", "naive"):
        err = pr[f"pred_{k}"] - pr[ml.TARGET]
        assert result["metrics"].loc[k, "MAE_kW"] == pytest.approx(np.abs(err).mean())
        assert result["metrics"].loc[k, "RMSE_kW"] == pytest.approx(np.sqrt((err ** 2).mean()))


def test_models_beat_naive_baseline_and_label(result):
    m = result["metrics"]
    assert m.loc["rf", "MAE_kW"] < m.loc["naive", "MAE_kW"]
    assert m.loc["gb", "MAE_kW"] < m.loc["naive", "MAE_kW"]
    assert result["best"] in ("rf", "gb")
    assert "محاكاة" in result["label_ar"]
    assert set(result["importances"].columns) == {"rf", "gb"}


def test_reproducible_training():
    a = ml.train_and_compare(rf_trees=20, gb_trees=30)["metrics"]
    b = ml.train_and_compare(rf_trees=20, gb_trees=30)["metrics"]
    assert a[["MAE_kW", "RMSE_kW"]].equals(b[["MAE_kW", "RMSE_kW"]])


def test_predict_day(result):
    d = int(result["test"]["day_index"].iloc[0])
    out = ml.predict_day(result, d, "rf")
    assert len(out) == 96 and {"simulated_kw", "predicted_kw"} <= set(out.columns)
    with pytest.raises(ValueError):
        ml.predict_day(result, 0, "rf")
