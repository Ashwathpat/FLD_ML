FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends rclone && rm -rf /var/lib/apt/lists/*
WORKDIR /srv
COPY app/requirements.txt .
RUN pip install --no-cache-dir psycopg[binary]
COPY app/replicator/replicate.py .
CMD ["python", "replicate.py"]
