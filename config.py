from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    serpapi_key: str
    nocodb_url: str = "https://app.nocodb.com"
    nocodb_api_key: str
    nocodb_base_id: str
    scheduler_time: str = "08:00"
    default_currency: str = "BRL"
    default_language: str = "pt"
    default_country: str = "br"
    openrouter_key: str = ""

    # IDs das tabelas (preenchidos pelo setup_nocodb.py)
    table_clientes: str = ""
    table_buscas: str = ""
    table_precos_ota: str = ""
    table_disparidades: str = ""
    table_relatorios: str = ""

    class Config:
        env_file = "../.env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
