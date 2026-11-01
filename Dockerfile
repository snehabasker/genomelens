# ── Stage 1: build the frontend ───────────────────────────────────────────────
FROM node:20-alpine AS frontend-build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN cd frontend && npm ci
COPY frontend/ ./frontend/
COPY docs/ ./docs/
RUN cd frontend && npm run build

# ── Stage 2: API + static frontend (Hugging Face Spaces: Docker SDK, port 7860) ──
FROM python:3.12-slim
RUN useradd -m -u 1000 app
WORKDIR /home/app
COPY --chown=app backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=app backend/ ./
COPY --chown=app --from=frontend-build /app/frontend/dist ./static
USER app

# writable locations (Spaces' filesystem is ephemeral outside /tmp and /data)
ENV CACHE_DB=/tmp/cache.db RUNS_DB=/tmp/runs.db PORT=7860
EXPOSE 7860
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
