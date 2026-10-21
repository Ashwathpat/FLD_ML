"""
ml/train.py
Full ML training pipeline for Tongue-FLD binary classification.
- Trains LR, SVM, RF, GradientBoosting, XGBoost + Stacking Ensemble.
- Cross-validation with mean ± std reporting.
- Feature selection (drop zero-variance + low-importance features).
- Hyperparameter tuning via RandomizedSearchCV on best model.
- Exports best model artifact to ml/artifacts/model.joblib.
"""
import os
import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.linear_model import LogisticRegression
from sklearn.svm import SVC
from sklearn.ensemble import (
    RandomForestClassifier,
    GradientBoostingClassifier,
    StackingClassifier,
)
from sklearn.model_selection import (
    RandomizedSearchCV,
    StratifiedKFold,
    cross_val_score,
)
from sklearn.feature_selection import VarianceThreshold
from xgboost import XGBClassifier

from ml.data import load_real_dataset, get_train_val_test_splits, CLASSES
from ml.evaluate import (
    compute_evaluation_metrics,
    plot_and_save_confusion_matrix,
    plot_roc_curve,
    plot_precision_recall,
    plot_combined_roc,
    plot_ablation_bar_chart,
    plot_cv_boxplot,
    save_classification_report,
)
from ml.explain import compute_shap_importance, compute_permutation_importance
from ml.ablation import run_ablation_study


def _select_features(train_df, val_df, test_df, feature_cols):
    """
    Remove zero-variance features and return filtered DataFrames.
    """
    selector = VarianceThreshold(threshold=0.0)
    selector.fit(train_df[feature_cols])
    kept = train_df[feature_cols].columns[selector.get_support()].tolist()
    dropped = len(feature_cols) - len(kept)
    if dropped:
        print(f"  Feature selection: dropped {dropped} zero-variance features, {len(kept)} remaining.")
    return kept


