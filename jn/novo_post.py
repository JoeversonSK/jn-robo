"""Adiciona um post à fila, já convertendo as imagens para JPG no tamanho certo.

Exemplos:
  python -m jn.novo_post --tipo post --quando "2026-11-09 12:00" --legenda legenda.txt arte.png
  python -m jn.novo_post --tipo carrossel --quando "2026-11-11 19:00" --legenda "Texto aqui" 1.png 2.png 3.png
  python -m jn.novo_post --tipo story --quando "2026-11-10 09:00" story.png
  python -m jn.novo_post --tipo reel --quando "2026-11-09 12:00" --legenda legenda.txt video.mp4 --capa capa.png

O post entra com "aprovado": false. Para liberar: python -m jn.aprovar <pasta>
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import unicodedata
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps

from jn import fila, painel

TAMANHOS = {"story": (1080, 1920), "reel": (1080, 1920)}
FEED = (1080, 1350)  # 4:5, ocupa mais tela no feed


def slug(t: str) -> str:
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:40] or "post"


def converter_imagem(origem: Path, destino: Path, tamanho: tuple[int, int]):
    img = Image.open(origem)
    img = ImageOps.exif_transpose(img).convert("RGB")
    img = ImageOps.fit(img, tamanho, Image.LANCZOS)
    img.save(destino, "JPEG", quality=92, optimize=True)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--tipo", required=True, choices=sorted(fila.TIPOS))
    ap.add_argument("--quando", required=True, help='"AAAA-MM-DD HH:MM" no horário de Brasília')
    ap.add_argument("--legenda", default="", help="texto ou caminho de um .txt")
    ap.add_argument("--nome", default="", help="nome curto da pasta")
    ap.add_argument("--capa", help="imagem de capa (só reel)")
    ap.add_argument("arquivos", nargs="+")
    a = ap.parse_args(argv)

    quando = datetime.strptime(a.quando, "%Y-%m-%d %H:%M").replace(tzinfo=fila._brt())
    legenda = a.legenda
    if legenda and Path(legenda).is_file():
        legenda = Path(legenda).read_text(encoding="utf-8").strip()

    nome = f"{quando:%Y-%m-%d-%H%M}-{a.tipo}-{slug(a.nome or legenda[:40] or a.tipo)}"
    pasta = fila.CONTEUDO / nome
    pasta.mkdir(parents=True, exist_ok=False)
    tamanho = TAMANHOS.get(a.tipo, FEED)

    saida = []
    for n, arq in enumerate(a.arquivos, 1):
        p = Path(arq)
        if p.suffix.lower() in (".mp4", ".mov"):
            destino = f"{n:02d}.mp4"
            shutil.copy(p, pasta / destino)
        else:
            destino = f"{n:02d}.jpg"
            converter_imagem(p, pasta / destino, tamanho)
        saida.append(destino)

    dados = {"tipo": a.tipo, "publicar_em": quando.isoformat(), "legenda": legenda,
             "arquivos": saida, "aprovado": False}
    if a.capa:
        converter_imagem(Path(a.capa), pasta / "capa.jpg", tamanho)
        dados["capa"] = "capa.jpg"

    item = fila.Item(pasta, dados)
    item.salvar()
    erros = item.validar()
    painel.atualizar()
    print(f"Criado: conteudo/{nome}")
    for e in erros:
        print(f"  atenção: {e}")


if __name__ == "__main__":
    main()
