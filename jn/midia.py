"""Mídia em trânsito: deixa no repositório PÚBLICO (jn-robo/midia/) só o que vai ser publicado em breve.

O Instagram precisa baixar as imagens e vídeos de um link público. Para não expor a fila inteira,
o relógio copia para jn-robo/midia/<post>/ apenas os posts APROVADOS que saem nos próximos minutos,
e apaga a pasta assim que o post foi publicado, recusado ou saiu da fila.

Uso: python -m jn.midia <pasta do jn-robo>   (imprime "mudou" se algo foi copiado ou removido)
"""
from __future__ import annotations

import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jn import fila

ANTECEDENCIA = timedelta(minutes=25)  # tempo para o GitHub Pages publicar antes do horário


def sincronizar(robo: Path, agora: datetime | None = None) -> bool:
    agora = agora or datetime.now(timezone.utc)
    destino = robo / "midia"
    destino.mkdir(exist_ok=True)
    querer = {}
    for it in fila.carregar():
        if it.status == "aprovado" and not it.validar() and it.quando <= agora + ANTECEDENCIA:
            arqs = list(it.dados["arquivos"]) + ([it.dados["capa"]] if it.dados.get("capa") else [])
            querer[it.nome] = (it.pasta, arqs)
    mudou = False
    for p in destino.iterdir():
        if p.is_dir() and p.name not in querer:
            shutil.rmtree(p)
            mudou = True
    for nome, (origem, arqs) in querer.items():
        alvo = destino / nome
        alvo.mkdir(exist_ok=True)
        for a in arqs:
            src, dst = origem / a, alvo / a
            if not dst.exists() or dst.stat().st_size != src.stat().st_size:
                shutil.copy2(src, dst)
                mudou = True
    (destino / ".gitkeep").touch()
    return mudou


if __name__ == "__main__":
    print("mudou" if sincronizar(Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()) else "igual")
