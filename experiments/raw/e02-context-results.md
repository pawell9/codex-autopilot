# E02 context results

## Positive inherited-context control (`/root/e02_positive`)

### Raw observations returned by child

- Exact synthetic token `E02_PARENT_9f6c72a1`: not visible to the child.
- Child reported that the visible context contained the parent conversation's
  user qualification brief and governing instructions.
- Child received the assignment as a new task from `/root`.
- No concrete runtime model identifier, reasoning effort, service tier, or
  model-routing receipt was exposed.

### Inference

- The known `fork_turns=all` transport did expose substantive parent history,
  so it is a positive control for contamination/inheritance.
- The missing late marker shows that inheritance is selective or timing-bound;
  it cannot establish complete-history semantics.

## Minimal-context arm (`/root/e02_minimal`)

### Raw observations returned by child

- Packet marker read: `E02_PACKET_4bd881e3`.
- No synthetic parent-history token was present in the received task or the
  two permitted fixture files.
- Directly visible inputs were the task, exact project/path constraints, both
  fixture files, platform system/developer/tool/skill/environment envelope,
  and task-routing envelope.
- No substantive parent conversation content was reported.
- A generic developer declaration said "based on GPT-5" and a generic tool
  rule described full-history inheritance, but no concrete runtime model,
  effort, fork mode, or inheritance receipt was exposed.

### Inference

- This is behavioural clean evidence for this bounded arm, not strict context
  isolation proof. It is eligible evidence for routine worker/review routing
  only with the packet and integrity controls specified by design.
- Strict-final context remains UNKNOWN because the runtime input contract is
  not inspectable and non-recall alone is insufficient.

