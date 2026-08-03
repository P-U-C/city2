# Authority evaluator contract v1

The machine-readable vocabulary is
[`../../config/authority-policy.v1.json`](../../config/authority-policy.v1.json)
and validates against
[`../../schemas/v1/authority-policy.schema.json`](../../schemas/v1/authority-policy.schema.json).

```text
evaluate(operation, task, manifest, runner, tool, filesystem, network,
         credential, policy, approval) -> city2.authority-decision/v1
```

Evaluation is a deny-by-default intersection. Every required dimension must
return `allow`; explicit deny wins. Missing, stale, conflicting, unsupported or
unparsable input denies. Authority classes classify operations but are not a
numeric permission minimum, and a prompt cannot alter the result.

For `A1+`, independent review is an additional gate. The maker cannot be the
sole reviewer and the reviewer cannot possess the capability, approval,
credential or mutable workspace needed to execute the reviewed operation.

An approval binds one exact operation as defined by `city2.approval/v1` and is
consumed atomically with action preparation. Any operation change requires a
new approval. The decision trace uses bounded reason codes and contains no task
content, secret, path, target details or raw identifiers beyond the operation's
namespaced idempotency key.
