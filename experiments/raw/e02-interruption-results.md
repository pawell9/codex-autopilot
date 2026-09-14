# E02 parent interruption and durable return results

## Fixture identity

```text
parent=/root/e02_interrupt_parent
child=/root/e02_interrupt_parent/e02_writer
writer.sh sha256=213bc36e781a83a71ffb3dd5eec807665755b8f3efc8eb31fc6ff5b617036a39
packet.json sha256=8810ab31f3f656fdbb0a9bbe594788f723fe2ab16334a0ca8ddd9b8f6973d2d3
```

## Raw observations

1. Dedicated parent spawned exactly one child and sent
   `/root/e02_interrupt_parent/e02_writer READY_FOR_PARENT_INTERRUPT`.
2. `interrupt_agent` was called only on the parent and returned
   `previous_status=running`.
3. Immediately afterward, native state reported parent=`interrupted` and
   child=`running`.
4. The bounded trace reached all 12 steps and `return-published`.
5. `return.json` exists and contains the expected 92-byte completed payload.
6. Later native state reported the child completed with shell exit 0 and
   confirmed the return file exists. The parent remained interrupted.

## Inference

- Native control interruption of this dedicated parent did not terminate its
  already-published child or prevent completion of the child's active tool.
- A completed attempt-specific return survived parent interruption and was
  recoverable from both the registered inbox and the canonical child handle,
  without spawning another agent.
- This observation does not establish abrupt process/session-loss or UI
  disconnect semantics. Those modes remain UNKNOWN and require user/runtime
  facilities not exposed by this session.

