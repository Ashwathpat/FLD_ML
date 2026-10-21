import numpy as np
from typing import Dict, Tuple, List
from .color import extract_color_features
from .texture import extract_texture_features
from .coating import extract_coating_features
from .shape import extract_shape_features

def extract_all_biomarkers(img_bgr: np.ndarray, mask: np.ndarray = None) -> Dict[str, float]:
    """
    Extracts all color, texture, coating, and shape biomarkers from a tongue image.
    
    Args:
        img_bgr: BGR image array (H, W, 3).
        mask: Optional binary mask of tongue region (H, W).
        
    Returns:
        Dict[str, float] containing all feature names and values.
    """
    features = {}
    features.update(extract_color_features(img_bgr, mask))
    features.update(extract_texture_features(img_bgr, mask))
    features.update(extract_coating_features(img_bgr, mask))
    features.update(extract_shape_features(img_bgr, mask))
    return features
