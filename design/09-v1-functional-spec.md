# Codex Autopilot V1 functional specification

**DECISION.** Это implementation acceptance contract. Нормативные детали принадлежат 01–08; MUST ниже — проверяемые deliverables, а не альтернативные definitions. V1 реализует один scoped software run в Git repository (existing либо scoped greenfield bootstrap) с native Codex workers и independent acceptance.

## Product boundary

Supported targets и qualification — [07](07-preflight-capabilities.md). Default outcome — accepted local run branch/commit и reproducible report. Landing в default branch только если requested и включён в acceptance scope. Runtime dependencies: local supported Codex, Git, Python 3 stdlib. Наличие конкретной модели, dashboard, Claude или cloud service не prerequisite. По E03 выбран automatic routine export/barrier; V1 critical/G5 использует user-assisted clean-session fallback (05/06). Optional automatic restricted process/custom reviewer требует новой qualification.

User-facing entry: explicit start/resume/status/pause/cancel через один skill. Skill не требует от пользователя ручного чтения всех spec/tickets или routine gate approvals. User-assisted critical/G5 требует setup/transfer независимого review, но не чтения всех tickets пользователем. Это обязательная видимая граница данного V1 режима. Она отличается от optional manual final approval: если последнее requested, G6 ждёт ещё и его.

| Capability | V1 delivery mode |
|---|---|
| Workers, routine coverage/change/plan review, audit/candidate Git, packet/return bookkeeping | Automatic при valid probes и existing authority; conditional risk/oracle checks сохраняются |
| Required critical axes и каждый fresh G5 round | User-assisted isolated clean session; подготовка/валидация автоматические, setup/transfer/receipt требуют пользователя |
| Fully automatic strict critical/G5, custom sandbox transport или managed isolated runner | Post-V1 после E03 requalification; manual mode не ждёт их реализации |

## V1 MUST

| ID | Requirement | Observable implementation acceptance | Design owner / experiment |
|---|---|---|---|
| V1-01 | Explicit invocation и narrow supported target handling | Start/status/resume различаются; implicit ordinary edit не запускает run; unsupported target выдаёт точную причину, не simulated execution | 07/08, E02/E07 |
| V1-02 | Current intent traceability | Каждая пользовательская active requirement имеет provenance и observable criteria; amendments versioned; deferred/dropped только с authority | 01/02/05, E08 |
| V1-03 | Complete lifecycle | Legal transitions/gates validated; normal run достигает ACCEPTED только через G5/G6 | 01, E07 |
| V1-04 | Independent design coverage | G2 reviewer на current intent/spec выявляет seeded omission до implementation | 03/05, E08 |
| V1-05 | Executable plan | Acyclic dependencies; criterion→ticket/oracle coverage; disjoint/exclusive zones; no artificial ticket counts | 01/02/06, E08 |
| V1-06 | Single canonical JSON ledger | One owner/epoch/revision; structural+semantic validation; JSON = state; canonical Markdown = prose с refs/hashes; generated status/report не authority | 02, E01 |
| V1-07 | Atomic updates and effect recovery | Partial write/crash/duplicate owner не теряют last committed state и не повторяют effect без reconciliation | 02, E01/E04 |
| V1-08 | Native bounded worker execution | Новый bounded native child на ticket; worker DEGRADED_CONTEXT допустим по 03; no parent implementation; strict final freshness отдельно | 03/05/07, E02 |
| V1-09 | Minimal structured packets/returns | Required fields достаточны; optional branches absent when unnecessary; malformed/stale return не интегрируется | 05, E02/E08 |
| V1-10 | Single product writer and ownership | Post-worker audit учитывает tracked/untracked/relevant ignored/type/rename changes; undeclared writes quarantine | 06, E04/E08 |
| V1-11 | Git-required controlled execution | G0 scoped init/initial commit либо existing baseline; clean run branch или qualified sibling worktree; exact approvals; orchestrator candidate commit до review; INTEGRATED после PASS | 06, E04 |
| V1-12 | Independent reviewer and separate repair | Reviewer не может незаметно изменить authoritative candidate/state; disposable mutations отделены от pristine checks; qualified routine integrity; manual critical environment receipt по 06, отдельный repair | 03/05/06, E03 |
| V1-13 | Cause-first routing | Implementation/contract/oracle/environment/permission/ownership failures идут разными маршрутами; model names optional discovered bindings | 04/07, E05/E08 |
| V1-14 | Bounded progress and honest limits | No unchanged repeat without new evidence; quota checkpoint/resume; unavailable usage metrics null; no arbitrary auto-success | 01/04, E05/E07 |
| V1-15 | Cheap/conditional/deep preflight | Второй unchanged task не повторяет model/worktree/isolation deep probes; changed permission/build invalidates applicable facts | 07, E02/E03/E04 |
| V1-16 | Evidence beyond worker tests | Critical seams have independent expected-value/live/negative oracle; green-but-broken fixture fails gate | 04/05, E07/E08 |
| V1-17 | Clean current-intent final verifier | Final packet includes current amendments/criteria, excludes history/self-report; fresh manual setup + isolated export receipts и independent outcomes required; old candidate/native routine review cannot satisfy G5 | 05, E07/E08 |
| V1-18 | Honest acceptance and report | Every active criterion fulfilled for PASS; partial/missing/unverifiable block; report lists exclusions, placeholders, risks and exact candidate | 01/05, E07 |
| V1-19 | Checkpoint/resume/cancel | Fresh orchestrator resumes from files+Git after lost handles; cancel retains owned partial state and does not clean foreign files | 01/02/06, E01/E04/E07 |
| V1-20 | Protected namespace and external authority | No automatic AGENTS/config/global skill edits; no incidental messaging/deploy/production mutation; denial does not reroute around controls | 06, E03/E08 |
| V1-21 | Progressive file loading and deterministic core | Entry/current phase separate from role context; helper validates without model; 16 core file purposes in 08 implemented without duplicate schemas; re-grounding after compaction/resume verified | 08, static package review/E08 |
| V1-22 | Reviewer disagreement and requirement steering | Conflicting verdicts adjudicated by evidence/intent; active worker stale after relevant amendment; final verifies updated intent | 01/04/05, E08 |
| V1-23 | Economical orchestration across compaction | E09 records helper/agent/model turns, bytes/tokens if available, approvals/interventions; happy path ≤4 bookkeeping calls/ticket or explicit accepted target revision; protocol survives forced compaction | 02/08/10, E09 |

