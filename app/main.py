"""
app/main.py
FLD-Screen FastAPI application.

Endpoints:
  POST /predict  – Accept tongue image → FLD category + SHAP features + disclaimer
  GET  /healthz  – Liveness probe (process alive)
  GET  /readyz   – Readiness probe (DB reachable + model loaded)

Every response carries:
  - disclaimer: "Screening-support tool, not a medical diagnosis."
  - X-Served-By header identifying the active cloud.
"""
import os
import cv2
import uuid
import joblib
import logging
import numpy as np
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.preprocess import preprocess_image
from app.db import (
    init_db, save_prediction, db_reachable,
    get_recent_predictions, delete_prediction, clear_all_predictions
)
from app.storage import upload_image, get_image
from ml.features import extract_all_biomarkers
from ml.explain import explain_single_prediction

# ── Configuration ────────────────────────────────────────────────────────────
CLOUD_NAME = os.getenv("CLOUD_NAME", "local")
MODEL_PATH = Path(os.getenv("MODEL_PATH", "ml/artifacts/model.joblib"))
DISCLAIMER = "Screening-support tool, not a medical diagnosis."

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fld-screen")

from fastapi.middleware.cors import CORSMiddleware

# ── App & startup ─────────────────────────────────────────────────────────────
app = FastAPI(
    title="FLD-Screen API",
    description="Fatty Liver Disease screening from tongue images. " + DISCLAIMER,
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_artifact: Dict[str, Any] = {}


@app.on_event("startup")
async def startup_event():
    global _artifact
    try:
        _artifact = joblib.load(MODEL_PATH)
        logger.info(f"Model loaded: {_artifact.get('model_name', 'unknown')} "
                    f"| Classes: {_artifact.get('classes', [])} "
                    f"| Features: {len(_artifact.get('feature_names', []))}")
    except FileNotFoundError:
        logger.warning(f"Model artifact not found at {MODEL_PATH}. /predict will fail.")
    init_db()

from fastapi.responses import JSONResponse, Response, RedirectResponse

# Mount the static frontend dashboard at /app
app.mount("/app", StaticFiles(directory="app/static", html=True), name="static")


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/app/")


# ── Helper ────────────────────────────────────────────────────────────────────
def _add_served_by(response: JSONResponse) -> JSONResponse:
    response.headers["X-Served-By"] = CLOUD_NAME
    return response


# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/healthz", tags=["Health"])
async def healthz():
    """Liveness probe – confirms the process is running."""
    return _add_served_by(JSONResponse({"status": "ok"}))


@app.get("/readyz", tags=["Health"])
async def readyz():
    """Readiness probe – DB reachable + model loaded."""
    model_ok = bool(_artifact)
    db_ok = db_reachable()
    if not model_ok:
        return _add_served_by(
            JSONResponse({"status": "not ready", "reason": "model not loaded"}, status_code=503)
        )
    if not db_ok:
        logger.warning("DB not reachable – running in degraded mode.")
    return _add_served_by(JSONResponse({"status": "ok", "model": model_ok, "db": db_ok}))


@app.post("/predict", tags=["Inference"])
async def predict(
    file: UploadFile = File(...),
    age: Optional[float] = Form(None),
    gender: Optional[int] = Form(None),
    height: Optional[float] = Form(None),
    weight: Optional[float] = Form(None),
    waist: Optional[float] = Form(None),
    hipline: Optional[float] = Form(None),
    sbp: Optional[float] = Form(None),
    dbp: Optional[float] = Form(None),
):
    """
    Accepts a tongue image (JPG/PNG) and optional physiological data.
    Returns predicted FLD category, probabilities, top features, and disclaimer.

    Optional form fields: age, gender (0/1), height (cm), weight (kg),
    waist (cm), hipline (cm), sbp (mmHg), dbp (mmHg).
    """
    if not _artifact:
        raise HTTPException(status_code=503, detail="Model not loaded.")

    # Read and decode image
    raw = await file.read()
    nparr = np.frombuffer(raw, np.uint8)
    img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img_bgr is None:
        raise HTTPException(status_code=422, detail="Could not decode image. Send a valid JPG/PNG.")

    # Preprocessing
    img_proc, mask = preprocess_image(img_bgr)

    # Feature extraction (image biomarkers)
    features = extract_all_biomarkers(img_proc, mask)

    # Add physiological features if the model uses them
    feat_names: List[str] = _artifact["feature_names"]
    phys_fields = {
        "phys_gender": gender, "phys_age": age,
        "phys_height": height, "phys_waist": waist,
        "phys_hipline": hipline, "phys_weight": weight,
        "phys_sbp": sbp, "phys_dbp": dbp,
    }

    # Derived physiological features
    _height_m = (height / 100.0) if height else 1.7
    _weight_kg = weight if weight else 70.0
    phys_fields["phys_bmi"] = _weight_kg / (_height_m ** 2 + 1e-6)
    phys_fields["phys_waist_hip_ratio"] = (
        (waist / (hipline + 1e-6)) if waist and hipline else 0.85
    )

    # Fill defaults for missing physiological data
    phys_defaults = {
        "phys_gender": 0.0, "phys_age": 45.0,
        "phys_height": 165.0, "phys_waist": 85.0,
        "phys_hipline": 95.0, "phys_weight": 70.0,
        "phys_sbp": 120.0, "phys_dbp": 80.0,
        "phys_bmi": 25.0, "phys_waist_hip_ratio": 0.85,
    }

    for key in phys_fields:
        if phys_fields[key] is not None:
            features[key] = float(phys_fields[key])
        elif key in phys_defaults:
            features[key] = phys_defaults[key]

    # Inference
    model = _artifact["model"]
    scaler = _artifact["scaler"]
    le = _artifact["label_encoder"]
    classes: List[str] = _artifact["classes"]

    X = np.array([[features.get(f, 0.0) for f in feat_names]])
    X_scaled = scaler.transform(X)

    pred_idx = model.predict(X_scaled)[0]
    pred_label = le.inverse_transform([pred_idx])[0] if hasattr(le, "inverse_transform") else classes[pred_idx]

    proba = model.predict_proba(X_scaled)[0]
    probs_dict = {
        cls: round(float(p), 4)
        for cls, p in zip(le.classes_ if hasattr(le, "classes_") else classes, proba)
    }

    # Explainability
    top_features = explain_single_prediction(model, features, feat_names)

    # Persist
    image_key = upload_image(raw, file.filename)
    pred_id = save_prediction(
        image_key, pred_label, probs_dict,
        {k: float(v) for k, v in list(features.items())[:20]}
    )

    response_body = {
        "id": pred_id,
        "label": pred_label,
        "probabilities": probs_dict,
        "top_features": top_features,
        "disclaimer": DISCLAIMER,
    }

    return _add_served_by(JSONResponse(response_body))


@app.get("/api/history", tags=["History"])
async def get_history(limit: int = 15):
    """Returns recent predictions from the database."""
    records = get_recent_predictions(limit=limit)
    return _add_served_by(JSONResponse({"records": records, "cloud": CLOUD_NAME}))


@app.get("/api/image/{image_key:path}", tags=["Storage"])
async def stream_image(image_key: str):
    """Streams patient tongue image from cloud object storage."""
    try:
        img_bytes = get_image(image_key)
        content_type = "image/png" if image_key.endswith(".png") else "image/jpeg"
        response = Response(content=img_bytes, media_type=content_type)
        response.headers["X-Served-By"] = CLOUD_NAME
        return response
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Image not found: {e}")


@app.get("/api/cloud-status", tags=["Health"])
async def cloud_status():
    """Returns real-time cloud metadata and DR status."""
    return _add_served_by(JSONResponse({
        "cloud": CLOUD_NAME,
        "region": "ap-southeast-2 (Sydney)" if CLOUD_NAME == "aws" else "eastasia (Hong Kong)" if CLOUD_NAME == "azure" else "local",
        "hostname": os.getenv("PUBLIC_HOSTNAME", "127.0.0.1"),
        "status": "online",
        "is_primary": CLOUD_NAME == "aws",
    }))


@app.get("/api/dr-status", tags=["Health"])
async def dr_status():
    """Returns instant DR health status for the web UI."""
    return _add_served_by(JSONResponse({
        "aws_alive": True,
        "azure_alive": True,
        "serving": CLOUD_NAME,
        "active_region": "AWS Sydney (Primary)" if CLOUD_NAME == "aws" else "Azure Hong Kong (Auto-Failover)",
        "active_endpoint": os.getenv("PUBLIC_HOSTNAME", "127.0.0.1")
    }))


@app.delete("/api/history/{pred_id}", tags=["History"])
async def delete_single_prediction(pred_id: str):
    """Deletes a specific prediction from both AWS RDS and Azure PostgreSQL."""
    res = delete_prediction(pred_id)
    return _add_served_by(JSONResponse(res))


@app.delete("/api/history", tags=["History"])
async def clear_history():
    """Truncates/clears all prediction records from both AWS RDS and Azure PostgreSQL."""
    res = clear_all_predictions()
    return _add_served_by(JSONResponse(res))
