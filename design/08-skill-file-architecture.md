# Future skill file architecture

**DECISION.** Один explicitly invoked skill `codex-autopilot`, 16 core production package files; optional reviewer setup artifact зависит от E03. Здесь только blueprint: ни одного из перечисленных production-файлов этот pass не создаёт. Логика основана на [writing-for-agents](/Users/pawell_9/.agents/skills/writing-for-agents/SKILL.md) как методологии hierarchy/co-location; локальный установленный источник: `/Users/pawell_9/.agents/skills/writing-for-agents/SKILL.md`.

## Invocation contract and syntax conflict

Purpose: invoke explicitly to start/resume/cancel a scoped Autopilot run or inspect its status. Ordinary «fix this typo» не должен включать весь lifecycle неявно. Один entry route выбирает нужную sequence; subskills/router zoo не нужны.

**FACT:** Codex documented invocation policy — `policy.allow_implicit_invocation: false` в `agents/openai.yaml`; name/description metadata и `SKILL.md` progressive disclosure описаны в [Build skills](https://learn.chatgpt.com/docs/build-skills).

**DECISION:** используем этот Codex mechanism. `disable-model-invocation: true` из SKILL-MECHANICS не переносится как Codex frontmatter. «Zero context load» не обещается: official docs говорят о начальном name/description/path inventory, поэтому metadata всё равно короткая. YAML здесь metadata skill, не `.toml` custom agent. Schema/API syntax перед implementation сверяется по текущему supported build, без global edits.

## Proposed package

```text
codex-autopilot/
├── SKILL.md
├── agents/openai.yaml
├── phases/
│   ├── start.md
│   ├── intent.md
│   ├── design.md
│   ├── plan.md
│   ├── execute.md
│   ├── recover.md
│   └── accept.md
├── references/
│   ├── ledger.md
│   ├── routing.md
│   └── safety.md
├── contracts/
│   ├── worker.md
│   └── reviewer.md
├── schemas/contracts.schema.json
└── tools/ledger.py
```

No dashboard/assets/prompts copied from upstream. Future development tests/fixtures — отдельная repo test area с coverage из 09/10, не дополнительный always-read skill subtree. `tools/ledger.py` — ограниченный deterministic helper, не процесс orchestration и не model bridge.

## Per-file contracts and information budget

Budgets — ориентировочные **слова для authored prose**, строки для metadata, conceptual definition size для schema/helper. Это design authoring targets, не hard truncation/runtime constants и не evidence об оптимальном размере. Не сокращать обязательный acceptance criterion ради числа слов.

| File | Purpose / invocation condition | Reader | Why separate / budget |
|---|---|---|---|
| `SKILL.md` | Entry purpose, invariants-as-short-guards, explicit delegation request, classify start/status/resume/pause/cancel, route next phase | Orchestrator при invocation | Единственный human entry; 350–550 слов, description 1 короткое предложение |
| `agents/openai.yaml` | Explicit invocation policy и минимальные UI name/summary | Codex loader | Native metadata; примерно 6–12 meaningful строк; no dependencies/config role duplication |
| `phases/start.md` | G0 cheap checks; canonical root/owner lookup; new/resume branch; conditional preflight triggers | Orchestrator на start и environment recheck | Preflight не грузит execution/review steps; 450–700 слов |
| `phases/intent.md` | Extract current user wording/criteria/amendments/exclusions; G1 | Orchestrator на INTENT/amendment | Scope legwork завершается до spec; 400–650 слов |
| `phases/design.md` | Spec/interfaces, oracle plan, G2 independent coverage request | Orchestrator на DESIGN; coverage reviewer читает свой packet | Отдельный gate не теряется среди tickets; 400–650 слов |
| `phases/plan.md` | Vertical tickets, DAG, zones, waves, routing assessment, G3 | Orchestrator на PLAN | Full path после G2; compact branch читает plan rules уже в DESIGN для joint artifact (01); 400–650 слов |
| `phases/execute.md` | Ready→packet→dispatch→audit→candidate commit→review→integrate; cause triage branch and G4 | Orchestrator на EXECUTE | Один normal loop вместо executor/repair/review scripts; 600–900 слов, failure details pointer |
| `phases/recover.md` | Quiesce, checkpoint, pause/cancel, abrupt recovery, owner transfer, operation reconciliation | Orchestrator при pause/resume/uncertain state/quota | Редкая ветка; скрыта из normal implementation context; 550–850 слов |
| `phases/accept.md` | G5 clean current-intent package, user-assisted handoff/import по 05/06, independent verdict, G6 report/terminal state | Orchestrator на VERIFY/ACCEPT | Не тянет завершение раньше текущего gate; 450–700 слов |
| `references/ledger.md` | State transitions, transaction/prepared effects, canonical/derived semantics, recovery invariants; links schema defs | Orchestrator перед первой state mutation или state/recovery question | Single source state semantics; 800–1,100 слов, без перепечатки schema field tables |
| `references/routing.md` | Task/risk/effort bands, discovery resolution, cause-first retry/repair, no-progress and frontier policy | Orchestrator при route/triage изменении | Нет model slugs/runtime catalog; 650–950 слов |
| `references/safety.md` | Zone/path/Git/reviewer isolation/manual environment receipts/rollback/action authority semantics | Orchestrator до первого project/Git effect; contracts point relevant sections | Один guard owner; 800–1,100 слов |
| `contracts/worker.md` | Worker role, packet consumption, stop conditions, repair mode, return semantics и pointer schema | Каждый новый worker | Не lifecycle; packet=runtime data, contract=behavior; 350–550 слов |
| `contracts/reviewer.md` | Authoritative read-only role, disposable mutation scope, mandate-specific coverage/research/change/final branches, findings, no-repair | Каждый reviewer, только applicable branch | Мандаты разделены headings, не отдельные agents; 500–800 слов целиком, final section disclosed directly |
| `schemas/contracts.schema.json` | `$defs`: ledger/task/worker-return/review/research/acceptance, IDs/enums/required/type validation | Helper; agent получает только нужный schema slice | Structural SSOT, no prose copy; размер достаточный для closed schemas, не all-in-context payload |
| `tools/ledger.py` | intent-level dispatch/candidate/integrate/gate/amend/recover + brief/status; advisory lock/atomic replace/hash/write-audit checks | Orchestrator вызывает | Нужен deterministic state safety; no model/network/agent loops. Размер оценивается correctness/coverage, не искусственным LOC ceiling |

V1 runtime dependencies helper: Python 3 stdlib и Git. Structural SSOT — schema; helper поддерживает только используемый закрытый subset, unsupported keyword fail-closed, dev-time validator oracle проверяет parity (02). Generic external validator/install не runtime prerequisite. Helper intent может объединять несколько publications/effect receipt, но Git исполняется только через qualified native approval boundary (02/06); никаких model/network/agent loops. V1 core реализует только bundle preparation, pending handoff и validated return import существующими helper intents; supervisor process/VM manager не добавляется. Optional один custom read-only reviewer file допускается как отдельно scoped setup artifact после успешной restricted E03 qualification; discovery/install location и live overrides проверяются до использования, package не превращается в TOML library.

## Loading routes

```text
Outside invocation: name/description/path + native metadata only
start: SKILL → start → ledger (state init) → intent
resume/pause/cancel: SKILL → recover → ledger/safety as needed
planning: intent → design (G2) → plan (G3); compact: joint design/plan artifact, distinct gates
execution: execute → worker contract + bounded packet in new child (context grade 03)
failure: execute → routing or recover + applicable safety section
review: reviewer contract mandate + frozen subject packet in fresh child
final: accept → reviewer acceptance section + clean intent projection → user-assisted handoff/validated import (05/06)
status: SKILL → helper read/project → compact result (no full preflight)
```

Последовательный переход между файлами уменьшает active reading; он не очищает уже виденную историю. Новый bounded child обязателен для нового worker ticket; context grades различаются по 03. Main context восстанавливается по canonical ledger+Markdown и re-grounding ниже. Не обещать isolation от простого pointer.

## SKILL.md content boundary

Entry содержит короткую цель, «orchestrator owns run state; scoped workers implement; independent reviewers verify», disclosure manual critical/G5 fallback и pointer на 05/06, обязанность сохранить state до dispatch, ссылку на canonical root lookup и triggers всех phase branches. Делегирование явно предписано на implementation/review, чтобы native runtime имел applicable skill instruction. Никаких статических model names, tool-call ceilings, full lifecycle enum/table, full schema, подробного preflight, catalog of rationalizations или копий user/project instructions.

Completion criteria entry: выбран один route по actual run state; status-only не мутирует product; start/resume не дублирует active run. Остальные done conditions co-located в соответствующей phase, с semantic validator reference.

## Re-grounding after compaction/resume

Entry содержит обязательный trigger: после compaction, resume, owner transfer или сомнения в retained protocol прочитать SKILL entry, получить fresh brief и перечитать текущий phase file плюс branch-specific safety/recovery pointers. До завершения этого чтения dispatch/Git/state-changing actions не выполняются. Summary и old chat — hints, не protocol authority.

`brief` включает run/phase/control/revision, next_action/preconditions, current phase path, active issues и 5–8 коротких guards: orchestrator не пишет product; current intent; attempt/lease/base; candidate-before-review; independent integrity; selective prepared effect; blind G5; stale-owner rejection. Он bounded, без all-ticket/history dump.

Перед side effect brief должен соответствовать current revision/epoch/instructions. Intent-level helper commands возвращают его вместе с result и проверяют guards; отдельный brief call нужен, если context/phase был утрачен или полученный brief stale. Дешёвые проверки не порождают отдельный model turn на каждую строку protocol. Это уменьшает overhead, но не превращает helper в sandbox: прямую rogue product edit он не предотвращает. E09 принудительно compact-ит перед commit, после return и перед G5 и проверяет reread/guards на actual trace.

## Single source and duplication rules

| Meaning | Owner | Elsewhere |
|---|---|---|
| Workflow legal transitions/atomic semantics | references/ledger.md | Phase ссылается на gate/transition, schema содержит лишь machine encoding |
| Structural fields/enums | schemas/contracts.schema.json | Contracts объясняют behavior; helper derives validation, не поддерживает вторую enum table вручную |
| Retry/escalation/review topology | references/routing.md | execute вызывает cause branch, без второй таблицы thresholds |
| Write/Git/isolation | references/safety.md | Worker/reviewer guard короткий + точный section pointer |
| Role return semantics | contracts/worker.md, reviewer.md | Packet хранит только runtime goal/values/refs |
| Current intent/contracts/decisions | Canonical versioned Markdown для prose; ledger для refs/status/decisions | Packets — hash-verified frozen slices; status/report derived |
| Models/tools/version/permissions | capability records | Static docs содержат discovery protocol, не catalog |

Schema не может проверить всю semantic authority; helper проверяет machine invariants, reviewer/orchestrator проверяют значение. Implementation tests связывают phase conditions с schema/semantic validator, чтобы natural-language и machine paths не расходились.

## Full mapping of upstream 21 files

Основание — полная [component map](../research/01-component-map.md); corpus повторно не читается без конкретного спора.

| # | Old file | Decision → future home |
|---|---|---|
| 1 | SKILL.md | MODIFY → SKILL.md, detailed rules moved behind pointers |
| 2 | phases/0-preflight.md | REWRITE → phases/start.md; recovery branch → recover.md |
| 3 | phases/0-modes.md | DROP T0–T3 quotas; risk → routing.md; compact phase depth и requested checkpoints → design/plan |
| 4 | phases/0-memory.md | DROP instruction bootstrap; discovery → start.md; prior ACCEPTED memory intake → intent.md |
| 5 | phases/0-instruments.md | REWRITE state bootstrap → start.md + helper; legacy state.js browser/server flow removed; optional read-only ledger dashboard lives in tools/dashboard.py |
| 6 | phases/1-manifest.md | KEEP semantics → intent.md + requirements/criteria schema; canonical intent Markdown refs |
| 7 | phases/2-briefing.md | MERGE with manifest → intent.md; current amendments kept |
| 8 | phases/3-spec.md | KEEP/MODIFY → design.md; canonical spec/interfaces Markdown + versioned ledger refs |
| 9 | phases/4-plan.md | MODIFY → plan.md; ticket quotas removed; neighbour/payback heuristic retained |
| 10 | phases/5-subagents.md | REWRITE → execute.md + worker contract; native transport only |
| 11 | phases/5-repair.md | SPLIT by cause → routing.md, recover.md, worker repair section |
| 12 | phases/6-review.md | MERGE normal loop → execute.md + reviewer mandate; persistence removed |
| 13 | phases/7-instruments.md | REWRITE → ledger.md + schema + helper; no mutable dashboard fields |
| 14 | phases/8-final.md | KEEP/MODIFY → accept.md + current-intent final mandate |
| 15 | phases/9-memory.md | DROP automatic AGENTS/ADR; durable handoff → recover.md/final report; successor read-only intake retained |
| 16 | phases/polish.md | DROP V1; required UX criteria remain normal tickets |
| 17 | phases/rationalizations.md | DROP catalog; concrete gate assertions → semantic validation/contract done criteria |
| 18 | prompts/executor.md | REWRITE → contracts/worker.md, smaller packet, no 50-calls ceiling |
| 19 | prompts/craft-review.md | MERGE → contracts/reviewer.md/change axis; checks retained when relevant |
| 20 | phases/dashboard-template.html | DROP V1 template; generated status.md remains sufficient, optional dashboard uses a new ledger projection |
| 21 | tools/sync.py | REWRITE → tools/ledger.py; validation/atomicity only; read-only HTTP serving is isolated in tools/dashboard.py |

## Why 16 core files

Разделены реальные sequences и role invocations, объединены данные одного назначения. Нет отдельного файла на каждый model/tier/axis/error. Worker не читает full execute/routing/ledger docs; orchestrator не копирует worker behavior в task text. Extra schema/helper оправданы corruption/write-race проблемами, а не симметрией структуры.

**Completion:** каждый файл имеет входной trigger, reader, completion responsibility и budget; 21 legacy component учтён; отсутствуют orphan references, дублированный runtime catalog и production implementation в этом pass.
