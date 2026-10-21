"""
ml/features/color.py
RGB, HSV, Lab color statistics, histogram descriptors, CLAHE-enhanced stats,
dominant colour clustering, redness index, and higher-order colour moments.
"""
import cv2
import numpy as np
from typing import Dict
from scipy.stats import skew, kurtosis


def extract_color_features(img_bgr: np.ndarray, mask: np.ndarray = None) -> Dict[str, float]:
    """
    Extracts comprehensive colour features from a tongue image.

    Args:
        img_bgr: BGR image array (H, W, 3).
        mask: Binary mask of tongue region (H, W), 255/1 for tongue, 0 for background.

    Returns:
        Dict[str, float] mapping feature names to numerical scalar values.
    """
    features: Dict[str, float] = {}

    if mask is not None:
        valid_mask = mask > 0
    else:
        valid_mask = np.ones((img_bgr.shape[0], img_bgr.shape[1]), dtype=bool)

    if not np.any(valid_mask):
        valid_mask = np.ones((img_bgr.shape[0], img_bgr.shape[1]), dtype=bool)

    # ---------- 1. RGB channel statistics ----------
    b, g, r = cv2.split(img_bgr)
    for channel, c_name in [(r, "r"), (g, "g"), (b, "b")]:
        vals = channel[valid_mask].astype(np.float64)
        features[f"color_{c_name}_mean"] = float(np.mean(vals))
        features[f"color_{c_name}_std"] = float(np.std(vals))
        features[f"color_{c_name}_median"] = float(np.median(vals))

    # ---------- 2. HSV channel statistics ----------
    img_hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(img_hsv)
    for channel, c_name in [(h, "h"), (s, "s"), (v, "v")]:
        vals = channel[valid_mask].astype(np.float64)
        features[f"color_{c_name}_mean"] = float(np.mean(vals))
        features[f"color_{c_name}_std"] = float(np.std(vals))

    # ---------- 3. Lab channel statistics ----------
    img_lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    l_ch, a_ch, b_lab = cv2.split(img_lab)
    for channel, c_name in [(l_ch, "lab_l"), (a_ch, "lab_a"), (b_lab, "lab_b")]:
        vals = channel[valid_mask].astype(np.float64)
        features[f"color_{c_name}_mean"] = float(np.mean(vals))
        features[f"color_{c_name}_std"] = float(np.std(vals))

    # ---------- 4. Colour ratios & brightness descriptors ----------
    r_val = features["color_r_mean"] + 1e-6
    g_val = features["color_g_mean"] + 1e-6
    b_val = features["color_b_mean"] + 1e-6
    features["color_rg_ratio"] = r_val / g_val
    features["color_rb_ratio"] = r_val / b_val
    features["color_gb_ratio"] = g_val / b_val

    # ---------- 5. Compact histograms (4 bins per RGB channel) ----------
    for channel, c_name in [(r, "r"), (g, "g"), (b, "b")]:
        hist, _ = np.histogram(channel[valid_mask], bins=4, range=(0, 256))
        hist_norm = hist / (np.sum(hist) + 1e-6)
        for bin_idx, val in enumerate(hist_norm):
            features[f"color_hist_{c_name}_bin{bin_idx}"] = float(val)

    # ---------- 6. Redness index (clinically relevant for tongue diagnosis) ----------
    # redness = 2*R / (G + B + eps)  — higher in FLD tongues
    r_vals = r[valid_mask].astype(np.float64)
    g_vals = g[valid_mask].astype(np.float64)
    b_vals = b[valid_mask].astype(np.float64)
    redness = (2.0 * r_vals) / (g_vals + b_vals + 1e-6)
    features["color_redness_index_mean"] = float(np.mean(redness))
    features["color_redness_index_std"] = float(np.std(redness))

    # ---------- 7. Colour moments (skewness, kurtosis per channel) ----------
    for channel, c_name in [(r, "r"), (g, "g"), (b, "b")]:
        vals = channel[valid_mask].astype(np.float64)
        features[f"color_{c_name}_skew"] = float(skew(vals)) if len(vals) > 2 else 0.0
        features[f"color_{c_name}_kurt"] = float(kurtosis(vals)) if len(vals) > 2 else 0.0

    # ---------- 8. CLAHE-enhanced luminance stats ----------
    try:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l_clahe = clahe.apply(l_ch)
        vals = l_clahe[valid_mask].astype(np.float64)
        features["color_clahe_l_mean"] = float(np.mean(vals))
        features["color_clahe_l_std"] = float(np.std(vals))
    except Exception:
        features["color_clahe_l_mean"] = 0.0
        features["color_clahe_l_std"] = 0.0

    # ---------- 9. Dominant colour clustering (K-means, K=3) ----------
    try:
        pixels = img_bgr[valid_mask].reshape(-1, 3).astype(np.float32)
        # Sub-sample for speed (max 5000 pixels)
        if len(pixels) > 5000:
            idx = np.random.default_rng(42).choice(len(pixels), 5000, replace=False)
            pixels = pixels[idx]

        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
        _, labels, centres = cv2.kmeans(
            pixels, 3, None, criteria, 3, cv2.KMEANS_PP_CENTERS
        )
        # Sort clusters by population (descending)
        counts = np.bincount(labels.flatten(), minlength=3)
        order = np.argsort(-counts)
        for rank, ci in enumerate(order):
            b_c, g_c, r_c = centres[ci]
            prop = counts[ci] / (np.sum(counts) + 1e-6)
            features[f"color_dom{rank}_r"] = float(r_c)
            features[f"color_dom{rank}_g"] = float(g_c)
            features[f"color_dom{rank}_b"] = float(b_c)
            features[f"color_dom{rank}_prop"] = float(prop)
    except Exception:
        for rank in range(3):
            features[f"color_dom{rank}_r"] = 0.0
            features[f"color_dom{rank}_g"] = 0.0
            features[f"color_dom{rank}_b"] = 0.0
            features[f"color_dom{rank}_prop"] = 0.0

    return features
