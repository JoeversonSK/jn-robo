"""Renova o token do Instagram (ele vence em 60 dias) e imprime o novo.

No GitHub Actions o workflow pega a saída e grava no segredo IG_ACCESS_TOKEN.
"""
import os
import sys

import requests


def main():
    token = os.environ.get("IG_ACCESS_TOKEN")
    if not token:
        sys.exit("IG_ACCESS_TOKEN não configurado.")
    if not token.startswith("IG"):
        # token do login unificado (usuário do sistema) não vence: nada a renovar
        print("Token do login unificado não expira; nada a renovar.", file=sys.stderr)
        print(token)
        return
    r = requests.get(
        "https://graph.instagram.com/refresh_access_token",
        params={"grant_type": "ig_refresh_token", "access_token": token},
        timeout=60,
    )
    d = r.json()
    if "access_token" not in d:
        sys.exit(f"Falha ao renovar: {d.get('error', d)}")
    dias = int(d.get("expires_in", 0)) // 86400
    print(f"Token renovado. Vale por mais {dias} dias.", file=sys.stderr)
    print(d["access_token"])


if __name__ == "__main__":
    main()
