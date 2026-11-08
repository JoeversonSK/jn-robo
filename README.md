# jn-robo

Robô de publicação e app de aprovação da **JN Higienização** (@jn_.higienizacao).

Este repositório é **público e não guarda dados**. A fila de posts, as artes, os números e o sistema de design ficam no
repositório **privado** `jn-marketing`.

| O quê | Onde |
| --- | --- |
| Código do robô (`jn/`), fluxos automáticos (`.github/`) | aqui (público) |
| App de aprovação: https://joeversonsk.github.io/jn-robo/app/ | aqui (público; sem a chave não mostra nada) |
| Fila, publicados, métricas, artes, design | `jn-marketing` (privado) |
| Tokens do Instagram e do GitHub | Segredos do GitHub (nunca em arquivos) |

## Como funciona

O **Relógio da fila** confere a fila a cada 5 minutos:

1. baixa a fila do repositório privado (segredo `DADOS_TOKEN`);
2. copia para `midia/` **só** a mídia dos posts aprovados que saem nos próximos 25 minutos — o Instagram precisa de um link público para baixar;
3. publica o que está no horário;
4. apaga de `midia/` o que já foi publicado;
5. salva a fila atualizada no repositório privado;
6. de hora em hora, coleta as métricas do painel "Resultados".

## Segredos (Settings → Secrets and variables → Actions)

| Nome | O que é |
| --- | --- |
| `IG_ACCESS_TOKEN` | token do usuário do sistema `jn-robo` (Meta Business), não vence |
| `IG_USER_ID` | `17841447491627225` |
| `DADOS_TOKEN` | chave do GitHub (fine-grained) só com **jn-marketing → Contents: Read and write** |

## Testes

```
pip install -r requirements.txt pytest
python -m pytest -q
```
