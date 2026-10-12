"""Isolated preview entrypoint; leaves the main port-8501 service untouched.

Build: npm run build --prefix frontend -- --outDir ../runtime/plant-overview-preview
Run: python -m uvicorn scripts.plant_overview_preview:app --host 127.0.0.1 --port 5173
"""
from fastapi.staticfiles import StaticFiles

from astra_bio import api

api.DIST = api.ROOT / "runtime" / "plant-overview-preview"
api.app.router.routes = [route for route in api.app.router.routes if getattr(route, "path", "") != "/assets"]
if api.DIST.exists():
    api.app.mount("/assets", StaticFiles(directory=api.DIST / "assets"), name="preview-assets")
app = api.app
