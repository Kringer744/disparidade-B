"""
Integração com SERPAPI - Google Hotels.
Busca preços finais (com taxas) de OTAs para um hotel específico.

O SERPAPI tem dois modos de resposta:
  1. Lista de propriedades (quando busca geral) -> 'properties' list
  2. Hotel direto (quando busca específica)     -> campos no nível raiz
"""
import httpx
from datetime import date
from typing import Optional
from config import get_settings

settings = get_settings()

SERPAPI_URL = "https://serpapi.com/search.json"

# Fontes conhecidas como preço direto do hotel
DIRECT_PRICE_SOURCES = {
    "official site",
    "site oficial",
    "hotel website",
    "book direct",
    "reserva direta",
    "fasano.com",
    "marriott.com",
    "hilton.com",
    "ihg.com",
    "wyndham.com",
    "hyatt.com",
    "radisson.com",
    "accorhotels.com",
    "bestwestern.com",
}


def _is_direct_source(source_name: str, hotel_name: str = "") -> bool:
    s = source_name.lower()
    # Verifica apenas keywords explícitas de site oficial
    return any(kw in s for kw in DIRECT_PRICE_SOURCES)


async def search_hotel_prices(
    query: str,
    check_in: date,
    check_out: date,
    adults: int = 2,
    rooms: int = 1,
    currency: str = "BRL",
) -> dict:
    params = {
        "engine": "google_hotels",
        "q": query,
        "check_in_date": check_in.isoformat(),
        "check_out_date": check_out.isoformat(),
        "adults": adults,
        "rooms": rooms,
        "currency": currency,
        "hl": settings.default_language,
        "gl": settings.default_country,
        "api_key": settings.serpapi_key,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(SERPAPI_URL, params=params)
        r.raise_for_status()
        data = r.json()

    return _parse_response(data, query, check_in, check_out)


def _parse_response(data: dict, query: str, check_in: date, check_out: date) -> dict:
    nights = (check_out - check_in).days or 1

    # API retornou erro
    if "error" in data:
        return {"found": False, "query": query, "error": data["error"], "otas": [], "preco_direto": None}

    # Modo 1: lista de propriedades (busca geral)
    properties = data.get("properties", [])
    if properties:
        hotel = properties[0]
        hotel_name = hotel.get("name", query)
        return _extract_from_hotel(hotel, hotel_name, query, nights, check_in, check_out)

    # Modo 2: hotel único retornado diretamente (busca específica)
    hotel_name = data.get("name")
    if hotel_name:
        return _extract_from_hotel(data, hotel_name, query, nights, check_in, check_out)

    return {"found": False, "query": query, "error": "Nenhum hotel encontrado", "otas": [], "preco_direto": None}


def _extract_from_hotel(hotel: dict, hotel_name: str, query: str, nights: int,
                         check_in: date, check_out: date) -> dict:
    otas: list[dict] = []
    preco_direto: Optional[float] = None
    direct_source: Optional[str] = None

    # Combina prices + featured_prices (sem duplicatas por source)
    all_prices = list(hotel.get("prices", []))
    seen_sources = {p.get("source") for p in all_prices}
    for fp in hotel.get("featured_prices", []):
        if fp.get("source") not in seen_sources:
            all_prices.append(fp)

    for price_info in all_prices:
        source = price_info.get("source", "")
        rate = price_info.get("rate_per_night", {})
        night_price = rate.get("extracted_lowest")
        if not night_price:
            continue

        final_price = round(night_price * nights, 2)
        is_direct = _is_direct_source(source, hotel_name)

        entry = {
            "ota_nome": source,
            "preco_total": final_price,
            "moeda": "BRL",
            "link": price_info.get("link", ""),
            "tipo_quarto": price_info.get("room_type", ""),
            "is_preco_direto": is_direct,
        }
        otas.append(entry)

        if is_direct and preco_direto is None:
            preco_direto = final_price
            direct_source = source

    # Referência: se sem preço direto, usa total_rate como referência
    # (é o menor agregado do Google — serve como baseline)
    if preco_direto is None:
        top_rate = hotel.get("total_rate", {}) or hotel.get("rate_per_night", {})
        extracted = top_rate.get("extracted_lowest")
        if extracted:
            preco_direto = round(extracted * nights, 2)
            direct_source = "Google Hotels (referência)"

    images = hotel.get("images", [{}])
    thumb = images[0].get("thumbnail", "") if images else ""

    return {
        "found": True,
        "hotel_name": hotel_name,
        "query": query,
        "check_in": check_in.isoformat(),
        "check_out": check_out.isoformat(),
        "nights": nights,
        "otas": otas,
        "preco_direto": preco_direto,
        "direct_source": direct_source,
        "thumbnail": thumb,
        "rating": hotel.get("overall_rating"),
        "reviews": hotel.get("reviews"),
    }


def calculate_disparity(preco_direto: float, otas: list[dict]) -> dict:
    """
    Disparidade = quando OTA vende MAIS BARATO que o preço oficial do hotel.
    Retorna a contagem e lista de OTAs mais baratas e mais caras.
    """
    otas_sem_direto = [o for o in otas if not o["is_preco_direto"]]

    empty = {
        "menor_preco_ota": None,
        "ota_mais_barata": None,
        "maior_preco_ota": None,
        "diferenca_valor": None,
        "diferenca_pct": None,
        "status": "sem_dados",
        "otas_mais_baratas": [],
        "otas_mais_caras": [],
        "count_mais_baratas": 0,
        "count_mais_caras": 0,
    }

    if not otas_sem_direto or not preco_direto:
        return empty

    mais_baratas = []
    mais_caras = []

    for ota in otas_sem_direto:
        diff = preco_direto - ota["preco_total"]          # positivo = OTA mais barata
        pct_ota = round((diff / preco_direto) * 100, 2)
        entry = {
            "ota_nome": ota["ota_nome"],
            "preco_total": ota["preco_total"],
            "diferenca_valor": round(diff, 2),
            "diferenca_pct": pct_ota,
            "link": ota.get("link", ""),
        }
        if diff > 0:
            mais_baratas.append(entry)   # OTA mais barata = DISPARIDADE
        else:
            mais_caras.append(entry)     # OTA mais cara = OK

    mais_baratas.sort(key=lambda x: x["diferenca_pct"], reverse=True)  # maior desconto primeiro
    mais_caras.sort(key=lambda x: x["diferenca_pct"])                   # mais caro primeiro

    menor = min(otas_sem_direto, key=lambda x: x["preco_total"])
    maior = max(otas_sem_direto, key=lambda x: x["preco_total"])
    diferenca = preco_direto - menor["preco_total"]
    pct = round((diferenca / preco_direto) * 100, 2)

    status = "disparidade" if mais_baratas else "ok"

    return {
        "menor_preco_ota": menor["preco_total"],
        "ota_mais_barata": menor["ota_nome"],
        "maior_preco_ota": maior["preco_total"],
        "diferenca_valor": round(diferenca, 2),
        "diferenca_pct": pct,
        "status": status,
        "otas_mais_baratas": mais_baratas,
        "otas_mais_caras": mais_caras,
        "count_mais_baratas": len(mais_baratas),
        "count_mais_caras": len(mais_caras),
    }
