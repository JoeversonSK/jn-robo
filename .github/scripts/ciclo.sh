#!/usr/bin/env bash
# Um ciclo do robô. Roda na raiz do jn-robo, com os dados privados em $JN_DADOS.
set -u
git -C "$JN_DADOS" pull -q --rebase -X theirs origin main || git -C "$JN_DADOS" rebase --abort 2>/dev/null
git pull -q --rebase origin main || git rebase --abort 2>/dev/null
echo "== $(TZ=America/Sao_Paulo date '+%d/%m %H:%M')"

# 1) mídia em trânsito: só o que sai nos próximos minutos fica pública
if [ "$(python -m jn.midia .)" = "mudou" ]; then
  git config user.name "jn-robo"; git config user.email "jn-robo@users.noreply.github.com"
  git add -A midia
  git diff --cached --quiet || { git commit -q -m "Robô: mídia em trânsito"; git push -q origin HEAD:main; }
  gh api -X POST "repos/$GITHUB_REPOSITORY/pages/builds" >/dev/null 2>&1 || true
fi

# 2) publica o que está aprovado e no horário (espera a mídia estar no ar)
python -m jn.publicar || true

# 3) salva a fila no repositório privado
bash .github/scripts/salvar_fila.sh
