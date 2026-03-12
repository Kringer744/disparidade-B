from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from datetime import date, datetime
import os
import nocodb_client as db
from routes.disparidades import dashboard_resumo

router = APIRouter(prefix="/relatorios", tags=["Relatórios"])

REPORTS_DIR = "/tmp/reports" if os.getenv("VERCEL") else os.path.join(os.path.dirname(__file__), "..", "reports")


class RelatorioRequest(BaseModel):
    cliente_id: int | None = None   # None = todos
    periodo_inicio: date
    periodo_fim: date


@router.post("/gerar")
async def gerar_relatorio(body: RelatorioRequest):
    from pdf_generator import generate_pdf

    dashboard = await dashboard_resumo()

    # Filtra se cliente específico
    if body.cliente_id:
        dashboard["cards"] = [
            c for c in dashboard["cards"] if c["cliente_id"] == body.cliente_id
        ]

    # Busca detalhes (OTAs) da última busca de cada cliente
    detalhes = []
    for card in dashboard["cards"]:
        busca_id = card.get("ultima_busca_id")
        if not busca_id:
            continue
        result = await db.list_records(
            "precos_ota", where=f"(busca_id,eq,{busca_id})", limit=50
        )
        otas = result.get("list", [])
        detalhes.append({
            "nome": card["nome"],
            "localizacao": card["localizacao"],
            "status": card["status"],
            "preco_direto": card["preco_direto"],
            "menor_preco_ota": card["menor_preco_ota"],
            "ota_mais_barata": card["ota_mais_barata"],
            "diferenca_pct": card["diferenca_pct"],
            "otas": otas,
        })

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"relatorio_{timestamp}.pdf"
    path = os.path.join(REPORTS_DIR, filename)

    generate_pdf(
        dashboard_data=dashboard,
        detalhes=detalhes,
        periodo_inicio=body.periodo_inicio.strftime("%d/%m/%Y"),
        periodo_fim=body.periodo_fim.strftime("%d/%m/%Y"),
        output_path=path,
    )

    # Salva registro no NocoDB
    await db.create_record("relatorios", {
        "cliente_id": body.cliente_id,
        "periodo_inicio": body.periodo_inicio.isoformat(),
        "periodo_fim": body.periodo_fim.isoformat(),
        "pdf_path": filename,
    })

    return {"filename": filename, "path": f"/relatorios/download/{filename}"}


@router.get("/download/{filename}")
async def download_relatorio(filename: str):
    path = os.path.join(REPORTS_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(404, "Relatório não encontrado")
    return FileResponse(path, media_type="application/pdf", filename=filename)


@router.get("/")
async def listar_relatorios():
    result = await db.list_records("relatorios", limit=100)
    return result.get("list", [])
