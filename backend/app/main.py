"""Entrypoint inicial da API: nenhuma regra de negócio foi implementada."""
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.schemas import HealthResponse

app = FastAPI(title="SingMatch API", version="0.1.0")

@app.get("/api/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="singmatch-api")

# Publicação futura: servir o build do frontend pela mesma origem,
# mas apenas depois das rotas /api; não capturar /api com fallback SPA.
frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if (frontend_dist / "index.html").is_file():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
