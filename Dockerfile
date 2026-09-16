# Creative Intelligence on Render Free (Docker multi-stage).
#
# Stage 1 builds the React/Vite frontend with the same toolchain as CI
# (Node 22, pnpm 10.14.0, frozen lockfile). Stage 2 is a slim Python
# runtime: locked backend dependencies, the repo tree the backend
# addresses by path (Backend/, Web/, fixtures/), and the built dist/
# the FastAPI app serves at /. Oracle deployment is untouched — this
# file is purely additive.

# ---- Frontend build ----
FROM node:22-bookworm-slim AS frontend
RUN corepack enable && corepack prepare pnpm@10.14.0 --activate
WORKDIR /build/apps/creative-intelligence-ui
COPY apps/creative-intelligence-ui/package.json apps/creative-intelligence-ui/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY apps/creative-intelligence-ui/ ./
RUN pnpm build

# ---- Python runtime ----
FROM python:3.13-slim

# Video preprocessing needs both ffmpeg and ffprobe in the runtime image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && ffmpeg -version \
    && ffprobe -version \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CREATIVE_INTEL_DATA_DIR=/app/data \
    CREATIVE_INTEL_DEMO_SEED=true
WORKDIR /app
COPY requirements.lock pyproject.toml ./
COPY Backend/ ./Backend/
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --require-hashes -r requirements.lock \
    && pip install --no-deps .
COPY Web/ ./Web/
COPY fixtures/ ./fixtures/
COPY --from=frontend /build/apps/creative-intelligence-ui/dist ./apps/creative-intelligence-ui/dist
RUN mkdir -p /app/data
# No EXPOSE: Render injects $PORT and main.py binds 0.0.0.0 to it.
CMD ["python", "Backend/ci_backend/main.py"]
