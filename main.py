import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

load_dotenv()

from database import engine, Base, SessionLocal
import models  # noqa: F401  (rejestruje wszystkie tabele)
from routers import alerts, deliveries, people, rules, runbooks, sources
from seed import seed_all

# Tworzenie tabel bazy danych (SQLite / Postgres)
Base.metadata.create_all(bind=engine)


db = SessionLocal()
try:
    seed_all(db)
finally:
    db.close()

app = FastAPI(
    title="Flexible Alerting & Notification Service",
    description="Ingest -> rules -> alerts -> deliveries. Podział pracy: TEAM.md",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API – każdy router ma właściciela (TEAM.md)
for r in (alerts, rules, people, sources, deliveries, runbooks):
    app.include_router(r.router)


@app.get("/health", tags=["System"])
def health_check():
    """Endpoint używany przez Render/Railway do weryfikacji działania."""
    return {"status": "ok"}


# Obsługa Frontendu: Jeśli zbudowano Reacta w frontend/dist -> serwuj React SPA
FRONTEND_DIST = Path(__file__).resolve().parent / "frontend" / "dist"

if FRONTEND_DIST.exists():
    # Montowanie plików statycznych zbudowanego Reacta
    if (FRONTEND_DIST / "assets").exists():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_react_spa(full_path: str):
        if full_path.startswith("api") or full_path in ["docs", "redoc", "openapi.json", "health"]:
            return None
        file_path = FRONTEND_DIST / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(FRONTEND_DIST / "index.html")
else:
    @app.get("/", include_in_schema=False)
    def root():
        return {"msg": "Frontend nie jest zbudowany. Odpal `cd frontend && npm run dev` albo zajrzyj na /docs"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
