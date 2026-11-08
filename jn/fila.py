"""Fila de conteúdo.

Cada post é uma pasta dentro de `conteudo/` com um `post.json`:

{
  "tipo": "post" | "carrossel" | "reel" | "story",
  "publicar_em": "2026-11-09T12:00:00-03:00",
  "legenda": "texto do post",
  "arquivos": ["arte.jpg"],          # na ordem; reel = [video.mp4] (+ "capa" opcional)
  "capa": "capa.jpg",                # opcional, só para reel
  "aprovado": false                  # o dono muda para true para liberar
}

Depois de publicado, a pasta vai para `publicado/` com `media_id` e `publicado_em`.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import os

# Os dados (fila, publicados, métricas) ficam no repositório PRIVADO jn-marketing.
# JN_DADOS aponta para a cópia dele; sem a variável, usa a pasta deste código (testes/uso local).
RAIZ = Path(os.environ.get("JN_DADOS") or Path(__file__).resolve().parent.parent).resolve()
CONTEUDO = RAIZ / "conteudo"
PUBLICADO = RAIZ / "publicado"
TIPOS = {"post", "carrossel", "reel", "story"}
MAX_TENTATIVAS = 3


@dataclass
class Item:
    pasta: Path
    dados: dict = field(default_factory=dict)

    @property
    def nome(self) -> str:
        return self.pasta.name

    @property
    def quando(self) -> datetime:
        q = datetime.fromisoformat(self.dados["publicar_em"])
        if q.tzinfo is None:  # sem fuso = horário de Brasília
            q = q.replace(tzinfo=_brt())
        return q

    @property
    def status(self) -> str:
        if self.dados.get("media_id"):
            return "publicado"
        if self.dados.get("recusado"):
            return "recusado"
        if self.dados.get("falhou"):
            return "falhou"
        if not self.dados.get("aprovado"):
            return "aguardando aprovação"
        return "aprovado"

    def salvar(self):
        (self.pasta / "post.json").write_text(
            json.dumps(self.dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    def validar(self) -> list[str]:
        erros = []
        d = self.dados
        if d.get("tipo") not in TIPOS:
            erros.append(f"tipo inválido: {d.get('tipo')!r} (use {', '.join(sorted(TIPOS))})")
        try:
            self.quando
        except Exception:
            erros.append("publicar_em inválido (formato: 2026-11-09T12:00:00-03:00)")
        arqs = d.get("arquivos") or []
        if not arqs:
            erros.append("nenhum arquivo em 'arquivos'")
        for a in arqs + ([d["capa"]] if d.get("capa") else []):
            if not (self.pasta / a).exists():
                erros.append(f"arquivo não encontrado: {a}")
            elif not a.lower().endswith((".jpg", ".jpeg", ".mp4")):
                erros.append(f"{a}: o Instagram só aceita JPG (fotos) e MP4 (vídeos)")
        tipo = d.get("tipo")
        if tipo == "reel" and (len(arqs) != 1 or not arqs[0].lower().endswith(".mp4")):
            erros.append("reel precisa de exatamente 1 vídeo .mp4")
        if tipo == "post" and len(arqs) != 1:
            erros.append("post precisa de exatamente 1 arquivo (para vários, use carrossel)")
        if tipo == "carrossel" and not (2 <= len(arqs) <= 10):
            erros.append("carrossel precisa de 2 a 10 arquivos")
        if tipo == "story" and len(arqs) != 1:
            erros.append("story precisa de exatamente 1 arquivo")
        if tipo != "story" and len(d.get("legenda", "")) > 2200:
            erros.append("legenda passa de 2.200 caracteres")
        return erros


def _brt():
    from datetime import timedelta
    return timezone(timedelta(hours=-3))


def carregar(pasta_base: Path | None = None) -> list[Item]:
    pasta_base = pasta_base or CONTEUDO
    itens = []
    if not pasta_base.exists():
        return itens
    for p in sorted(pasta_base.iterdir()):
        arq = p / "post.json"
        if p.is_dir() and arq.exists():
            itens.append(Item(p, json.loads(arq.read_text(encoding="utf-8"))))
    return sorted(itens, key=lambda i: i.dados.get("publicar_em", ""))


def prontos_para_publicar(agora: datetime | None = None) -> list[Item]:
    agora = agora or datetime.now(timezone.utc)
    saida = []
    for it in carregar():
        if it.status != "aprovado" or it.validar():
            continue
        if it.quando <= agora:
            saida.append(it)
    return saida


def mover_para_publicado(item: Item) -> Path:
    PUBLICADO.mkdir(exist_ok=True)
    destino = PUBLICADO / item.nome
    if destino.exists():
        shutil.rmtree(destino)
    shutil.move(str(item.pasta), str(destino))
    item.pasta = destino
    return destino
