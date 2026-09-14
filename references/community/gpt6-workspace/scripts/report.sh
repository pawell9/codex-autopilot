#!/usr/bin/env bash
# Отчёт по логам строгим JSON — вход для n8n и скриптов. Запуск без интерфейса: codex exec.
# Использование: scripts/report.sh [запрос] [файл_вывода]
# --output-schema заставляет ответ соответствовать schemas/report.json; --json печатает события по ходу (для отладки добавь флаг).
set -eu
here="$(cd "$(dirname "$0")/.." && pwd)"
query="${1:-Собери отчёт по логам за последние сутки: ошибки по типам, топ-5 по частоте, что чинить первым и почему.}"
out="${2:-$here/report.json}"
codex exec --profile safe --output-schema "$here/schemas/report.json" -o "$out" "$query"
echo "Отчёт: $out"
# Продолжить тот же прогон: codex exec resume --last "уточни второй пункт"
