"""Publica também na Página do Facebook "JN Higienização" o que saiu no Instagram.

Usa o mesmo token do usuário do sistema (permissões pages_manage_posts e publish_video) para obter
o token da Página. Post e carrossel viram post com foto(s); Reel vira vídeo da Página. Stories ficam
só no Instagram. Uma falha no Facebook nunca desfaz nem bloqueia a publicação no Instagram.
"""
from __future__ import annotations

import json
import os

import requests

from jn.instagram import GRAPH_VERSION, ErroInstagram

BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"


class Facebook:
    def __init__(self, token_sistema: str, sessao=None, page_id: str | None = None):
        self.http = sessao or requests.Session()
        contas = self._req("GET", "me/accounts", token_sistema, fields="id,name,access_token")["data"]
        if page_id:
            contas = [c for c in contas if c["id"] == page_id]
        if not contas or "access_token" not in contas[0]:
            raise ErroInstagram("Página do Facebook não encontrada para este token.")
        self.page_id, self.token = contas[0]["id"], contas[0]["access_token"]

    def _req(self, metodo, caminho, token, **params):
        params["access_token"] = token
        url = f"{BASE}/{caminho}"
        r = self.http.get(url, params=params, timeout=120) if metodo == "GET" else \
            self.http.post(url, data=params, timeout=300)
        try:
            corpo = r.json()
        except ValueError:
            corpo = {"error": {"message": r.text[:300]}}
        if r.status_code >= 400 or "error" in corpo:
            raise ErroInstagram("Facebook: " + corpo.get("error", {}).get("message", f"HTTP {r.status_code}"))
        return corpo

    def post(self, caminho, **p):
        return self._req("POST", caminho, self.token, **p)

    def foto(self, url, legenda):
        r = self.post(f"{self.page_id}/photos", url=url, message=legenda, published="true")
        return r.get("post_id") or r["id"]

    def album(self, urls, legenda):
        ids = [self.post(f"{self.page_id}/photos", url=u, published="false")["id"] for u in urls]
        midia = {f"attached_media[{i}]": json.dumps({"media_fbid": i_d}) for i, i_d in enumerate(ids)}
        return self.post(f"{self.page_id}/feed", message=legenda, **midia)["id"]

    def video(self, url, legenda, capa_url=None):
        p = dict(file_url=url, description=legenda, published="true")
        return self.post(f"{self.page_id}/videos", **p)["id"]


def publicar_no_facebook(fb: Facebook, tipo: str, urls: list[str], legenda: str, capa: str | None = None):
    """Devolve o id do post na Página, ou None para tipos que não vão para o Facebook (story)."""
    if tipo == "post":
        return fb.foto(urls[0], legenda)
    if tipo == "carrossel":
        fotos = [u for u in urls if not u.lower().endswith(".mp4")]
        return fb.album(fotos, legenda)
    if tipo == "reel":
        return fb.video(urls[0], legenda, capa)
    return None


def ativo() -> bool:
    # DESLIGADO desde 09/11/2026 a pedido do dono (a conta tomou restrição): só Instagram.
    # Para religar no futuro, defina a variável FACEBOOK=1 nos fluxos.
    return os.environ.get("FACEBOOK", "0") == "1"
