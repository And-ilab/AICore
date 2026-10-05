FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

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
    && apt-get install -y --no-install-recommends unrar-free unar || true \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-ocr-paddle.txt ./
ARG OCR_ENABLE_PADDLE=1
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt \
    && if [ "$OCR_ENABLE_PADDLE" = "1" ]; then \
         pip install -r requirements-ocr-paddle.txt || echo "PaddleOCR skipped"; \
       fi

COPY . .

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
