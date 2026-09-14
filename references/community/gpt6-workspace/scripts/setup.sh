#!/usr/bin/env bash
# Разовая установка глобальных частей: правила команд → ~/.codex/rules. Проектные части (config, hooks, agents, skills) работают из папки.
set -eu
here="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$HOME/.codex/rules"
if [ -f "$HOME/.codex/rules/default.rules" ]; then
  cp "$HOME/.codex/rules/default.rules" "$HOME/.codex/rules/default.rules.bak.$(date +%Y%m%d%H%M%S)"
  echo "Старые правила сохранены в default.rules.bak.*"
fi
cp "$here/rules/default.rules" "$HOME/.codex/rules/default.rules"
echo "Правила команд установлены. Проверка: codex execpolicy check"
echo "Дальше: codex   (профиль work) или codex --profile night"
