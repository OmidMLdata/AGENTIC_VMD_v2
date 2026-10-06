#!/usr/bin/env bash
# Pushes AGENTIC_VMD_v2 to https://github.com/OmidMLdata/AGENTIC_VMD_v2
# Run from inside the unzipped AGENTIC_VMD_v2 folder:  bash push_to_github.sh
set -euo pipefail
REPO="OmidMLdata/AGENTIC_VMD_v2"

# Use your own git identity on the commits if you have one configured
if git config --global user.email >/dev/null 2>&1; then
  git rebase -q --root --exec 'git commit -q --amend --no-edit --reset-author'
fi

if command -v gh >/dev/null 2>&1; then
  gh auth status >/dev/null 2>&1 || gh auth login
  gh repo create "$REPO" --public --source=. --remote=origin --push \
    --description "Toolkit and benchmark for LLM-driven molecular visualization (VMD-style workflows)" \
  || git push -u origin main
else
  echo "GitHub CLI not found. Create an EMPTY repo named AGENTIC_VMD_v2 at https://github.com/new"
  echo "(no README/license/.gitignore), then press Enter."
  read -r
  git push -u origin main
fi
echo "Done: https://github.com/$REPO"
