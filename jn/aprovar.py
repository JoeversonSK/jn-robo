"""Aprova posts da fila. Uso:
  python -m jn.aprovar              -> lista o que está aguardando
  python -m jn.aprovar todos        -> aprova tudo que está aguardando
  python -m jn.aprovar <pasta> ...  -> aprova só essas pastas
"""
import sys

from jn import fila, painel


def main(argv=None):
    nomes = sys.argv[1:] if argv is None else argv
    pend = [i for i in fila.carregar() if i.status == "aguardando aprovação"]
    if not nomes:
        for i in pend:
            print(f"{i.nome}  ({i.dados['tipo']}, {i.quando:%d/%m %H:%M})")
        print(f"{len(pend)} aguardando aprovação.")
        return
    alvo = pend if nomes == ["todos"] else [i for i in pend if i.nome in nomes]
    for i in alvo:
        erros = i.validar()
        if erros:
            print(f"x {i.nome}: não aprovado — {'; '.join(erros)}")
            continue
        i.dados["aprovado"] = True
        i.salvar()
        print(f"✓ {i.nome}")
    painel.atualizar()


if __name__ == "__main__":
    main()
