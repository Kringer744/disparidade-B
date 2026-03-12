"""
Rota /ai — Analise e busca com IA (Agno + OpenRouter + SERPAPI).
"""
import os
import asyncio
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import nocodb_client as db
from serpapi_client import calculate_disparity

router = APIRouter(prefix="/ai", tags=["IA"])

REPORTS_DIR = "/tmp/reports" if os.getenv("VERCEL") else os.path.join(os.path.dirname(__file__), "..", "reports")


class AnaliseRequest(BaseModel):
    busca_id: int
    hotel_name: Optional[str] = None


class BuscaIARequest(BaseModel):
    hotel_name: str
    check_in: str
    check_out: str
    adultos: int = 2


class RelatorioPDFIARequest(BaseModel):
    hotel_name: str
    analise: str
    check_in: str = ""
    check_out: str = ""


@router.post("/analisar")
async def analisar_busca(body: AnaliseRequest):
    """
    Analisa uma busca existente com IA (dados já no banco).
    """
    from ai_agent import analisar_disparidade
    import ai_history

    disp_result = await db.list_records(
        "disparidades",
        where=f"(busca_id,eq,{body.busca_id})",
        limit=1,
    )
    disp_list = disp_result.get("list", [])
    if not disp_list:
        raise HTTPException(404, "Busca não encontrada")

    disp = disp_list[0]
    preco_direto = disp.get("preco_direto")
    if not preco_direto:
        raise HTTPException(400, "Sem preço direto para análise")

    precos_result = await db.list_records(
        "precos_ota",
        where=f"(busca_id,eq,{body.busca_id})",
        limit=100,
    )
    otas = precos_result.get("list", [])
    if not otas:
        raise HTTPException(400, "Sem dados de OTAs para análise")

    calc = calculate_disparity(preco_direto, otas)

    busca_result = await db.get_record("buscas", body.busca_id)
    check_in  = busca_result.get("check_in", "") if busca_result else ""
    check_out = busca_result.get("check_out", "") if busca_result else ""
    nights = 1
    if check_in and check_out:
        from datetime import date
        try:
            nights = max(1, (date.fromisoformat(check_out) - date.fromisoformat(check_in)).days)
        except Exception:
            pass

    hotel_name = body.hotel_name or "Hotel"
    cliente_id = disp.get("cliente_id")
    if cliente_id:
        try:
            c = await db.get_record("clientes", cliente_id)
            hotel_name = c.get("nome", hotel_name)
        except Exception:
            pass

    analise_result = await analisar_disparidade(
        hotel_name=hotel_name,
        preco_direto=preco_direto,
        otas_mais_baratas=calc["otas_mais_baratas"],
        otas_mais_caras=calc["otas_mais_caras"],
        check_in=check_in,
        check_out=check_out,
        nights=nights,
    )

    # analisar_disparidade retorna (content, tokens)
    if isinstance(analise_result, tuple):
        analise, tokens = analise_result
    else:
        analise, tokens = analise_result, {"input": 0, "output": 0, "total": 0}

    # Salva no histórico local com tokens
    try:
        ai_history.save_analysis(
            hotel_name=hotel_name,
            check_in=check_in,
            check_out=check_out,
            adultos=2,
            analise=analise,
            tipo="analise_busca",
            tokens=tokens,
        )
    except Exception:
        pass

    return {
        "busca_id":   body.busca_id,
        "hotel_name": hotel_name,
        "status":     calc["status"],
        "analise":    analise,
        "tokens":     tokens,
    }


@router.post("/buscar-analisar")
async def buscar_e_analisar_ia(body: BuscaIARequest):
    """
    O agente IA faz a busca via SERPAPI E analisa os resultados (busca completa com IA).
    """
    from ai_agent import busca_e_analisa
    import ai_history

    result = await busca_e_analisa(
        hotel_name=body.hotel_name,
        check_in=body.check_in,
        check_out=body.check_out,
        adultos=body.adultos,
    )

    tokens = result.get("tokens", {"input": 0, "output": 0, "total": 0})

    # Salva automaticamente no histórico com tokens
    try:
        ai_history.save_analysis(
            hotel_name=body.hotel_name,
            check_in=body.check_in,
            check_out=body.check_out,
            adultos=body.adultos,
            analise=result["analise"],
            tipo="busca_ia",
            tokens=tokens,
        )
    except Exception:
        pass

    return {
        "hotel_name": body.hotel_name,
        "analise":    result["analise"],
        "tokens":     tokens,
    }


@router.post("/relatorio-pdf")
async def relatorio_pdf_ia(body: RelatorioPDFIARequest):
    """
    Gera PDF com a análise de IA e retorna link para download.
    Reutiliza o endpoint /relatorios/download/{filename} para servir o arquivo.
    """
    import pdf_generator as pg

    safe_name = (
        body.hotel_name
        .replace(" ", "_")
        .replace("/", "_")
        .replace("\\", "_")[:30]
    )
    filename = f"analise_ia_{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    output_path = os.path.join(REPORTS_DIR, filename)

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        pg.generate_ai_pdf,
        body.hotel_name,
        body.analise,
        body.check_in,
        body.check_out,
        output_path,
    )

    return {"filename": filename, "path": f"/relatorios/download/{filename}"}


@router.get("/historico")
async def historico_ia(limit: int = 50):
    """Lista histórico de análises com IA (armazenado localmente)."""
    import ai_history
    return ai_history.get_history(limit)


@router.get("/historico/{entry_id}")
async def get_analise_historico(entry_id: int):
    """Retorna análise completa de uma entrada do histórico IA."""
    import ai_history
    entry = ai_history.get_analysis(entry_id)
    if not entry:
        raise HTTPException(404, "Análise não encontrada")
    return entry


@router.get("/tokens")
async def get_token_stats():
    """
    Retorna estatísticas acumuladas de uso de tokens das análises IA.
    Inclui custo estimado (gpt-4o-mini via OpenRouter).
    """
    import ai_history
    return ai_history.get_token_stats()
