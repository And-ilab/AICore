# TEST ASR stub (no Vosk / GPU). For vosk mode use services/asr/requirements.txt.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ASR_MODE=stub \
    ASR_HOST=0.0.0.0 \
    ASR_WS_PORT=8765 \
    ASR_HEALTH_PORT=8764 \
    AI_INFERENCE_PROFILE=test

WORKDIR /app
RUN python -m pip install --no-cache-dir "websockets==12.0"
COPY runtime.py /app/runtime.py

EXPOSE 8764 8765
HEALTHCHECK --interval=10s --timeout=3s --retries=8 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8764/health', timeout=2)"

CMD ["python", "/app/runtime.py"]
