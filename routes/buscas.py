"""
Rota /buscar — executa busca de preços e salva disparidade no NocoDB.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import date, timedelta
from typing import Optional
import nocodb_client as db
from serpapi_client import search_hotel_prices, calculate_disparity
from config import get_settings

settings = get_settings()
router = APIRouter(prefix="/buscar", tags=["Buscas"])


class BuscaRequest(BaseModel):
    cliente_id: Optional[int] = None   # Se não informar, usa query manual
    query: Optional[str] = None        # Nome manual do hotel
    check_in: date
    check_out: date
    adultos: int = 2
    quartos: int = 1
    currency: str = "BRL"


@router.post("/")
async def executar_busca(body: BuscaRequest):
    """
    Busca preços de um hotel. Pode ser por cliente_id (cadastrado)
    ou por query manual (nome digitado).
    """
    if not body.cliente_id and not body.query:
        raise HTTPException(400, "Informe cliente_id ou query")

    # Determina o termo de busca
    preco_manual = None
    if body.cliente_id:
        cliente = await db.get_record("clientes", body.cliente_id)
        if not cliente:
            raise HTTPException(404, "Cliente não encontrado")
        query = cliente.get("serpapi_query") or cliente.get("nome")
        cliente_id = body.cliente_id
        preco_manual = cliente.get("preco_direto_manual")  # preço oficial cadastrado
    else:
        query = body.query
        cliente_id = None

    # Salva a busca
    busca_data = {
        "cliente_id": cliente_id,
        "query_manual": query if not cliente_id else None,
        "check_in": body.check_in.isoformat(),
        "check_out": body.check_out.isoformat(),
        "adultos": body.adultos,
        "quartos": body.quartos,
    }
    busca = await db.create_record("buscas", busca_data)
    busca_id = busca.get("Id") or busca.get("id")

    # Chama SERPAPI
    resultado = await search_hotel_prices(
        query=query,
        check_in=body.check_in,
        check_out=body.check_out,
        adults=body.adultos,
        rooms=body.quartos,
        currency=body.currency,
    )

    if not resultado["found"]:
        return {"busca_id": busca_id, "found": False, "error": resultado.get("error")}

    # Salva preços das OTAs
    otas = resultado["otas"]
    # Prioridade: preço manual cadastrado > preço detectado pelo SERPAPI
    preco_direto = preco_manual if preco_manual else resultado["preco_direto"]
    direct_source = "Preço cadastrado manualmente" if preco_manual else resultado.get("direct_source")

    if otas:
        rows = [
            {
                "busca_id": busca_id,
                "cliente_id": cliente_id,
                "ota_nome": o["ota_nome"],
                "preco_total": o["preco_total"],
                "moeda": o.get("moeda", "BRL"),
                "tipo_quarto": o.get("tipo_quarto", ""),
                "link": o.get("link", ""),
                "is_preco_direto": o["is_preco_direto"],
            }
            for o in otas
        ]
        await db.create_many("precos_ota", rows)

    # Calcula e salva disparidade
    disp = calculate_disparity(preco_direto, otas)
    disparidade_data = {
        "busca_id": busca_id,
        "cliente_id": cliente_id,
        "preco_direto": preco_direto,
        "menor_preco_ota": disp["menor_preco_ota"],
        "ota_mais_barata": disp["ota_mais_barata"],
        "maior_preco_ota": disp["maior_preco_ota"],
        "diferenca_valor": disp["diferenca_valor"],
        "diferenca_pct": disp["diferenca_pct"],
        "status": disp["status"],
    }
    await db.create_record("disparidades", disparidade_data)

    return {
        "busca_id": busca_id,
        "found": True,
        "hotel_name": resultado.get("hotel_name"),
        "thumbnail": resultado.get("thumbnail"),
        "rating": resultado.get("rating"),
        "check_in": resultado["check_in"],
        "check_out": resultado["check_out"],
        "nights": resultado["nights"],
        "preco_direto": preco_direto,
        "direct_source": direct_source,
        "otas": otas,
        "disparidade": disp,
    }


@router.post("/todos-clientes")
async def buscar_todos_clientes(
    check_in: date = None,
    check_out: date = None,
    adultos: int = 2,
):
    """Dispara busca para todos os clientes ativos (usado pelo scheduler)."""
    if not check_in:
        from datetime import date as d, timedelta
        check_in = d.today() + timedelta(days=30)
        check_out = check_in + timedelta(days=1)

    result = await db.list_records("clientes", where="(ativo,eq,true)", limit=500)
    clientes = result.get("list", [])

    resultados = []
    for c in clientes:
        try:
            req = BuscaRequest(
                cliente_id=c["Id"],
                check_in=check_in,
                check_out=check_out,
                adultos=adultos,
            )
            r = await executar_busca(req)
            resultados.append({"cliente": c["nome"], "status": "ok", "disparidade": r.get("disparidade")})
        except Exception as e:
            resultados.append({"cliente": c.get("nome"), "status": "erro", "erro": str(e)})

    return {"total": len(clientes), "resultados": resultados}
