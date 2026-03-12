"""
Agente de IA com Agno + OpenRouter.
O agente usa SERPAPI (Google Hotels) como ferramenta para buscar preços
e depois analisa os dados para fornecer insights de Revenue Management.
"""
import json
import asyncio
from datetime import date as DateType
from agno.agent import Agent
from agno.models.openai.like import OpenAILike
from agno.tools import Toolkit
from agno.tools.serpapi import SerpApiTools
from config import get_settings
import serpapi_client as sc

settings = get_settings()

SYSTEM_PROMPT = """Você é um especialista em Revenue Management hoteleiro com acesso
a duas ferramentas de busca em tempo real:

1. `buscar_precos_hotel` — busca preços estruturados de OTAs via Google Hotels (SERPAPI).
   Use esta para obter comparação detalhada de preços.
2. `search_google` — busca geral no Google para contexto adicional: notícias do hotel,
   avaliações, eventos locais, informações de mercado.

Fluxo ideal para análise completa:
1. Use `buscar_precos_hotel` para obter dados de preços das OTAs
2. Use `search_google` para buscar contexto adicional do hotel/destino (opcional)
3. Analise TODOS os dados e forneça relatório completo

Use SEMPRE português brasileiro. Seja objetivo e profissional.
Organize com seções ## e listas com -.
"""


class HotelSearchToolkit(Toolkit):
    """Toolkit que expõe busca de preços de hotel via SERPAPI para o agente."""

    def __init__(self):
        super().__init__(name="hotel_search")
        self.register(self.buscar_precos_hotel)

    def buscar_precos_hotel(
        self,
        query: str,
        check_in: str,
        check_out: str,
        adultos: int = 2,
    ) -> str:
        """
        Busca preços de hotel em OTAs via Google Hotels.
        Args:
            query: Nome do hotel (ex: 'Hotel Fasano Sao Paulo')
            check_in: Data de check-in no formato YYYY-MM-DD
            check_out: Data de check-out no formato YYYY-MM-DD
            adultos: Numero de adultos (padrao 2)
        Returns:
            JSON com preco oficial e lista de OTAs com precos
        """
        try:
            cin  = DateType.fromisoformat(check_in)
            cout = DateType.fromisoformat(check_out)
        except ValueError:
            return json.dumps({"erro": "Datas invalidas. Use formato YYYY-MM-DD."})

        try:
            import concurrent.futures

            def _run_in_thread():
                return asyncio.run(
                    sc.search_hotel_prices(
                        query=query, check_in=cin, check_out=cout,
                        adults=adultos, currency="BRL",
                    )
                )

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                resultado = pool.submit(_run_in_thread).result(timeout=35)
        except Exception as e:
            return json.dumps({"erro": f"Erro na busca: {str(e)}"})

        if not resultado.get("found"):
            return json.dumps({"erro": resultado.get("error", "Hotel nao encontrado")})

        preco_direto = resultado["preco_direto"]
        otas = resultado["otas"]
        disp = sc.calculate_disparity(preco_direto, otas)

        output = {
            "hotel": resultado.get("hotel_name", query),
            "periodo": f"{check_in} a {check_out}",
            "noites": resultado.get("nights", 1),
            "preco_oficial": f"R$ {preco_direto:,.2f}" if preco_direto else "N/D",
            "status": disp["status"],
            "otas_mais_baratas": [
                {
                    "ota": o["ota_nome"],
                    "preco": f"R$ {o['preco_total']:,.2f}",
                    "desconto": f"{abs(o.get('diferenca_pct', 0)):.1f}%",
                }
                for o in disp["otas_mais_baratas"]
            ],
            "otas_mais_caras": [
                {
                    "ota": o["ota_nome"],
                    "preco": f"R$ {o['preco_total']:,.2f}",
                    "acrescimo": f"{abs(o.get('diferenca_pct', 0)):.1f}%",
                }
                for o in disp["otas_mais_caras"]
            ],
            "total_disparidades": disp["count_mais_baratas"],
            "total_paridade_ok": disp["count_mais_caras"],
        }
        return json.dumps(output, ensure_ascii=False, indent=2)