## V1 SHOULD

- Use available adequate lower-cost routes for bounded work and de-escalate new repeated patterns after evidence; unknown relative costs remain explicit.
- Run independent read-only questions/axes concurrently on frozen views when available slots and sandbox permit. Serial execution of these reads is still conforming.
- Use qualified native `/review` for supported change scopes; explicit reviewer subagent is adequate default. `/review` не заменяет final product verification автоматически.
- Produce compact human status on gates/status request; regenerate stale views without user work.
- Retain minimal attempts/duration/packet-size/route outcomes for later economic tuning; no raw conversation telemetry requirement.
- Preserve one audited logical candidate per commit when changes are nonempty; no forced empty commits and no requirement to squash repair history.

SHOULD не вводит новые gates. Optional convenience отсутствует — run остаётся полноценным, если MUST satisfied.

## Explicit non-goals

Universal agent framework/surface abstraction; no-Git recovery; shared-checkout parallel writers; universal worktree orchestrator; custom TOML library; mandatory external process bridge/daemon/App Server; scheduled/unattended operation; mandatory frontier/Astra/Claude; automatic external provider dispatch; exact credits optimizer; mandatory dashboard/backend; automatic global/project instruction memory edits; ADR factory; generic polish loop; deployment/messaging/production data mutation; auto legacy state migration; malicious-agent-proof semantic sandbox; remote disaster backup. An optional local read-only dashboard may project the current ledger without adding state or controlling a run.

Bounded parallel (≤2–3) через per-ticket permanent worktrees — post-V1 gated capability E10, не structural non-goal. Serial остаётся V1 default; extension сохраняет роли, phase × control, attempt.checkout и checkout leases.

UX polish, docs или config изменения, **которые прямо входят в current intent**, остаются обычными scoped tickets. Non-goal generic polish не позволяет пропустить явное продуктовое требование.

## Run artifacts and roles

