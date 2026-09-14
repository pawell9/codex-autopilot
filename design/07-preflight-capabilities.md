# Preflight and capability facts

**DECISION — OD-02/08/12.** Preflight отвечает на вопрос «безопасен ли следующий переход», а не повторяет полный doctor перед каждым ticket. Cheap checks обязательны на entry/resume; conditional probes запускаются при первой реальной потребности; deep qualification кэшируется по fingerprint. Основание и отклонения от audit — [research 06](../research/06-preflight.md).

## V1 support policy

Primary qualification target — macOS local interactive CLI и local filesystem. Local macOS app/IDE допускаются по required capability probes, а не surface name. E02/E04a и routine E03 дали scoped PASS на наблюдаемой local session; active build/child identity UNKNOWN, полного build-qualified release пока нет ([summary](../experiments/SUMMARY.md)). `qualified` означает recorded matching matrix; `probed-unqualified` — текущие обязательные probes пройдены, но комбинация не covered release matrix. Последняя может выполнять только действия с подтверждёнными prerequisites; label не превращает UNKNOWN в PASS.

| Environment | V1 boundary / conditions |
|---|---|
| Local macOS CLI/app/IDE, permanent checkout | Native bounded workers, valid context grades по 03, Git/Python stdlib, writable canonical state, qualified review route. CLI проверяется первым; identical evidence requirements для остальных |
| Linux/WSL/Windows | Qualification OS/filesystem scope отложен; diagnostic/planning, без V1 execution promise |
| Cloud/web/remote/mobile, network-mounted control store | Нет V1 local ownership/locking/lifecycle qualification |
| `codex exec` | Не основной orchestrator surface; только optional bounded reviewer transport arm E03, без daemon/worker bridge |
| No Git/unborn folder | G0 greenfield bootstrap по 06, затем normal Git path; no-commit policy blocks execution |
| Bare/nested/submodule mutation, managed ephemeral authority checkout | Не поддержаны V1; exact diagnostic/fallback к permanent supported target |

Surface/build facts имеют provenance: active runtime metadata/tool schema предпочтительнее PATH binary. `codex --version` сообщает версию найденного binary, не автоматически запущенной app/IDE session. Если active build неизвестен, record UNKNOWN; session-specific probes всё равно возможны, across-session safety qualification не reuse по guessed version. Permission/config changes требуют соответствующих fresh probes. Global setup edits не выполняются автоматически.

Документация подтверждает local subagents/custom settings, не полную Autopilot matrix. [Official Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents).

## Selected V1 automation boundary

По [qualification summary](../experiments/SUMMARY.md) автоматизируются bounded native workers/returns, routine native review на frozen export и clean-checkout Git flow с обычными approvals. Limits E02 (descendant writer может пережить interrupt, identity opaque) и E04a (worktree persistence/root topology conditional) остаются прежними guards, не переоцениваются этим pass.

Для G5 и required critical axes выбрать `user_assisted` route по 05/06. На start сообщить объём участия: prepare bundle автоматически, setup/transfer/independent review receipt через пользователя, validation/resume автоматически. Подтверждение этой capability означает готовность организовать handoff, не заранее полученный PASS на будущий candidate. При невозможном setup dependent gate BLOCKED с конкретным условием. Environment/permission/context receipts обновлять при изменении среды/пакета; каждую новую G5 session подтверждать отдельно.

Authenticating CLI само по себе не закрывает E03: automatic promotion требует context, tool isolation, oracle/return и interruption evidence. Automatic strict critical/G5, custom agent setup и managed isolated runner — post-V1 upgrades, не prerequisite ручного fallback. Main local runtime support matrix сохраняется.

## Cheap: entry/resume and pre-action checks

| Check | Минимальное действие | Gate consequence |
|---|---|---|
| Intent/authority | Текущий request, scope, restrictions и expected outcome | Только build-authorized run пишет product; design/review просьба не превращается в build |
| Exact repository | Resolve CWD, Git identity/inventory или greenfield G0 из 06 | Unknown target, merge/rebase/conflict → BLOCKED; no Git не автоматический UNSUPPORTED |
| Existing/prior run | Validate canonical ledger/owner/effect refs; find relevant prior ACCEPTED run | Active→recover; successor reads prior contracts/decisions по 02; foreign namespace не overwrite |
| Changed state | Git status incl staged/unstaged/untracked; expected base и foreign inventory | Overlap/drift → quarantine/ownership resolution |
| Instructions | Applicable paths/fingerprints и уже известные constraints; пересчитать только changed chain | Missing/truncation/contradiction relevant to action → read targeted rules/block |
| Effective authority surface | Known sandbox/roots/approval mode/reviewer, protected common-dir, reusable command policy, changed permission signal, tool presence | Unknown required write permission → conditional proof; denial → blocker |
| Skill/helper identity | Version/hash/schema compatibility, helper executable/interpreter presence | Unknown schema or shadowed skill → diagnostic |
| Dispatch guard | Relevant contract/current intent fingerprints, dependency receipts, lease и current capability refs | Stale packet → regenerate, не spawn |

