"""Coleta os números do Instagram para o painel "Resultados" do app.

Gera dados/metricas.json (lido pelo app) e mantém dados/historico.json (um ponto por dia).
Roda de hora em hora pelo relógio da fila. Métricas que a Meta não liberar ficam como null,
sem quebrar a coleta (algumas só existem para contas com 100+ seguidores).

Uso: python -m jn.metricas [--diagnostico]
"""
from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from jn import fila
from jn.instagram import ErroInstagram, Instagram

PASTA = fila.RAIZ / "dados"
ARQ = PASTA / "metricas.json"
HIST = PASTA / "historico.json"
BRT = fila._brt()

METRICAS_CONTA = ["reach", "views", "profile_views", "accounts_engaged", "total_interactions",
                  "profile_links_taps", "follows_and_unfollows"]
METRICAS_MIDIA = ["reach", "views", "saved", "shares", "total_interactions"]
METRICAS_STORY = ["reach", "views", "replies", "navigation"]

# Melhores horários de referência (Buffer 2026, 9,6 mi de posts) enquanto não há dados próprios
REFERENCIA = {"dom": [20, 21, 22], "seg": [18, 19, 20], "ter": [19], "qua": [12, 18],
              "qui": [8, 9], "sex": [21, 22], "sab": [20, 21, 22]}
DIAS = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]


def _tentar(fn, *a, **k):
    try:
        return fn(*a, **k), None
    except (ErroInstagram, KeyError, IndexError, TypeError, ValueError) as e:
        return None, str(e)[:160]


def total_periodo(ig, metrica, desde, ate):
    r = ig.get(f"{ig.ig_id}/insights", metric=metrica, period="day", metric_type="total_value",
               since=int(desde.timestamp()), until=int(ate.timestamp()))
    return r["data"][0]["total_value"]["value"]


def serie_diaria(ig, metrica, dias=30):
    """Série por dia (ex.: reach, follower_count) — a Meta limita a 30 dias por chamada."""
    ate = datetime.now(timezone.utc)
    desde = ate - timedelta(days=dias)
    r = ig.get(f"{ig.ig_id}/insights", metric=metrica, period="day",
               since=int(desde.timestamp()), until=int(ate.timestamp()))
    return [{"data": v["end_time"][:10], "valor": v["value"]} for v in r["data"][0]["values"]]


def seguidores_online(ig):
    """Seguidores online por hora (média dos últimos dias). Só para contas com 100+ seguidores."""
    ate = datetime.now(timezone.utc)
    r = ig.get(f"{ig.ig_id}/insights", metric="online_followers", period="lifetime",
               since=int((ate - timedelta(days=29)).timestamp()), until=int(ate.timestamp()))
    soma, n = defaultdict(float), defaultdict(int)
    for v in r["data"][0]["values"]:
        for hora_pt, qtd in (v.get("value") or {}).items():  # horas em horário do Pacífico (PT)
            h = (int(hora_pt) + 5) % 24  # PT -> Brasília (aprox., PST=UTC-8 -> BRT=UTC-3)
            soma[h] += qtd
            n[h] += 1
    if not soma:
        raise ValueError("sem dados de seguidores online")
    return {h: round(soma[h] / n[h], 1) for h in range(24) if n[h]}


def insights_midia(ig, mid, story=False):
    out = {}
    for m in (METRICAS_STORY if story else METRICAS_MIDIA):
        v, _ = _tentar(lambda: ig.get(f"{mid}/insights", metric=m)["data"][0]["values"][0]["value"])
        out[m] = v
    return out


