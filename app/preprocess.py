"""
app/preprocess.py
Tongue image preprocessing wrapper.
Switchable via env var PREPROC_BACKEND=cpu|cuda.
CPU backend uses OpenCV. CUDA backend invokes compiled binary if available.
"""
import os
import cv2
import numpy as np
from typing import Tuple

BACKEND = os.getenv("PREPROC_BACKEND", "cpu").lower()


def _resize_normalize(img: np.ndarray, size: Tuple[int, int] = (256, 256)) -> np.ndarray:
    return cv2.resize(img, size, interpolation=cv2.INTER_AREA)


def _gaussian_cpu(img: np.ndarray, ksize: int = 5, sigma: float = 1.0) -> np.ndarray:
    return cv2.GaussianBlur(img, (ksize, ksize), sigma)


def _sobel_cpu(gray: np.ndarray) -> np.ndarray:
    sx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    sy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    mag = np.sqrt(sx**2 + sy**2)
    return np.clip(mag, 0, 255).astype(np.uint8)


def _median_cpu(img: np.ndarray, ksize: int = 3) -> np.ndarray:
    return cv2.medianBlur(img, ksize)


def preprocess_image(img_bgr: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Applies tongue image preprocessing pipeline.

    Steps:
      1. Resize to 256×256
      2. Gaussian smoothing (noise reduction)
      3. Median filter (salt-and-pepper noise)
      4. Colour normalisation
      5. Simple mask generation (Otsu on V channel)

    Args:
        img_bgr: Raw input image in BGR format (H, W, 3).

    Returns:
        (processed_img, mask): Both np.ndarray.
    """
    if BACKEND == "cuda":
        return _preprocess_cuda(img_bgr)
    return _preprocess_cpu(img_bgr)


def _preprocess_cpu(img: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    img = _resize_normalize(img)
    img = _gaussian_cpu(img)
    img = _median_cpu(img)

    # Colour normalisation (per-channel min-max)
    img = img.astype(np.float32)
    for c in range(3):
        ch = img[:, :, c]
        mn, mx = ch.min(), ch.max()
        img[:, :, c] = (ch - mn) / (mx - mn + 1e-6) * 255.0
    img = img.astype(np.uint8)

    # Tongue mask via Otsu on HSV Value channel
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    v = hsv[:, :, 2]
    _, mask = cv2.threshold(v, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    return img, mask


def _preprocess_cuda(img: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Placeholder for CUDA backend. Falls back to CPU if binary not available.
    When cuda/ module is built, this calls the compiled pipeline via ctypes or subprocess.
    """
    cuda_bin = os.path.join(os.path.dirname(__file__), "..", "cuda", "build", "fld_preprocess")
    if os.path.exists(cuda_bin):
        # In a future phase, write img to temp file, call binary, read result back.
        raise NotImplementedError("CUDA binary integration not yet wired (Phase 3/4).")
    # Graceful fallback
    print("[preprocess.py] CUDA binary not found – falling back to CPU backend.")
    return _preprocess_cpu(img)
