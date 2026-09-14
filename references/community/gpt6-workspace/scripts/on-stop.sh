#!/usr/bin/env bash
# Stop: напоминание про отчёт ночной смены, если работа шла под профилем night. Ничего не блокирует.
set -u
if [ "${CODEX_PROFILE:-}" = "night" ]; then   # [ПРОВЕРИТЬ] имя переменной с активным профилем
  echo "night: перед завершением — отчёт по шаблону из .agents/skills/night/SKILL.md и ссылка на снимок чата."
fi
exit 0
