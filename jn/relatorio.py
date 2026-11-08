"""Relatório semanal: seguidores, alcance e melhores posts. Salva em relatorios/AAAA-MM-DD.md.

Métricas que a Meta não liberar para a conta são puladas sem quebrar o relatório.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

from jn import fila
from jn.instagram import ErroInstagram, Instagram

PASTA = fila.RAIZ / "relatorios"
HIST = PASTA / "historico.json"
METRICAS_POST = ["reach", "views", "saved", "shares", "total_interactions"]


def insights_post(ig: Instagram, media_id: str) -> dict:
    out = {}
    for m in METRICAS_POST:
        try:
            r = ig.get(f"{media_id}/insights", metric=m)
            out[m] = r["data"][0]["values"][0]["value"] if r.get("data") else None
        except (ErroInstagram, KeyError, IndexError):
            out[m] = None
    return out


def alcance_conta(ig: Instagram, desde: datetime, ate: datetime) -> dict:
    out = {}
    for m in ["reach", "views", "profile_views", "accounts_engaged"]:
        try:
            r = ig.get(f"{ig.ig_id}/insights", metric=m, period="day", metric_type="total_value",
                       since=int(desde.timestamp()), until=int(ate.timestamp()))
            out[m] = r["data"][0]["total_value"]["value"]
        except (ErroInstagram, KeyError, IndexError):
            out[m] = None
    return out


def fmt(v):
    return "—" if v is None else f"{v:,}".replace(",", ".")


def main():
    ig = Instagram(os.environ.get("IG_ACCESS_TOKEN", ""), os.environ.get("IG_USER_ID") or None)
    agora = datetime.now(timezone.utc)
    desde = agora - timedelta(days=7)

    perfil = ig.get(ig.ig_id, fields="username,followers_count,follows_count,media_count")
    conta = alcance_conta(ig, desde, agora)
    midias = ig.get(f"{ig.ig_id}/media", limit=25,
                    fields="id,caption,media_product_type,timestamp,permalink,like_count,comments_count")
    posts = []
    for m in midias.get("data", []):
        ts = datetime.fromisoformat(m["timestamp"].replace("+0000", "+00:00"))
        if ts < desde:
            continue
        m.update(insights_post(ig, m["id"]))
        posts.append(m)
    posts.sort(key=lambda p: (p.get("reach") or 0), reverse=True)

    PASTA.mkdir(exist_ok=True)
    hist = json.loads(HIST.read_text(encoding="utf-8")) if HIST.exists() else []
    seg_antes = hist[-1]["seguidores"] if hist else None
    seg = perfil.get("followers_count")
    hist.append({"data": agora.date().isoformat(), "seguidores": seg, **conta})
    HIST.write_text(json.dumps(hist, ensure_ascii=False, indent=2), encoding="utf-8")

    ganho = f" ({seg - seg_antes:+d} na semana)" if seg is not None and seg_antes is not None else ""
    linhas = [
        f"# Relatório semanal — @{perfil.get('username')} — {agora.astimezone(fila._brt()):%d/%m/%Y}",
        "",
        f"**Seguidores:** {fmt(seg)}{ganho}  ",
        f"**Posts na semana:** {len(posts)}  ",
        f"**Contas alcançadas (7 dias):** {fmt(conta['reach'])}  ",
        f"**Visualizações (7 dias):** {fmt(conta['views'])}  ",
        f"**Visitas ao perfil (7 dias):** {fmt(conta['profile_views'])}  ",
        f"**Contas que interagiram (7 dias):** {fmt(conta['accounts_engaged'])}",
        "",
        "## Posts da semana (do maior alcance para o menor)",
        "",
        "| Post | Tipo | Alcance | Views | Curtidas | Coment. | Salvos | Compart. |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for p in posts:
        titulo = (p.get("caption") or "(sem legenda)").split("\n")[0][:50].replace("|", "/")
        linhas.append(
            f"| [{titulo}]({p.get('permalink')}) | {p.get('media_product_type', '').lower()} | "
            f"{fmt(p.get('reach'))} | {fmt(p.get('views'))} | {fmt(p.get('like_count'))} | "
            f"{fmt(p.get('comments_count'))} | {fmt(p.get('saved'))} | {fmt(p.get('shares'))} |"
        )
    if not posts:
        linhas.append("| Nenhum post nos últimos 7 dias | | | | | | | |")
    if posts:
        top = posts[0]
        linhas += ["", f"**Destaque:** \"{(top.get('caption') or '').split(chr(10))[0][:80]}\" "
                       f"foi o que mais alcançou. Repita o formato ({top.get('media_product_type', '').lower()})."]
    arq = PASTA / f"{agora.date().isoformat()}.md"
    arq.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    print(arq.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
