#!/usr/bin/env bash
# Parallel shallow-clone of the research corpus.
# Usage: clone.sh [manifest] [parallelism]
set -uo pipefail

ROOT="/home/bud/ditto/agent-inter-op"
MANIFEST="${1:-$ROOT/scripts/repos.manifest}"
PAR="${2:-10}"
DEST="$ROOT/research/repos"
LOG="$ROOT/research/repos/_clone.log"

mkdir -p "$DEST"
: > "$LOG"

clone_one() {
  local cat="$1" name="$2" url="$3" depth="$4"
  local dir="$DEST/$cat/$name"
  if [ -d "$dir/.git" ]; then
    echo "SKIP  $cat/$name (exists)" >> "$LOG"; return 0
  fi
  mkdir -p "$(dirname "$dir")"
  if GIT_TERMINAL_PROMPT=0 git clone --depth "$depth" --single-branch --quiet "$url" "$dir" 2>>"$LOG"; then
    local n; n=$(find "$dir" -type f -not -path '*/.git/*' | wc -l)
    echo "OK    $cat/$name  files=$n" >> "$LOG"
  else
    echo "FAIL  $cat/$name  $url" >> "$LOG"
    rm -rf "$dir"
  fi
}
export -f clone_one
export DEST LOG

grep -v '^\s*#' "$MANIFEST" | grep -v '^\s*$' | \
  awk -F'\t' '{print $1"\t"$2"\t"$3"\t"$4}' | \
  xargs -P "$PAR" -I{} bash -c 'IFS=$'"'"'\t'"'"' read -r c n u d <<< "{}"; clone_one "$c" "$n" "$u" "${d:-1}"'

echo "=== DONE ===" >> "$LOG"
{ echo "OK:   $(grep -c '^OK'   "$LOG")"
  echo "SKIP: $(grep -c '^SKIP' "$LOG")"
  echo "FAIL: $(grep -c '^FAIL' "$LOG")"; } >> "$LOG"
