# Runner contract v1

A runner turns one immutable task envelope plus one immutable context artifact
into one result envelope. It is replaceable execution infrastructure, not an
authority or state owner.

## Operations

```text
capabilities() -> city2.runner-capability/v1
start(task: city2.task/v1, context: city2.artifact/v1) -> run_handle
cancel(run_handle, fencing_token) -> cancellation_receipt
wait(run_handle) -> city2.result/v1 | runner_error
```

Before `start`, Core validates the runner capability manifest and intersects it
with the exact task, agent manifest, policy and approval requirements. A
missing, unsupported or degraded required capability denies dispatch. The
runner cannot widen tools, network, filesystem, credentials, budget or
authority.

## Required behavior

1. Verify the task and context hashes before execution.
2. Start a fresh task-local session and expose only declared capabilities.
3. Enforce time, cancellation, tool and budget limits to the declared level.
4. Preserve exact artifact hashes and return `city2.result/v1`.
5. Report the concrete runner/model and measured or explicitly estimated usage.
6. Destroy task-local session state after a result or terminal error.
7. Keep no authoritative hidden state and never emit a Core acceptance event.
8. Treat a stale fencing token as cancelled and quarantine late output as
   `completed_after_cancel`.

`runner_error` is content-free and contains `code`, `retryable` and a bounded
operator message. Stable codes are `unsupported_contract`,
`capability_missing`, `capability_degraded`, `invalid_envelope`,
`context_hash_mismatch`, `budget_exceeded`, `cancelled`, `runner_unavailable`
and `internal_error`. An error does not authorize automatic replay; Core decides
using task and action state.

Conformance MUST cover mutated envelopes, undeclared tools, forged approval or
acceptance, cancellation races, hidden state dependency, missing accounting and
silent capability degradation.
