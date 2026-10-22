import time
import json
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from app.config import settings
from app.database import Base, engine
from app.routers import (
    auth,
    catalog,
    rfid,
    circulation,
    tracking,
    monitoring
)

# Configure structured JSON logger (CloudWatch / ELK format)
logger = logging.getLogger("rfid_cloud")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(message)s"))
logger.handlers = [handler]

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB schema on startup
    Base.metadata.create_all(bind=engine)
    logger.info(json.dumps({
        "event": "startup",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "db_url": settings.DATABASE_URL.split("@")[-1] if "@" in settings.DATABASE_URL else settings.DATABASE_URL
    }))
    yield
    logger.info(json.dumps({"event": "shutdown"}))

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Container-native RFID Library Management Backend with HMAC Edge Ingest, Real-time Circulation, and Cloud Metrics",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Structured Request Logging Middleware
@app.middleware("http")
async def structured_logging_middleware(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration_ms = round((time.time() - start_time) * 1000, 2)

    # Do not log spam for high-frequency health/metrics scraping unless debug
    if request.url.path not in ["/health", "/metrics"] or settings.DEBUG:
        log_payload = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            "client_ip": request.client.host if request.client else "unknown"
        }
        logger.info(json.dumps(log_payload))

    return response

# Include Feature Routers
app.include_router(auth.router)
app.include_router(catalog.router)
app.include_router(rfid.router)
app.include_router(circulation.router)
app.include_router(tracking.router)
app.include_router(monitoring.router)

# Serve Frontend static directory if present
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend")
if os.path.exists(frontend_dir):
    @app.get("/style.css", include_in_schema=False)
    def get_style():
        return FileResponse(os.path.join(frontend_dir, "style.css"), media_type="text/css")

    @app.get("/app.js", include_in_schema=False)
    def get_script():
        return FileResponse(os.path.join(frontend_dir, "app.js"), media_type="application/javascript")

    @app.get("/background.jpg", include_in_schema=False)
    def get_background():
        return FileResponse(os.path.join(frontend_dir, "background.jpg"), media_type="image/jpeg")

    @app.get("/", include_in_schema=False)
    def root_redirect():
        return FileResponse(os.path.join(frontend_dir, "index.html"))

    app.mount("/dashboard", StaticFiles(directory=frontend_dir, html=True), name="frontend")

