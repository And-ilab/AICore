FROM python:3.12-slim
# 1. ОБЯЗАТЕЛЬНО декларируем аргументы сборки, которые придут из docker-compose
ARG http_proxy
ARG https_proxy
ARG no_proxy
ARG PIP_TRUSTED_HOST
ARG PIP_BREAK_SYSTEM_PACKAGES

# 2. Превращаем аргументы в переменные среды для текущего слоя сборки
ENV http_proxy=$http_proxy
ENV https_proxy=$https_proxy
ENV no_proxy=$no_proxy
ENV PIP_TRUSTED_HOST=$PIP_TRUSTED_HOST
ENV PIP_BREAK_SYSTEM_PACKAGES=$PIP_BREAK_SYSTEM_PACKAGES

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \ 
    PIP_TRUSTED_HOST="pypi.org files.pythonhosted.org pypi.python.org"

WORKDIR /app

ARG OCR_ENABLE_PADDLE=1
ARG LDAP_ENABLE=1

# Tesseract for OCR (FR-OCR); ffmpeg for audio/video ASR (§5.1.38).
# Liberation Serif ≈ Times New Roman for Cyrillic PDF reports.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-rus \
        tesseract-ocr-eng \
        antiword \
        ffmpeg \
        fonts-dejavu-core \
        libgomp1 \
        fonts-liberation \ 
    && if [ "$LDAP_ENABLE" = "1" ]; then \ 
         apt-get install -y --no-install-recommends \ 
           gcc libldap2-dev libsasl2-dev libssl-dev; \ 
       fi \
    && apt-get install -y --no-install-recommends unrar-free unar || true \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-ocr-paddle.txt requirements-ldap.txt ./

RUN python -m pip install --upgrade pip && \
    python -m pip install -r requirements.txt && \
    if [ "$LDAP_ENABLE" = "1" ]; then \
         python -m pip install -r requirements-ldap.txt || echo "LDAP skipped"; \
    fi && \
    if [ "$OCR_ENABLE_PADDLE" = "1" ]; then \
         python -m pip install -r requirements-ocr-paddle.txt || echo "PaddleOCR skipped"; \
    fi

COPY . .

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
