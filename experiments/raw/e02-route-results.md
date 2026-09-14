# E02 route/model observations

## Raw observations

- `spawn_agent` rejected requested model
  `definitely-not-a-codex-model` before returning a child handle.
- Exact rejection exposed this available override catalog:
  `gpt-6-astra`, `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`, `gpt-5.5`.
- Agent inventory immediately afterward contained no
  `/root/e02_invalid_route` entry.
- No fallback spawn was attempted.
- The exposed `spawn_agent` contract states that full-history forks inherit
  parent model/reasoning and cannot accept overrides. It does not return the
  observed child model or effort.
- A default opaque `fork_turns=none` child successfully read a bounded packet;
  another default opaque child successfully ran and verified a bounded local
  writing command.

## Inference

- Invalid requested binding rejection and no-spawn detection: PASS for this
  exact native error path. No duplicate was created.
- Actual child identity/effort: UNKNOWN. The override catalog is availability
  input, not an execution receipt.
- Opaque default child adequacy: PASS only for the bounded representative
  fixture. Parent model adequacy cannot be transferred to `fork_turns=none`
  through an inspectable inheritance chain on current evidence.
- Full-history model/effort inheritance is documented by exposed tool schema,
  but the behavioural context arm showed selective history visibility; model
  identity still remains UNKNOWN.

