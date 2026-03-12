from fastapi import APIRouter
from typing import Optional
import nocodb_client as db
from serpapi_client import calculate_disparity

router = APIRouter(prefix="/disparidades", tags=["Disparidades"])


@router.get("/")
async def listar_disparidades(
    cliente_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    where_parts = []
    if cliente_id:
        where_parts.append(f"(cliente_id,eq,{cliente_id})")
    if status:
        where_parts.append(f"(status,eq,{status})")

    where = "~and".join(where_parts)
    result = await db.list_records("disparidades", where=where, limit=limit, offset=offset)
    return result.get("list", [])


@router.get("/dashboard")
async def dashboard_resumo():
    # Busca todas as disparidades recentes (últimas por cliente)
    result = await db.list_records("disparidades", limit=500)
    all_disp = result.get("list", [])

    # Agrupa por cliente_id, pega a mais recente
    latest: dict[int, dict] = {}
    for d in all_disp:
        cid = d.get("cliente_id")
        if cid is None:
            continue
        if cid not in latest or d.get("Id", 0) > latest[cid].get("Id", 0):
            latest[cid] = d

    clientes_result = await db.list_records("clientes", where="(ativo,eq,true)", limit=500)
    clientes = {c["Id"]: c for c in clientes_result.get("list", [])}

    # Para cada card, busca os preços da última busca e recalcula contagem de OTAs
    cards = []
    total_disparidade = 0

    for cid, d in latest.items():
        cliente = clientes.get(cid, {})
        st = d.get("status", "sem_dados")
        if st == "disparidade":
            total_disparidade += 1

        busca_id = d.get("busca_id")
        count_mais_baratas = 0
        count_mais_caras   = 0

        if busca_id and d.get("preco_direto"):
            precos_result = await db.list_records(
                "precos_ota",
                where=f"(busca_id,eq,{busca_id})",
                limit=50,
            )
            otas = precos_result.get("list", [])
            if otas:
                disp_calc = calculate_disparity(d["preco_direto"], otas)
                count_mais_baratas = disp_calc["count_mais_baratas"]
                count_mais_caras   = disp_calc["count_mais_caras"]

        cards.append({
            "cliente_id": cid,
            "nome": cliente.get("nome", "—"),
            "localizacao": cliente.get("localizacao", ""),
            "status": st,
            "preco_direto": d.get("preco_direto"),
            "menor_preco_ota": d.get("menor_preco_ota"),
            "ota_mais_barata": d.get("ota_mais_barata"),
            "diferenca_pct": d.get("diferenca_pct"),
            "diferenca_valor": d.get("diferenca_valor"),
            "ultima_busca_id": busca_id,
            "count_mais_baratas": count_mais_baratas,
            "count_mais_caras": count_mais_caras,
        })

    return {
        "total_clientes": len(clientes),
        "total_monitorados": len(cards),
        "total_disparidade": total_disparidade,
        "total_ok": len([c for c in cards if c["status"] == "ok"]),
        "total_sem_dados": len([c for c in cards if c["status"] == "sem_dados"]),
        "cards": sorted(cards, key=lambda x: x["status"] == "disparidade", reverse=True),
    }


@router.get("/historico/{cliente_id}")
async def historico_cliente(cliente_id: int, limit: int = 30):
    result = await db.list_records(
        "disparidades",
        where=f"(cliente_id,eq,{cliente_id})",
        limit=limit,
    )
    return result.get("list", [])


@router.get("/precos/{busca_id}")
async def precos_por_busca(busca_id: int):
    result = await db.list_records(
        "precos_ota",
        where=f"(busca_id,eq,{busca_id})",
        limit=100,
    )
    otas = result.get("list", [])
    return otas


@router.get("/comparacao/{busca_id}")
async def comparacao_por_busca(busca_id: int):
    """Retorna a comparação completa (mais baratas vs mais caras) de uma busca."""
    # Busca o preco_direto desta busca
    disp_result = await db.list_records(
        "disparidades",
        where=f"(busca_id,eq,{busca_id})",
        limit=1,
    )
    disp_list = disp_result.get("list", [])
    preco_direto = disp_list[0].get("preco_direto") if disp_list else None

    precos_result = await db.list_records(
        "precos_ota",
        where=f"(busca_id,eq,{busca_id})",
        limit=100,
    )
    otas = precos_result.get("list", [])

    if not preco_direto or not otas:
        return {"preco_direto": preco_direto, "otas_mais_baratas": [], "otas_mais_caras": [], "status": "sem_dados"}

    disp = calculate_disparity(preco_direto, otas)
    return {
        "preco_direto": preco_direto,
        "status": disp["status"],
        "count_mais_baratas": disp["count_mais_baratas"],
        "count_mais_caras":   disp["count_mais_caras"],
        "otas_mais_baratas":  disp["otas_mais_baratas"],
        "otas_mais_caras":    disp["otas_mais_caras"],
    }


@router.get("/recentes")
async def buscas_recentes(limit: int = 20):
    """Últimas buscas realizadas (histórico global)."""
    result = await db.list_records("buscas", limit=limit)
    buscas = result.get("list", [])

    # Enriquece com nome do cliente e status de disparidade
    output = []
    for b in buscas:
        cid = b.get("cliente_id")
        nome = b.get("query_manual") or "—"
        if cid:
            try:
                c = await db.get_record("clientes", cid)
                nome = c.get("nome", nome)
            except Exception:
                pass

        # Pega a disparidade associada
        d_result = await db.list_records(
            "disparidades",
            where=f"(busca_id,eq,{b['Id']})",
            limit=1,
        )
        d_list = d_result.get("list", [])
        disp = d_list[0] if d_list else {}

        output.append({
            "busca_id": b["Id"],
            "cliente_id": cid,
            "nome": nome,
            "check_in": b.get("check_in"),
            "check_out": b.get("check_out"),
            "adultos": b.get("adultos"),
            "created_at": b.get("CreatedAt"),
            "preco_direto": disp.get("preco_direto"),
            "menor_preco_ota": disp.get("menor_preco_ota"),
            "ota_mais_barata": disp.get("ota_mais_barata"),
            "diferenca_pct": disp.get("diferenca_pct"),
            "status": disp.get("status", "sem_dados"),
        })

    return output
