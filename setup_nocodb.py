"""
Setup automatico das tabelas no NocoDB Cloud.
Execute UMA VEZ antes de rodar o sistema: python setup_nocodb.py
"""
import asyncio
import json
import os
import sys
import httpx
from dotenv import load_dotenv

# Fix encoding on Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

load_dotenv("../.env")

NOCODB_URL = os.getenv("NOCODB_URL", "https://app.nocodb.com")
NOCODB_API_KEY = os.getenv("NOCODB_API_KEY")
NOCODB_BASE_ID = os.getenv("NOCODB_BASE_ID")
TABLE_IDS_FILE = os.path.join(os.path.dirname(__file__), "table_ids.json")

HEADERS = {
    "xc-token": NOCODB_API_KEY,
    "Content-Type": "application/json",
}

TABLES_SCHEMA = {
    "clientes": {
        "title": "clientes",
        "columns": [
            {"title": "nome", "uidt": "SingleLineText"},
            {"title": "localizacao", "uidt": "SingleLineText"},
            {"title": "serpapi_query", "uidt": "SingleLineText"},
            {"title": "website", "uidt": "URL"},
            {"title": "ativo", "uidt": "Checkbox"},
        ],
    },
    "buscas": {
        "title": "buscas",
        "columns": [
            {"title": "cliente_id", "uidt": "Number"},
            {"title": "query_manual", "uidt": "SingleLineText"},
            {"title": "check_in", "uidt": "Date"},
            {"title": "check_out", "uidt": "Date"},
            {"title": "adultos", "uidt": "Number"},
            {"title": "quartos", "uidt": "Number"},
        ],
    },
    "precos_ota": {
        "title": "precos_ota",
        "columns": [
            {"title": "busca_id", "uidt": "Number"},
            {"title": "cliente_id", "uidt": "Number"},
            {"title": "ota_nome", "uidt": "SingleLineText"},
            {"title": "preco_total", "uidt": "Currency"},
            {"title": "moeda", "uidt": "SingleLineText"},
            {"title": "tipo_quarto", "uidt": "SingleLineText"},
            {"title": "link", "uidt": "URL"},
            {"title": "is_preco_direto", "uidt": "Checkbox"},
        ],
    },
    "disparidades": {
        "title": "disparidades",
        "columns": [
            {"title": "busca_id", "uidt": "Number"},
            {"title": "cliente_id", "uidt": "Number"},
            {"title": "preco_direto", "uidt": "Currency"},
            {"title": "menor_preco_ota", "uidt": "Currency"},
            {"title": "ota_mais_barata", "uidt": "SingleLineText"},
            {"title": "maior_preco_ota", "uidt": "Currency"},
            {"title": "diferenca_valor", "uidt": "Currency"},
            {"title": "diferenca_pct", "uidt": "Number"},
            {
                "title": "status",
                "uidt": "SingleSelect",
                "dtxp": "'ok','disparidade','sem_dados'",
            },
        ],
    },
    "relatorios": {
        "title": "relatorios",
        "columns": [
            {"title": "cliente_id", "uidt": "Number"},
            {"title": "periodo_inicio", "uidt": "Date"},
            {"title": "periodo_fim", "uidt": "Date"},
            {"title": "pdf_path", "uidt": "SingleLineText"},
        ],
    },
}


async def get_existing_tables() -> dict[str, str]:
    """Retorna {nome: id} das tabelas já existentes no base."""
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{NOCODB_URL}/api/v1/db/meta/projects/{NOCODB_BASE_ID}/tables",
            headers=HEADERS,
        )
        if r.status_code == 404:
            # Tenta endpoint alternativo para versões mais novas
            r = await client.get(
                f"{NOCODB_URL}/api/v1/meta/bases/{NOCODB_BASE_ID}/tables",
                headers=HEADERS,
            )
        r.raise_for_status()
        tables = r.json().get("list", [])
        return {t["title"]: t["id"] for t in tables}


async def create_table(title: str, schema: dict) -> str:
    """Cria tabela e retorna seu ID."""
    async with httpx.AsyncClient() as client:
        # Tenta endpoint v1 (padrão Cloud)
        r = await client.post(
            f"{NOCODB_URL}/api/v1/db/meta/projects/{NOCODB_BASE_ID}/tables",
            headers=HEADERS,
            json=schema,
        )
        if r.status_code in (404, 422):
            r = await client.post(
                f"{NOCODB_URL}/api/v1/meta/bases/{NOCODB_BASE_ID}/tables",
                headers=HEADERS,
                json=schema,
            )
        r.raise_for_status()
        return r.json()["id"]


async def main():
    print("=" * 55)
    print("  Setup NocoDB - Sistema de Disparidade de Hoteis")
    print("=" * 55)
    print(f"  Base: {NOCODB_BASE_ID}")
    print(f"  URL:  {NOCODB_URL}")
    print()

    if not NOCODB_API_KEY or not NOCODB_BASE_ID:
        print("ERRO: Configure NOCODB_API_KEY e NOCODB_BASE_ID no .env")
        sys.exit(1)

    print("-> Verificando tabelas existentes...")
    existing = await get_existing_tables()
    print(f"  Tabelas encontradas: {list(existing.keys())}")
    print()

    ids: dict[str, str] = {}

    for table_key, schema in TABLES_SCHEMA.items():
        title = schema["title"]
        if title in existing:
            ids[table_key] = existing[title]
            print(f"  [OK] {title:20s} ja existe  [{existing[title]}]")
        else:
            print(f"  [+] Criando {title}...", end=" ")
            tid = await create_table(title, schema)
            ids[table_key] = tid
            print(f"OK [{tid}]")

    # Salva IDs em arquivo local
    with open(TABLE_IDS_FILE, "w") as f:
        json.dump(ids, f, indent=2)

    print()
    print(f"[OK] table_ids.json salvo em {TABLE_IDS_FILE}")
    print()
    print("Setup concluído! Agora execute:")
    print("  cd backend && uvicorn main:app --reload")
    print()
    print("IDs das tabelas:")
    for k, v in ids.items():
        print(f"  {k:20s} → {v}")


if __name__ == "__main__":
    asyncio.run(main())
