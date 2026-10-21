# FLD-Screen: Non-Invasive Fatty Liver Disease Screening & Resilient Multi-Cloud System

> **Medical Disclaimer:** *FLD-Screen is an intelligent clinical decision-support and screening tool, not an autonomous medical diagnostic device.*

FLD-Screen is an end-to-end medical AI screening system integrating **Computer Vision**, **High-Performance Parallel Computing (CUDA)**, and **Multi-Cloud Disaster Recovery (AWS + Azure)** to detect Fatty Liver Disease (FLD / NAFLD) from non-invasive tongue morphology and standard physiological biomarkers.

---

## 🌟 Key Highlights & Engineering Features

### 1. Machine Learning & Clinical Biomarkers (`ml/`)
- **Multimodal Feature Extraction:** 174 handcrafted biomarkers spanning multiple color spaces (RGB, CIE-L\*a\*b\*, HSV moments), multi-scale Gray-Level Co-occurrence Matrix (GLCM) textures, Gabor spatial-frequency filter banks, tongue coating thickness/greasiness ratios, and Hu invariant shape moments.
- **Ensemble Modeling:** Benchmarked 6 classifiers (Logistic Regression, SVM, Random Forest, Gradient Boosting, XGBoost, and Stacking Ensemble) across 5,717 clinically annotated patient records.
- **Top Performance:** Heterogeneous Stacking Ensemble achieves **80.65% Test Accuracy**, **0.8801 ROC-AUC**, and **80.42% Weighted F1-Score**.
- **Clinical Explainability:** TreeSHAP game-theoretic feature attribution identifying BMI, waist circumference, SBP, and yellow tongue coating intensity (CIE-b*) as primary pathophysiological drivers.

### 2. High-Performance GPU Acceleration (`cuda/`)
- **Hardware Benchmarked:** NVIDIA GeForce RTX 4060 GPU with CUDA architecture.
- **Custom Kernels:** 2D Gaussian blur with constant-memory kernel caching, Sobel spatial gradient magnitude, and non-linear median filtering.
- **Memory Optimization:** 2D shared-memory tiling with boundary halo loading to eliminate global memory roundtrips.
- **Asynchronous Pipelining:** Multi-stream batch processing with pinned host memory scaling throughput to **789.9 images/second** (7.46× over single-stream execution) and peak kernel speedup of **17.0×** with bit-level verification (PSNR > 52 dB).

### 3. Multi-Cloud Resilience & DevOps (`app/` & `infra/`)
- **Active-Passive DR:** Active primary cluster in AWS (us-east-1) with warm standby in Microsoft Azure (East US).
- **Automated DNS Failover:** Amazon Route 53 health checking (`/healthz` every 10s) with 10s TTL, triggering automatic failover upon 3 consecutive dropouts.
- **Asynchronous Data Replication:** Dual-tier sync engine (`app/replicator/replicate.py`) synchronizing PostgreSQL transaction logs and S3-to-Blob object storage every 15 seconds.
- **Empirical Chaos Drills:** Validated Disaster Recovery metrics with Recovery Time Objective (**RTO = 42.4s**) and Recovery Point Objective (**RPO = 14.8s**).
- **Cost Efficiency:** Warm standby model achieves **62% cost savings** over active-active multi-cloud setups.

---

## 📁 Repository Structure

```
fld-screen/
├── app/                           # FastAPI Inference Microservice & Web UI
│   ├── main.py                    # REST API endpoints (/predict, /healthz, /readyz)
│   ├── preprocess.py              # Image preprocessing pipeline (CPU / CUDA backends)
│   ├── db.py                      # PostgreSQL persistence adapter
│   ├── storage.py                 # S3 / Azure Blob storage adapter
│   ├── static/                    # Clinician web dashboard (HTML5, CSS3, Chart.js)
│   ├── replicator/                # Cross-cloud DB & object storage sync daemon
│   └── Dockerfile                 # Multi-stage non-root OCI container
├── cuda/                          # CUDA Parallel Computing Suite
│   ├── src/                       # CUDA kernels (tiled shared-memory, multi-stream)
│   ├── benchmark_cuda_suite.py    # Microsecond benchmark harness & validation
│   └── results/                   # Benchmark CSVs and publication-grade plots
├── infra/                         # Infrastructure as Code (Terraform)
│   ├── aws/                       # Primary AWS stack (EC2, RDS Multi-AZ, S3, Caddy)
│   ├── azure/                     # Standby Azure stack (VM, PostgreSQL Flex, Blob)
│   ├── dns/                       # Route 53 health probes and failover records
│   ├── compose/                   # Local container orchestration
│   └── results/                   # Architecture diagrams and chaos drill plots
├── ml/                            # Machine Learning & Biomarkers
│   ├── features/                  # Color, texture, coating, and shape extractors
│   ├── data.py                    # Dataset loader & preprocessor
│   ├── train.py                   # 5-Fold cross-validation & model training
│   ├── evaluate.py                # ROC, PR, confusion matrix evaluation
│   ├── explain.py                 # TreeSHAP & permutation importance
│   ├── ablation.py                # Feature group ablation analysis
│   └── results/                   # Evaluation charts and feature attributions
├── scripts/                       # Operational scripts & chaos drill harness
├── IEEE_Report_ML_FLD_Screen.docx # Full IEEE 2-Column Report (Machine Learning)
├── IEEE_Report_PCAP_CUDA_Acceleration.docx # Full IEEE 2-Column Report (Parallel Computing)
├── IEEE_Report_CCDL_MultiCloud_DR.docx     # Full IEEE 2-Column Report (Cloud Computing)
└── README.md
```

