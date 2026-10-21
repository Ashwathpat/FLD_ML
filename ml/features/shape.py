"""
ml/features/shape.py
Tongue shape features: area, perimeter, aspect ratio, circularity, solidity,
Hu moments, convexity defects, extent, and tip-vs-base colour ratio.
"""
import cv2
import numpy as np
from typing import Dict


def extract_shape_features(img_bgr: np.ndarray, mask: np.ndarray = None) -> Dict[str, float]:
    """
    Extracts tongue shape features.

    Args:
        img_bgr: BGR image array (H, W, 3).
        mask: Binary mask of tongue region (H, W).

    Returns:
        Dict[str, float] mapping feature names to numerical scalar values.
    """
    features: Dict[str, float] = {}
    h, w = img_bgr.shape[:2]

    if mask is not None and np.any(mask > 0):
        binary = (mask > 0).astype(np.uint8) * 255
    else:
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if contours:
        largest_cnt = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(largest_cnt)
        perimeter = cv2.arcLength(largest_cnt, True)

        x, y, bw, bh = cv2.boundingRect(largest_cnt)
        aspect_ratio = float(bw) / float(bh) if bh > 0 else 1.0

        # Circularity
        circularity = (4.0 * np.pi * area) / (perimeter ** 2 + 1e-6)

        # Solidity
        hull = cv2.convexHull(largest_cnt)
        hull_area = cv2.contourArea(hull)
        solidity = area / (hull_area + 1e-6)

        # Extent = contour area / bounding rect area
        extent = area / (float(bw) * float(bh) + 1e-6)

        features["shape_area"] = float(area)
        features["shape_perimeter"] = float(perimeter)
        features["shape_aspect_ratio"] = float(aspect_ratio)
        features["shape_circularity"] = float(circularity)
        features["shape_solidity"] = float(solidity)
        features["shape_relative_area"] = float(area) / float(h * w)
        features["shape_extent"] = float(extent)

        # ---- Hu Moments (7 rotation/scale-invariant descriptors) ----
        try:
            moments = cv2.moments(largest_cnt)
            hu = cv2.HuMoments(moments).flatten()
            # Log-transform to compress dynamic range
            for i, val in enumerate(hu):
                features[f"shape_hu{i}"] = float(-np.sign(val) * np.log10(abs(val) + 1e-30))
        except Exception:
            for i in range(7):
                features[f"shape_hu{i}"] = 0.0

        # ---- Convexity Defects Count ----
        try:
            hull_indices = cv2.convexHull(largest_cnt, returnPoints=False)
            if len(hull_indices) > 3 and len(largest_cnt) > 3:
                defects = cv2.convexityDefects(largest_cnt, hull_indices)
                if defects is not None:
                    # Count significant defects (depth > 5% of perimeter)
                    threshold = perimeter * 0.05
                    sig_defects = sum(1 for d in defects if d[0][3] / 256.0 > threshold)
                    features["shape_convexity_defects"] = float(sig_defects)
                    features["shape_max_defect_depth"] = float(
                        max(d[0][3] / 256.0 for d in defects) / (perimeter + 1e-6)
                    )
                else:
                    features["shape_convexity_defects"] = 0.0
                    features["shape_max_defect_depth"] = 0.0
            else:
                features["shape_convexity_defects"] = 0.0
                features["shape_max_defect_depth"] = 0.0
        except Exception:
            features["shape_convexity_defects"] = 0.0
            features["shape_max_defect_depth"] = 0.0

        # ---- Tip vs Base Colour Ratio ----
        # Partition tongue vertically: top half = "tip", bottom half = "base"
        try:
            tip_mask = np.zeros_like(binary)
            base_mask = np.zeros_like(binary)
            tip_mask[:h // 2, :] = binary[:h // 2, :]
            base_mask[h // 2:, :] = binary[h // 2:, :]

            r_ch = img_bgr[:, :, 2].astype(np.float64)  # red channel (BGR)
            tip_vals = r_ch[tip_mask > 0]
            base_vals = r_ch[base_mask > 0]

            if len(tip_vals) > 0 and len(base_vals) > 0:
                features["shape_tip_base_r_ratio"] = float(
                    np.mean(tip_vals) / (np.mean(base_vals) + 1e-6)
                )
                features["shape_tip_base_r_diff"] = float(
                    np.mean(tip_vals) - np.mean(base_vals)
                )
            else:
                features["shape_tip_base_r_ratio"] = 1.0
                features["shape_tip_base_r_diff"] = 0.0
        except Exception:
            features["shape_tip_base_r_ratio"] = 1.0
            features["shape_tip_base_r_diff"] = 0.0

    else:
        features["shape_area"] = 0.0
        features["shape_perimeter"] = 0.0
        features["shape_aspect_ratio"] = 1.0
        features["shape_circularity"] = 0.0
        features["shape_solidity"] = 0.0
        features["shape_relative_area"] = 0.0
        features["shape_extent"] = 0.0
        for i in range(7):
            features[f"shape_hu{i}"] = 0.0
        features["shape_convexity_defects"] = 0.0
        features["shape_max_defect_depth"] = 0.0
        features["shape_tip_base_r_ratio"] = 1.0
        features["shape_tip_base_r_diff"] = 0.0

    return features
