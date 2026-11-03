"""FastAPI, API primeiro e build do React na mesma origem quando disponível."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routes import router
from app.schemas import HealthResponse

app = FastAPI(title="SingMatch API", version="0.4.0")


@app.get("/api/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="singmatch-api")


app.include_router(router)

# As rotas de /api sempre ficam registradas antes deste mount.
# StaticFiles(html=True) não captura fallback SPA em /api.
frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if (frontend_dist / "index.html").is_file():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
