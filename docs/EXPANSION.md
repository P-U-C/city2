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
- the deployed coordinator still has Owner role and must be demoted first; and
- there are zero successful live recovery drills versus a threshold of three.

The bound `config/coordinator-agent.m7.json` grants no credential, write,
publication or outward-action authority. No Core database, service, identity,
channel, model call or deployment is created by this decision.

## Promotion procedure

1. Demote the live coordinator from Owner to Bot or Member in its existing
   private channels and preserve a verified identity/relay backup.
2. Run the reviewed A0 status path through Core with fresh sessions and no
   conversation dependence.
3. Prove restart/relay-loss recovery three times and attach immutable evidence.
4. Revise the admission record, its measurement window and digest; do not edit
   the existing decision in place.
5. Obtain accountable approval and independent review.
6. Activate only the exact reviewed pilot, then enforce its stop/removal plan.

Until those steps pass, the correct M7 decision is `defer`.
