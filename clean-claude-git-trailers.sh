#!/usr/bin/env bash
# Remove Claude/Anthropic co-author or co-editor trailers from a local branch.
#
# Usage: ./clean-claude-git-trailers.sh [branch]
#
# The script does not push. It makes both an explicit backup ref and Git's
# standard refs/original backup before changing the chosen local branch.

set -euo pipefail

die() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

git rev-parse --git-dir >/dev/null 2>&1 || die 'run this inside a Git repository'

branch="${1:-$(git branch --show-current)}"
[[ -n "$branch" ]] || die 'pass the local branch to rewrite (for example: main)'
git check-ref-format --branch "$branch" >/dev/null || die "invalid branch name: $branch"
git show-ref --verify --quiet "refs/heads/$branch" || die "local branch does not exist: $branch"

[[ -z "$(git status --porcelain)" ]] || die 'working tree is not clean'

# The verification below pairs commits oldest-to-newest, so reject merge
# histories instead of claiming a validation the script cannot establish.
if git rev-list --parents "$branch" | awk 'NF > 2 { exit 1 }'; then
  :
else
  die 'branch has merge commits; use a merge-aware history-rewrite tool'
fi

has_claude_trailer() {
  git show -s --format=%B "$1" |
    grep -Eiq '^co-(authored|edited)-by:.*(claude|anthropic)'
}

affected=0
while IFS= read -r commit; do
  if has_claude_trailer "$commit"; then
    affected=$((affected + 1))
  fi
done < <(git rev-list "$branch")

if (( affected == 0 )); then
  printf 'No Claude/Anthropic co-author or co-editor trailers found on %s; nothing changed.\n' "$branch"
  exit 0
fi

old_tip="$(git rev-parse "$branch")"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_ref="refs/backup/pre-remove-claude-trailers/${branch}-${timestamp}"
git update-ref "$backup_ref" "$old_tip"

before_file="$(mktemp "${TMPDIR:-/tmp}/claude-trailers-before.XXXXXX")"
after_file="$(mktemp "${TMPDIR:-/tmp}/claude-trailers-after.XXXXXX")"
trap 'rm -f "$before_file" "$after_file"' EXIT

before_count="$(git rev-list --count "$branch")"
git log --reverse --format='%H%x09%T%x09%an%x09%ae%x09%at%x09%cn%x09%ce%x09%ct' "$branch" >"$before_file"

printf 'Rewriting %s (%d matching trailer(s)); backup: %s\n' "$branch" "$affected" "$backup_ref"
FILTER_BRANCH_SQUELCH_WARNING=1 git filter-branch --force \
  --msg-filter 'perl -ne '\''print unless /^co-(?:authored|edited)-by:.*(?:claude|anthropic)/i'\''' \
  -- "$branch"

after_count="$(git rev-list --count "$branch")"
git log --reverse --format='%H%x09%T%x09%an%x09%ae%x09%at%x09%cn%x09%ce%x09%ct' "$branch" >"$after_file"

[[ "$before_count" == "$after_count" ]] || die "commit count changed: $before_count -> $after_count"

if ! paste "$before_file" "$after_file" | awk -F '\t' '
  NF != 16 { mismatch = 1 }
  { for (i = 2; i <= 8; i++) if ($i != $(i + 8)) mismatch = 1 }
  END { exit mismatch }
'; then
  die 'tree, author, or timestamp verification failed; recover from the backup ref above'
fi

remaining=0
while IFS= read -r commit; do
  if has_claude_trailer "$commit"; then
    remaining=$((remaining + 1))
  fi
done < <(git rev-list "$branch")
(( remaining == 0 )) || die "$remaining matching trailer(s) remain; recover from the backup ref above"

new_tip="$(git rev-parse "$branch")"
printf 'Success: rewrote %s; %d commits retained; no matching trailers remain.\n' "$branch" "$after_count"
printf 'Backup ref: %s\n' "$backup_ref"
printf 'No remote was changed. To publish, review first and then run:\n'
printf '  git push --force-with-lease=refs/heads/%s:%s origin %s\n' "$branch" "$old_tip" "$branch"
printf 'New local tip: %s\n' "$new_tip"
