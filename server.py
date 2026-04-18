"""
server.py — Backend do Analisador de Reviews
Instale: pip install flask flask-cors google-play-scraper
Rode:    python server.py
Acesse:  http://localhost:5000
"""

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from google_play_scraper import reviews, Sort, app as app_info
from collections import Counter
import re, os

app = Flask(__name__, static_folder=".")
CORS(app, resources={r"/api/*": {"origins": "*"}})

# ─── Temas para classificação ───────────────────────────────────────────────
TEMAS = {
    "bug / erro":            ["bug", "erro", "trava", "crash", "falha", "não funciona", "parou", "quebrou", "lento"],
    "perda de dados":        ["sumiu", "perdeu", "apagou", "desapareceu", "backup", "dados"],
    "sincronização":         ["sincroniz", "nuvem", "cloud", "carregando"],
    "notif / importação":    ["notificaç", "importa", "duplica", "duplic", "automátic"],
    "cartão / parcelas":     ["cartão", "fatura", "parcel", "crédito"],
    "preço / plano":         ["preço", "caro", "assinatura", "mensalid", "vitalíci", "plano", "grátis"],
    "interface / UX":        ["interface", "intuitiv", "fácil", "difícil", "confus", "visual"],
    "investimentos":         ["investim", "cdb", "cdi", "ações", "rendiment"],
    "integração bancária":   ["open finance", "integraç"],
    "relatórios":            ["relatório", "gráfico", "análise", "subcategor"],
}

# ─── Helpers ─────────────────────────────────────────────────────────────────

def extrair_id(url_or_id: str) -> str | None:
    """Aceita URL completa ou ID direto."""
    m = re.search(r"id=([a-zA-Z0-9_.]+)", url_or_id)
    if m:
        return m.group(1)
    if "/" not in url_or_id and "=" not in url_or_id:
        return url_or_id.strip()
    return None


def detectar_temas(texto: str) -> list[str]:
    texto_lower = texto.lower()
    temas = [t for t, palavras in TEMAS.items() if any(p in texto_lower for p in palavras)]
    return temas or ["geral"]


def sentimento(score: int) -> str:
    if score >= 4:
        return "positivo"
    if score == 3:
        return "neutro"
    return "negativo"


def formatar_brl(valor: float) -> str:
    return f"R$ {valor:,.0f}".replace(",", ".")


