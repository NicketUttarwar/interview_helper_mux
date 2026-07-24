#!/usr/bin/env bash
# Soft lexicon check on a small core set.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

CORE=(
  "$ROOT/docs/workflows/operator-gates.md"
  "$ROOT/docs/prompts/_shared/analysis-preamble.system.txt"
)

bad=""
for f in "${CORE[@]}"; do
  [[ -f "$f" ]] || continue
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    if echo "$line" | rg -qi '\bvolley\b' && ! echo "$line" | rg -qi 'speaker volley|LLM volley|llm volley|message packet|message-packet|compact|framer|arbiter|user / assistant|system / user'; then
      bad+="$f:$line"$'\n'
    fi
  done < <(rg -n -i '\bvolley\b' "$f" 2>/dev/null || true)
done

if [[ -n "$bad" ]]; then
  echo "Ambiguous bare 'volley' in core docs (qualify as speaker volley or LLM volley):"
  echo "$bad"
  exit 1
fi
echo "volley lexicon check (core docs): ok"
echo "Historical schema keys (volley.turns, build_message_volley) are LLM volley — see volley-glossary.md / volley-inventory.md"
