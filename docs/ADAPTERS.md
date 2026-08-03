# City2 adapters — M3 implementation boundary

M3 implements provider-neutral boundaries for Buzz ingress and PfTerminal
execution. It does **not** route the live coordinator through Core. Activation
still requires Chad's explicit deployment instruction after review.

## Buzz adapter

`BuzzAdapter` accepts a structured task only when the signed upstream envelope
identifies the configured owner public key and an explicitly allowed private
channel. The initial coordinator is hard-limited to `A0`; elevated tasks are
denied before Core mutation.

Buzz message content is not canonical authority and is not retained. Core
stores only a message/profile hash and task mapping. Task creation uses the Buzz
event ID as its command idempotency key, so a crash after task commit but before
mapping commit recovers the same task. Work is subsequently rendered from Core
and survives relay loss or restart.

The CEO projection is read-only: objective state, tasks awaiting approval,
reconciliation/terminal exceptions and open memory conflicts. It reports
`authority_class: A0` and performs no approval or action.

## PfTerminal runner adapter

`PfTerminalRunnerAdapter` emits a schema-valid, hashed capability manifest. It
reports current degraded dimensions honestly: usage accounting is estimated,
model controls are partial and budget enforcement is best effort. Negotiation
validates the manifest hash and denies every missing, unsupported or degraded
required capability.

Fresh requests verify task/context hashes and contain the immutable task
envelope, deterministic context, `fresh_session: true` and an explicitly empty
conversation history. Prepared dispatch metadata is durable but stores no
provider session or hidden model state. Actual `pfterminal exec`, cancellation
wiring and live result submission remain activation-gated.

## Conformance and activation

`tests/test_adapters.py` proves owner/channel/A0 denial, Buzz event collision
handling, restart recovery, read-only CEO projection, manifest hash checks,
fail-closed degradation, fresh-session construction, durable dispatch,
conversation/provider-session absence and semantic equivalence across two
fixture providers.

This offline proof does not satisfy M3's live-routing criterion. Activation
remains open. The coordinator is now Bot in each bootstrap channel, but it must
still be reviewed, backed up and explicitly switched to Core with a tested
rollback.
