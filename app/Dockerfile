FROM python:3.11-slim AS build
WORKDIR /w
COPY app/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim
RUN useradd -m app \
 && apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*
COPY --from=build /install /usr/local
WORKDIR /srv
COPY app/ ./app/
COPY ml/ ./ml/
COPY ml/artifacts/model.joblib ./model.joblib
ENV MODEL_PATH=/srv/model.joblib
ENV PREPROC_BACKEND=cpu
USER app
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s CMD \
  python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/healthz')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