def train_and_evaluate_all(use_real: bool = True, tune: bool = True):
    """
    Full ML pipeline: data → multi-model training → CV → tuning → ablation
    → SHAP → permutation importance → export.

    Args:
        use_real: If True, use real Tongue-FLD dataset.
        tune: If True, run hyperparameter tuning on the best model.
    """
    results_dir = "ml/results"
    artifacts_dir = "ml/artifacts"
    os.makedirs(results_dir, exist_ok=True)
    os.makedirs(artifacts_dir, exist_ok=True)

    # ================================================================
    # 1. Load data
    # ================================================================
    print("\n" + "=" * 70)
    print("  PHASE 1: DATA LOADING")
    print("=" * 70)

    if use_real:
        df = load_real_dataset()
    else:
        from ml.data import load_real_dataset as _lr
        df = _lr()

    train_df, val_df, test_df = get_train_val_test_splits(df)
    feature_cols = [c for c in df.columns if c != "label"]

    print(f"Train: {len(train_df)} | Val: {len(val_df)} | Test: {len(test_df)}")
    print(f"Features: {len(feature_cols)}")

    le = LabelEncoder()
    y_train = le.fit_transform(train_df["label"])
    y_val = le.transform(val_df["label"])
    y_test = le.transform(test_df["label"])

    # Feature selection
    feature_cols = _select_features(train_df, val_df, test_df, feature_cols)

    scaler = StandardScaler()
    X_train = pd.DataFrame(
        scaler.fit_transform(train_df[feature_cols]), columns=feature_cols
    )
    X_val = pd.DataFrame(scaler.transform(val_df[feature_cols]), columns=feature_cols)
    X_test = pd.DataFrame(scaler.transform(test_df[feature_cols]), columns=feature_cols)

    # Class imbalance ratio for XGBoost
    n_neg = np.sum(y_train == 0)
    n_pos = np.sum(y_train == 1)
    scale_pos = n_neg / max(n_pos, 1)

    # ================================================================
    # 2. Define Models (with class imbalance handling)
    # ================================================================
    print("\n" + "=" * 70)
    print("  PHASE 2: MODEL TRAINING & EVALUATION")
    print("=" * 70)

    models = {
        "LogisticRegression": LogisticRegression(
            max_iter=2000, random_state=42, class_weight="balanced", C=1.0
        ),
        "SVM": SVC(
            probability=True, random_state=42, class_weight="balanced", C=1.0
        ),
        "RandomForest": RandomForestClassifier(
            n_estimators=200, random_state=42, class_weight="balanced",
            max_depth=None, min_samples_split=5
        ),
        "GradientBoosting": GradientBoostingClassifier(
            n_estimators=200, random_state=42, learning_rate=0.1,
            max_depth=5, min_samples_split=5, subsample=0.8,
        ),
        "XGBoost": XGBClassifier(
            n_estimators=200, random_state=42, eval_metric="logloss",
            scale_pos_weight=scale_pos, learning_rate=0.1, max_depth=6
        ),
    }

    model_performance = []
    best_model_name = None
    best_f1 = -1.0
    best_model_obj = None
    cv_results_all: dict = {}
    test_probas_all: dict = {}

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

    for name, model in models.items():
        print(f"\n  Training {name}...")

        # Cross-validation
        cv_scores = cross_val_score(
            model, X_train, y_train, cv=cv, scoring="f1_weighted", n_jobs=-1
        )
        cv_results_all[name] = cv_scores.tolist()
        print(f"    CV F1: {cv_scores.mean():.4f} ± {cv_scores.std():.4f}")

        model.fit(X_train, y_train)

        # Validation
        val_preds = model.predict(X_val)
        val_probas = model.predict_proba(X_val)
        val_metrics = compute_evaluation_metrics(y_val, val_preds, val_probas, CLASSES)
        val_metrics["model"] = name
        val_metrics["split"] = "validation"
        val_metrics["cv_f1_mean"] = float(cv_scores.mean())
        val_metrics["cv_f1_std"] = float(cv_scores.std())
        model_performance.append(val_metrics)

        # Test
        test_preds = model.predict(X_test)
        test_probas = model.predict_proba(X_test)
        test_metrics = compute_evaluation_metrics(y_test, test_preds, test_probas, CLASSES)
        test_metrics["model"] = name
        test_metrics["split"] = "test"
        model_performance.append(test_metrics)

        test_probas_all[name] = {"y_proba": test_probas}

        print(
            f"  {name:20s} | Val F1: {val_metrics['f1_weighted']:.4f} "
            f"| Test F1: {test_metrics['f1_weighted']:.4f} "
            f"| Test Acc: {test_metrics['accuracy']:.4f} "
            f"| AUC: {test_metrics['roc_auc']:.4f}"
        )

        # Confusion matrix
        cm_path = os.path.join(results_dir, f"cm_{name.lower()}.png")
        plot_and_save_confusion_matrix(y_test, test_preds, CLASSES, cm_path, title=f"Confusion Matrix ({name})")

        # ROC curve
        roc_path = os.path.join(results_dir, f"roc_{name.lower()}.png")
        plot_roc_curve(y_test, test_probas, CLASSES, roc_path, title=f"ROC Curve ({name})")

        # Precision-recall curve
        pr_path = os.path.join(results_dir, f"pr_{name.lower()}.png")
        plot_precision_recall(y_test, test_probas, pr_path, title=f"Precision-Recall ({name})")

        # Classification report
        report_path = os.path.join(results_dir, f"report_{name.lower()}.txt")
        save_classification_report(y_test, test_preds, CLASSES, report_path)

        if val_metrics["f1_weighted"] > best_f1:
            best_f1 = val_metrics["f1_weighted"]
            best_model_name = name
            best_model_obj = model

    # ================================================================
    # 2b. Stacking Ensemble
    # ================================================================
    print("\n  Training StackingEnsemble...")

    stack = StackingClassifier(
        estimators=[
            ("lr", LogisticRegression(max_iter=2000, random_state=42, class_weight="balanced")),
            ("rf", RandomForestClassifier(n_estimators=200, random_state=42, class_weight="balanced")),
            ("xgb", XGBClassifier(
                n_estimators=200, random_state=42, eval_metric="logloss",
                scale_pos_weight=scale_pos, learning_rate=0.1, max_depth=6
            )),
        ],
        final_estimator=LogisticRegression(max_iter=2000, random_state=42),
        cv=5,
        n_jobs=-1,
        passthrough=False,
    )

    stack_cv = cross_val_score(stack, X_train, y_train, cv=cv, scoring="f1_weighted", n_jobs=-1)
    cv_results_all["StackingEnsemble"] = stack_cv.tolist()
    print(f"    CV F1: {stack_cv.mean():.4f} ± {stack_cv.std():.4f}")

    stack.fit(X_train, y_train)

    stack_val_preds = stack.predict(X_val)
    stack_val_probas = stack.predict_proba(X_val)
    stack_val_metrics = compute_evaluation_metrics(y_val, stack_val_preds, stack_val_probas, CLASSES)
    stack_val_metrics["model"] = "StackingEnsemble"
    stack_val_metrics["split"] = "validation"
    stack_val_metrics["cv_f1_mean"] = float(stack_cv.mean())
    stack_val_metrics["cv_f1_std"] = float(stack_cv.std())
    model_performance.append(stack_val_metrics)

    stack_test_preds = stack.predict(X_test)
    stack_test_probas = stack.predict_proba(X_test)
    stack_test_metrics = compute_evaluation_metrics(y_test, stack_test_preds, stack_test_probas, CLASSES)
    stack_test_metrics["model"] = "StackingEnsemble"
    stack_test_metrics["split"] = "test"
    model_performance.append(stack_test_metrics)

    test_probas_all["StackingEnsemble"] = {"y_proba": stack_test_probas}

    print(
        f"  {'StackingEnsemble':20s} | Val F1: {stack_val_metrics['f1_weighted']:.4f} "
        f"| Test F1: {stack_test_metrics['f1_weighted']:.4f} "
        f"| Test Acc: {stack_test_metrics['accuracy']:.4f} "
        f"| AUC: {stack_test_metrics['roc_auc']:.4f}"
    )

    cm_path = os.path.join(results_dir, "cm_stackingensemble.png")
    plot_and_save_confusion_matrix(y_test, stack_test_preds, CLASSES, cm_path, title="Confusion Matrix (Stacking)")
    roc_path = os.path.join(results_dir, "roc_stackingensemble.png")
    plot_roc_curve(y_test, stack_test_probas, CLASSES, roc_path, title="ROC Curve (Stacking)")
    pr_path = os.path.join(results_dir, "pr_stackingensemble.png")
    plot_precision_recall(y_test, stack_test_probas, pr_path, title="Precision-Recall (Stacking)")
    report_path = os.path.join(results_dir, "report_stackingensemble.txt")
    save_classification_report(y_test, stack_test_preds, CLASSES, report_path)

    if stack_val_metrics["f1_weighted"] > best_f1:
        best_f1 = stack_val_metrics["f1_weighted"]
        best_model_name = "StackingEnsemble"
        best_model_obj = stack

    print(f"\n  >>> Best Model: {best_model_name} (Val F1: {best_f1:.4f})")

    # Combined ROC
    plot_combined_roc(test_probas_all, y_test, os.path.join(results_dir, "roc_combined.png"))

    # CV boxplot
    plot_cv_boxplot(cv_results_all, os.path.join(results_dir, "cv_boxplot.png"))

    # Save comparison table
    res_df = pd.DataFrame(model_performance)
    res_df.to_csv(os.path.join(results_dir, "model_comparison.csv"), index=False)

    # Save CV summary
    cv_summary = {name: {"mean": np.mean(s), "std": np.std(s)} for name, s in cv_results_all.items()}
    cv_df = pd.DataFrame(cv_summary).T
    cv_df.to_csv(os.path.join(results_dir, "cv_summary.csv"))
    print("\n  Cross-validation summary:")
    for name, scores in cv_results_all.items():
        print(f"    {name:20s} | {np.mean(scores):.4f} ± {np.std(scores):.4f}")

    # ================================================================
    # 3. Hyperparameter Tuning on best model
    # ================================================================
    if tune and best_model_name != "StackingEnsemble":
        print("\n" + "=" * 70)
        print(f"  PHASE 3: HYPERPARAMETER TUNING ({best_model_name})")
        print("=" * 70)

        tuned_model = _tune_best_model(best_model_name, X_train, y_train, scale_pos)
        if tuned_model is not None:
            tuned_val_preds = tuned_model.predict(X_val)
            tuned_val_probas = tuned_model.predict_proba(X_val)
            tuned_val_metrics = compute_evaluation_metrics(y_val, tuned_val_preds, tuned_val_probas, CLASSES)

            tuned_test_preds = tuned_model.predict(X_test)
            tuned_test_probas = tuned_model.predict_proba(X_test)
            tuned_test_metrics = compute_evaluation_metrics(y_test, tuned_test_preds, tuned_test_probas, CLASSES)

            print(
                f"  Tuned {best_model_name}: Val F1: {tuned_val_metrics['f1_weighted']:.4f} "
                f"| Test F1: {tuned_test_metrics['f1_weighted']:.4f} "
                f"| Test Acc: {tuned_test_metrics['accuracy']:.4f}"
            )

            if tuned_val_metrics["f1_weighted"] >= best_f1:
                print("  Tuned model is better — using it.")
                best_model_obj = tuned_model
                best_f1 = tuned_val_metrics["f1_weighted"]

                cm_path = os.path.join(results_dir, f"cm_{best_model_name.lower()}_tuned.png")
                plot_and_save_confusion_matrix(y_test, tuned_test_preds, CLASSES, cm_path,
                                               title=f"Confusion Matrix ({best_model_name} Tuned)")
                roc_path = os.path.join(results_dir, f"roc_{best_model_name.lower()}_tuned.png")
                plot_roc_curve(y_test, tuned_test_probas, CLASSES, roc_path,
                               title=f"ROC Curve ({best_model_name} Tuned)")
            else:
                print("  Tuned model is not better — keeping original.")

    # ================================================================
    # 4. Ablation Study
    # ================================================================
    print("\n" + "=" * 70)
    print("  PHASE 4: FEATURE GROUP ABLATION STUDY")
    print("=" * 70)
    ablation_csv = os.path.join(results_dir, "ablation_study.csv")
    run_ablation_study(train_df, val_df, ablation_csv)
    plot_ablation_bar_chart(ablation_csv, os.path.join(results_dir, "ablation_chart.png"))

    # ================================================================
    # 5. SHAP Explainability
    # ================================================================
    print("\n" + "=" * 70)
    print("  PHASE 5: SHAP FEATURE IMPORTANCE")
    print("=" * 70)
    shap_info = compute_shap_importance(best_model_obj, X_train, X_test, save_dir=results_dir)

    # ================================================================
    # 6. Permutation Importance
    # ================================================================
    print("\n" + "=" * 70)
    print("  PHASE 6: PERMUTATION IMPORTANCE")
    print("=" * 70)
    compute_permutation_importance(best_model_obj, X_test, y_test, save_dir=results_dir)

    # ================================================================
    # 7. Export
    # ================================================================
    print("\n" + "=" * 70)
    print("  PHASE 7: EXPORTING MODEL ARTIFACT")
    print("=" * 70)

    artifact_path = os.path.join(artifacts_dir, "model.joblib")
    artifact_data = {
        "model_name": best_model_name,
        "model": best_model_obj,
        "scaler": scaler,
        "label_encoder": le,
        "classes": CLASSES,
        "feature_names": feature_cols,
        "top_features": shap_info["top_features"],
    }
    joblib.dump(artifact_data, artifact_path)
    print(f"  Exported: {artifact_path}")
    print(f"  Model: {best_model_name} | Features: {len(feature_cols)} | Classes: {CLASSES}")

    return artifact_data


