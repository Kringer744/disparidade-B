"""
Cliente NocoDB Cloud (API v2).
Todas as operações de leitura/escrita no banco passam por aqui.
"""
import httpx
from typing import Any, Optional
from config import get_settings

settings = get_settings()

HEADERS = {
    "xc-token": settings.nocodb_api_key,
    "Content-Type": "application/json",
}
BASE = settings.nocodb_url.rstrip("/")


# ─── Tabelas (IDs carregados dinamicamente via table_ids.py) ────────────────
_TABLE_IDS: dict[str, str] = {}


def set_table_ids(ids: dict[str, str]):
    global _TABLE_IDS
    _TABLE_IDS = ids


def get_table_id(name: str) -> str:
    tid = _TABLE_IDS.get(name, "")
    if not tid:
        raise ValueError(f"Table ID para '{name}' não configurado. Rode setup_nocodb.py primeiro.")
    return tid


# ─── CRUD genérico ────────────────────────────────────────────────────────────

async def list_records(table_name: str, where: str = "", limit: int = 200, offset: int = 0) -> dict:
    tid = get_table_id(table_name)
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if where:
        params["where"] = where
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE}/api/v2/tables/{tid}/records", headers=HEADERS, params=params)
        r.raise_for_status()
        return r.json()


async def get_record(table_name: str, row_id: int) -> dict:
    tid = get_table_id(table_name)
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE}/api/v2/tables/{tid}/records/{row_id}", headers=HEADERS)
        r.raise_for_status()
        return r.json()


async def create_record(table_name: str, data: dict) -> dict:
    tid = get_table_id(table_name)
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{BASE}/api/v2/tables/{tid}/records", headers=HEADERS, json=data)
        r.raise_for_status()
        return r.json()


async def update_record(table_name: str, row_id: int, data: dict) -> dict:
    tid = get_table_id(table_name)
    async with httpx.AsyncClient() as client:
        r = await client.patch(
            f"{BASE}/api/v2/tables/{tid}/records/{row_id}",
            headers=HEADERS,
            json={**data, "Id": row_id},
        )
        r.raise_for_status()
        return r.json()


async def delete_record(table_name: str, row_id: int) -> bool:
    tid = get_table_id(table_name)
    async with httpx.AsyncClient() as client:
        r = await client.delete(
            f"{BASE}/api/v2/tables/{tid}/records",
            headers=HEADERS,
            json=[{"Id": row_id}],
        )
        r.raise_for_status()
        return True


async def create_many(table_name: str, rows: list[dict]) -> list[dict]:
    """Insere múltiplos registros de uma vez."""
    if not rows:
        return []
    tid = get_table_id(table_name)
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{BASE}/api/v2/tables/{tid}/records",
            headers=HEADERS,
            json=rows,
        )
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else [data]


# ─── Meta API (listar tabelas do base) ───────────────────────────────────────

async def list_tables(base_id: str) -> list[dict]:
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{BASE}/api/v1/db/meta/projects/{base_id}/tables",
            headers=HEADERS,
        )
        r.raise_for_status()
        return r.json().get("list", [])


async def create_table(base_id: str, title: str, columns: list[dict]) -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{BASE}/api/v1/db/meta/projects/{base_id}/tables",
            headers=HEADERS,
            json={"title": title, "columns": columns},
        )
        r.raise_for_status()
        return r.json()
