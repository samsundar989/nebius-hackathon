#!/usr/bin/env bash
# Replace your personal e-mail in the repository's history with your GitHub noreply address
# (QUESTION 0012; for Samuel to run, only if he answers yes). Prepared by Claude Code, never run
# by it: a history rewrite cannot be undone once pushed.
#
#   scripts/rewrite_history.sh --dry-run NOREPLY      list what would change; changes nothing
#   scripts/rewrite_history.sh NOREPLY                rewrite in a fresh clone next to this one
#
# NOREPLY is the address GitHub shows under Settings -> Emails ("Keep my email addresses
# private"), e.g. 12345678+yourname@users.noreply.github.com. The old address defaults to this
# checkout's `git config user.email`; pass OLD=... to override.
#
# Needs git-filter-repo (`pip install git-filter-repo`). It works on a fresh clone in
# ../nebius-hackathon-rewrite, keeps a backup branch there, rewrites author/committer e-mails
# (mailmap) and the address inside file contents (replace-text), and prints the one force-push
# command for you to run yourself. This checkout is left untouched.
set -euo pipefail

dry=0
if [ "${1:-}" = "--dry-run" ]; then dry=1; shift; fi
NOREPLY="${1:?usage: $0 [--dry-run] NOREPLY_ADDRESS}"
OLD="${OLD:-$(git config user.email)}"
NAME="$(git config user.name)"
HERE="$(git rev-parse --show-toplevel)"
REMOTE="$(git -C "$HERE" remote get-url origin)"

echo "old address: $OLD"
echo "new address: $NOREPLY"
echo "commits with the old address as author or committer:"
git -C "$HERE" log --all --format='%h %an <%ae> | %cn <%ce> | %s' \
  | grep -F "$OLD" | sed 's/^/  /' | head -50
echo "  ($(git -C "$HERE" log --all --format='%ae %ce' | grep -cF "$OLD") in total)"
echo "commits whose content adds or removes the old address:"
git -C "$HERE" log --all --oneline -S "$OLD" | sed 's/^/  /'
echo "files that contain it now:"
git -C "$HERE" grep -lF "$OLD" || echo "  (none)"
if [ "$dry" = 1 ]; then
  echo "dry run: nothing changed."
  exit 0
fi

command -v git-filter-repo >/dev/null || { echo "install git-filter-repo first" >&2; exit 1; }
WORK="$(dirname "$HERE")/nebius-hackathon-rewrite"
[ -e "$WORK" ] && { echo "$WORK exists; remove it first" >&2; exit 1; }
git clone --no-local "$HERE" "$WORK"
cd "$WORK"
git branch "backup/pre-rewrite-$(date +%Y%m%d-%H%M)"
tmp="$(mktemp -d)"
printf '%s <%s> <%s>\n' "$NAME" "$NOREPLY" "$OLD" > "$tmp/mailmap"
printf '%s==><your git identity>\n' "$OLD" > "$tmp/replace"
git filter-repo --force --mailmap "$tmp/mailmap" --replace-text "$tmp/replace"
git remote add origin "$REMOTE"
echo
echo "rewritten in $WORK; check it:"
echo "  git -C '$WORK' log --format='%an <%ae>' | sort | uniq -c"
echo "  git -C '$WORK' grep -F '$OLD' || echo clean"
echo "then, from $WORK, the one command that publishes it (cannot be undone):"
echo "  git push --force origin main"
