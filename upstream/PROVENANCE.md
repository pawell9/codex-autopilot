# Upstream Autopilot — provenance

| Поле | Значение |
|---|---|
| Repository | https://github.com/nick-vels/skills |
| Branch | `main` |
| Commit SHA | `99c7e73678195cac08080bdd442f0e49a7ccb640` |
| Commit date | 2026-08-19 15:16:50 +0300 |
| Commit subject | «Таск в ремонте виден цветом, а не подписью» |
| Source path in repo | `skills/autopilot/` |
| Local path | `upstream/autopilot/` |
| Retrieved | 2026-09-12 (`git clone`, копия через `cp -Rp`, проверено `diff -r` — идентично) |
| Files | 21 |
| sha256 `SKILL.md` | `795a46e50a79d5f00b6decd161acd7a0c9737e5e71aae618bdb5beb63dee9eda` |
| sha256 of sorted per-file sha256 list | `0952dd0aff9fa45b7ab0a7b25369ec2ff96322ef1e7a1e12b0223deb94a6f84a` |

Содержимое `upstream/autopilot/` не изменялось.

## Что в upstream-репозитории есть, но сюда не скопировано

- `.agents/skills/autopilot` и `.claude/skills/autopilot` — симлинки на
  `skills/autopilot` (не отдельные копии).
- `README.md`, `LICENSE`, `assets/` (скриншоты дашборда, логотипы).
- `docs/audit-2026-08-17.md` — аудит автора upstream.
- `tools/measure-run.py` — утилита вне папки skill.
- `skills-lock.json` — `computedHash` `918d6306…` посчитан установщиком `skills`
  по своему алгоритму; с sha256 отдельного `SKILL.md` не сравнивается напрямую.

Перечитать можно командой:

```bash
git clone https://github.com/nick-vels/skills.git
git -C skills checkout 99c7e73678195cac08080bdd442f0e49a7ccb640
```
