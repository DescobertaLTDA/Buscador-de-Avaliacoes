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
CORS(app)

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

def extrair_id(url_or_id):
    """Aceita URL completa ou ID direto"""
    m = re.search(r"id=([a-zA-Z0-9_.]+)", url_or_id)
    if m:
        return m.group(1)
    # se não tem '/' nem '=' assume que já é o ID
    if "/" not in url_or_id and "=" not in url_or_id:
        return url_or_id.strip()
    return None

def detectar_temas(texto):
    texto_lower = texto.lower()
    return [t for t, palavras in TEMAS.items() if any(p in texto_lower for p in palavras)] or ["geral"]

def sentimento(score):
    if score >= 4: return "positivo"
    if score == 3: return "neutro"
    return "negativo"

@app.route("/")
def index():
    return send_from_directory(".", "index.html")

@app.route("/api/analisar", methods=["POST"])
def analisar():
    data     = request.json or {}
    url      = data.get("url", "").strip()
    qtd      = min(int(data.get("quantidade", 300)), 500)

    app_id = extrair_id(url)
    if not app_id:
        return jsonify({"erro": "URL ou ID inválido. Cole a URL do app na Google Play."}), 400

    # Info do app
    try:
        info = app_info(app_id, lang="pt", country="br")
        nome       = info.get("title", app_id)
        score_geral = round(info.get("score", 0), 1)
        instalacoes = info.get("installs", "?")
        icone       = info.get("icon", "")
        developer   = info.get("developer", "")
    except Exception as e:
        return jsonify({"erro": f"App não encontrado: {e}"}), 404

    # Reviews
    try:
        result, _ = reviews(app_id, lang="pt", country="br", sort=Sort.NEWEST, count=qtd)
    except Exception as e:
        return jsonify({"erro": f"Erro ao buscar reviews: {e}"}), 500

    if not result:
        return jsonify({"erro": "Nenhuma review encontrada para este app."}), 404

    # Análise
    total     = len(result)
    sentimentos = Counter(sentimento(r["score"]) for r in result)
    dist_notas  = Counter(r["score"] for r in result)
    media       = round(sum(r["score"] for r in result) / total, 2)

    temas_neg = Counter()
    temas_pos = Counter()
    for r in result:
        txt = r.get("content") or ""
        for t in detectar_temas(txt):
            if r["score"] <= 2: temas_neg[t] += 1
            if r["score"] >= 4: temas_pos[t] += 1

    top_reviews = sorted(result, key=lambda x: x.get("thumbsUpCount", 0), reverse=True)[:8]
    top_reviews_out = [{
        "score":   r["score"],
        "texto":   (r.get("content") or "")[:400],
        "curtidas": r.get("thumbsUpCount", 0),
        "data":    r["at"].strftime("%d/%m/%Y") if r.get("at") else "",
        "usuario": r.get("userName", ""),
    } for r in top_reviews]

    # Reviews recentes negativas (mais úteis para análise)
    recentes_neg = [r for r in result if r["score"] <= 2][:20]
    recentes_neg_out = [{
        "score":   r["score"],
        "texto":   (r.get("content") or "")[:400],
        "curtidas": r.get("thumbsUpCount", 0),
        "data":    r["at"].strftime("%d/%m/%Y") if r.get("at") else "",
    } for r in recentes_neg]

    return jsonify({
        "nome":        nome,
        "app_id":      app_id,
        "score_geral": score_geral,
        "instalacoes": instalacoes,
        "developer":   developer,
        "icone":       icone,
        "total":       total,
        "media":       media,
        "sentimentos": dict(sentimentos),
        "dist_notas":  {str(k): v for k, v in dist_notas.items()},
        "temas_neg":   dict(temas_neg.most_common(8)),
        "temas_pos":   dict(temas_pos.most_common(8)),
        "top_reviews": top_reviews_out,
        "recentes_neg": recentes_neg_out,
    })

if __name__ == "__main__":
    print("\n  Analisador de Reviews rodando em http://localhost:5000\n")
    app.run(debug=True, port=5000)
