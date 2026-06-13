import logging
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.redis_client import get_redis
from app.routers import auth, portfolio, stocks

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai-investor")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(
    title="AI Investor Assistant",
    description="SaaS-платформа для управления портфелем и AI-анализа акций",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.include_router(auth.router)
app.include_router(portfolio.router)
app.include_router(stocks.router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})


def serve_page(filename: str) -> FileResponse:
    return FileResponse(STATIC_DIR / filename)


@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    redis_ok = get_redis() is not None
    return {"status": "ok", "database": "ok", "redis": "ok" if redis_ok else "unavailable"}


@app.get("/")
def landing():
    return serve_page("index.html")


@app.get("/login")
def login_page():
    return serve_page("login.html")


@app.get("/register")
def register_page():
    return serve_page("register.html")


@app.get("/dashboard")
def dashboard_page():
    return serve_page("dashboard.html")


@app.get("/portfolio")
def portfolio_page():
    return serve_page("portfolio.html")


@app.get("/analysis")
def analysis_page():
    return serve_page("analysis.html")