Canonical artifacts — layout [02](02-run-ledger-and-artifacts.md): JSON ledger, canonical versioned Markdown intent/spec/interfaces/plan, immutable objects/packets and selected recovery snapshots, generated status/final report. Product changes/commits живут в Git run branch. File existence само по себе не доказывает gate completion.

Roles — [03](03-agent-architecture.md): orchestrator maintains state/routes/integration; worker implements/repairs; reviewer performs independent coverage/plan/change/research/final mandates. Persistent process identity не required. Native capability unavailable → explicit execution blocker/planning-recovery path, не parent writes disguised as worker. Manual clean-session handoff — explicit supported critical/G5 fallback с условиями 05/06; native workers остаются execution prerequisite.

## Lifecycle and failure behavior acceptance

Happy path: G0 preflight → G1 current intent → G2 coverage → G3 plan → per-ticket audit/candidate commit/review/integration check → run-level G4 → G5 independent final → G6 terminal report.

Required alternate paths: pause/quota, abrupt interruption, lost worker, malformed return, failed oracle/verification, contract/zone defect, environment/permission failure, reviewer conflict, amendment mid-run, cancellation, state corruption, no-progress diagnostic. Каждый путь должен сохранить authoritative state и привести к next safe action либо explicit BLOCKED/FAILED/CANCELLED. Ни один error handler не может переходить в ACCEPTED как fallback.

Resume считается корректным, когда fresh context с доступом только к package, canonical Markdown + ledger/evidence и Git определяет next_action и actual outstanding effects, не спрашивая старую переписку. Terminal accepted run immutable; новая задача или correction создаёт successor run.

## Qualification and implementation sequence

1. Pre-implementation spikes E02/E03/E04a выполнены; [reports](../experiments/SUMMARY.md) сохраняют исходные PASS/FAIL/UNKNOWN. Bounded workers/returns, routine export/barrier и clean Git path usable; strict automatic critical/G5 отсутствует.
2. D-21 выбирает bounded user-assisted critical/G5 fallback contract (05/06). **IMPLEMENTATION READY WITH MANUAL G5 FALLBACK** разрешает отдельный implementation pass, а не объявляет E03 PASS или release-ready. Manual setup/roundtrip ещё не наблюдался: E03-M проверяет реальную isolated environment, clean receipt и transport до release; конкретный run без admissible receipts/result остаётся BLOCKED.
3. После отдельной implementation authority: schema/helper + E01/E04b; manual bundle/import path + E03-M, затем static package review и повтор affected probes на actual package. Full automatic strict transport не prerequisite этого release, integrity/current-intent acceptance не ослабляются. Early spike PASS не заменяет integrated tests.
4. E08 adversarial cases, functional E05/E06 guards, E07 full micro-project lifecycle с manual G5 и required critical handoff, затем **E09 economy/compaction 6–10 tickets**. Safety/correctness/economy release blockers имеют recorded evidence; comparative model/frontier tuning optional.
5. CLI — primary qualification build. App/IDE release matrix расширяется той же relevant suite; failing optional target не блокирует qualified primary и не скрывается. Probed-unqualified session допускается только по action prerequisites из 07.
6. Independent release review проверяет V1-01–23 и economics disposition: target pass либо evidence-backed явно approved revision budget до объявления release-ready. Новая cost/authority boundary требует согласия; ритуальное budget approval при PASS не нужно. E10 остаётся post-V1; Idea Scout production/V2 не первый тест.

E09 требует recorded counts и observable bytes/turns даже при unavailable token meter (tokens=null + reason). Числовые estimates review не release evidence. Без проведённого E09 экономика протокола остаётся непроверенной, release не complete. Все дальнейшие real-project trials требуют отдельно authorized disposable clone.

## Completion criteria самой V1

V1 implementation complete iff все V1-01–23 имеют passing evidence на primary supported build, обязательные failure сценарии проходят, manual setup/roundtrip validation E03-M пройдена, нет unresolved safety/context issues для выбранного assisted mode, package instructions follow file contracts 08, final release report различает tested/unsupported environments и observed/unknown economics. Secondary target может быть deferred только явно по правилу выше.

Это **не** критерий завершения текущего design-pass: сейчас требуются законченные contracts и bounded experiments, а не выполнение runtime evals или production skill. Design package готовность фиксируется в [STATUS](STATUS.md); experiment registry — [10](10-decisions-and-experiments.md).
