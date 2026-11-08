"""Gera FILA.md: a lista de tudo que está programado, para ver no GitHub (até pelo celular)."""
from __future__ import annotations

from jn import fila

ICONES = {
    "aguardando aprovação": "🟡 aguardando aprovação",
    "aprovado": "🟢 aprovado",
    "publicado": "✅ publicado",
    "falhou": "🔴 falhou",
    "recusado": "⛔ recusado",
}


def _linha(it: fila.Item, base: str) -> str:
    d = it.dados
    quando = it.quando.strftime("%d/%m %H:%M")
    prev = ""
    arqs = d.get("arquivos") or []
    img = d.get("capa") or next((a for a in arqs if a.lower().endswith((".jpg", ".jpeg"))), None)
    if img:
        prev = f'<img src="{base}/{it.nome}/{img}" width="90">'
    status = ICONES.get(it.status, it.status)
    erros = it.validar() if it.status != "publicado" else []
    if erros:
        status = "⚠️ " + "; ".join(erros)
    elif d.get("ultimo_erro"):
        status += f" — último erro: {d['ultimo_erro']}"
    legenda = (d.get("legenda") or "").split("\n")[0][:70].replace("|", "/")
    return f"| {quando} | {d.get('tipo')} | {prev} | {legenda} | {status} | `{base}/{it.nome}` |"


def atualizar() -> None:
    linhas = [
        "# Fila de conteúdo — JN Higienização",
        "",
        "Para aprovar, use o app no celular: https://joeversonsk.github.io/jn-marketing/app/",
        "O sistema publica sozinho quando chegar o horário (confere a cada 10 minutos).",
        "",
        "## Programados",
        "",
        "| Quando | Tipo | Prévia | Legenda | Situação | Pasta |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    pend = fila.carregar(fila.CONTEUDO)
    linhas += [_linha(i, "conteudo") for i in pend] or ["| — | — | — | Nada programado | — | — |"]
    pub = fila.carregar(fila.PUBLICADO)[-10:]
    if pub:
        linhas += ["", "## Últimos publicados", "",
                   "| Quando | Tipo | Prévia | Legenda | Situação | Pasta |",
                   "| --- | --- | --- | --- | --- | --- |"]
        linhas += [_linha(i, "publicado") for i in reversed(pub)]
    (fila.RAIZ / "FILA.md").write_text("\n".join(linhas) + "\n", encoding="utf-8")


if __name__ == "__main__":
    atualizar()
