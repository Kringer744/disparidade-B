from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import nocodb_client as db

router = APIRouter(prefix="/clientes", tags=["Clientes"])


class ClienteCreate(BaseModel):
    nome: str
    localizacao: str
    serpapi_query: str
    website: Optional[str] = ""
    preco_direto_manual: Optional[float] = None  # Preço oficial do site do hotel
    ativo: bool = True


class ClienteUpdate(BaseModel):
    nome: Optional[str] = None
    localizacao: Optional[str] = None
    serpapi_query: Optional[str] = None
    website: Optional[str] = None
    preco_direto_manual: Optional[float] = None
    ativo: Optional[bool] = None


@router.get("/")
async def listar_clientes(apenas_ativos: bool = False):
    where = "(ativo,eq,true)" if apenas_ativos else ""
    result = await db.list_records("clientes", where=where, limit=500)
    return result.get("list", [])


@router.get("/{cliente_id}")
async def obter_cliente(cliente_id: int):
    try:
        return await db.get_record("clientes", cliente_id)
    except Exception:
        raise HTTPException(404, "Cliente não encontrado")


@router.post("/", status_code=201)
async def criar_cliente(body: ClienteCreate):
    return await db.create_record("clientes", body.model_dump())


@router.patch("/{cliente_id}")
async def atualizar_cliente(cliente_id: int, body: ClienteUpdate):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    return await db.update_record("clientes", cliente_id, data)


@router.delete("/{cliente_id}", status_code=204)
async def deletar_cliente(cliente_id: int):
    await db.delete_record("clientes", cliente_id)
