# E02 normal child interruption and descendant-tool liveness

## Fixture

```text
child=/root/e02_cancel_child
script sha256=1adc27f4a755a8ec8b6798fee73252888d93b6e63e435e739c349663ba2bed21
script-recorded shell pid=4987
```

## Raw observations

1. Before interruption, `return.tmp` existed with 43 bytes, trace contained
   only `partial-written`, and the script recorded PID 4987.
2. `interrupt_agent` targeted only `/root/e02_cancel_child` and returned
   `previous_status=running`. Native state then reported child=`interrupted`.
3. Sandboxed `ps -p 4987` was denied. A reviewed, read-only escalated
   `ps -p 4987` returned no row at that observation point.
4. Immediately after interruption, final `return.json` did not exist.
5. After the script's bounded 30-second window, `return.json` existed with 45
   bytes and trace appended `return-published`.

## Inference

- Interrupting the native child agent did not reliably stop its already-running
  descendant tool/writer. The final publication proves continued effect after
  the child was marked interrupted.
- An agent status of `interrupted` is therefore not stop proof for checkout
  reuse on this surface. Exact descendant-process control is not exposed by the
  native agent handle in this arm.
- The empty single-PID `ps` observation was incomplete and is not termination
  proof; the later file effect contradicts it. A known writer must remain
  quarantined until bounded completion or stronger stop/attestation evidence.
- Partial temp correctly did not look complete before rename; recovery can
  ignore it, but cannot assume the producer stopped.

