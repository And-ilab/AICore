# CPU-only embedding HTTP service (E5 multilingual, 1024-d).
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/models/hf-cache \
    TRANSFORMERS_CACHE=/models/hf-cache \
    SENTENCE_TRANSFORMERS_HOME=/models/hf-cache \
    EMBEDDING_MODEL=intfloat/multilingual-e5-large \
    EMBEDDING_DIMENSIONS=1024

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /app/requirements.txt

# Force CPU torch wheels (no CUDA).
RUN python -m pip install --no-cache-dir --upgrade pip \
 && python -m pip install --no-cache-dir \
      --index-url https://download.pytorch.org/whl/cpu \
      torch==2.6.0 \
 && python -m pip install --no-cache-dir \
      fastapi==0.115.6 \
      uvicorn==0.34.0 \
      "sentence-transformers==3.4.1" \
      "numpy==2.2.3" \
      "huggingface_hub>=0.26"

COPY main.py /app/main.py
RUN mkdir -p /models/hf-cache

EXPOSE 8090
HEALTHCHECK --interval=20s --timeout=5s --retries=15 --start-period=180s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8090/health', timeout=3)"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8090"]
