import importlib
import sys
from pathlib import Path
from typing import Callable

from fastapi import FastAPI


def _load_create_app() -> Callable[[], FastAPI]:
    root_dir = Path(__file__).resolve().parents[2]
    if str(root_dir) not in sys.path:
        sys.path.insert(0, str(root_dir))

    module = importlib.import_module("server.app.main")
    return module.create_app


def test_create_app_registers_api_routes() -> None:
    create_app = _load_create_app()
    app = create_app()
    paths = {getattr(route, "path", "") for route in app.routes}

    assert "/api/v1/test/gemini" in paths
    assert "/api/v2/curation/roadmap/{user_id}" in paths
    assert "/api/v3/jobs/recommend/{user_id}" in paths
