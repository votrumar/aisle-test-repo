FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "Cython<3.0" "wheel" "setuptools"

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
ENV PYTHONPATH=/app/src

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
    CMD curl -fsS http://localhost:8000/healthz || exit 1

# gunicorn fronts uvicorn workers; deployment expects to sit behind a TE-stripping proxy (caddy/nginx)
CMD ["gunicorn", "monitoring.main:app", "-k", "uvicorn.workers.UvicornWorker", "-w", "2", "-b", "0.0.0.0:8000", "--forwarded-allow-ips=127.0.0.1", "--limit-request-line=8190", "--limit-request-fields=64"]