def _get_agent() -> Agent:
    model = OpenAILike(
        id="openai/gpt-4o-mini",
        api_key=settings.openrouter_key,
        base_url="https://openrouter.ai/api/v1",
    )
    tools = [HotelSearchToolkit()]
    # Adiciona SerpApiTools (busca geral Google) se a chave estiver configurada
    if settings.serpapi_key:
        tools.append(SerpApiTools(
            api_key=settings.serpapi_key,
            enable_search_google=True,
        ))
    return Agent(
        model=model,
        tools=tools,
        instructions=SYSTEM_PROMPT,
        markdown=True,
    )


def _extract_tokens(response) -> dict:
    """Extrai contagem de tokens do RunResponse do Agno."""
    try:
        metrics = response.metrics or {}
        inp  = sum(metrics.get("input_tokens",  [0]))
        out  = sum(metrics.get("output_tokens", [0]))
        tot  = sum(metrics.get("total_tokens",  [0]))
        if tot == 0:
            tot = inp + out
        return {"input": inp, "output": out, "total": tot}
    except Exception:
        return {"input": 0, "output": 0, "total": 0}


async def busca_e_analisa(
    hotel_name: str,
    check_in: str,
    check_out: str,
    adultos: int = 2,
) -> dict:
    """
    O agente IA busca os precos via SERPAPI e analisa os resultados.
    Retorna o texto de analise + uso de tokens.
    """
    agent = _get_agent()
    prompt = (
        f"Analise a paridade de precos para o hotel **{hotel_name}**.\n"
        f"- Check-in: {check_in}\n"
        f"- Check-out: {check_out}\n"
        f"- Adultos: {adultos}\n\n"
        f"Use a ferramenta de busca para obter os precos atuais e forneca "
        f"um diagnostico completo com recomendacoes praticas."
    )
    response = await agent.arun(prompt)
    return {"analise": response.content, "tokens": _extract_tokens(response)}


async def analisar_disparidade(
    hotel_name: str,
    preco_direto: float,
    otas_mais_baratas: list,
    otas_mais_caras: list,
    check_in: str = "",
    check_out: str = "",
    nights: int = 1,
) -> str:
    """
    Analisa dados de disparidade ja calculados (sem nova busca).
    """
    def fmt(v):
        return f"R$ {v:,.2f}" if v is not None else "N/D"

    baratas_txt = "\n".join(
        f"  - {o['ota_nome']}: {fmt(o['preco_total'])} ({abs(o.get('diferenca_pct', 0)):.1f}% abaixo)"
        for o in otas_mais_baratas
    ) or "  Nenhuma"

    caras_txt = "\n".join(
        f"  - {o['ota_nome']}: {fmt(o['preco_total'])} ({abs(o.get('diferenca_pct', 0)):.1f}% acima)"
        for o in otas_mais_caras
    ) or "  Nenhuma"

    status = "DISPARIDADE DETECTADA" if otas_mais_baratas else "PARIDADE MANTIDA"

    agent = _get_agent()
    prompt = f"""Analise estes dados de paridade de precos (ja disponíveis, nao precisa buscar):

**Hotel:** {hotel_name}
**Periodo:** {check_in} a {check_out} ({nights} noite(s))
**Status:** {status}
**Preco Oficial:** {fmt(preco_direto)}

**OTAs mais baratas ({len(otas_mais_baratas)} — disparidade):**
{baratas_txt}

**OTAs mais caras ({len(otas_mais_caras)} — paridade ok):**
{caras_txt}

Forneca diagnostico, impacto e recomendacoes praticas de Revenue Management.
Indique o nivel de urgencia."""

    response = await agent.arun(prompt)
    # Retorna tupla (content, tokens) — chamadores que não usam tokens continuam OK
    return response.content, _extract_tokens(response)
