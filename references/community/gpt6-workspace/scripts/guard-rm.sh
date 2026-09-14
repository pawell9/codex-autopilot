#!/usr/bin/env bash
# PreToolUse: блокирует rm -rf за пределами папки проекта и любые rm -rf по корневым путям. exit 2 = блок.
# Вход — JSON события в stdin; поле с командой — [ПРОВЕРИТЬ] имя поля по документации хуков (ниже — tool_input.command).
set -u
payload="$(cat)"
cmd="$(printf '%s' "$payload" | python3 -c 'import sys,json
try:
    d=json.load(sys.stdin); print((d.get("tool_input") or {}).get("command",""))
except Exception: print("")' 2>/dev/null)"
case "$cmd" in
  *"rm -rf /"*|*"rm -rf ~"*|*"rm -rf \$HOME"*|*"rm -rf .."*)
    echo "guard-rm: удаление вне проекта заблокировано: $cmd" >&2; exit 2;;
esac
if printf '%s' "$cmd" | grep -Eq '(^|[;&| ])rm +-rf? ' && ! printf '%s' "$cmd" | grep -Eq 'rm +-rf? +(\./|[A-Za-z0-9_.-]+/?)( |$)'; then
  echo "guard-rm: rm -rf с абсолютным или странным путём — заблокировано: $cmd" >&2; exit 2
fi
exit 0
