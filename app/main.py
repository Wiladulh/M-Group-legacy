from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from app.core.config import get_settings
from app.core.db import Database
from app.core.logging import configure_logging
from app.api.routes import build_router
from importlib.resources import files as resource_files

def create_app():
    s = get_settings()
    configure_logging()
    db = Database(s.db_path)
    db.migrate()
    app = FastAPI(title="NVM", version="0.1.0")
    app.state.settings = s
    app.state.db = db
    app.include_router(build_router(db, s))
    webui_dir = Path(__file__).resolve().parent / "webui"
    app.mount("/assets", StaticFiles(directory=webui_dir / "assets"), name="webui-assets")
    app.mount("/pages", StaticFiles(directory=webui_dir / "pages"), name="webui-pages")

    @app.get("/", response_class=HTMLResponse)
    def index():
        return resource_files("app").joinpath("webui/index.html").read_text(encoding="utf-8")

    return app

app = create_app()
