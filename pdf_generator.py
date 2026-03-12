"""
Geração de relatórios PDF com xhtml2pdf (pure Python, sem dependências de sistema).
"""
import os
from datetime import datetime
from jinja2 import Environment, BaseLoader

TEMPLATE_HTML = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<style>
  * { margin: 0; padding: 0; }
  body { font-family: Helvetica, Arial, sans-serif; color: #1a1a2e; font-size: 12px; }
  .header { background: #1a1a2e; color: white; padding: 24px 32px; }
  .header h1 { font-size: 20px; font-weight: bold; }
  .header p { font-size: 11px; color: #aaa; margin-top: 4px; }
  .content { padding: 24px 32px; }
  .section-title { font-size: 11px; font-weight: bold; color: #374151;
                   border-bottom: 2px solid #e5e7eb; padding-bottom: 6px;
                   margin-bottom: 14px; margin-top: 24px; text-transform: uppercase;
                   letter-spacing: 0.5px; }
  .summary-table { width: 100%; border-collapse: collapse; margin-bottom: 20px; }
  .summary-table td { width: 25%; padding: 12px 14px; text-align: center;
                      border: 1px solid #e5e7eb; background: white; }
  .summary-value { font-size: 26px; font-weight: bold; color: #111827; }
  .summary-label { font-size: 10px; color: #6b7280; margin-top: 3px; }
  .summary-blue td:first-child { border-left: 4px solid #6366f1; }
  .card-red .summary-value { color: #dc2626; }
  .card-green .summary-value { color: #16a34a; }
  .card-gray .summary-value { color: #9ca3af; }
  table.main { width: 100%; border-collapse: collapse; background: white;
               font-size: 11px; border: 1px solid #e5e7eb; }
  table.main thead th { background: #1a1a2e; color: white; padding: 8px 10px;
                        text-align: left; font-weight: bold; font-size: 10px; }
  table.main tbody td { padding: 8px 10px; border-bottom: 1px solid #f3f4f6; }
  table.main tbody tr:nth-child(even) td { background: #f9fafb; }
  .status-ok { color: #16a34a; font-weight: bold; }
  .status-disp { color: #dc2626; font-weight: bold; }
  .status-nd { color: #9ca3af; }
  .hotel-block { background: white; border: 1px solid #e5e7eb; border-radius: 4px;
                 padding: 14px 16px; margin-bottom: 14px; page-break-inside: avoid; }
  .hotel-name { font-size: 13px; font-weight: bold; margin-bottom: 8px; color: #111827; }
  .hotel-meta { font-size: 10px; color: #6b7280; margin-bottom: 10px; }
  .badge { font-size: 9px; font-weight: bold; padding: 2px 7px; border-radius: 10px;
           display: inline; margin-left: 6px; }
  .badge-red { background: #fee2e2; color: #dc2626; border: 1px solid #fecaca; }
  .badge-green { background: #dcfce7; color: #16a34a; border: 1px solid #bbf7d0; }
  .badge-gray { background: #f3f4f6; color: #6b7280; border: 1px solid #e5e7eb; }
  table.otas { width: 100%; border-collapse: collapse; font-size: 11px; }
  table.otas td { padding: 5px 8px; border-bottom: 1px solid #f3f4f6; }
  table.otas tr:last-child td { border-bottom: none; }
  .direct-row td { color: #6366f1; font-weight: bold; background: #eef2ff; }
  .disparity-box { background: #fef2f2; border: 1px solid #fecaca;
                   border-radius: 4px; padding: 8px 12px; margin-top: 10px;
                   font-size: 11px; color: #dc2626; }
  .ok-box { background: #f0fdf4; border: 1px solid #bbf7d0;
            border-radius: 4px; padding: 8px 12px; margin-top: 10px;
            font-size: 11px; color: #16a34a; }
  .footer { text-align: center; padding: 16px; font-size: 10px; color: #9ca3af;
            border-top: 1px solid #e5e7eb; margin-top: 24px; }
  .price-right { text-align: right; font-weight: bold; }
</style>
</head>
<body>
<div class="header">
  <h1>Relatorio de Disparidade de Precos</h1>
  <p>Periodo: {{ periodo_inicio }} a {{ periodo_fim }} | Gerado em: {{ gerado_em }}</p>
</div>

<div class="content">
  <!-- Resumo -->
  <div class="section-title">Resumo Geral</div>
  <table class="summary-table">
    <tr>
      <td><div class="summary-value">{{ total_clientes }}</div><div class="summary-label">Hotels Monitorados</div></td>
      <td><div class="summary-value" style="color:#dc2626">{{ total_disparidade }}</div><div class="summary-label">Com Disparidade</div></td>
      <td><div class="summary-value" style="color:#16a34a">{{ total_ok }}</div><div class="summary-label">Sem Disparidade</div></td>
      <td><div class="summary-value" style="color:#9ca3af">{{ total_sem_dados }}</div><div class="summary-label">Sem Dados</div></td>
    </tr>
  </table>

  <!-- Tabela resumo -->
  <div class="section-title">Visao Geral por Hotel</div>
  <table class="main">
    <thead>
      <tr>
        <th>Hotel</th>
        <th>Localizacao</th>
        <th style="text-align:right">Preco Direto</th>
        <th style="text-align:right">Menor OTA</th>
        <th>OTA</th>
        <th style="text-align:right">Diferenca</th>
        <th style="text-align:right">%</th>
        <th>Status</th>
      </tr>
    </thead>
    <tbody>
      {% for c in cards %}
      <tr>
        <td><strong>{{ c.nome }}</strong></td>
        <td>{{ c.localizacao or '' }}</td>
        <td style="text-align:right">{{ fmt_brl(c.preco_direto) }}</td>
        <td style="text-align:right">{{ fmt_brl(c.menor_preco_ota) }}</td>
        <td>{{ c.ota_mais_barata or '—' }}</td>
        <td style="text-align:right">{{ fmt_brl(c.diferenca_valor) }}</td>
        <td style="text-align:right">{{ fmt_pct(c.diferenca_pct) }}</td>
        <td>
          {% if c.status == 'disparidade' %}
            <span class="status-disp">Disparidade</span>
          {% elif c.status == 'ok' %}
            <span class="status-ok">OK</span>
          {% else %}
            <span class="status-nd">Sem dados</span>
          {% endif %}
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>

  <!-- Detalhe por hotel -->
  {% if detalhes %}
  <div class="section-title" style="margin-top:30px">Detalhe por Hotel</div>
  {% for item in detalhes %}
  <div class="hotel-block">
    <div class="hotel-name">
      {{ item.nome }}
      {% if item.status == 'disparidade' %}
        <span class="badge badge-red">Disparidade</span>
      {% elif item.status == 'ok' %}
        <span class="badge badge-green">OK</span>
      {% else %}
        <span class="badge badge-gray">Sem dados</span>
      {% endif %}
    </div>
    <div class="hotel-meta">{{ item.localizacao or '' }}</div>
    <table class="otas">
      <tr class="direct-row">
        <td><strong>Preco Direto (site oficial)</strong></td>
        <td class="price-right">{{ fmt_brl(item.preco_direto) }}</td>
      </tr>
      {% for ota in item.otas %}
      {% if not ota.is_preco_direto %}
      <tr>
        <td>{{ ota.ota_nome }}</td>
        <td class="price-right">{{ fmt_brl(ota.preco_total) }}</td>
      </tr>
      {% endif %}
      {% endfor %}
    </table>
    {% if item.status == 'disparidade' and item.menor_preco_ota %}
    <div class="disparity-box">
      DISPARIDADE: {{ item.ota_mais_barata or '' }} vende por {{ fmt_brl(item.menor_preco_ota) }},
      {{ fmt_pct_abs(item.diferenca_pct) }} mais barato que o site oficial ({{ fmt_brl(item.preco_direto) }}).
    </div>
    {% elif item.status == 'ok' %}
    <div class="ok-box">
      Paridade mantida. O site oficial esta competitivo.
    </div>
    {% endif %}
  </div>
  {% endfor %}
  {% endif %}
</div>

<div class="footer">
  Sistema de Disparidade de Hotels | Relatorio gerado automaticamente
</div>
</body>
</html>
"""


def _fmt_brl(v):
    if v is None:
        return "—"
    try:
        return f"R$ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return "—"


def _fmt_pct(v):
    if v is None:
        return "—"
    try:
        return f"{float(v):.1f}%"
    except (TypeError, ValueError):
        return "—"


def _fmt_pct_abs(v):
    if v is None:
        return "—"
    try:
        return f"{abs(float(v)):.1f}%"
    except (TypeError, ValueError):
        return "—"


AI_PDF_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<style>
  * { margin: 0; padding: 0; }
  body { font-family: Helvetica, Arial, sans-serif; color: #1a1a2e; font-size: 12px; }
  .header { background: #1a1a2e; color: white; padding: 24px 32px; }
  .header h1 { font-size: 20px; font-weight: bold; }
  .header p { font-size: 11px; color: #aaa; margin-top: 4px; }
  .ai-badge { background: #7c3aed; color: white; font-size: 10px; font-weight: bold;
              padding: 3px 12px; border-radius: 12px; display: inline-block; margin-bottom: 18px; }
  .content { padding: 24px 32px; }
  h2 { font-size: 13px; font-weight: bold; color: #1a1a2e; margin: 18px 0 8px 0;
       border-bottom: 2px solid #e5e7eb; padding-bottom: 5px; text-transform: uppercase;
       letter-spacing: 0.5px; }
  h3 { font-size: 12px; font-weight: bold; color: #374151; margin: 12px 0 5px 0; }
  p { margin: 6px 0; line-height: 1.6; color: #374151; }
  ul { margin: 6px 0 10px 20px; }
  li { margin: 4px 0; line-height: 1.5; color: #374151; }
  strong { font-weight: bold; color: #111827; }
  .footer { text-align: center; padding: 16px; font-size: 10px; color: #9ca3af;
            border-top: 1px solid #e5e7eb; margin-top: 24px; }
  .meta-box { background: #f5f3ff; border: 1px solid #ddd6fe; border-radius: 4px;
              padding: 12px 16px; margin-bottom: 20px; }
  .meta-row { display: table-row; }
  .meta-label { display: table-cell; font-weight: bold; color: #6d28d9;
                font-size: 11px; padding-right: 16px; padding-bottom: 4px; }
  .meta-val { display: table-cell; color: #374151; font-size: 11px; padding-bottom: 4px; }
</style>
</head>
<body>
<div class="header">
  <h1>Analise com IA — {{ hotel_name }}</h1>
  <p>Periodo: {{ check_in }} → {{ check_out }} | Gerado em: {{ gerado_em }}</p>
</div>

<div class="content">
  <div class="ai-badge">Analise Inteligente — Revenue Management</div>

  <div class="meta-box">
    <table width="100%">
      <tr>
        <td class="meta-label">Hotel:</td>
        <td class="meta-val">{{ hotel_name }}</td>
        <td class="meta-label">Check-in:</td>
        <td class="meta-val">{{ check_in }}</td>
        <td class="meta-label">Check-out:</td>
        <td class="meta-val">{{ check_out }}</td>
      </tr>
    </table>
  </div>

  {{ analise_html }}
</div>

<div class="footer">
  Sistema de Disparidade de Hoteis | Analise gerada por IA (OpenRouter + Agno + SERPAPI)
</div>
</body>
</html>
"""


def _markdown_to_html(text: str) -> str:
    """Converte markdown simples para HTML compatível com xhtml2pdf."""
    import re

    lines = text.split("\n")
    result = []
    in_ul = False

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("### "):
            if in_ul:
                result.append("</ul>")
                in_ul = False
            content = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", stripped[4:].strip())
            result.append(f"<h3>{content}</h3>")

        elif stripped.startswith("## "):
            if in_ul:
                result.append("</ul>")
                in_ul = False
            content = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", stripped[3:].strip())
            result.append(f"<h2>{content}</h2>")

        elif stripped.startswith("# "):
            if in_ul:
                result.append("</ul>")
                in_ul = False
            content = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", stripped[2:].strip())
            result.append(f"<h2>{content}</h2>")

        elif stripped.startswith("- ") or stripped.startswith("* "):
            if not in_ul:
                result.append("<ul>")
                in_ul = True
            content = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", stripped[2:].strip())
            result.append(f"<li>{content}</li>")

        elif not stripped:
            if in_ul:
                result.append("</ul>")
                in_ul = False

        else:
            if in_ul:
                result.append("</ul>")
                in_ul = False
            content = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", stripped)
            result.append(f"<p>{content}</p>")

    if in_ul:
        result.append("</ul>")

    return "\n".join(result)


def generate_ai_pdf(
    hotel_name: str,
    analise: str,
    check_in: str,
    check_out: str,
    output_path: str,
) -> str:
    """Gera PDF com análise textual da IA (Revenue Management)."""
    from xhtml2pdf import pisa

    env = Environment(loader=BaseLoader())
    tmpl = env.from_string(AI_PDF_TEMPLATE)

    html_content = tmpl.render(
        hotel_name=hotel_name,
        check_in=check_in or "—",
        check_out=check_out or "—",
        gerado_em=datetime.now().strftime("%d/%m/%Y %H:%M"),
        analise_html=_markdown_to_html(analise),
    )

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    with open(output_path, "wb") as f:
        status = pisa.CreatePDF(html_content.encode("utf-8"), dest=f, encoding="utf-8")

    if status.err:
        raise RuntimeError(f"Erro ao gerar PDF IA: {status.err}")

    return output_path


def generate_pdf(
    dashboard_data: dict,
    detalhes: list,
    periodo_inicio: str,
    periodo_fim: str,
    output_path: str,
) -> str:
    from xhtml2pdf import pisa

    env = Environment(loader=BaseLoader())
    env.globals["fmt_brl"] = _fmt_brl
    env.globals["fmt_pct"] = _fmt_pct
    env.globals["fmt_pct_abs"] = _fmt_pct_abs

    tmpl = env.from_string(TEMPLATE_HTML)
    html_content = tmpl.render(
        periodo_inicio=periodo_inicio,
        periodo_fim=periodo_fim,
        gerado_em=datetime.now().strftime("%d/%m/%Y %H:%M"),
        total_clientes=dashboard_data.get("total_clientes", 0),
        total_disparidade=dashboard_data.get("total_disparidade", 0),
        total_ok=dashboard_data.get("total_ok", 0),
        total_sem_dados=dashboard_data.get("total_sem_dados", 0),
        cards=dashboard_data.get("cards", []),
        detalhes=detalhes,
    )

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    with open(output_path, "wb") as f:
        status = pisa.CreatePDF(html_content.encode("utf-8"), dest=f, encoding="utf-8")

    if status.err:
        raise RuntimeError(f"Erro ao gerar PDF: {status.err}")

    return output_path
