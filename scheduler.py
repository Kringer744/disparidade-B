"""
Agendador diário — executa busca de preços para todos os clientes ativos.
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from config import get_settings
import httpx
import logging

logger = logging.getLogger("scheduler")
settings = get_settings()
scheduler = AsyncIOScheduler()


async def _run_daily_search():
    logger.info("Scheduler: iniciando busca diária para todos os clientes...")
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post("http://localhost:8000/buscar/todos-clientes")
            data = r.json()
            logger.info(f"Busca diária concluída: {data.get('total')} clientes processados")
    except Exception as e:
        logger.error(f"Erro na busca diária: {e}")


def start_scheduler():
    hour, minute = settings.scheduler_time.split(":")
    scheduler.add_job(
        _run_daily_search,
        CronTrigger(hour=int(hour), minute=int(minute)),
        id="daily_search",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(f"Scheduler iniciado — busca diária às {settings.scheduler_time}")


def stop_scheduler():
    scheduler.shutdown()
