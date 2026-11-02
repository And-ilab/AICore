# CPU-only embedding HTTP service (E5 multilingual, 1024-d).
FROM python:3.12-slim-bookworm

ARG http_proxy
ARG https_proxy
ARG no_proxy
ARG PIP_TRUSTED_HOST

ENV http_proxy=$http_proxy \
    https_proxy=$https_proxy \
    no_proxy=$no_proxy \
    PIP_TRUSTED_HOST=$PIP_TRUSTED_HOST

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \ 
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \ 
    PIP_TRUSTED_HOST="pypi.org files.pythonhosted.org pypi.python.org download.pytorch.org download-r2.pytorch.org" \ 
    #PIP_TRUSTED_HOST="download.pytorch.org pypi.org manylinux1_x86_64.whl files.pythonhosted.org pypi.python.org" \
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
COPY wheels/torch-2.6.0+cpu-cp312-cp312-linux_x86_64.whl /tmp/torch-2.6.0+cpu-cp312-cp312-linux_x86_64.whl

RUN python -m pip install --no-cache-dir --upgrade pip \
 && python -m pip install --no-cache-dir /tmp/torch-2.6.0+cpu-cp312-cp312-linux_x86_64.whl \
 && rm /tmp/torch-2.6.0+cpu-cp312-cp312-linux_x86_64.whl \
 && python -m pip install --no-cache-dir \
      fastapi==0.115.6 \
      uvicorn==0.34.0 \
      "sentence-transformers==3.4.1" \
      "numpy==2.2.3" \
      "huggingface_hub>=0.26"
 #&& python -m pip install --no-cache-dir \
      #--index-url https://pytorch.org \
      #torch==2.6.0 \


COPY main.py /app/main.py
RUN mkdir -p /models/hf-cache

EXPOSE 8090
HEALTHCHECK --interval=20s --timeout=5s --retries=15 --start-period=180s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8090/health', timeout=3)"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8090"]
