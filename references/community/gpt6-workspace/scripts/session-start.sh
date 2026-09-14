#!/usr/bin/env bash
# SessionStart: проверяет, что глобальные части рабочего места на месте. Ничего не блокирует.
set -u
missing=()
[ -f "$HOME/.codex/rules/default.rules" ] || missing+=("~/.codex/rules/default.rules — правила команд (scripts/setup.sh скопирует)")
if [ ${#missing[@]} -gt 0 ]; then
  echo "Рабочее место: не хватает —"
  printf '  %s\n' "${missing[@]}"
fi
exit 0
