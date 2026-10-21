"""
ml/data.py
Dataset loader for the Tongue-FLD dataset (binary classification).
- Loads tongue images + physiological CSV in one pass.
- Extracts image biomarkers via multiprocessing.
- Caches features to CSV for instant re-runs.
- Merges physiological indicators (Age, Gender, BMI-related, BP) as extra features.
"""
import os
import cv2
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Tuple
from concurrent.futures import ProcessPoolExecutor, as_completed
from sklearn.model_selection import train_test_split
from tqdm import tqdm

CLASSES = ["No_FLD", "FLD"]
CLASS_MAP = {"_0": "No_FLD", "_1": "FLD"}
CLASS_TO_IDX = {cls: idx for idx, cls in enumerate(CLASSES)}

# Paths
DATA_DIR = Path("ml/data/raw")
CSV_PATH = DATA_DIR / "Physiological_Indicators_and_Labels.csv"
IMG_DIR = DATA_DIR / "Tongue_Images"
CACHE_PATH = Path("ml/data/features_cache.csv")


def _extract_one(img_path: str) -> dict:
    """Extract all image biomarkers from a single image file. Top-level for pickling."""
    from ml.features import extract_all_biomarkers
    from app.preprocess import preprocess_image

    img_bgr = cv2.imread(img_path)
    if img_bgr is None:
        return {}
    img_proc, mask = preprocess_image(img_bgr)
    feats = extract_all_biomarkers(img_proc, mask)
    return feats


def load_real_dataset(
    data_dir: str = None,
    cache_path: str = None,
    max_workers: int = None,
    force_reextract: bool = False,
) -> pd.DataFrame:
    """
    Load the Tongue-FLD dataset: images + physiological CSV → unified feature DataFrame.

    Steps:
        1. Read CSV for labels and physiological indicators.
        2. For each row, extract image biomarkers (or load from cache).
        3. Merge image features with physiological features.
        4. Return a single DataFrame with all features + 'label' column.

    Args:
        data_dir: Path to raw data directory (default: ml/data/raw).
        cache_path: Path to feature cache CSV (default: ml/data/features_cache.csv).
        max_workers: Number of parallel workers (default: cpu_count - 1).
        force_reextract: If True, ignore cache and re-extract all features.

    Returns:
        pd.DataFrame with feature columns + 'label'.
    """
    _data_dir = Path(data_dir) if data_dir else DATA_DIR
    _cache = Path(cache_path) if cache_path else CACHE_PATH
    _csv = _data_dir / "Physiological_Indicators_and_Labels.csv"
    _img_dir = _data_dir / "Tongue_Images"

    # --- Read CSV ---
    meta_df = pd.read_csv(_csv)
    meta_df["label"] = meta_df["FLD"].map(CLASS_MAP)
    meta_df["img_path"] = meta_df["quesid"].apply(lambda q: str(_img_dir / q))

    # Validate all images exist
    valid_mask = meta_df["img_path"].apply(os.path.isfile)
    if not valid_mask.all():
        n_missing = (~valid_mask).sum()
        print(f"[ml/data.py] WARNING: {n_missing} images not found, skipping them.")
        meta_df = meta_df[valid_mask].reset_index(drop=True)

    print(f"[ml/data.py] Dataset: {len(meta_df)} samples | "
          f"No_FLD: {(meta_df['label']=='No_FLD').sum()} | FLD: {(meta_df['label']=='FLD').sum()}")

    # --- Image feature extraction (with cache) ---
    if _cache.exists() and not force_reextract:
        print(f"[ml/data.py] Loading cached features from {_cache}")
        feat_df = pd.read_csv(_cache)
        # Verify cache matches current dataset
        if len(feat_df) == len(meta_df):
            print(f"[ml/data.py] Cache valid ({len(feat_df)} rows).")
        else:
            print(f"[ml/data.py] Cache size mismatch ({len(feat_df)} vs {len(meta_df)}). Re-extracting...")
            feat_df = _extract_all_features(meta_df["img_path"].tolist(), max_workers)
            feat_df.to_csv(_cache, index=False)
    else:
        print(f"[ml/data.py] Extracting image features for {len(meta_df)} images...")
        feat_df = _extract_all_features(meta_df["img_path"].tolist(), max_workers)
        _cache.parent.mkdir(parents=True, exist_ok=True)
        feat_df.to_csv(_cache, index=False)
        print(f"[ml/data.py] Features cached to {_cache}")

    # --- Physiological features ---
    phys_cols = ["Gender", "Age", "Height", "Waist", "Hipline", "Weight", "SBP", "DBP"]
    phys_df = meta_df[phys_cols].copy()

    # Encode Gender: _1 (male?) → 1, _0 → 0 (based on dataset convention)
    if phys_df["Gender"].dtype == object:
        phys_df["Gender"] = phys_df["Gender"].map({"_1": 1, "_0": 0}).fillna(0).astype(float)

    # Rename with phys_ prefix for ablation grouping
    phys_df.columns = [f"phys_{c.lower()}" for c in phys_df.columns]

    # Convert all to float
    for col in phys_df.columns:
        phys_df[col] = pd.to_numeric(phys_df[col], errors="coerce").fillna(0.0)

    # Add derived features
    phys_df["phys_bmi"] = phys_df["phys_weight"] / ((phys_df["phys_height"] / 100) ** 2 + 1e-6)
    phys_df["phys_waist_hip_ratio"] = phys_df["phys_waist"] / (phys_df["phys_hipline"] + 1e-6)

    # --- Merge ---
    result_df = pd.concat([feat_df.reset_index(drop=True), phys_df.reset_index(drop=True)], axis=1)
    result_df["label"] = meta_df["label"].values

    # Drop rows where feature extraction failed (all zeros)
    img_feat_cols = [c for c in feat_df.columns]
    zero_rows = (result_df[img_feat_cols].abs().sum(axis=1) == 0)
    if zero_rows.any():
        print(f"[ml/data.py] Dropping {zero_rows.sum()} rows with failed feature extraction.")
        result_df = result_df[~zero_rows].reset_index(drop=True)

    print(f"[ml/data.py] Final dataset: {len(result_df)} samples, {len(result_df.columns)-1} features.")
    return result_df


def _extract_all_features(img_paths: list, max_workers: int = None) -> pd.DataFrame:
    """Extract image biomarkers from all images using multiprocessing."""
    if max_workers is None:
        max_workers = max(1, os.cpu_count() - 1)

    results = [None] * len(img_paths)

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {
            executor.submit(_extract_one, path): idx
            for idx, path in enumerate(img_paths)
        }
        for future in tqdm(as_completed(future_to_idx), total=len(img_paths),
                           desc="Extracting features", unit="img"):
            idx = future_to_idx[future]
            try:
                results[idx] = future.result()
            except Exception as e:
                print(f"[ml/data.py] Error extracting {img_paths[idx]}: {e}")
                results[idx] = {}

    return pd.DataFrame(results).fillna(0.0)


def get_train_val_test_splits(
    df: pd.DataFrame, random_state: int = 42
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Stratified split into Train (70%), Validation (15%), and Test (15%)."""
    train_df, temp_df = train_test_split(
        df, test_size=0.30, stratify=df["label"], random_state=random_state
    )
    val_df, test_df = train_test_split(
        temp_df, test_size=0.50, stratify=temp_df["label"], random_state=random_state
    )
    return train_df, val_df, test_df
