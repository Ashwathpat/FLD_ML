"""
ml/features/coating.py
Tongue coating features: area, ratios, intensity statistics,
thickness estimate, distribution uniformity, and Lab channel stats.
"""
import cv2
import numpy as np
from typing import Dict
from scipy.ndimage import distance_transform_edt


def extract_coating_features(img_bgr: np.ndarray, mask: np.ndarray = None) -> Dict[str, float]:
    """
    Extracts tongue coating features.

    Args:
        img_bgr: BGR image array (H, W, 3).
        mask: Binary mask of tongue region (H, W).

    Returns:
        Dict[str, float] mapping feature names to numerical scalar values.
    """
    features: Dict[str, float] = {}
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)

    if mask is not None:
        tongue_mask = mask > 0
    else:
        tongue_mask = np.ones((img_bgr.shape[0], img_bgr.shape[1]), dtype=bool)

    tongue_pixel_count = float(np.sum(tongue_mask)) + 1e-6

    h, s, v = cv2.split(hsv)
    l_chan, a_chan, b_chan = cv2.split(lab)

    # ---- 1. White / Yellow Coating Thresholding ----
    white_coating_mask = (s < 80) & (v > 130) & tongue_mask
    yellow_coating_mask = (s >= 50) & (s <= 160) & (b_chan > 140) & tongue_mask
    coating_combined_mask = (white_coating_mask | yellow_coating_mask) & tongue_mask

    coating_pixel_count = float(np.sum(coating_combined_mask))

    features["coating_area_pixels"] = coating_pixel_count
    features["coating_tongue_ratio"] = coating_pixel_count / tongue_pixel_count
    features["coating_white_ratio"] = float(np.sum(white_coating_mask)) / tongue_pixel_count
    features["coating_yellow_ratio"] = float(np.sum(yellow_coating_mask)) / tongue_pixel_count

    # ---- 2. Coating Region Intensity & Saturation Stats ----
    if np.any(coating_combined_mask):
        features["coating_intensity_mean"] = float(np.mean(v[coating_combined_mask]))
        features["coating_intensity_std"] = float(np.std(v[coating_combined_mask]))
        features["coating_saturation_mean"] = float(np.mean(s[coating_combined_mask]))
        features["coating_saturation_std"] = float(np.std(s[coating_combined_mask]))
        features["coating_lab_l_mean"] = float(np.mean(l_chan[coating_combined_mask]))
        features["coating_lab_a_mean"] = float(np.mean(a_chan[coating_combined_mask]))
        features["coating_lab_b_mean"] = float(np.mean(b_chan[coating_combined_mask]))
    else:
        features["coating_intensity_mean"] = 0.0
        features["coating_intensity_std"] = 0.0
        features["coating_saturation_mean"] = 0.0
        features["coating_saturation_std"] = 0.0
        features["coating_lab_l_mean"] = 0.0
        features["coating_lab_a_mean"] = 0.0
        features["coating_lab_b_mean"] = 0.0

    # ---- 3. Coating Thickness Estimate ----
    # Mean distance of coating pixels to the tongue boundary
    try:
        if np.any(coating_combined_mask):
            # distance_transform_edt on tongue mask gives distance to boundary
            dt = distance_transform_edt(tongue_mask.astype(np.uint8))
            coating_dists = dt[coating_combined_mask]
            features["coating_thickness_mean"] = float(np.mean(coating_dists))
            features["coating_thickness_std"] = float(np.std(coating_dists))
            features["coating_thickness_max"] = float(np.max(coating_dists))
        else:
            features["coating_thickness_mean"] = 0.0
            features["coating_thickness_std"] = 0.0
            features["coating_thickness_max"] = 0.0
    except Exception:
        features["coating_thickness_mean"] = 0.0
        features["coating_thickness_std"] = 0.0
        features["coating_thickness_max"] = 0.0

    # ---- 4. Coating Distribution Uniformity (quadrant analysis) ----
    try:
        h_img, w_img = tongue_mask.shape
        h_mid, w_mid = h_img // 2, w_img // 2
        quadrants = [
            tongue_mask[:h_mid, :w_mid] & coating_combined_mask[:h_mid, :w_mid],
            tongue_mask[:h_mid, w_mid:] & coating_combined_mask[:h_mid, w_mid:],
            tongue_mask[h_mid:, :w_mid] & coating_combined_mask[h_mid:, :w_mid],
            tongue_mask[h_mid:, w_mid:] & coating_combined_mask[h_mid:, w_mid:],
        ]
        q_counts = [float(np.sum(q)) for q in quadrants]
        total_q = sum(q_counts) + 1e-6
        q_props = [c / total_q for c in q_counts]
        features["coating_uniformity_std"] = float(np.std(q_props))
        features["coating_uniformity_max_diff"] = float(max(q_props) - min(q_props))
    except Exception:
        features["coating_uniformity_std"] = 0.0
        features["coating_uniformity_max_diff"] = 0.0

    return features
