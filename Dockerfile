# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY openai_tts_gradio_app ./openai_tts_gradio_app
COPY openai_tts_gradio.py ./
RUN pip install . && \
    useradd --create-home --uid 1000 appuser

USER appuser

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7860/', timeout=3)" || exit 1

ENTRYPOINT ["openai-tts-gradio"]
CMD ["--host", "0.0.0.0", "--port", "7860"]
