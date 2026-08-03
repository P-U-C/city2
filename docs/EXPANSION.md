# M7 measured expansion admission

M7 begins with a fail-closed admission decision, not another agent. The accepted
Company OS requires every role or write-authority expansion to have a role
manifest, measured baseline, evaluation, budget, incident boundary, accountable
approval and removal plan. `city2.expansion-admission/v1` makes that requirement
machine-checkable and portable.

## One-unit rule

An admission candidate is disabled and binds one exact agent manifest. It is
either:

- a `role` addition at the same authority class; or
- a `write-authority` increase by exactly one class.

Combining a new role with elevated authority, skipping an authority class or
activating the candidate inside the decision is invalid. A later activation is
a separate reviewed transaction.

Candidate manifests use repository `git:` references. Unpinned references
resolve from Git's index, never from live, ignored or untracked files;
historical evidence uses a full commit SHA or an immutable Git blob SHA plus
its SHA-256 content digest.

An `admit` decision fails unless all evaluation criteria pass with evidence, a
numeric threshold is met in its declared direction or an explicit threshold
matches, at least one measured sample exists, the target improves on the
baseline and the accountable approver signs after the decision and evidence.
Incident and outward-action boundaries must match the target authority.
Measurement samples must fall inside the declared window, and the bound
manifest cannot exceed the admission runtime, concurrency or cost ceiling.
The decision digest excludes only its own digest and storage aggregate version.

## Current decision: defer

`config/expansion-admission.m7.json` evaluates the smallest useful next unit: a
disabled A0 coordinator pilot routed through Core. It is deliberately deferred:

- M6 is accepted;
- the M2 fresh-session criterion has not run in the live path;
- the M3 live Core-routing/restart criterion has not run;
- the checked-in decision predates the coordinator's completed demotion; and
- there are zero successful live recovery drills versus a threshold of three.

The decision is immutable evidence of what was known when it was created. On
2026-08-03 the coordinator subsequently signed its own reduction from Owner to
Bot in all three bootstrap channels after explicit owner direction. The human
identity is now the sole Owner. The first self-targeted event attempt failed
closed because the pinned upstream CLI removed its own `p` tag; no role changed.
A disposable patched signer preserved the explicit self tag, its focused unit
test passed and the relay accepted exactly three signed role events. The binary
was not installed or committed. Public, content-free evidence is in
`docs/M7-DEMOTION-EVIDENCE.md`; complete signed evidence remains private and
off-repository.

This completed precondition does not convert the old decision to `admit` and
does not authorize Core routing. M2/M3 live evidence and three recovery drills
remain absent.

The bound `config/coordinator-agent.m7.json` grants no credential, write,
publication or outward-action authority. No Core database, service, identity,
channel, model call or deployment is created by this decision.

## Promotion procedure

1. Completed 2026-08-03: demote the live coordinator to Bot and preserve a
   verified identity/relay backup.
2. Run the reviewed A0 status path through Core with fresh sessions and no
   conversation dependence.
3. Prove restart/relay-loss recovery three times and attach immutable evidence.
4. Revise the admission record, its measurement window and digest; do not edit
   the existing decision in place.
5. Obtain accountable approval and independent review.
6. Activate only the exact reviewed pilot, then enforce its stop/removal plan.

Until those steps pass, the correct M7 decision is `defer`.
