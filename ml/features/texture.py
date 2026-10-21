"""
ml/features/texture.py
GLCM (multi-scale), LBP, Gabor filter bank, Haralick extras, entropy,
and local-variance texture gradient descriptors.
"""
import cv2
import numpy as np
from typing import Dict
from skimage.feature import graycomatrix, graycoprops, local_binary_pattern
from skimage.measure import shannon_entropy


def _gabor_features(gray: np.ndarray, mask: np.ndarray) -> Dict[str, float]:
    """Gabor filter bank: 4 frequencies × 4 orientations → mean + energy per filter."""
    features: Dict[str, float] = {}
    frequencies = [0.05, 0.1, 0.2, 0.4]
    orientations = [0, np.pi / 4, np.pi / 2, 3 * np.pi / 4]

    for fi, freq in enumerate(frequencies):
        for oi, theta in enumerate(orientations):
            kernel = cv2.getGaborKernel(
                ksize=(21, 21), sigma=3.0, theta=theta,
                lambd=1.0 / freq, gamma=0.5, psi=0,
            )
            filtered = cv2.filter2D(gray, cv2.CV_64F, kernel)
            vals = filtered[mask]
            tag = f"texture_gabor_f{fi}_o{oi}"
            features[f"{tag}_mean"] = float(np.mean(vals))
            features[f"{tag}_energy"] = float(np.mean(vals ** 2))

    return features


def extract_texture_features(img_bgr: np.ndarray, mask: np.ndarray = None) -> Dict[str, float]:
    """
    Extract GLCM (multi-scale), LBP, Gabor, Haralick, entropy, and local-variance
    texture descriptors.

    Args:
        img_bgr: BGR image array (H, W, 3).
        mask: Binary mask of tongue region (H, W).

    Returns:
        Dict[str, float] of texture feature values.
    """
    features: Dict[str, float] = {}
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

    if mask is not None:
        valid_mask = mask > 0
    else:
        valid_mask = np.ones_like(gray, dtype=bool)

    if not np.any(valid_mask):
        valid_mask = np.ones_like(gray, dtype=bool)

    gray_masked = np.where(valid_mask, gray, 0)

    # ---- 1. Multi-scale GLCM (distances 1, 3, 5 — separate stats) ----
    glcm_props = ["contrast", "dissimilarity", "homogeneity", "energy", "correlation", "ASM"]
    distances = [1, 3, 5]
    angles = [0, np.pi / 4, np.pi / 2, 3 * np.pi / 4]

    try:
        gray_q = (gray_masked // 8).astype(np.uint8)
        glcm = graycomatrix(
            gray_q, distances=distances, angles=angles,
            levels=32, symmetric=True, normed=True,
        )

        for prop in glcm_props:
            vals = graycoprops(glcm, prop)  # shape: (len(distances), len(angles))
            # Overall stats (backward compatible)
            features[f"texture_glcm_{prop}_mean"] = float(np.mean(vals))
            features[f"texture_glcm_{prop}_std"] = float(np.std(vals))
            # Per-distance stats (new)
            for di, d in enumerate(distances):
                row = vals[di, :]
                features[f"texture_glcm_{prop}_d{d}_mean"] = float(np.mean(row))
    except Exception:
        for prop in glcm_props:
            features[f"texture_glcm_{prop}_mean"] = 0.0
            features[f"texture_glcm_{prop}_std"] = 0.0
            for d in distances:
                features[f"texture_glcm_{prop}_d{d}_mean"] = 0.0

    # ---- 2. LBP ----
    try:
        radius = 1
        n_points = 8 * radius
        lbp = local_binary_pattern(gray, n_points, radius, method="uniform")
        lbp_vals = lbp[valid_mask]
        features["texture_lbp_mean"] = float(np.mean(lbp_vals))
        features["texture_lbp_std"] = float(np.std(lbp_vals))

        lbp_hist, _ = np.histogram(lbp_vals, bins=n_points + 2, range=(0, n_points + 2))
        lbp_hist_norm = lbp_hist / (np.sum(lbp_hist) + 1e-6)
        for bin_idx, val in enumerate(lbp_hist_norm[:5]):
            features[f"texture_lbp_hist_bin{bin_idx}"] = float(val)
    except Exception:
        features["texture_lbp_mean"] = 0.0
        features["texture_lbp_std"] = 0.0
        for bin_idx in range(5):
            features[f"texture_lbp_hist_bin{bin_idx}"] = 0.0

    # ---- 3. Entropy ----
    try:
        features["texture_entropy"] = float(shannon_entropy(gray[valid_mask]))
    except Exception:
        features["texture_entropy"] = 0.0

    # ---- 4. Gabor filter bank ----
    try:
        gabor = _gabor_features(gray, valid_mask)
        features.update(gabor)
    except Exception:
        for fi in range(4):
            for oi in range(4):
                features[f"texture_gabor_f{fi}_o{oi}_mean"] = 0.0
                features[f"texture_gabor_f{fi}_o{oi}_energy"] = 0.0

    # ---- 5. Local variance (texture gradient) ----
    try:
        local_mean = cv2.blur(gray_masked.astype(np.float64), (5, 5))
        local_sq_mean = cv2.blur((gray_masked.astype(np.float64)) ** 2, (5, 5))
        local_var = local_sq_mean - local_mean ** 2
        local_var = np.clip(local_var, 0, None)
        var_vals = local_var[valid_mask]
        features["texture_local_var_mean"] = float(np.mean(var_vals))
        features["texture_local_var_std"] = float(np.std(var_vals))
    except Exception:
        features["texture_local_var_mean"] = 0.0
        features["texture_local_var_std"] = 0.0

    return features