Cheap не значит «всегда рекурсивно хешировать весь repo». Entry использует Git/instruction metadata и retained manifests; before/after write audit из 06 читает достаточно для доказательства actual set. Изменённые инструкции перечитываются до действия даже если Codex автоматически загрузил старую chain; fresh child получает актуальные pointers. Не утверждать completeness inherited instructions по одному filename.

## Conditional: only when needed

| Capability needed | Probe / data source | Cache / failure behavior |
|---|---|---|
| Native worker dispatch | Exposed spawn/control tool schema и read-only smoke на bounded fixture при первом dispatch | Reuse valid qualification; absent → planning-only/BLOCKED execution |
| Context grade by mandate | Actual schema/input evidence + E02 marker/positive control; manual input/context receipt по 05/06 | Worker/research may DEGRADED_CONTEXT; routine review behavioural clean; G5 automatic strict proof либо explicit MANUAL_ATTESTED_CLEAN fallback по declared inputs, не native non-recall и не STRICT_FRESH claim |
| Model/effort override | Effective runtime catalog/options if exposed; actual accepted spawn resolution | Inherit adequate route если override unknown/denied; не brute-force slugs |
| Independent review | Routine E03 export/barrier; critical/G5 manual input-boundary/context receipt по 05/06 | На G0 disclose user-assisted mode, до affected critical work подтвердить path/oracle; fully automatic demand → strict transport blocker. Known authoritative input/connector exposure or required receipt/return missing → gate BLOCKED; unobservable host-layer unknown записывается как residual trust |
| Git actions / worktree placement | E04a approval counts, roots/common-dir, sibling placement; conditional required action proof | Clean exclusive checkout default; sibling worktree gated; denied Git action remains blocker |
| Test/build/live oracle | Repo command definition, executable/version, fixture/service availability, baseline check when it changes interpretation | Missing oracle → explicit blocker/unverifiable; не silent skip |
| Network/install/browser/API | Tool-specific permission/effect requirements, primary docs when unknown | Use local fixture if valid oracle; new authority asked only if actually needed |
| High-risk path handling | Symlink/case-fold/ignored/hook analysis в relevant zones | Unresolved path semantics → zone not dispatchable |
| Quota/time limits | Runtime-reported meter if present | Unknown = null; no billing/credential scrape; no false numerical remaining budget |

Smoke требует реально needed capability. «Перебрать все модели, agents и tools» не часть preflight. Read-only smoke не должен изменять product или запускать expensive full suite. Cost реального smoke прозрачен и ограничен одним конкретным вопросом; повторяется только при invalidation/new evidence.

## Deep: qualification, environment change or uncertainty

- E01: local helper lock/atomic publication/crash recovery на disposable fixture.
- E02 (до schema/helper): context grades/return/cancellation, parent interruption and descendant liveness, opaque child adequacy по build; applicable instructions и parent history различаются.
- E03 (до schema/helper): reviewer transport matrix, custom defaults ± live overrides, disposable mutation/pristine checks, integrity detection и critical prevention.
- E04a (до schema/helper): Git approvals, greenfield setup и permanent sibling placement. E04b после helper: effect recovery, actual write audit, user dirtiness, ignored inputs и cancel/resume.

E02/E03/E04a выполнены до schema/helper; scoped results и D-21 adaptation в 10. Strict automatic critical/G5 остаётся unqualified; approved manual fallback contract снимает именно package implementation blocker, его actual setup/roundtrip подлежит E03-M до release. E01/E04b и повтор relevant probes на implementation обязательны до release; это не работа каждого run. Во время normal run повторить лишь affected probe при новом build, effective permissions/config/surface change или contradicting observation. Если нет безопасной disposable среды, expensive probe не проводится на product: выбрать supported fallback либо BLOCKED capability.