def _tune_best_model(model_name: str, X_train, y_train, scale_pos: float):
    """Run RandomizedSearchCV for the best model."""
    param_grids = {
        "LogisticRegression": {
            "C": [0.01, 0.1, 0.5, 1.0, 5.0, 10.0],
            "solver": ["lbfgs", "liblinear"],
        },
        "SVM": {
            "C": [0.1, 0.5, 1.0, 5.0, 10.0],
            "kernel": ["rbf", "linear"],
            "gamma": ["scale", "auto"],
        },
        "RandomForest": {
            "n_estimators": [100, 200, 300, 500],
            "max_depth": [None, 10, 20, 30],
            "min_samples_split": [2, 5, 10],
            "min_samples_leaf": [1, 2, 4],
        },
        "GradientBoosting": {
            "n_estimators": [100, 200, 300, 500],
            "max_depth": [3, 5, 7, 10],
            "learning_rate": [0.01, 0.05, 0.1, 0.2],
            "subsample": [0.7, 0.8, 0.9, 1.0],
            "min_samples_split": [2, 5, 10],
        },
        "XGBoost": {
            "n_estimators": [100, 200, 300, 500],
            "max_depth": [3, 5, 6, 8, 10],
            "learning_rate": [0.01, 0.05, 0.1, 0.2],
            "subsample": [0.7, 0.8, 0.9, 1.0],
            "colsample_bytree": [0.7, 0.8, 0.9, 1.0],
        },
    }

    base_models = {
        "LogisticRegression": LogisticRegression(max_iter=2000, random_state=42, class_weight="balanced"),
        "SVM": SVC(probability=True, random_state=42, class_weight="balanced"),
        "RandomForest": RandomForestClassifier(random_state=42, class_weight="balanced"),
        "GradientBoosting": GradientBoostingClassifier(random_state=42),
        "XGBoost": XGBClassifier(
            random_state=42, eval_metric="logloss", scale_pos_weight=scale_pos
        ),
    }

    if model_name not in param_grids:
        print(f"  No tuning grid for {model_name}.")
        return None

    search = RandomizedSearchCV(
        base_models[model_name],
        param_grids[model_name],
        n_iter=20,
        scoring="f1_weighted",
        cv=StratifiedKFold(n_splits=5, shuffle=True, random_state=42),
        random_state=42,
        n_jobs=-1,
        verbose=1,
    )
    search.fit(X_train, y_train)
    print(f"  Best params: {search.best_params_}")
    print(f"  Best CV F1: {search.best_score_:.4f}")
    return search.best_estimator_


if __name__ == "__main__":
    train_and_evaluate_all()
