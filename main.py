import os
import json
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import get_settings
import nocodb_client as db
from scheduler import start_scheduler, stop_scheduler
from routes import clientes, buscas, disparidades, relatorios, ai

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")
settings = get_settings()

TABLE_IDS_FILE = os.path.join(os.path.dirname(__file__), "table_ids.json")
REPORTS_DIR = "/tmp/reports" if os.getenv("VERCEL") else os.path.join(os.path.dirname(__file__), "reports")


def load_table_ids():
    if os.path.exists(TABLE_IDS_FILE):
        with open(TABLE_IDS_FILE) as f:
            ids = json.load(f)
        db.set_table_ids(ids)
        logger.info(f"Table IDs carregados: {ids}")
        return True
    logger.warning("table_ids.json não encontrado — execute setup_nocodb.py primeiro!")
    return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(REPORTS_DIR, exist_ok=True)
    load_table_ids()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="Sistema de Disparidade de Hotéis",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(clientes.router)
app.include_router(buscas.router)
app.include_router(disparidades.router)
app.include_router(relatorios.router)
app.include_router(ai.router)


@app.get("/")
async def root():
    return {
        "status": "online",
        "version": "1.0.0",
        "scheduler_time": settings.scheduler_time,
    }


@app.get("/health")
async def health():
    return {"status": "ok"}
