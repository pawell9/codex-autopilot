#!/usr/bin/env bash
# PreToolUse: перед git push гоняет сканер безопасности по репозиторию. Нашёл — блок (exit 2).
# Сканер: npx @openai/codex-security (работает без облака). [ПРОВЕРИТЬ] флаги и формат вывода.
set -u
payload="$(cat)"
cmd="$(printf '%s' "$payload" | python3 -c 'import sys,json
try:
    d=json.load(sys.stdin); print((d.get("tool_input") or {}).get("command",""))
except Exception: print("")' 2>/dev/null)"
case "$cmd" in
  *"git push"*)
    if command -v npx >/dev/null 2>&1; then
      if ! npx --yes @openai/codex-security >/tmp/codex-security.log 2>&1; then
        echo "security: найдены проблемы, push заблокирован. Лог: /tmp/codex-security.log" >&2; exit 2
      fi
    fi;;
esac
exit 0
