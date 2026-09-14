# Design status

**CODEX-AUTOPILOT V1.0.0 — FROZEN / RELEASE READY.**

The frozen baseline includes the latest real-world remediation fixes, durable
presets, and 40-ticket scale qualification. This status file remains the
design provenance record; the standalone usage guide is [`../README.md`](../README.md).

## Bounded run preset addendum — 2026-09-14

The production package now persists optional `run_settings` (`semi`/`full` interaction and `normal`/`deep` analysis depth). Resolution is deliberately small and phrase-based; omission or ambiguity uses `semi + normal`. The preset is an orchestration intent, not a model binding or lifecycle/safety change. Legacy ledgers resolve the same defaults without migration; mid-run changes are out of scope. A synthetic 40-ticket qualification fixture covers the existing serialized lifecycle helpers.

**V1 RELEASE READY — 2026-09-13.** Release-state reconciliation подтверждает E01, E03-M, E04b, E05, E06, E07, E08 и E09 PASS на текущем production package. Strict automatic reviewer transport **не qualified**; V1 использует проверенный user-assisted critical/G5 fallback. См. [reconciliation](../experiments/v1-release-ready-reconciliation-2026-09-13.md).

## Read-only dashboard addendum — 2026-09-13

`tools/dashboard.py` + `dashboard/index.html` provide a local GET-only projection of the selected current `.autopilot/runs/<run-id>/ledger.json`. The page refreshes from that ledger, never writes it, never controls a run, and records missing ledger facts as visible `CONCERN`; no second state store was added.

## Evidence and disposition

Прочитаны qualification reports/raw logs/fixture payloads и свежие targeted PASS outputs. Старые blocked verdicts сохранены как historical provenance; current authority — release-state reconciliation.

| Experiment | Observed result | V1 disposition |
|---|---|---|
| [E02](../experiments/E02-native-context-and-interruption.md) | PASS bounded worker/behavioural clean/file returns; strict context/model identity/abrupt loss UNKNOWN; descendant stop FAIL | Existing bounded native worker + file/message return, scoped adequacy; liveness quarantine/attestation сохраняются |
| [E03](../experiments/E03-reviewer-isolation-and-transports.md) | Routine export/barrier PASS; authoritative prevention/write-and-restore FAIL; CLI auth blocked sampling; custom/native review unavailable | Automatic routine path сохраняется. Critical/G5 — D-21 user-assisted fallback, не тот же broad-write native reviewer |
| [E04a](../experiments/E04a-git-approvals-bootstrap-worktrees.md) | PASS clean Git/bootstrap; 11 successful mutations, 0 prompts/escalations в fixture; outside-root denial, prefix/persistence UNKNOWN | Existing clean exclusive checkout default; approval counts только для measured fingerprint; worktree условен и не promoted этим pass |

Active session build/observed child model остаются UNKNOWN. PATH CLI version не заменяет active runtime identity; across-session reuse требует matching observable facts/fresh relevant probes.

## What V1 automates

Bounded workers, cause-first repair, routine coverage/plan/change review на frozen export с serialized integrity barrier, write-set audit, candidate commits и approved Git actions, packet/return bookkeeping. Handoff bundle preparation, validated result import и дальнейшие gate transitions также автоматизируются. Authority/oracle/permission failure по-прежнему может остановить dependent action.

## What requires user assistance

**Каждый G5 round и required critical axis** используют independent clean reviewer session с declared review-surface boundary: пользователю/ reviewer передаются только bundle/export, без authoritative repo/state/history, implementation narrative, project memory и connectors. Пользователь обеспечивает setup/transfer и возвращает exact reviewer result с input/environment receipts; допустим Codex или явно выбранный внешний reviewer service, обязательного provider нет. Выбор режима disclosed при G0, critical prerequisites до affected work/G3.

Нормативный protocol — [05: handoff](05-task-and-return-contracts.md#user-assisted-criticalg5-handoff); input-boundary policy — [06: environment](06-safety-write-git-model.md#manual-review-environment). Clean-input provenance имеет grade `MANUAL_ATTESTED_CLEAN`: human setup trust по переданным inputs/context принят явно, `STRICT_FRESH` не заявляется. Без input inventory/context attestation/independent checks, либо при известном authoritative access, конкретный run остаётся BLOCKED. Непроверяемые host-layer свойства — residual trust, не фиктивный blocker и не PASS. User approval не заменяет G5; current-intent criteria, pristine candidate, independent verdict и required critical axes сохранены.

Полностью unattended acceptance не входит в этот V1 delivery mode. При отказе от manual участия и отсутствии нового qualified automatic transport completion blocked. Новый request не требует от пользователя ручного чтения всех tickets или routine gate approvals.

## What remains post-V1

- Fully automatic strict critical/G5 после targeted authenticated/restricted E03 rerun; login сам по себе не isolation PASS.
- Custom restricted reviewer, native review transport или automatic isolated-runner provisioning — только по evidence, без обязательного framework/daemon.
- Bounded parallel worktrees E10 остаются прежним post-V1 experiment. Worktree full session-loss recovery qualification остаётся prerequisite его включения, clean V1 её не ждёт.

## Necessary design changes

Изменены только [01](01-lifecycle-state-machine.md) (human interaction point), [03](03-agent-architecture.md), [05](05-task-and-return-contracts.md), [06](06-safety-write-git-model.md), [07](07-preflight-capabilities.md), [08](08-skill-file-architecture.md), [09](09-v1-functional-spec.md), [10](10-decisions-and-experiments.md), [11](11-review-adjudication.md) и этот STATUS. D-21 и сравнение вариантов — [10](10-decisions-and-experiments.md#e03-blocker-adaptation--2026-09-13). 27 исходных adjudications сохранены; 11 получил dated addendum.

00/02/04 не менялись; 01 только перечисляет новый handoff среди human interaction points. Lifecycle transitions, workers/routing policy, ledger и Git execution model сохраняются. Routine reviewer algorithm не заменён. Manual path использует существующие attempts/evidence/capabilities/acceptance, BLOCKED/RECOVERING и next_action; новых states/collections/production files нет.

## Completed release validation

E01, E03-M, E04b, E05, E06, E07, E08 и E09 теперь имеют PASS evidence, включая исторические 16/16 regression tests, E04b target-mismatch rejection и E09 worker-lease/restart/usage qualification. Текущий bounded enhancement добавляет отдельные preset tests и synthetic 40-ticket qualification; E10 остаётся post-V1.

E07/E08 проверяют отсутствие G5 bypass, contaminated/stale/malformed/manual returns и missing input-boundary evidence; E09 отдельно измеряет human setup/transfer/wait и число critical/G5 rounds, сохраняя routine bookkeeping target ≤4 calls/ticket.

## Verification and next step

Static validation PASS: local links/anchors/fences и scope hashes; выполнена проверка согласованности handoff/authority/context/acceptance/recovery. Experiment evidence не меняется; runtime PASS здесь не заявляется.

Следующий authorized action — установить текущий production skill глобально; config.toml не изменять, legacy `autopilot` не использовать и не удалять.

Resume: STATUS → 10/D-21 → 05/06 → 07/09; остальные документы по соответствующей ветке. Старая переписка не нужна.
