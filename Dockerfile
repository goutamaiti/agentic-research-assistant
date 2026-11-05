# Agentic Research Assistant: one container serving the API and the built web interface.
# Used by Hugging Face Spaces (port 7860); also runs anywhere Docker runs:
#   docker build -t ara . && docker run -p 7860:7860 -e GEMINI_API_KEY=... ara

# ---- 1. Build the React frontend -------------------------------------------------
FROM node:22-slim AS frontend
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- 2. Python backend -----------------------------------------------------------
FROM python:3.12-slim

# Tesseract reads scanned pages (optional for text PDFs, small to include).
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

# Hugging Face Spaces run the container as user 1000.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/home/user/.cache/huggingface
WORKDIR /home/user/app

# CPU-only PyTorch first (the default Linux wheel bundles ~3 GB of CUDA libraries).
COPY --chown=user backend/requirements.txt backend/requirements.txt
RUN pip install --user --index-url https://download.pytorch.org/whl/cpu \
        "torch==$(grep -E '^torch==' backend/requirements.txt | cut -d= -f3)" \
    && pip install --user -r backend/requirements.txt

# Bake the embedding model into the image so the first analysis does not download it.
ARG EMBEDDING_MODEL=sentence-transformers/multi-qa-mpnet-base-cos-v1
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL}')"

COPY --chown=user backend/ backend/
COPY --chown=user storage/ storage/
COPY --chown=user --from=frontend /src/dist frontend/dist

ENV APP_ENV=production \
    EMBEDDING_MODEL=${EMBEDDING_MODEL} \
    HF_HUB_OFFLINE=1 \
    ANONYMIZED_TELEMETRY=False \
    PORT=7860
EXPOSE 7860
WORKDIR /home/user/app/backend
CMD ["sh", "-c", "exec python -m uvicorn app.main:create_app --factory --host 0.0.0.0 --port ${PORT}"]
