"""Publica no Instagram os posts aprovados cujo horário já chegou.

Roda de hora em hora no GitHub Actions. Uso local:  python -m jn.publicar [--simular]
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

import requests

from jn import fila, painel
from jn import facebook
from jn.instagram import ErroInstagram, Instagram


def url_publica(item: fila.Item, arquivo: str) -> str:
    # A mídia é copiada para o repositório público jn-robo (pasta midia/) só alguns minutos
    # antes de publicar, para o Instagram conseguir baixar, e removida depois (jn/midia.py).
    base = os.environ["MIDIA_BASE_URL"].rstrip("/")
    return f"{base}/{item.nome}/{arquivo}"


def midia_no_ar(url: str) -> bool:
    try:
        return requests.head(url, timeout=20, allow_redirects=True).status_code == 200
    except requests.RequestException:
        return False


def publicar_item(ig: Instagram, item: fila.Item) -> str:
    d = item.dados
    urls = [url_publica(item, a) for a in d["arquivos"]]
    capa = url_publica(item, d["capa"]) if d.get("capa") else None
    legenda = d.get("legenda", "")
    tipo = d["tipo"]
    if tipo == "post":
        return ig.foto(urls[0], legenda)
    if tipo == "carrossel":
        return ig.carrossel(urls, legenda)
    if tipo == "reel":
        return ig.reel(urls[0], legenda, capa)
    if tipo == "story":
        return ig.story(urls[0])
    raise ValueError(tipo)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--simular", action="store_true", help="mostra o que seria publicado, sem publicar")
    args = ap.parse_args(argv)

    prontos = fila.prontos_para_publicar()
    print(f"{len(prontos)} item(ns) pronto(s) para publicar.")
    if args.simular or not prontos:
        for it in prontos:
            print(f"  - {it.nome} ({it.dados['tipo']}, {it.dados['publicar_em']})")
        painel.atualizar()
        return 0

    ig = Instagram(os.environ.get("IG_ACCESS_TOKEN", ""), os.environ.get("IG_USER_ID") or None)
    falhas = 0
    fb = None
    for it in prontos:
        urls = [url_publica(it, a) for a in it.dados["arquivos"]]
        if not all(midia_no_ar(u) for u in urls):
            print(f"  ~ {it.nome}: arquivos ainda não estão no ar no GitHub Pages; tento na próxima hora.")
            continue
        try:
            media_id = publicar_item(ig, it)
        except (ErroInstagram, requests.RequestException) as e:
            falhas += 1
            n = it.dados.get("tentativas", 0) + 1
            it.dados.update(tentativas=n, ultimo_erro=str(e))
            if n >= fila.MAX_TENTATIVAS:
                it.dados["falhou"] = True
            it.salvar()
            print(f"  x {it.nome}: {e} (tentativa {n})")
            continue
        it.dados.update(
            media_id=media_id,
            publicado_em=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        it.dados.pop("ultimo_erro", None)
        # Também na Página do Facebook (falha aqui não afeta o Instagram)
        if facebook.ativo() and it.dados.get("facebook", True) and it.dados["tipo"] != "story":
            try:
                fb = fb or facebook.Facebook(os.environ.get("IG_ACCESS_TOKEN", ""))
                d = it.dados
                fb_id = facebook.publicar_no_facebook(
                    fb, d["tipo"], [url_publica(it, a) for a in d["arquivos"]], d.get("legenda", ""),
                    url_publica(it, d["capa"]) if d.get("capa") else None)
                if fb_id:
                    it.dados["facebook_id"] = fb_id
                    print(f"    + Facebook: {fb_id}")
            except (ErroInstagram, requests.RequestException) as e:
                it.dados["facebook_erro"] = str(e)[:200]
                print(f"    ! Facebook: {e}")
        it.salvar()
        fila.mover_para_publicado(it)
        print(f"  ✓ {it.nome} publicado (id {media_id})")

    painel.atualizar()
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
