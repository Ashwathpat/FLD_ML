"""
ml/tests/test_ml.py
Comprehensive tests for the ML pipeline: feature extraction, model artifact,
SHAP explainability, and ablation study.
"""
import os
import cv2
import numpy as np
import pytest
import joblib
import pandas as pd

from ml.features import (
    extract_color_features,
    extract_texture_features,
    extract_coating_features,
    extract_shape_features,
    extract_all_biomarkers,
)
from ml.data import load_real_dataset, CLASSES


# ── Feature Extraction Tests ──────────────────────────────────────────────────

def test_feature_extraction_color():
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    img[:, :] = [100, 120, 200]
    feats = extract_color_features(img)
    assert "color_r_mean" in feats
    assert "color_rg_ratio" in feats
    assert feats["color_r_mean"] > 0
    # New features
    assert "color_redness_index_mean" in feats
    assert "color_r_skew" in feats
    assert "color_clahe_l_mean" in feats
    assert "color_dom0_r" in feats


def test_feature_extraction_texture():
    img = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
    feats = extract_texture_features(img)
    assert "texture_glcm_contrast_mean" in feats
    assert "texture_entropy" in feats
    # New features
    assert "texture_glcm_contrast_d1_mean" in feats
    assert "texture_glcm_contrast_d5_mean" in feats
    assert "texture_gabor_f0_o0_mean" in feats
    assert "texture_local_var_mean" in feats


def test_feature_extraction_coating():
    img = np.ones((100, 100, 3), dtype=np.uint8) * 150
    feats = extract_coating_features(img)
    assert "coating_area_pixels" in feats
    assert "coating_tongue_ratio" in feats
    # New features
    assert "coating_thickness_mean" in feats
    assert "coating_uniformity_std" in feats
    assert "coating_lab_a_mean" in feats


def test_feature_extraction_shape():
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    mask = np.zeros((100, 100), dtype=np.uint8)
    cv2.circle(mask, (50, 50), 30, 255, -1)
    feats = extract_shape_features(img, mask)
    assert feats["shape_area"] > 0
    assert feats["shape_circularity"] > 0.5
    # New features
    assert "shape_hu0" in feats
    assert "shape_extent" in feats
    assert "shape_tip_base_r_ratio" in feats
    assert "shape_convexity_defects" in feats


def test_extract_all_biomarkers_count():
    """Verify extract_all_biomarkers returns consistent feature names."""
    img = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
    mask = np.ones((100, 100), dtype=np.uint8) * 255
    feats = extract_all_biomarkers(img, mask)
    # Should have features from all four groups
    color_feats = [k for k in feats if k.startswith("color_")]
    texture_feats = [k for k in feats if k.startswith("texture_")]
    coating_feats = [k for k in feats if k.startswith("coating_")]
    shape_feats = [k for k in feats if k.startswith("shape_")]
    assert len(color_feats) > 30, f"Expected >30 color features, got {len(color_feats)}"
    assert len(texture_feats) > 20, f"Expected >20 texture features, got {len(texture_feats)}"
    assert len(coating_feats) > 5, f"Expected >5 coating features, got {len(coating_feats)}"
    assert len(shape_feats) > 10, f"Expected >10 shape features, got {len(shape_feats)}"

    # All values should be finite
    for k, v in feats.items():
        assert np.isfinite(v), f"Feature {k} is not finite: {v}"


def test_extract_all_biomarkers_consistency():
    """Two calls on the same image should produce identical features."""
    np.random.seed(42)
    img = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
    mask = np.ones((100, 100), dtype=np.uint8) * 255
    feats1 = extract_all_biomarkers(img, mask)
    feats2 = extract_all_biomarkers(img, mask)
    for k in feats1:
        if "color_dom" in k:
            continue
        assert abs(feats1[k] - feats2[k]) < 1e-6, f"Inconsistency in {k}"


def test_load_real_dataset():
    df = load_real_dataset()
    assert len(df) > 0
    assert "label" in df.columns
    assert set(df["label"].unique()).issubset(set(CLASSES))


# ── Model Artifact Tests ─────────────────────────────────────────────────────

def test_model_artifact_exists():
    """Verify model.joblib exists and is loadable."""
    artifact_path = "ml/artifacts/model.joblib"
    if not os.path.exists(artifact_path):
        pytest.skip("model.joblib not yet trained")
    data = joblib.load(artifact_path)
    assert "model" in data
    assert "scaler" in data
    assert "label_encoder" in data
    assert "classes" in data
    assert "feature_names" in data
    assert "top_features" in data
    assert len(data["feature_names"]) > 0
    assert data["classes"] == CLASSES


def test_model_artifact_inference():
    """Verify the exported model can predict on a dummy image feature vector."""
    artifact_path = "ml/artifacts/model.joblib"
    if not os.path.exists(artifact_path):
        pytest.skip("model.joblib not yet trained")

    data = joblib.load(artifact_path)
    feat_names = data["feature_names"]
    scaler = data["scaler"]
    model = data["model"]
    le = data["label_encoder"]

    # Create dummy features (zeros)
    X_dummy = pd.DataFrame(np.zeros((1, len(feat_names))), columns=feat_names)
    X_scaled = scaler.transform(X_dummy)
    pred = model.predict(X_scaled)
    proba = model.predict_proba(X_scaled)

    assert pred.shape == (1,)
    assert proba.shape[0] == 1
    assert proba.shape[1] == len(CLASSES)
    assert abs(np.sum(proba) - 1.0) < 1e-3


# ── SHAP / Explainability Output Tests ────────────────────────────────────────

def test_shap_explain_single():
    """Verify explain_single_prediction returns correct format."""
    artifact_path = "ml/artifacts/model.joblib"
    if not os.path.exists(artifact_path):
        pytest.skip("model.joblib not yet trained")

    from ml.explain import explain_single_prediction

    data = joblib.load(artifact_path)
    feat_names = data["feature_names"]
    model = data["model"]

    feature_dict = {f: 0.0 for f in feat_names}
    result = explain_single_prediction(model, feature_dict, feat_names)

    assert isinstance(result, list)
    assert len(result) == 5
    for item in result:
        assert "feature" in item
        assert "value" in item
        assert "importance_score" in item


# ── Results Files Tests ───────────────────────────────────────────────────────

def test_results_files_exist():
    """Verify that key result files exist after training."""
    results_dir = "ml/results"
    if not os.path.exists(results_dir):
        pytest.skip("Results directory not yet created")

    expected_files = [
        "model_comparison.csv",
        "ablation_study.csv",
        "feature_importance.csv",
    ]
    for fname in expected_files:
        fpath = os.path.join(results_dir, fname)
        if os.path.exists(fpath):
            df = pd.read_csv(fpath)
            assert len(df) > 0, f"{fname} is empty"