def coletar(ig: Instagram, diag=False) -> dict:
    agora = datetime.now(timezone.utc)
    erros = {}
    perfil, e = _tentar(ig.get, ig.ig_id, fields="username,followers_count,follows_count,media_count")
    if e:
        raise ErroInstagram(f"perfil: {e}")

    conta = {}
    for periodo, dias in (("7d", 7), ("28d", 28)):
        conta[periodo] = {}
        for m in METRICAS_CONTA:
            v, e = _tentar(total_periodo, ig, m, agora - timedelta(days=dias), agora)
            conta[periodo][m] = v
            if e:
                erros[f"{m}_{periodo}"] = e

    series = {}
    for m in ("reach", "follower_count"):
        v, e = _tentar(serie_diaria, ig, m)
        series[m] = v or []
        if e:
            erros[f"serie_{m}"] = e

    online, e = _tentar(seguidores_online, ig)
    if e:
        erros["online_followers"] = e

    midias, e = _tentar(ig.get, f"{ig.ig_id}/media", limit=30,
                        fields="id,caption,media_type,media_product_type,timestamp,permalink,"
                               "thumbnail_url,media_url,like_count,comments_count")
    posts = []
    for m in (midias or {}).get("data", []):
        ins = insights_midia(ig, m["id"])
        ts = datetime.fromisoformat(m["timestamp"].replace("+0000", "+00:00")).astimezone(BRT)
        posts.append({
            "id": m["id"], "tipo": (m.get("media_product_type") or m.get("media_type") or "").lower(),
            "data": ts.isoformat(timespec="minutes"), "dia": DIAS[ts.weekday()], "hora": ts.hour,
            "legenda": (m.get("caption") or "").split("\n")[0][:90], "link": m.get("permalink"),
            "imagem": m.get("thumbnail_url") or m.get("media_url"),
            "curtidas": m.get("like_count"), "comentarios": m.get("comments_count"), **ins,
        })

    stories_raw, e = _tentar(ig.get, f"{ig.ig_id}/stories", fields="id,timestamp,media_url,thumbnail_url")
    stories = []
    for s in (stories_raw or {}).get("data", []):
        ts = datetime.fromisoformat(s["timestamp"].replace("+0000", "+00:00")).astimezone(BRT)
        stories.append({"id": s["id"], "data": ts.isoformat(timespec="minutes"), "hora": ts.hour,
                        "imagem": s.get("thumbnail_url") or s.get("media_url"),
                        **insights_midia(ig, s["id"], story=True)})

    # melhores horários: 1) seguidores online; 2) alcance médio dos próprios posts por hora; 3) referência
    if online:
        top = sorted(online, key=online.get, reverse=True)[:4]
        horarios = {"fonte": "seus seguidores online (últimos 30 dias)", "por_hora": online,
                    "melhores": sorted(top)}
    elif len([p for p in posts if p.get("reach")]) >= 6:
        por_h = defaultdict(list)
        for p in posts:
            if p.get("reach") is not None:
                por_h[p["hora"]].append(p["reach"])
        media = {h: round(sum(v) / len(v)) for h, v in por_h.items()}
        horarios = {"fonte": "alcance médio dos seus posts por horário", "por_hora": media,
                    "melhores": sorted(sorted(media, key=media.get, reverse=True)[:3])}
    else:
        horarios = {"fonte": "referência geral (Buffer 2026) até a conta ter dados próprios",
                    "por_dia": REFERENCIA, "melhores": None}

    dados = {
        "atualizado_em": agora.astimezone(BRT).isoformat(timespec="minutes"),
        "perfil": {k: perfil.get(k) for k in ("username", "followers_count", "follows_count", "media_count")},
        "conta": conta, "series": series, "horarios": horarios,
        "posts": sorted(posts, key=lambda p: p["data"], reverse=True),
        "stories": stories,
    }
    if diag:
        dados["erros"] = erros
    return dados


def atualizar_historico(dados):
    hist = json.loads(HIST.read_text(encoding="utf-8")) if HIST.exists() else []
    hoje = dados["atualizado_em"][:10]
    ponto = {"data": hoje, "seguidores": dados["perfil"]["followers_count"],
             "posts": dados["perfil"]["media_count"]}
    hist = [h for h in hist if h["data"] != hoje] + [ponto]
    hist.sort(key=lambda h: h["data"])
    HIST.write_text(json.dumps(hist, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return hist


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--diagnostico", action="store_true", help="inclui as métricas recusadas e o motivo")
    a = ap.parse_args(argv)
    ig = Instagram(os.environ.get("IG_ACCESS_TOKEN", ""), os.environ.get("IG_USER_ID") or None)
    dados = coletar(ig, a.diagnostico)
    PASTA.mkdir(exist_ok=True)
    dados["historico"] = atualizar_historico(dados)
    ARQ.write_text(json.dumps(dados, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    c7 = dados["conta"]["7d"]
    print(f"@{dados['perfil']['username']}: {dados['perfil']['followers_count']} seguidores, "
          f"alcance 7d {c7.get('reach')}, views 7d {c7.get('views')}, {len(dados['posts'])} posts")
    if a.diagnostico:
        print(json.dumps(dados.get("erros", {}), ensure_ascii=False, indent=1))
        print(json.dumps({"conta": dados["conta"], "horarios": dados["horarios"],
                          "posts": dados["posts"][:3], "stories": dados["stories"][:3],
                          "series": {k: v[-5:] for k, v in dados["series"].items()}}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
