#!/bin/sh
# Publish this folder to GitHub, safely.
#
#   sh scripts/publish.sh                 commit everything that is not ignored, create the repo, push
#   sh scripts/publish.sh --no-push       only make the local commit (a good first try)
#   sh scripts/publish.sh -m "message"    choose the commit message
#   sh scripts/publish.sh --skip-workflows   leave .github/workflows out (GitHub refuses them unless your token has the
#                                         `workflow` scope: `gh auth refresh -s workflow` adds it)
#   sh scripts/publish.sh --branch v2     publish to a NEW branch (never overwrites one that exists; when the repository
#                                         already has a main branch, the new branch starts from it, so it can be reviewed
#                                         as a pull request)
#   GITHUB_REPO=owner/name sh scripts/publish.sh     publish somewhere else
#
# It starts a git repository if there is none, REFUSES to commit a file that looks like a secret (an API key, a
# private key, a saved key in a settings file) or a large file outside tests/data, shows what will be committed,
# and then pushes with the GitHub CLI (`gh`) if you have it, or tells you the two commands to run by hand.
# Safe to run again: with nothing new it does nothing.
set -eu

cd "$(dirname "$0")/.."
REPO="${GITHUB_REPO:-OmidMLdata/AGENTIC_VMD_v2}"
PUSH=1
MSG=""
BRANCH="main"
SKIP_WORKFLOWS=0
while [ $# -gt 0 ]; do
  case "$1" in
    --no-push) PUSH=0 ;;
    -m) shift; MSG="${1:-}" ;;
    --skip-workflows) SKIP_WORKFLOWS=1 ;;
    --branch) shift; BRANCH="${1:-}"; [ -n "$BRANCH" ] || { echo "--branch needs a name" >&2; exit 2; } ;;
    -h|--help) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1 (try --help)" >&2; exit 2 ;;
  esac
  shift
done

say() { printf '\n==> %s\n' "$*"; }
die() { printf '\npublish: %s\n' "$*" >&2; exit 1; }

command -v git >/dev/null 2>&1 || die "git is not installed (https://git-scm.com/downloads)."

if [ ! -d .git ]; then
  say "Starting a git repository"
  git init -q -b "$BRANCH" 2>/dev/null || { git init -q && git symbolic-ref HEAD "refs/heads/$BRANCH"; }
fi
if ! git remote get-url origin >/dev/null 2>&1 && command -v gh >/dev/null 2>&1 \
   && gh repo view "$REPO" >/dev/null 2>&1; then
  git remote add origin "https://github.com/$REPO.git"          # the repository already exists: publish into it
fi
if git remote get-url origin >/dev/null 2>&1; then
  say "Looking at the remote ($(git remote get-url origin))"
  git fetch -q origin || die "could not reach the remote (check your network and that you may push to it)."
  if git ls-remote --exit-code --heads origin "$BRANCH" >/dev/null 2>&1; then
    die "the remote already has a branch called $BRANCH; choose another name with --branch (this script never overwrites a branch)."
  fi
  if ! git rev-parse --verify -q HEAD >/dev/null && git rev-parse --verify -q origin/main >/dev/null; then
    # no commits here yet but the remote has a main: start the new branch from it (the working files are left alone)
    git symbolic-ref HEAD "refs/heads/$BRANCH"
    git reset -q origin/main
    BASED_ON="origin/main"
  fi
fi
[ -n "$(git config user.name 2>/dev/null)" ]  || [ -n "${GIT_AUTHOR_NAME:-}" ]  || die "git does not know who you are. Run:  git config --global user.name \"Your Name\""
[ -n "$(git config user.email 2>/dev/null)" ] || [ -n "${GIT_AUTHOR_EMAIL:-}" ] || die "git does not know your email. Run:  git config --global user.email you@example.com"

