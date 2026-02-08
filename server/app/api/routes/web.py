from pathlib import Path
from typing import Final

from fastapi import APIRouter, Header, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from server.app.api.routes.health import HEALTH_PAYLOAD

APP_DIR = Path(__file__).resolve().parents[2]
TEMPLATES_DIR: Final[Path] = APP_DIR / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

ACTION_SUCCESS_PARTIAL: Final[str] = """
<div class="bg-green-50 text-green-700 p-4 rounded-xl border border-green-200 animate-pulse flex items-center justify-center gap-2">
    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" class="w-6 h-6">
        <path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
    <span class="font-bold">Action Successful!</span>
</div>
"""

router = APIRouter(tags=["web"])


def _layout_name(hx_request: str | None) -> str:
    return "layout/partial.html" if hx_request else "layout/app_shell.html"


def _render_page(
    request: Request, page_name: str, hx_request: str | None
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name=page_name,
        context={"layout_name": _layout_name(hx_request)},
    )


@router.get("/", response_class=HTMLResponse)
async def read_root(
    request: Request,
    hx_request: str | None = Header(default=None),
    accept: str | None = Header(default=None),
):
    if accept and "application/json" in accept and "text/html" not in accept:
        return JSONResponse(content=HEALTH_PAYLOAD)

    return _render_page(request, "pages/home/index.html", hx_request)


@router.get("/search", response_class=HTMLResponse)
async def read_search(request: Request, hx_request: str | None = Header(default=None)):
    return _render_page(request, "pages/search/index.html", hx_request)


@router.get("/profile", response_class=HTMLResponse)
async def read_profile(request: Request, hx_request: str | None = Header(default=None)):
    return _render_page(request, "pages/profile/index.html", hx_request)


@router.post("/api/action", response_class=HTMLResponse)
@router.post("/api/web/action", response_class=HTMLResponse, include_in_schema=False)
async def handle_htmx_action():
    return HTMLResponse(content=ACTION_SUCCESS_PARTIAL)
