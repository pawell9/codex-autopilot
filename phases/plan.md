# Plan and G3

Read the G2-approved design and `references/routing.md`, `references/safety.md`, and `references/ledger.md` as needed. Build vertical tickets backward from observable outcomes, not from arbitrary file counts.

## Ticket contract

Each active criterion maps to a ticket or an explicit shared verification owner. Each ticket has goal, criterion/contract refs, integrated dependencies, complexity and consequence risk, literal versioned write zone, allowed operations/denies, oracle commands/scenarios, and a replacement path. Zones are disjoint for serial product writers; symlinks, generated files, lockfiles, deletes, and both rename endpoints are accounted for.

The DAG is acyclic. A dependency is usable only after its reviewed/current outcome is `INTEGRATED`, never merely after a candidate commit. Serial V1 executes product writers one at a time. Read-only checks may use frozen views when the available capability permits; bounded parallel worktrees are post-V1 E10.

Resolve routing per attempt from task complexity, risk, cause, valid capability facts, and user/project restrictions. Store requested versus observed binding, adequacy, context grade, fallback cause, and evidence. Do not invent model slugs, effort enums, costs, quotas, or a stronger route just because a name sounds capable.

## G3 readiness

Plan review is required for elevated/critical work and can be combined with G2 only on an unchanged compact artifact with separate outcomes. The plan is ready when:

- the DAG is acyclic and each ticket has a current criterion/oracle owner;
- plan risk is at least every ticket and integration risk;
- every write, dependency, review, and recovery boundary is executable;
- Git baseline/branch/approval and checkpoint requirements are known;
- the selected worker/reviewer/oracle capabilities are confirmed or have an exact fallback/blocker.

Publish the plan, tickets, routes, and G3 evidence atomically. A new user amendment, contract change, zone overlap, or oracle loss invalidates affected packets and returns through the legal phase transition. Do not dispatch while G3 is stale.

**Done when:** every active criterion is covered by an executable ticket/oracle, the DAG and zones pass semantic validation, required plan review is PASS, and G3 next action is durable.
