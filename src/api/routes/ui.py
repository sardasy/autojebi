from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "web" / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(tags=["ui"])


@router.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/ui/dashboard")


@router.get("/ui/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def page_dashboard(request: Request):
    return templates.TemplateResponse(request, "dashboard.html", {})


@router.get("/ui/bids", response_class=HTMLResponse, include_in_schema=False)
async def page_bids(request: Request):
    return templates.TemplateResponse(request, "bids.html", {})


@router.get("/ui/rules", response_class=HTMLResponse, include_in_schema=False)
async def page_rules(request: Request):
    return templates.TemplateResponse(request, "rules.html", {})


@router.get("/ui/awards", response_class=HTMLResponse, include_in_schema=False)
async def page_awards(request: Request):
    return templates.TemplateResponse(request, "awards.html", {})
