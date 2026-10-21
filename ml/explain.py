"""
ml/explain.py
SHAP feature importance, permutation importance, and single-prediction explanations.
"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import shap
from typing import Dict, List, Any
from sklearn.inspection import permutation_importance


def _get_model_feature_importances(model: Any, n_features: int) -> np.ndarray:
    """Extract feature importances from single models or StackingClassifier ensembles."""
    if hasattr(model, "feature_importances_"):
        return np.array(model.feature_importances_)
    elif hasattr(model, "coef_"):
        return np.mean(np.abs(model.coef_), axis=0)
    elif hasattr(model, "estimators_"):
        all_imps = []
        for est in model.estimators_:
            if hasattr(est, "feature_importances_"):
                fi = np.array(est.feature_importances_)
                if np.sum(fi) > 0:
                    all_imps.append(fi / np.sum(fi))
            elif hasattr(est, "coef_"):
                fi = np.mean(np.abs(est.coef_), axis=0)
                if np.sum(fi) > 0:
                    all_imps.append(fi / np.sum(fi))
        if all_imps:
            return np.mean(all_imps, axis=0)
    return np.ones(n_features) / n_features


def compute_shap_importance(
    model: Any,
    X_train: pd.DataFrame,
    X_test: pd.DataFrame,
    save_dir: str = "ml/results",
) -> Dict[str, Any]:
    """Compute SHAP feature importance and save summary plot."""
    os.makedirs(save_dir, exist_ok=True)

    sample_size = min(200, len(X_test))
    bg_size = min(200, len(X_train))
    sample_X = X_test.iloc[:sample_size]

    try:
        explainer = shap.Explainer(model, X_train.iloc[:bg_size])
        shap_values = explainer(sample_X)

        plt.figure(figsize=(12, 8))
        if hasattr(shap_values, "values"):
            if len(shap_values.values.shape) == 3:
                shap.summary_plot(shap_values.values[:, :, 1], sample_X, show=False, max_display=20)
            else:
                shap.summary_plot(shap_values, sample_X, show=False, max_display=20)
        plt.tight_layout()
        plt.savefig(os.path.join(save_dir, "shap_summary.png"), dpi=300, bbox_inches="tight")
        plt.close()

        if len(shap_values.values.shape) == 3:
            mean_abs_shap = np.mean(np.abs(shap_values.values), axis=(0, 2))
        else:
            mean_abs_shap = np.mean(np.abs(shap_values.values), axis=0)

        feature_importance = pd.Series(mean_abs_shap, index=X_test.columns).sort_values(ascending=False)

    except Exception as e:
        print(f"[ml/explain.py] SHAP fallback: {e}")
        imps = _get_model_feature_importances(model, X_test.shape[1])
        feature_importance = pd.Series(imps, index=X_test.columns).sort_values(ascending=False)

    # Save feature importance CSV
    feature_importance.to_csv(os.path.join(save_dir, "feature_importance.csv"), header=["importance"])
    print(f"  Top-10 features: {list(feature_importance.head(10).index)}")

    return {
        "top_features": feature_importance.head(10).to_dict(),
        "feature_importance_series": feature_importance,
    }


def compute_permutation_importance(
    model: Any,
    X_test: pd.DataFrame,
    y_test: np.ndarray,
    save_dir: str = "ml/results",
    n_repeats: int = 10,
) -> pd.Series:
    """
    Compute and save permutation importance.

    Permutation importance measures how much each feature actually contributes
    to model predictions by shuffling feature values and measuring accuracy drop.

    Args:
        model: Trained classifier.
        X_test: Test feature matrix.
        y_test: Ground-truth labels.
        save_dir: Output directory.
        n_repeats: Number of permutation repeats.

    Returns:
        pd.Series of permutation importance values sorted descending.
    """
    os.makedirs(save_dir, exist_ok=True)

    result = permutation_importance(
        model, X_test, y_test,
        n_repeats=n_repeats,
        scoring="f1_weighted",
        random_state=42,
        n_jobs=-1,
    )

    perm_imp = pd.Series(result.importances_mean, index=X_test.columns).sort_values(ascending=False)
    perm_std = pd.Series(result.importances_std, index=X_test.columns)

    # Save CSV
    perm_df = pd.DataFrame({
        "importance_mean": perm_imp,
        "importance_std": perm_std.reindex(perm_imp.index),
    })
    perm_df.to_csv(os.path.join(save_dir, "permutation_importance.csv"))

    # Plot top-20
    top_n = min(20, len(perm_imp))
    top_features = perm_imp.head(top_n)
    top_std = perm_std.reindex(top_features.index)

    fig, ax = plt.subplots(figsize=(10, 7))
    y_pos = np.arange(top_n)
    ax.barh(y_pos, top_features.values[::-1], xerr=top_std.values[::-1],
            color="#2563eb", alpha=0.85, capsize=3)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(top_features.index[::-1], fontsize=9)
    ax.set_xlabel("Mean Importance (F1 drop)", fontsize=12)
    ax.set_title("Permutation Feature Importance (Top 20)", fontsize=14, fontweight="bold")
    ax.grid(axis="x", alpha=0.2)
    plt.tight_layout()
    plt.savefig(os.path.join(save_dir, "permutation_importance.png"), dpi=300, bbox_inches="tight")
    plt.close()

    print(f"  Permutation importance saved. Top-5: {list(perm_imp.head(5).index)}")
    return perm_imp


def explain_single_prediction(
    model: Any, feature_dict: Dict[str, float], feature_names: List[str]
) -> List[Dict[str, Any]]:
    """Extract top-5 most influential features for an individual prediction."""
    X_single = pd.DataFrame([feature_dict])[feature_names]

    imps = _get_model_feature_importances(model, len(feature_names))

    top_indices = np.argsort(imps)[::-1][:5]

    explanation = []
    for idx in top_indices:
        feat_name = feature_names[idx]
        val = float(X_single[feat_name].values[0])
        imp = float(imps[idx])
        explanation.append({
            "feature": feat_name,
            "value": round(val, 4),
            "importance_score": round(imp, 4),
        })

    return explanation
