"""
Storage simples (JSON em disco) para histórico de análises da IA.
Não requer NocoDB — persiste em arquivo local backend/data/ai_history.json.
"""
import json
import os
import time
from typing import Any, Dict, List, Optional

_DATA_DIR = "/tmp/data" if os.getenv("VERCEL") else os.path.join(os.path.dirname(__file__), "data")
_HISTORY_FILE = os.path.join(_DATA_DIR, "ai_history.json")

# Custo aproximado gpt-4o-mini via OpenRouter (USD por 1M tokens)
_COST_INPUT_PER_M  = 0.15   # $0.15/1M tokens de entrada
_COST_OUTPUT_PER_M = 0.60   # $0.60/1M tokens de saída
_BRL_RATE          = 5.80   # taxa BRL/USD aproximada


def _load() -> List[Dict[str, Any]]:
    try:
        with open(_HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _persist(data: List[Dict[str, Any]]) -> None:
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_analysis(
    hotel_name: str,
    check_in: str,
    check_out: str,
    adultos: int,
    analise: str,
    tipo: str = "busca_ia",     # "busca_ia" ou "analise_busca"
    tokens: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """Salva análise no histórico local. Retorna o entry criado."""
    data = _load()
    entry: Dict[str, Any] = {
        "id": int(time.time() * 1000),
        "tipo": tipo,
        "hotel_name": hotel_name,
        "check_in": check_in,
        "check_out": check_out,
        "adultos": adultos,
        "analise": analise,
        "tokens": tokens or {"input": 0, "output": 0, "total": 0},
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    data.insert(0, entry)   # mais recente primeiro
    _persist(data[:200])    # mantém os últimos 200
    return entry


def get_history(limit: int = 50) -> List[Dict[str, Any]]:
    """Retorna lista de análises com prévia do texto."""
    records = _load()[:limit]
    return [
        {
            "id": r["id"],
            "tipo": r.get("tipo", "busca_ia"),
            "hotel_name": r["hotel_name"],
            "check_in": r["check_in"],
            "check_out": r["check_out"],
            "adultos": r.get("adultos", 2),
            "tokens": r.get("tokens", {"input": 0, "output": 0, "total": 0}),
            "created_at": r["created_at"],
            "analise_preview": (
                r["analise"][:150] + "..."
                if len(r.get("analise", "")) > 150
                else r.get("analise", "")
            ),
        }
        for r in records
    ]


def get_analysis(entry_id: int) -> Optional[Dict[str, Any]]:
    """Retorna análise completa por ID."""
    for r in _load():
        if r["id"] == entry_id:
            return r
    return None


def get_token_stats() -> Dict[str, Any]:
    """
    Calcula estatísticas acumuladas de tokens de todas as análises.
    Inclui custo estimado para gpt-4o-mini via OpenRouter.
    """
    data = _load()

    total_analises = len(data)
    total_input  = sum(r.get("tokens", {}).get("input",  0) for r in data)
    total_output = sum(r.get("tokens", {}).get("output", 0) for r in data)
    total_tokens = sum(r.get("tokens", {}).get("total",  0) for r in data)

    if total_tokens == 0:
        total_tokens = total_input + total_output

    # Custo estimado
    cost_input_usd  = (total_input  / 1_000_000) * _COST_INPUT_PER_M
    cost_output_usd = (total_output / 1_000_000) * _COST_OUTPUT_PER_M
    total_cost_usd  = cost_input_usd + cost_output_usd
    total_cost_brl  = total_cost_usd * _BRL_RATE

    # Por tipo
    tipo_counts = {"busca_ia": 0, "analise_busca": 0}
    for r in data:
        tipo_counts[r.get("tipo", "busca_ia")] = tipo_counts.get(r.get("tipo", "busca_ia"), 0) + 1

    # Últimos 7 dias por dia
    from datetime import datetime, timedelta
    today = datetime.now().date()
    daily: Dict[str, Dict[str, Any]] = {}
    for r in data:
        try:
            day = r["created_at"][:10]
            if day not in daily:
                daily[day] = {"data": day, "analises": 0, "tokens": 0}
            daily[day]["analises"] += 1
            daily[day]["tokens"] += r.get("tokens", {}).get("total", 0)
        except Exception:
            pass

    # Últimos 7 dias ordenados
    week_days = []
    for i in range(6, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        week_days.append(daily.get(d, {"data": d, "analises": 0, "tokens": 0}))

    return {
        "total_analises":       total_analises,
        "por_tipo":             tipo_counts,
        "total_input_tokens":   total_input,
        "total_output_tokens":  total_output,
        "total_tokens":         total_tokens,
        "custo_input_usd":      round(cost_input_usd,  6),
        "custo_output_usd":     round(cost_output_usd, 6),
        "custo_total_usd":      round(total_cost_usd,  6),
        "custo_total_brl":      round(total_cost_brl,  4),
        "modelo":               "openai/gpt-4o-mini",
        "ultimos_7_dias":       week_days,
    }
