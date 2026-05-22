# internal-ai-search backend — minimal dev image (API + hwp5txt runtime check)
# Build context: repository root (see docker-compose.dev.yml)
# syntax=docker/dockerfile:1

FROM python:3.12-slim-bookworm

WORKDIR /app

# Native deps for lxml, cryptography, pyhwp (build stability over minimal image size)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    python3-dev \
    libxml2 \
    libxml2-dev \
    libxslt1-dev \
    zlib1g-dev \
    libffi-dev \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY backend/app /app/app
COPY backend/tests /app/tests
COPY backend/db /app/backend/db
COPY tools /app/tools
COPY scripts /app/scripts
COPY docker/db /app/docker/db

ENV PYTHONPATH=/app
ENV HWP_EXTRACTION_STRATEGY=tiered
ENV HWP5TXT_BIN=hwp5txt
ENV HWP5HTML_BIN=hwp5html
ENV HWP_PARSER_TIMEOUT_SECONDS=120
ENV HWP_MIN_EXTRACTED_TEXT_LENGTH=50
ENV HWP_HTML_MIN_EXTRACTED_TEXT_LENGTH=50
ENV HWP_HTML_MIN_GAIN_RATIO=1.5

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