# ─── Rotas ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/api/analisar", methods=["POST"])
def analisar():
    data = request.json or {}
    url  = data.get("url", "").strip()
    qtd  = min(int(data.get("quantidade", 300)), 500)

    app_id = extrair_id(url)
    if not app_id:
        return jsonify({"erro": "URL ou ID inválido. Cole a URL do app na Google Play."}), 400

    # ── Info do app ──
    try:
        info        = app_info(app_id, lang="pt", country="br")
        nome        = info.get("title", app_id)
        score_geral = round(info.get("score", 0), 1)
        instalacoes = info.get("installs", "?")
        icone       = info.get("icon", "")
        developer   = info.get("developer", "")
        categoria   = info.get("genre", "")
        preco_app   = info.get("price", 0)
        preco_str   = f"R$ {preco_app:.2f}".replace(".", ",") if preco_app else "Grátis"
        in_app_str  = info.get("inAppProductPrice") or ""
        tem_inapp   = bool(in_app_str)
        installs_raw = info.get("minInstalls", 0) or 0

        # Estimativa: instalações totais ÷ 24 meses
        installs_mes = installs_raw / 24 if installs_raw else 0

        receita_est      = None
        receita_detalhes = {}

        if preco_app and preco_app > 0:
            # App pago: cada instalação = receita (70% ao dev)
            receita_est = installs_mes * preco_app * 0.70
            receita_detalhes = {
                "modelo":              "app pago",
                "preco_app":           preco_str,
                "instalacoes_mes_est": int(installs_mes),
                "receita_mensal_est":  formatar_brl(receita_est),
                "nota":                "Estimativa: instalações/mês × preço × 70% (comissão Google)",
            }
        elif tem_inapp:
            # Freemium: taxa conversão ~3%, ticket médio = média da faixa
            try:
                partes = in_app_str.replace("R$", "").replace(".", "").replace(",", ".").split("–")
                min_v  = float(partes[0].strip()) if len(partes) > 0 else 0
                max_v  = float(partes[-1].strip()) if len(partes) > 1 else min_v
                ticket = (min_v + max_v) / 2
            except Exception:
                ticket = 0

            taxa_conv   = 0.03
            receita_est = installs_mes * taxa_conv * ticket * 0.70 if ticket else None
            receita_detalhes = {
                "modelo":              "freemium (in-app)",
                "faixa_inapp":         in_app_str,
                "ticket_medio_est":    f"R$ {ticket:.2f}".replace(".", ",") if ticket else "?",
                "taxa_conversao":      "~3%",
                "instalacoes_mes_est": int(installs_mes),
                "receita_mensal_est":  formatar_brl(receita_est) if receita_est else "Não calculável",
                "nota":                "Estimativa: instalações/mês × 3% conversão × ticket médio × 70%",
            }
        else:
            receita_detalhes = {
                "modelo": "gratuito",
                "nota":   "App gratuito sem compras in-app identificadas (pode ter anúncios)",
            }

    except Exception as e:
        return jsonify({"erro": f"App não encontrado: {e}"}), 404

    # ── Reviews ──
    try:
        result, _ = reviews(app_id, lang="pt", country="br", sort=Sort.NEWEST, count=qtd)
    except Exception as e:
        return jsonify({"erro": f"Erro ao buscar reviews: {e}"}), 500

    if not result:
        return jsonify({"erro": "Nenhuma review encontrada para este app."}), 404

    # ── Análise ──
    total       = len(result)
    sentimentos = Counter(sentimento(r["score"]) for r in result)
    dist_notas  = Counter(r["score"] for r in result)
    media       = round(sum(r["score"] for r in result) / total, 2)

    temas_neg = Counter()
    temas_pos = Counter()
    for r in result:
        txt = r.get("content") or ""
        for t in detectar_temas(txt):
            if r["score"] <= 2:
                temas_neg[t] += 1
            if r["score"] >= 4:
                temas_pos[t] += 1

    # Top reviews por curtidas
    top_reviews = sorted(result, key=lambda x: x.get("thumbsUpCount", 0), reverse=True)[:8]
    top_reviews_out = [
        {
            "score":    r["score"],
            "texto":    (r.get("content") or "")[:400],
            "curtidas": r.get("thumbsUpCount", 0),
            "data":     r["at"].strftime("%d/%m/%Y") if r.get("at") else "",
            "usuario":  r.get("userName", ""),
        }
        for r in top_reviews
    ]

    # Reviews recentes negativas
    recentes_neg = [r for r in result if r["score"] <= 2][:20]
    recentes_neg_out = [
        {
            "score":    r["score"],
            "texto":    (r.get("content") or "")[:400],
            "curtidas": r.get("thumbsUpCount", 0),
            "data":     r["at"].strftime("%d/%m/%Y") if r.get("at") else "",
        }
        for r in recentes_neg
    ]

    return jsonify({
        "nome":             nome,
        "app_id":           app_id,
        "score_geral":      score_geral,
        "instalacoes":      instalacoes,
        "developer":        developer,
        "icone":            icone,
        "categoria":        categoria,
        "preco_app":        preco_str,
        "in_app":           in_app_str,
        "tem_inapp":        tem_inapp,
        "receita_detalhes": receita_detalhes,
        "total":            total,
        "media":            media,
        "sentimentos":      dict(sentimentos),
        "dist_notas":       {str(k): v for k, v in dist_notas.items()},
        "temas_neg":        dict(temas_neg.most_common(8)),
        "temas_pos":        dict(temas_pos.most_common(8)),
        "top_reviews":      top_reviews_out,
        "recentes_neg":     recentes_neg_out,
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\n  Review Lens rodando na porta {port}\n")
    app.run(host="0.0.0.0", debug=False, port=port)