say "Checking what would be committed"
FILES="$( { git ls-files; git ls-files --others --exclude-standard; } | sort -u )"
[ -n "$FILES" ] || die "nothing to commit."
BAD=""
# 1. secrets
for f in $FILES; do
  [ -f "$f" ] || continue
  if grep -IqE 'sk-ant-[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9]{32,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|"llm_key": *"[^"]+"|ghp_[A-Za-z0-9]{30,}' "$f" 2>/dev/null; then
    BAD="$BAD\n  looks like a secret:  $f"
  fi
done
# 2. big files (tests/data holds the real test data and is allowed)
for f in $FILES; do
  [ -f "$f" ] || continue
  case "$f" in tests/data/*) continue ;; esac
  size=$(wc -c < "$f" | tr -d ' ')
  [ "$size" -gt 5000000 ] && BAD="$BAD\n  larger than 5 MB:     $f ($((size / 1000000)) MB)"
done
if [ -n "$BAD" ]; then
  printf '%b\n' "$BAD" >&2
  die "refusing to commit. Remove the file, or add it to .gitignore, and run this again."
fi

if ! git rev-parse --verify -q HEAD >/dev/null; then
  git symbolic-ref HEAD "refs/heads/$BRANCH"                     # no commits yet: the first one goes on the chosen branch
elif [ "$(git symbolic-ref --short HEAD 2>/dev/null)" != "$BRANCH" ]; then
  git checkout -q -b "$BRANCH" || die "could not create the branch $BRANCH here (does it already exist locally?)."
fi
git add -A
[ "$SKIP_WORKFLOWS" -eq 1 ] && { git reset -q -- .github/workflows 2>/dev/null || true; }
CHANGED="$(git status --short | wc -l | tr -d ' ')"
if [ "$CHANGED" -gt 0 ]; then
  git status --short | head -25
  [ "$CHANGED" -gt 25 ] && echo "  ... and $((CHANGED - 25)) more"
  if [ -n "${BASED_ON:-}" ]; then : "${MSG:=Add vmd-agent v2 (replaces the earlier contents)}"
  elif git rev-parse --verify -q HEAD >/dev/null; then : "${MSG:=Update}"
  else : "${MSG:=Initial commit}"; fi
  git commit -q -m "$MSG"
  say "Committed $CHANGED changed files: $MSG"
else
  say "Nothing new to commit"
fi

[ "$PUSH" -eq 1 ] || { say "Not pushing (--no-push). To publish later:  sh scripts/publish.sh"; exit 0; }

if git remote get-url origin >/dev/null 2>&1; then
  say "Pushing branch $BRANCH to $(git remote get-url origin)"
  PUSHERR="$(mktemp)"
  if ! git push -u origin "$BRANCH" 2>"$PUSHERR"; then
    cat "$PUSHERR" >&2
    if grep -q "without .workflow. scope" "$PUSHERR"; then
      printf "\nGitHub refuses .github/workflows without the 'workflow' token scope. Either run:  gh auth refresh -s workflow\nor publish without them:  sh scripts/publish.sh --skip-workflows --branch %s\n" "$BRANCH" >&2
    fi
    rm -f "$PUSHERR"
    die "the push failed (see above)."
  fi
  rm -f "$PUSHERR"
elif command -v gh >/dev/null 2>&1; then
  gh auth status >/dev/null 2>&1 || gh auth login
  say "Creating https://github.com/$REPO and pushing"
  gh repo create "$REPO" --public --source=. --remote=origin --push \
    --description "Ask questions about molecular structures and simulations in plain language; VMD does the measuring and drawing."
else
  cat <<EOF

The GitHub CLI (gh) is not installed. Do this by hand:
  1. Create an EMPTY repository named ${REPO#*/} at https://github.com/new  (no README, licence or .gitignore)
  2. git remote add origin https://github.com/$REPO.git
  3. git push -u origin $BRANCH
EOF
  exit 0
fi
say "Published: $(git remote get-url origin) (branch $BRANCH)"