---

## 🚀 Complete Testing & Demonstration Guide

### 1. Launching the Local Microservice
```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
- API Docs (Swagger UI): `http://127.0.0.1:8000/docs`
- Clinician Web Dashboard: `http://127.0.0.1:8000/app/`

---

### 2. Testing a Random Tongue Image for Fatty Liver
You can test any custom or clinical tongue image using either the **Web Dashboard** or the **REST API**:

#### Option A: Interactive Web UI (Recommended for Demos)
1. Navigate to `http://127.0.0.1:8000/app/` in your browser.
2. Drag and drop any tongue image (`.jpg` or `.png`).
3. Enter patient vitals (Age, Gender, Height, Weight, Waist, Hipline, SBP, DBP).
4. Click **"Run Clinical Screening"** — the dashboard instantly returns:
   - **Diagnostic Prediction**: `FLD` (Fatty Liver Disease) or `Healthy`.
   - **Confidence Score & Class Probabilities** (via Stacking Ensemble).
   - **Dynamic Feature Attribution**: Top clinical biomarker contributors calculated via TreeSHAP.

#### Option B: Programmatic CLI / Python Request
Run the following one-liner in your terminal to screen an image:
```powershell
python -c "import requests; r = requests.post('http://127.0.0.1:8000/predict', files={'file': open('ml/data/raw/Tongue_Images/00000.jpg', 'rb')}, data={'age': 45, 'gender': 0, 'height': 165, 'weight': 70, 'waist': 85, 'hipline': 95, 'sbp': 120, 'dbp': 80}); print(r.json())"
```
**Sample JSON Response:**
```json
{
  "prediction": "FLD",
  "probability_fld": 0.841,
  "probability_healthy": 0.159,
  "top_features": {
    "BMI": 25.71,
    "Waist_Circumference": 85.0,
    "Tongue_Coating_b_star": 18.42,
    "GLCM_Contrast": 12.3
  },
  "served_by": "local"
}
```

---

### 3. Verifying Multi-Cloud Disaster Recovery (AWS & Azure)
The system is designed with an **Active-Passive Disaster Recovery** architecture between **AWS (us-east-1)** and **Azure (East US)**:

#### How to Check Which Cloud is Serving:
Every API response embeds the custom `X-Served-By` HTTP response header:
- `X-Served-By: aws-primary` → Primary AWS EC2/Caddy instance is actively serving traffic.
- `X-Served-By: azure-standby` → Standby Azure VM is serving traffic after automatic DNS failover.

To inspect this live:
```powershell
curl -I http://127.0.0.1:8000/healthz
```

#### How Failover Works in Production:
1. **Amazon Route 53 Health Checks** query `/healthz` on the primary AWS endpoint every 10 seconds.
2. If AWS fails 3 consecutive health checks (30 seconds), Route 53 updates DNS routing to point all domain traffic to the **Azure Standby** IP.
3. The cross-cloud replicator daemon (`app/replicator/replicate.py`) ensures the Azure PostgreSQL and Blob storage are kept in continuous sync (RPO < 15 seconds).
4. To simulate an outage and measure empirical recovery time:
   ```bash
   ./scripts/drill.sh fld-screen.example.com sg-0123456789abcdef0
   ```
   *Empirically validated benchmarks: **RTO = 42.4s**, **RPO = 14.8s**.*

---

### 4. Running the GPU CUDA Acceleration Benchmarks (RTX 4060)
To benchmark the custom CUDA image processing kernels (Gaussian blur, Sobel gradient, median filter, multi-stream batch pipeline) on your local NVIDIA GPU:
```powershell
python cuda/benchmark_cuda_suite.py
```
This executes 20 warm-up runs and 100 benchmark iterations using hardware `torch.cuda.Event` timers, outputting timing comparisons and speedup figures to `cuda/results/`.

---

### 5. Running the Complete Automated Test Suite
Run the 15 end-to-end integration and unit tests:
```powershell
python -m pytest app/tests/test_app.py ml/tests/test_ml.py -v
```

---

## 🔒 Security & Environment Configuration
- **Zero Secrets Committed**: All API keys, database credentials, and cloud secrets are loaded strictly from the environment (`.env`).
- `.env` is explicitly declared in `.gitignore` and is **never tracked by Git**.
- A sanitized template is provided in [`.env.example`](.env.example):
  ```bash
  cp .env.example .env
  # Populate your database credentials and optional cloud storage keys
  ```

---

## 📑 IEEE Publications
The full academic reports for all three sub-domains are available in IEEE two-column format in the repository root:
- [IEEE_Report_ML_FLD_Screen.docx](IEEE_Report_ML_FLD_Screen.docx) — *Multimodal Biomarker Extraction & Stacking Ensemble for Fatty Liver Disease Screening*
- [IEEE_Report_PCAP_CUDA_Acceleration.docx](IEEE_Report_PCAP_CUDA_Acceleration.docx) — *GPU-Accelerated Tongue Image Preprocessing via Tiled Shared-Memory CUDA Kernels*
- [IEEE_Report_CCDL_MultiCloud_DR.docx](IEEE_Report_CCDL_MultiCloud_DR.docx) — *Resilient Active-Passive Multi-Cloud Disaster Recovery Architecture Across AWS and Azure*

---

## 📄 License
This project is licensed under the Apache 2.0 License.
