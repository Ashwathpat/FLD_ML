"""
app/tests/test_app.py
API contract tests using FastAPI TestClient (no live DB or cloud needed).
"""
import io
import cv2
import numpy as np
import pytest

from fastapi.testclient import TestClient


def _make_test_image() -> bytes:
    """Generate a small test tongue image as JPEG bytes."""
    img = np.zeros((128, 128, 3), dtype=np.uint8)
    cv2.ellipse(img, (64, 70), (45, 55), 0, 0, 360, (180, 100, 200), -1)
    _, buf = cv2.imencode(".jpg", img)
    return buf.tobytes()


@pytest.fixture(scope="module")
def client():
    """Import app after model artifact exists (Phase 1 must have run)."""
    import importlib, sys
    # Ensure ml.artifacts.model.joblib exists from Phase 1 train
    import os
    if not os.path.exists("ml/artifacts/model.joblib"):
        from ml.train import train_and_evaluate_all
        train_and_evaluate_all()

    from app.main import app
    with TestClient(app) as c:
        yield c


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert "x-served-by" in r.headers


def test_readyz_model_loaded(client):
    r = client.get("/readyz")
    assert r.status_code in (200, 503)
    assert "status" in r.json()


def test_predict_valid_image(client):
    img_bytes = _make_test_image()
    r = client.post(
        "/predict",
        files={"file": ("tongue.jpg", img_bytes, "image/jpeg")}
    )
    assert r.status_code == 200
    body = r.json()
    assert "label" in body
    assert "probabilities" in body
    assert "top_features" in body
    assert body["disclaimer"] == "Screening-support tool, not a medical diagnosis."
    assert "x-served-by" in r.headers


def test_predict_invalid_file(client):
    r = client.post(
        "/predict",
        files={"file": ("bad.txt", b"not an image", "text/plain")}
    )
    assert r.status_code == 422
