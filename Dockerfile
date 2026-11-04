# SingMatch — React e FastAPI na mesma origem.
FROM node:22-alpine AS frontend-build
WORKDIR /frontend
COPY frontend/package*.json ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app/backend
WORKDIR /app
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ ./backend/
COPY scripts/ ./scripts/
COPY data/ ./data/
COPY --from=frontend-build /frontend/dist ./frontend/dist/
EXPOSE 10000
# Apenas uma instância no piloto. Migração e seed são idempotentes.
# Nunca configure OPENAI_API_KEY no Dockerfile nem no git.
CMD ["sh", "-c", "alembic -c backend/alembic.ini upgrade head && python3 scripts/import_catalog.py && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
