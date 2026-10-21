"""
ml/ablation.py
Feature group ablation study: evaluates model performance when trained on
different subsets of features (color, texture, coating, shape, physiological).
"""
import os
import pandas as pd
from typing import Dict, List
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.ensemble import RandomForestClassifier
from ml.evaluate import compute_evaluation_metrics


def get_feature_subsets(all_columns: List[str]) -> Dict[str, List[str]]:
    """Define ablation feature groups including physiological indicators."""
    color_cols = [c for c in all_columns if c.startswith("color_")]
    texture_cols = [c for c in all_columns if c.startswith("texture_")]
    coating_cols = [c for c in all_columns if c.startswith("coating_")]
    shape_cols = [c for c in all_columns if c.startswith("shape_")]
    phys_cols = [c for c in all_columns if c.startswith("phys_")]
    image_cols = color_cols + texture_cols + coating_cols + shape_cols

    subsets = {
        "Color Only": color_cols,
        "Texture Only": texture_cols,
        "Coating Only": coating_cols,
        "Shape Only": shape_cols,
        "Physiological Only": phys_cols,
        "Color + Texture": color_cols + texture_cols,
        "Color + Texture + Coating": color_cols + texture_cols + coating_cols,
        "All Image Features": image_cols,
        "All Image + Physiological (Full)": image_cols + phys_cols,
    }
    # Filter out empty groups
    return {k: v for k, v in subsets.items() if v}


def run_ablation_study(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    save_path: str = "ml/results/ablation_study.csv",
) -> pd.DataFrame:
    """Evaluate RandomForest across feature group subsets."""
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    all_cols = [c for c in train_df.columns if c != "label"]
    subsets = get_feature_subsets(all_cols)

    le = LabelEncoder()
    y_train = le.fit_transform(train_df["label"])
    y_val = le.transform(val_df["label"])

    ablation_results = []

    for name, cols in subsets.items():
        if not cols:
            continue
        scaler = StandardScaler()
        X_tr = scaler.fit_transform(train_df[cols])
        X_va = scaler.transform(val_df[cols])

        rf = RandomForestClassifier(
            n_estimators=200, random_state=42, class_weight="balanced"
        )
        rf.fit(X_tr, y_train)
        preds = rf.predict(X_va)
        probas = rf.predict_proba(X_va)

        metrics = compute_evaluation_metrics(y_val, preds, probas)
        metrics["feature_group"] = name
        metrics["num_features"] = len(cols)
        ablation_results.append(metrics)
        print(f"  {name:40s} | F1: {metrics['f1_weighted']:.4f} | Acc: {metrics['accuracy']:.4f} | AUC: {metrics['roc_auc']:.4f}")

    df_res = pd.DataFrame(ablation_results)
    cols_order = [
        "feature_group", "num_features", "accuracy", "f1_weighted",
        "f1_macro", "balanced_accuracy", "roc_auc",
    ]
    df_res = df_res[[c for c in cols_order if c in df_res.columns]]
    df_res.to_csv(save_path, index=False)
    print(f"  Saved ablation results to {save_path}")
    return df_res