## Capability record and invalidation

Каждый fact хранит `key`, `value`, `knowledge=CONFIRMED/REJECTED/UNKNOWN`, `evidence_ref`, `observed_at`, `scope`, `fingerprint`, `invalidated_by[]`. Gate outcome отдельно `PASS/DEGRADED/BLOCKED`; UNKNOWN не synonym DEGRADED.

Fingerprint включает применимые части: client/surface/build, OS/filesystem, effective permission/approval policy, tool-schema signature, selected config/skill/instruction hashes, account/workspace identity signal (без tokens), repo/common-dir/worktree, model binding. Не всё должно включаться в каждый fact: command availability не зависит от соседнего ticket status.

| Change | Invalidate |
|---|---|
| Client/build/tool schema | Native context, spawn/return, cancellation, model override and isolation qualification |
| Permission/profile/live override | Effective writes/read-only/network, child inheritance; перед следующим опасным действием обязательно re-evaluate |
| Account/plan/model rejection | Relevant model/effort catalog/binding; available route re-resolve |
| Repo/worktree/HEAD/instructions drift | Baseline/leases/context/readiness; affected test/tool facts |
| Lockfile/toolchain/config change | Corresponding tests/build/oracle availability/baseline |
| Resume/new session | Cheap checks всегда; session-only facts expire; safe version-scoped qualification reuse only if fingerprint observable |
| Contradictory observation | Immediate invalidation, независимо от timestamp |

Нет arbitrary TTL «24 часа». Runtime fact reused только при matching dependencies и отсутствии contradicting observation. Unobservable live permission change означает, что нельзя обещать reuse safety proof: перед dispatch effective policy проверяется или required action blocks. Cache хранится в ledger capabilities; при новом run прошлые facts копируются как references/provenance и повторно валидируются, не становятся global config.

## Model discovery protocol

1. Читать already-exposed current model/options/tools; surface-native documented catalog/status если реально доступен. Это предпочтительнее просмотра всей config или интернет-списка API моделей.
2. Resolver отделяет requirement class от binding. Если каталог неполон, записать partial coverage, не объявлять отсутствующую модель недоступной во всём Codex.
3. Для needed override использовать только discovered valid option; actual spawn rejection записать и перейти к [04 fallback](04-routing-and-escalation.md). Нет universal `/models` CLI/API, выдуманного этим design.
4. Effort из per-model effective options. Unknown effort → inherited/model default с honest resolution status, при adequacy gate. Конфликт названий в docs не закрывается guessed alias.
5. Unknown actual child model не равно unknown adequacy. Parent adequacy переносится лишь с evidence effective inheritance (включая agent defaults/custom layer); иначе representative bounded qualification может доказать adequate opaque route. Requested override без receipt остаётся unconfirmed. Resolver 04 запрещает endless decomposition; context grade/independent review сохраняются. Higher-priority запрет override соблюдается.

## Deliberate changes from audit

- Audit предлагал no-subagents → parent single-agent execution. **DECISION:** это нарушает brief «orchestrator не universal implementer» и независимость. V1 degradation — planning/status/recovery, затем handoff всего run в supported session с native workers и context grade по 03. User-assisted clean-session handoff — выбранный fallback только для critical/G5 по 05/06, не alternate worker transport; parent не имитирует все роли.
- Audit предлагал portable app/CLI/IDE/cloud abstraction. **DECISION:** одинаковый semantic contract, но macOS local capability admission для CLI/app/IDE; OS/cloud portability adapters не строятся.
- Audit предлагал широкие проверки при каждом substantial run. **DECISION:** split cheap/conditional/deep с fingerprint invalidation; runtime facts не дублируются в phase files.
- **FACT:** текущие official worktree docs описывают optional `.worktreeinclude` для managed local worktrees. [Worktrees](https://learn.chatgpt.com/docs/environments/git-worktrees). **DECISION:** это не используется для explicit CLI worktree и не разрешает копирование secrets.

## Exit record

Orchestrator публикует компактный verdict: exact target/baseline; authority/instruction changes; supported target qualification; enabled execution/review routes; relevant unresolved capabilities и safe fallback; next required probe; blockers. Нет raw config, credentials, enormous tool inventory в packet.

**Completion:** следующий phase gate знает, что подтверждено; optimization UNKNOWN имеет безопасный fallback, safety UNKNOWN блокирует именно dependent action; глубокий preflight не повторяется без причины.
