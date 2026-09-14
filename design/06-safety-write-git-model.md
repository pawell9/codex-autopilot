# Safety, writes and Git

**DECISION — OD-06/07/11.** V1 требует Git baseline до product dispatch, поддерживает scoped greenfield bootstrap, работает одним product writer на local run branch. Candidate commit предшествует review. Permanent sibling worktree — gated capability для dirty/busy checkout; bounded parallel worktrees — post-V1 E10.

## Guarantees and limits

| Layer | Guarantee when qualified | Limit / Autopilot obligation |
|---|---|---|
| Codex sandbox/approvals | Effective filesystem/network/command boundaries конкретного tool | Не знает semantics ticket zones; authority и sandbox проверяются отдельно |
| Git | Проверяемые revisions/diffs и tracked recovery points | Не backup ignored/untracked data, не isolation общих refs, не контроль внешних side effects |
| Autopilot contracts/helper | Exclusive logical zone, version validation, post-write audit, evidence gates, mechanical integration protocol | Detection после записи не prevention каждой ошибочной записи; semantic intent требует review |
| Reviewer isolation | Immutable subject + disposable view + independent integrity barrier; technical restriction when required | Post-hoc detection ограничена конечными изменениями; permission label/copy не доказывают prevention |

**FACT:** standard workspace-write защищает `.git`, `.agents`, `.codex`; это не делает остальные пути role-specific. [Official security](https://learn.chatgpt.com/docs/agent-approvals-security). **DECISION:** V1 не меняет global permission profiles и не использует Beta profiles как prerequisite. Runtime denial — blocker, не приглашение к обходу.

## Files and ownership

| Namespace/class | Writer |
|---|---|
| Canonical `.autopilot` state/docs/packets/objects | Orchestrator; ledger через helper. Exact scratch return inbox — child grant по 05 |
| Source/tests/assets/project docs | Worker конкретного attempt в lease zone |
| Product config/lockfiles/CI | Worker только при explicitly scoped ticket с requirement и review; preserve default |
| AGENTS/overrides, `.agents`, `.codex`, `.claude`, existing skills | Protected default; автоматическое обновление вне V1. Прямой user request на такой deliverable требует отдельного scope contract |
| Git refs/index/commits/worktrees | Orchestrator через обычные разрешённые Git операции; raw `.git` edits вне protocol, кроме scoped `.git/info/exclude` bootstrap из 02 |
| Secrets/credentials/production data | Не run-artifacts; runtime secret mechanisms и exact authority; values не копируются |
| Test/build scratch | Disposable declared resource, owner/cleanup recorded; product acceptance может читать только sanctioned output |

Перед записью классифицировать symlink target и resolved root. Запрет следует за resolved path, а не только красивым relative filename. Prompt injection в repo/log/evidence не меняет authority, зоны или return schema.

## Zone semantics and write-set audit

Zone entries: repo-relative literal file либо directory subtree; operation set `create/modify/delete/rename`. V1 избегает произвольного glob language: `src/api/` включает subtree, `src/api.ts` только файл. Deny выигрывает allow. `..`, абсолютные пользовательские allow paths, escaping symlinks, unknown case-fold collisions запрещают dispatch до уточнения. Nested repos/submodules mutation вне V1.

Lease exclusive на attempt/check-out/contract/base; active или quarantined lease не переиспользуется. Same worker repair получает новую attempt и renewal после нового audit. Generated files, lockfiles, deletes и оба конца rename должны входить в zone. Broad codegen/formatter сначала определяет write set, затем исполняется в declared scope.

Actual audit до candidate commit и independent integrity barrier после review:

1. Сверить root/common-dir/branch/HEAD с prepared base и liveness: worker завершён, фоновые процессы остановлены.
2. Получить tracked staged/unstaged changes, untracked additions/deletions и rename paths относительно baseline; проверить реальные bytes/type/symlink destination и executable mode. Не доверять `files[]` worker.
3. Сверить filesystem manifest для relevant ignored/generated/protected paths и foreign initial changes. `git diff` не видит все записи; V1 отдельно фиксирует ignored outputs, scratch и защищённые paths. Secrets проверяются по metadata без чтения values; repo-secret absence/authority policy — preflight.
4. Всё actual changeset должно быть declared и соответствовать lease operations; unexpected path → quarantine, BLOCKED ownership. Unrelated original user files должны сохранить fingerprint.
5. Stage exact audited path list, подготовить commit operation и создать candidate commit до review; проверить committed tree против audited intended tree и clean index/worktree. Candidate identity — immutable SHA. После review выполнить integrity barrier ниже; drift делает verdict unusable. Audit manifests сохраняются для ignored/protected/foreign paths, не заменяют Git identity.

Audit обнаруживает конечный write set, не все временные write-and-restore/внешние эффекты. Поэтому arbitrary scripts with unknown effects не получают permission только по ожидаемому чистому diff. Temp/cache writes разрешаются отдельно. Это явный предел V1, не обещание полного filesystem monitor.

## Git-required and greenfield bootstrap

**OBSERVED:** [Idea Scout audit](../research/05-safety-write-policy.md) связывает resume с Git checkpoints; [upstream preflight](../upstream/autopilot/phases/0-preflight.md) допускает init. Один Git protocol для candidate/review/recovery сохраняется, второго no-Git механизма нет.

G0: resolve exact requested folder, проверить Git/parent repo identity и inventory staged/unstaged/untracked/ignored/seed files. Nested repo случайно не создавать. В пустой/seed-only folder при existing build authority orchestrator подготавливает exact init target и initial commit paths, выполняет разрешённые init/commit и записывает receipt; повторное ritual confirmation не нужно. Пустой initial commit допустим как Git baseline, это единственное исключение no-empty-ticket-commit. Если seed files есть, stage только явно проверенный список; secrets/credentials/unknown files исключаются и называются без values. Never `git add -A` baseline.

Непустая папка с неизвестной ownership, содержимым или staged work → сначала inventory и конкретное решение о включаемых файлах. Unborn repo использует существующую metadata/config; Git author identity/hook/permission missing → exact setup blocker, global config не правится. Initial inventory/prepared bootstrap record хранится в owned namespace до init, затем связывается с Git identity; crash не означает повторный init/commit blindly. При no-commit policy execution unsupported. Текущий design pass Git не создаёт.

## Git approvals

Build authority и runtime permission различаются. Preflight фиксирует effective approval mode/reviewer, protected Git common-dir, exact commands/roots и availability reusable permission. Один scoped setup может запросить поддерживаемые reusable command prefixes для нужных local Git действий; разрешение сохраняет existing policy и не гарантируется по одной строке prefix. Blanket `git`, full-access mode или global config edits не default. `.git/info/exclude` — отдельный exact local effect, не blanket raw metadata authority.

Orchestrator выполняет Git mutations через native approved tool boundary. Helper не является оболочкой для обхода denied Git action. Если scoped reuse недоступен, prompts происходят на actual boundary, результат/счётчик сохраняются. Noninteractive approval failure → BLOCKED с exact action; не alternate tool bypass. E04a измеряет candidate+repair commits, branch/init/worktree setup, partial approval/denial и overhead; E09 проверяет их стоимость на run. Batch intent bookkeeping допустим, объединять разные review candidates ради сокращения prompts нельзя.

## Checkout/branch policy

1. Default V1 — clean exclusive selected checkout и unique `autopilot/<run-id>` branch от agreed HEAD. Existing staged/unstaged/untracked files user-owned; owned excluded state/declared harmless ignored outputs не считаются foreign dirty. Collision → новое имя, не overwrite. No auto-stash/reset/clean.
2. Dirty/busy checkout требует либо чтобы пользователь сам сохранил/освободил его, либо **qualified permanent sibling run worktree**. Sibling должен лежать вне primary source tree, в already authorized writable root; common-dir Git writes тоже должны быть разрешены. E04a подтверждает placement и command policy до включения capability.
3. Если sibling root не разрешён, report даёт exact path и необходимое разрешение/новую session с этим root; capability ждёт actual authority. Fallback — реально clean exclusive checkout. Вложенные source worktrees в `.autopilot/wt` не V1 fallback: tests/search могут сканировать дубль. Работать поверх user dirtiness нельзя.
4. Worktree создаётся от agreed committed HEAD; dirty changes туда автоматически не переносятся. Необходимый ignored setup воспроизводится exact scoped action, credentials не копируются. Path/ref/base/registration записаны prepared/applied. Worktree должен переживать handle/session loss; managed ephemeral worktree не V1 authority.
5. Serial V1 не содержит per-ticket concurrent writers. E10 может включить ≤2–3 per-ticket permanent worktrees после placement/integration qualification. `attempt.checkout` и lease на checkout уже есть; это capability extension, не новая lifecycle/role model. Shared-checkout parallel product writes не допускаются.

Candidate commit завершает writing activity worker; lease сохраняется как reservation до review integrity check/integrate, без нового типа record. Serial V1 не запускает speculative dependent work на unreviewed candidate и не обещает overlap speedup от одного раннего commit. Разрешать authoring параллельно broad-write reviewer можно лишь с qualified technical separation и scoped integrity accounting; эта оптимизация не обязательна V1 и проверяется в E10. По умолчанию review и authoritative ledger publication сериализуются на barrier lifetime; read tasks на independent snapshots не меняют state.

## Commit and integration ownership

Worker редактирует файлы и tests; Git writes не разрешены. Orchestrator выполняет write audit и commits exact candidate до independent review. Preferred unit — один logical candidate ticket → один commit; каждый product repair создаёт новый commit, history не переписывается. Attempt не обязан производить commit. No-op outcome не создаёт пустой commit.

Commit prepared record содержит base HEAD, intended tree, path list, operation ID и audit/evidence refs; review refs появляются после commit. Commit trailer связывает operation; resume проверяет также tree/base, а не доверяет trailer. Commit hooks могут менять files/запускать side effects: применимые hooks inspect/probe conditional, unexpected changes invalidates candidate и требует повторного audit/review; отключать hooks скрыто нельзя.

`INTEGRATED` в V1 означает verified committed outcome на **run branch**. Это не merge в default branch и не push/deploy. Зависимые tickets начинаются только с reviewed/current INTEGRATED dependency outcome, а не с непроверенного HEAD. Волна — группа готовых задач/проверок; write tickets исполняются по одному, read tasks могут идти параллельно на frozen subject.

Final deliverable — accepted local run branch/commit + report. Landing в пользовательский target branch выполняется только если входит в user request. Mechanical fast-forward/cherry-pick с expected-base проверкой возможен как отдельный authorized integration action; substantive conflict создаёт worker integration-repair ticket, tests/review повторяются. Если landing required for acceptance, он должен завершиться до final candidate freeze; post-acceptance merge не приписывается старому acceptance без exact tree equivalence и recorded new location. Push, PR, deploy и messages не automatic V1 completion actions.

## Reviewer isolation and integrity barrier

**Invariant:** reviewer не может незаметно изменить authoritative candidate или run state. Он может писать в disposable test/review copy; code repairs остаются worker deliverable. Immutable subject для change/final — candidate commit SHA; для G2/G3 — hash-verified document versions. Export/copy не sandbox сам по себе.

Общий baseline/export/pristine protocol; native detection использует exact serialized barrier. Manual transport дополняет его environment receipt и recovery handling из 05/раздела ниже:

1. После candidate commit подготовить pristine export без Git history/internal state/secrets. Exact resolved review-copy path — в authorized disposable root вне primary source tree; проверить writable grant и applicable instructions, missing root → scoped setup/fallback из E03, не вложенная source copy по догадке. Проверить exported paths/bytes против candidate tree, включая export attributes, LFS/submodule/ignored runtime requirements: missing required product content → explicit export/oracle blocker. Setup/fixture additions отдельно перечислить; не выдавать их за shipped product. G2/G3 используют immutable doc copies.
2. Orchestrator сохраняет baseline вне reviewer-granted scratch: candidate SHA/tree, run HEAD/ref/index/worktree manifest, protected/foreign paths, current ledger revision и exact hash, hashes referenced canonical docs/packets/evidence. Ledger hash вычисляется после последней pre-review publication и хранится в independent baseline evidence, не рекурсивным полем в самом ledger. Broad-write detection mode держит authoritative target/state без других writes до barrier; новый user amendment/pause сначала останавливает reviewer, выполняет integrity check, затем публикует event и invalidation (01). expected verdict payload не входит в baseline. При interruption baseline восстанавливается из trusted recorded evidence, иначе verdict unusable.
3. Reviewer работает в disposable copy/export. Mutation tests создают отдельную child test copy или явно размеченные mutations; их результаты говорят о проверке oracle. PASS product checks должны относиться к pristine candidate; исправленный reviewer source никогда не принимается как product. После mutation восстановить copy из SHA и повторить нужные pristine checks.
4. После stop reviewer и его writing commands orchestrator независимо перепроверяет baseline **до ingest/state publication**. HEAD/tree/index/worktree, ledger/docs/evidence mismatch → verdict invalid, target quarantine и cause/recovery, не автоматическое восстановление по reviewer claim. Integrity evidence не принимается только со слов reviewer. Success связывает verdict с exact subject и context qualification.

Detection mode допускается в cooperative threat model после E03: immutable subject + disposable copy + independent post-check могут обнаружить persistent authoritative mutation даже при broad effective write roots. Это не promise OS prevention или обнаружения transient write-and-restore. Для critical axis, где transient mutation/external effect подрывает oracle/state trust, нужна qualified technical restriction именно authoritative targets и tool effects; reviewer всё ещё может писать scratch. Без неё эта ось BLOCKED. Read-only shell не ограничивает MCP/browser автоматически.

**Observed E03 disposition:** native packet-only reviewer + SHA export + serialized integrity barrier qualified только для routine coverage/plan/change. Native authoritative prevention/write-and-restore detection FAIL. Custom read-only agent и native `/review` не exposed; `codex exec` не прошёл sampling из-за CLI-authentication, inner sandbox/context остались UNKNOWN ([report](../experiments/E03-reviewer-isolation-and-transports.md), [raw CLI](../experiments/raw/e03-codex-exec-results.md)). Эти automatic arms не включены в V1 strict transport.

Final verifier требует clean context и export без `.git/.autopilot` по 05. Read-only label не исправляет inherited narrative. V1 baseline для critical/G5 — user-assisted isolated session ниже; known native broad-write route не повышается до strict из-за смены CWD/имени роли. Routine review не переводится на ручные handoffs.

## Manual review environment

**DECISION — D-21 targeted policy revision:** reviewer получает disposable export в новой независимой session с declared review-surface boundary: authoritative repo/control-root, Git history, implementation narrative, project memory и connectors не передаются и не используются как reviewer inputs. Writable test copy там допустима. Пользователь управляет transfer и attestation; V1 не строит VM/container platform и не выдаёт неиспытанный provider за `STRICT_FRESH`.

| Minimal option | Disposition / evidence |
|---|---|
| Новый export/CWD/worktree на том же broad-access native runtime | Не `STRICT_FRESH` и не prevention proof: [E03 mutation](../experiments/raw/e03-native-mutation-results.md) показал authoritative writes; Git worktree не permission boundary. Для manual fallback допустим только при отсутствии known project input access и с residual-trust записью |
| Local separate `codex exec --sandbox read-only` | Candidate для повторной qualification, не выбранный automatic V1 path. CLI flags/auth failure зафиксированы в E03; read-only не означает невозможности читать другие доступные files, `--ephemeral` означает отсутствие persisted rollout, не isolation от config/memory/tools. [Official non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode), [security](https://learn.chatgpt.com/docs/agent-approvals-security) |
| User-assisted fresh session в scoped export review surface | Выбранный V1 fallback contract. Пригодность конкретной передачи устанавливается input/context receipt до использования; host-level isolation не заявляется, `STRICT_FRESH` не присваивается, этот design pass не объявляет manual experiment PASS |
| Custom restricted agent, native review, automated isolated runner | Post-V1 automation candidates после targeted E03 rerun; сохраняют те же packets/returns/gates |

Environment receipt содержит observable review-surface topology (какие volumes/paths/tool connections доступны), transferred input inventory/hashes, effective tool/network grants и nonsecret probes по declared surface. `authoritative_absent` означает, что authoritative repository/state/history и implementation narrative отсутствовали среди переданных project inputs и не использовались; это не утверждение об отсутствии непроверяемых host files, скрытой provider memory или любых системных credential-like environment variables. Known authoritative project access, connector use или credential use — blocker; unobservable host-layer unknown — residual trust. Negative probe без конфигурации/топологии не достаточен. Applicable higher-priority security rules сохраняются; setup не разрешает их обход через ignore-rules/full-access.

Context receipt — 05. Model connection/auth нужны reviewer runtime, но bundle не несёт author credentials; tools не получают доступ к production endpoints/state. Necessary oracle запускается на isolated copy/fixture. Если criterion требует недоступный real integration, записать UNVERIFIABLE либо отдельно разрешённую проверяемую isolated test surface; user assent не заменяет observation. Внешняя среда review не становится execution/control-root Autopilot и не расширяет OS/cloud orchestration support из 07.

После handoff authoritative candidate/docs остаются frozen; status/owner bookkeeping при ожидании/recovery разрешён только обычными owner transactions и проверяется по их receipts. Это исключение относится к scoped manual review surface: broad host access не превращается в strict isolation claim, а exact candidate/ledger-hash freeze сохраняется. Returned product checks относятся к pristine imported export, mutations в test copy отделяются; authoritative integrity проверяется orchestrator перед gate. Mismatch/known project-input access/connector use → invalid verdict, quarantine и setup requalification; unobservable host-layer unknown записывается как residual trust.

**Residual trust:** manual route полагается на достоверность operator setup/context receipt и не скрывает ограничение, что underlying host/platform может быть шире наблюдаемой review surface. V1 явно принимает эту ограниченную human-attested input/context freshness вместо недоступного automatic strict proof; `STRICT_FRESH` не присваивается. Technical input separation, no known narrative/project inputs, independent reviewer, current-intent criteria, pristine evidence и запрет self-repair сохраняются. E03-M/E07/E08 должны проверить путь до release; отсутствие receipts или known authoritative exposure блокирует run, а user approval/routine reviewer не закрывает G5.

## Destructive effects, rollback and cleanup

Обязательный action gate: exact target/effect, existing user authority, current fingerprint, recoverable checkpoint/backup либо признанная необратимость, effective permission, post-effect proof. Нормальная scoped file deletion, прямо необходимая authorized ticket, может использовать уже имеющуюся authority; дополнительные вопросы только при новой материальной границе.

V1 core не делает force-push, history rewrite, production migration, recursive cleanup чужих путей, credentials rotation, deployment/messaging. Если это essential product request, scope обозначается unsupported external action либо готовится reviewable handoff; не обещается automatic completion.

Rollback:

- Uncommitted partial attempt: сохранить patch/manifest evidence, stop/reuse guard по 02. Восстановить только доказанно owned paths к base отдельной prepared operation; foreign changes сохранить. New untracked files удалять лишь по exact inventory. Уже committed candidate, даже до INTEGRATED, исправляется новым repair/revert commit.
- Integrated defect: новый scoped revert/repair commit, revalidate affected dependencies/criteria. Никакого reset истории run.
- Unknown ownership/drift: quarantine и explicit resolution, не автоматический rollback.
- Environment/external data: Git не восстанавливает их; disposable local fixtures можно пересоздать, production rollback не часть V1.

Pause/cancel сохраняют worktree и changes. Cleanup optional после recorded accepted/abandoned ownership disposition, подтверждённой остановки процессов и сохранённого checkpoint; exact owned target, без recursive global prune. Отсутствие cleanup не блокирует terminal report. Reuse checkout после смены epoch требует отдельного guard/attestation из 02; epoch сам по себе не останавливает worker.

**Completion safety design:** write-set violation невозможно интегрировать как accepted; reviewer не может ремонтировать своё finding; crash между Git и ledger reconciles по 02; recovery/rollback не удаляют foreign state; technical и semantic guarantees названы отдельно.
