# NavIC API image. Builds the Python app and serves the FastAPI read surface.
# For the local demo it runs the in-memory backend pre-seeded with sample data
# (tools/demo/serve); for a real deployment, override the command to run uvicorn
# against apps.api.main:app with NAVIC_API_BACKEND=postgres.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/packages:/app

WORKDIR /app

# Build metadata + the flat source root, then install (builds core, pulls deps).
COPY pyproject.toml README.md ./
COPY packages ./packages
RUN pip install --upgrade pip && pip install .

# apps/ and tools/ are thin shells imported via PYTHONPATH; copied last for caching.
COPY apps ./apps
COPY tools ./tools

EXPOSE 8000

# Demo entrypoint: seed the in-memory store, then serve on 0.0.0.0:8000.
CMD ["python", "-m", "tools.demo.serve"]
