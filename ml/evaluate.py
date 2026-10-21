"""
ml/evaluate.py
Model evaluation metrics, confusion matrices, ROC curves, precision-recall curves,
ablation charts, and cross-validation boxplots.
"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from typing import Dict, List, Optional
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    balanced_accuracy_score, roc_auc_score, roc_curve, auc,
    confusion_matrix, ConfusionMatrixDisplay, classification_report,
    precision_recall_curve, average_precision_score,
)


def compute_evaluation_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_proba: np.ndarray = None,
    classes: list = None,
) -> Dict[str, float]:
    """Compute comprehensive classification metrics."""
    metrics = {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision_weighted": float(precision_score(y_true, y_pred, average="weighted", zero_division=0)),
        "recall_weighted": float(recall_score(y_true, y_pred, average="weighted", zero_division=0)),
        "f1_weighted": float(f1_score(y_true, y_pred, average="weighted", zero_division=0)),
        "f1_macro": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
    }

    # AUC — binary or multi-class
    if y_proba is not None and len(np.unique(y_true)) > 1:
        try:
            if y_proba.shape[1] == 2:
                metrics["roc_auc"] = float(roc_auc_score(y_true, y_proba[:, 1]))
            else:
                metrics["roc_auc"] = float(
                    roc_auc_score(y_true, y_proba, multi_class="ovr", average="weighted")
                )
        except Exception:
            metrics["roc_auc"] = 0.0
    else:
        metrics["roc_auc"] = 0.0

    return metrics


def plot_and_save_confusion_matrix(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    classes: list,
    save_path: str,
    title: str = "Confusion Matrix",
):
    """Plot and save confusion matrix."""
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    cm = confusion_matrix(y_true, y_pred)
    disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=classes)
    fig, ax = plt.subplots(figsize=(6, 5))
    disp.plot(cmap="Blues", ax=ax, values_format="d")
    plt.title(title, fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig(save_path, dpi=300)
    plt.close()


def plot_roc_curve(
    y_true: np.ndarray,
    y_proba: np.ndarray,
    classes: list,
    save_path: str,
    title: str = "ROC Curve",
):
    """Plot and save ROC curve (binary or multi-class)."""
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    fig, ax = plt.subplots(figsize=(7, 6))

    if y_proba.shape[1] == 2:
        fpr, tpr, _ = roc_curve(y_true, y_proba[:, 1])
        roc_auc_val = auc(fpr, tpr)
        ax.plot(fpr, tpr, linewidth=2, label=f"AUC = {roc_auc_val:.4f}")
    else:
        for i, cls_name in enumerate(classes):
            fpr, tpr, _ = roc_curve((y_true == i).astype(int), y_proba[:, i])
            roc_auc_val = auc(fpr, tpr)
            ax.plot(fpr, tpr, linewidth=2, label=f"{cls_name} (AUC={roc_auc_val:.3f})")

    ax.plot([0, 1], [0, 1], "k--", linewidth=1, alpha=0.5)
    ax.set_xlabel("False Positive Rate", fontsize=12)
    ax.set_ylabel("True Positive Rate", fontsize=12)
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.legend(loc="lower right", fontsize=11)
    ax.set_xlim([0, 1])
    ax.set_ylim([0, 1.02])
    plt.tight_layout()
    plt.savefig(save_path, dpi=300)
    plt.close()


def save_classification_report(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    classes: list,
    save_path: str,
):
    """Save sklearn classification report to a text file."""
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    report = classification_report(y_true, y_pred, target_names=classes, zero_division=0)
    with open(save_path, "w") as f:
        f.write(report)


# ── NEW evaluation functions ─────────────────────────────────────────────────

def plot_combined_roc(
    model_results: Dict[str, Dict],
    y_true: np.ndarray,
    save_path: str,
    title: str = "Combined ROC Curves — All Models",
):
    """
    Plot all models' ROC curves on a single figure for comparison.

    Args:
        model_results: {model_name: {"y_proba": np.ndarray, ...}}
        y_true: Ground-truth labels.
        save_path: Output path.
    """
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 7))

    colors = ["#2563eb", "#dc2626", "#16a34a", "#9333ea", "#ea580c", "#0891b2"]
    for idx, (name, data) in enumerate(model_results.items()):
        y_proba = data["y_proba"]
        if y_proba.shape[1] == 2:
            fpr, tpr, _ = roc_curve(y_true, y_proba[:, 1])
        else:
            fpr, tpr, _ = roc_curve(y_true, y_proba[:, 1])
        roc_auc_val = auc(fpr, tpr)
        color = colors[idx % len(colors)]
        ax.plot(fpr, tpr, linewidth=2, color=color, label=f"{name} (AUC={roc_auc_val:.4f})")

    ax.plot([0, 1], [0, 1], "k--", linewidth=1, alpha=0.4)
    ax.set_xlabel("False Positive Rate", fontsize=13)
    ax.set_ylabel("True Positive Rate", fontsize=13)
    ax.set_title(title, fontsize=15, fontweight="bold")
    ax.legend(loc="lower right", fontsize=11)
    ax.set_xlim([0, 1])
    ax.set_ylim([0, 1.02])
    ax.grid(alpha=0.2)
    plt.tight_layout()
    plt.savefig(save_path, dpi=300)
    plt.close()


def plot_precision_recall(
    y_true: np.ndarray,
    y_proba: np.ndarray,
    save_path: str,
    title: str = "Precision-Recall Curve",
):
    """Plot precision-recall curve for binary classification."""
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    fig, ax = plt.subplots(figsize=(7, 6))

    if y_proba.shape[1] == 2:
        prec, rec, _ = precision_recall_curve(y_true, y_proba[:, 1])
        ap = average_precision_score(y_true, y_proba[:, 1])
        ax.plot(rec, prec, linewidth=2, color="#2563eb", label=f"AP = {ap:.4f}")
    else:
        prec, rec, _ = precision_recall_curve(y_true, y_proba[:, 1])
        ap = average_precision_score(y_true, y_proba[:, 1])
        ax.plot(rec, prec, linewidth=2, color="#2563eb", label=f"AP = {ap:.4f}")

    ax.set_xlabel("Recall", fontsize=12)
    ax.set_ylabel("Precision", fontsize=12)
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.legend(loc="lower left", fontsize=11)
    ax.set_xlim([0, 1])
    ax.set_ylim([0, 1.02])
    ax.grid(alpha=0.2)
    plt.tight_layout()
    plt.savefig(save_path, dpi=300)
    plt.close()


def plot_ablation_bar_chart(
    ablation_csv_path: str,
    save_path: str,
    title: str = "Feature Group Ablation Study",
):
    """Generate a grouped bar chart from the ablation CSV."""
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    df = pd.read_csv(ablation_csv_path)
    if df.empty:
        return

    groups = df["feature_group"].tolist()
    metrics = ["accuracy", "f1_weighted", "roc_auc"]
    x = np.arange(len(groups))
    bar_width = 0.25

    fig, ax = plt.subplots(figsize=(14, 6))
    colors = ["#2563eb", "#16a34a", "#ea580c"]

    for i, metric in enumerate(metrics):
        if metric in df.columns:
            ax.bar(x + i * bar_width, df[metric], bar_width, label=metric.replace("_", " ").title(),
                   color=colors[i], alpha=0.85)

    ax.set_xticks(x + bar_width)
    ax.set_xticklabels(groups, rotation=35, ha="right", fontsize=9)
    ax.set_ylabel("Score", fontsize=12)
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.legend(fontsize=10)
    ax.set_ylim(0, 1.05)
    ax.grid(axis="y", alpha=0.2)
    plt.tight_layout()
    plt.savefig(save_path, dpi=300)
    plt.close()


def plot_cv_boxplot(
    cv_results: Dict[str, List[float]],
    save_path: str,
    title: str = "Cross-Validation F1 Scores",
):
    """Box-plot of cross-validation scores per model."""
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 5))

    labels = list(cv_results.keys())
    data = [cv_results[k] for k in labels]

    bp = ax.boxplot(data, patch_artist=True, showmeans=True)
    ax.set_xticklabels(labels)
    colors = ["#bfdbfe", "#fecaca", "#bbf7d0", "#e9d5ff", "#fed7aa"]
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)

    ax.set_ylabel("F1 Weighted", fontsize=12)
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.grid(axis="y", alpha=0.2)
    plt.tight_layout()
    plt.savefig(save_path, dpi=300)
    plt.close()
