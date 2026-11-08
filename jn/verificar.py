"""Testa o token e mostra o ID da conta. Uso: python -m jn.verificar

Não imprime o token. Mostra o tipo, o servidor usado e as respostas da Meta.
"""
import os
import sys

import requests

from jn.instagram import GRAPH_VERSION, ErroInstagram, Instagram, host_para


def tentar(host, caminho, token, **params):
    params["access_token"] = token
    try:
        r = requests.get(f"https://{host}/{GRAPH_VERSION}/{caminho}", params=params, timeout=30)
        d = r.json()
    except Exception as e:  # noqa: BLE001
        return f"falhou: {e}"
    if "error" in d:
        return f"erro: {d['error'].get('message')}"
    return d


def main():
    token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    if not token:
        sys.exit("IG_ACCESS_TOKEN não configurado.")
    id_cfg = os.environ.get("IG_USER_ID") or None
    print(f"Token: começa com '{token[:3]}...', {len(token)} caracteres")
    print(f"Servidor escolhido: {host_para(token)}")
    for host in ("graph.instagram.com", "graph.facebook.com"):
        print(f"\n[{host}]")
        if host == "graph.facebook.com":
            print("  me:", tentar(host, "me", token, fields="id,name"))
            print("  permissoes:", tentar(host, "me/permissions", token))
            print("  contas IG ligadas:", tentar(host, "me", token,
                  fields="instagram_accounts{id,username},businesses{id,name}"))
        else:
            print("  me:", tentar(host, "me", token, fields="user_id,username"))
        if host == "graph.facebook.com":
            print("  me/accounts:", tentar(host, "me/accounts", token,
                                           fields="name,instagram_business_account{id,username}"))
        if id_cfg:
            print("  IG_USER_ID:", tentar(host, id_cfg, token, fields="id,username"))

    print()
    try:
        ig = Instagram(token, id_cfg)
        perfil = ig.meu_perfil()
        limite = ig.limite_publicacao()
    except ErroInstagram as e:
        sys.exit(f"Não funcionou com a configuração atual: {e}")
    print(f"OK! Conectado como @{perfil.get('username')} (ID {ig.ig_id}) via {ig.host}")
    print(f"Limite de publicação: {limite}")


if __name__ == "__main__":
    main()
