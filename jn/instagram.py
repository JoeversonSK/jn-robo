"""Cliente mínimo da API do Instagram (Instagram API com login do Instagram).

Documentação: https://developers.facebook.com/docs/instagram-platform/content-publishing
"""
from __future__ import annotations

import os
import time

import requests

GRAPH_VERSION = os.environ.get("GRAPH_VERSION", "v24.0")


def host_para(token: str) -> str:
    """Tokens do login do Instagram começam com 'IG'; os do login unificado/Facebook ('EAA...')
    usam graph.facebook.com. Os endpoints de publicação são os mesmos nos dois."""
    if os.environ.get("GRAPH_HOST"):
        return os.environ["GRAPH_HOST"]
    return "graph.instagram.com" if token.startswith("IG") else "graph.facebook.com"


class ErroInstagram(Exception):
    pass


class Instagram:
    def __init__(self, token: str, ig_user_id: str | None = None, sessao=None):
        if not token:
            raise ErroInstagram("IG_ACCESS_TOKEN não configurado.")
        self.token = token
        self.http = sessao or requests.Session()
        self.host = host_para(token)
        self.base = f"https://{self.host}/{GRAPH_VERSION}"
        self.ig_id = ig_user_id or self._descobrir_id()

    def _descobrir_id(self) -> str:
        if self.host == "graph.instagram.com":
            return self.get("me", fields="user_id")["user_id"]
        # login unificado / Facebook: a conta do Instagram fica ligada a uma Página
        pags = self.get("me/accounts", fields="instagram_business_account{id,username}").get("data", [])
        for p in pags:
            conta = p.get("instagram_business_account")
            if conta:
                return conta["id"]
        raise ErroInstagram("Não achei a conta do Instagram pelo token. Configure o segredo IG_USER_ID.")

    # ---------- baixo nível ----------
    def _req(self, metodo: str, caminho: str, **params):
        params["access_token"] = self.token
        url = f"{self.base}/{caminho.lstrip('/')}"
        if metodo == "GET":
            r = self.http.get(url, params=params, timeout=60)
        else:
            r = self.http.post(url, data=params, timeout=60)
        try:
            corpo = r.json()
        except ValueError:
            corpo = {"error": {"message": r.text[:300]}}
        if r.status_code >= 400 or "error" in corpo:
            msg = corpo.get("error", {}).get("message", f"HTTP {r.status_code}")
            raise ErroInstagram(msg)
        return corpo

    def get(self, caminho, **params):
        return self._req("GET", caminho, **params)

    def post(self, caminho, **params):
        return self._req("POST", caminho, **params)

    # ---------- conta ----------
    def meu_perfil(self):
        return self.get(self.ig_id, fields="id,username")

    # ---------- publicação ----------
    def _container(self, **params) -> str:
        return self.post(f"{self.ig_id}/media", **params)["id"]

    def esperar_pronto(self, container_id: str, limite_s: int = 300, intervalo_s: int = 10):
        fim = time.time() + limite_s
        while True:
            status = self.get(container_id, fields="status_code").get("status_code")
            if status == "FINISHED":
                return
            if status in ("ERROR", "EXPIRED"):
                raise ErroInstagram(f"Mídia rejeitada pelo Instagram (status {status}).")
            if time.time() > fim:
                raise ErroInstagram("O Instagram demorou demais para processar a mídia.")
            time.sleep(intervalo_s)

    def _publicar(self, container_id: str) -> str:
        self.esperar_pronto(container_id)
        return self.post(f"{self.ig_id}/media_publish", creation_id=container_id)["id"]

    def foto(self, url: str, legenda: str) -> str:
        return self._publicar(self._container(image_url=url, caption=legenda))

    def carrossel(self, urls: list[str], legenda: str) -> str:
        filhos = []
        for u in urls:
            if u.lower().endswith(".mp4"):
                cid = self._container(video_url=u, media_type="VIDEO", is_carousel_item="true")
            else:
                cid = self._container(image_url=u, is_carousel_item="true")
            self.esperar_pronto(cid)
            filhos.append(cid)
        cid = self._container(media_type="CAROUSEL", children=",".join(filhos), caption=legenda)
        return self._publicar(cid)

    def reel(self, url: str, legenda: str, capa_url: str | None = None) -> str:
        params = dict(media_type="REELS", video_url=url, caption=legenda, share_to_feed="true")
        if capa_url:
            params["cover_url"] = capa_url
        return self._publicar(self._container(**params))

    def story(self, url: str) -> str:
        if url.lower().endswith(".mp4"):
            cid = self._container(media_type="STORIES", video_url=url)
        else:
            cid = self._container(media_type="STORIES", image_url=url)
        return self._publicar(cid)

    def limite_publicacao(self):
        return self.get(f"{self.ig_id}/content_publishing_limit", fields="quota_usage,config")
