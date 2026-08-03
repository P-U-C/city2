# Independent review — M4

M4 adds durable reviewer manifests and maker/checker enforcement without
deploying or routing the live coordinator.

`ReviewService` validates immutable agent manifests and records achieved
independence dimensions. A reviewer must be enabled for independent review,
must not be the maker, must not hold any maker execution tool or credential and
uses a separate model policy where configured. Task acceptance additionally
requires every mandatory criterion to have deterministic passing evidence, a
completed fenced result and no unresolved action. Failures deny acceptance.

Changes-requested decisions retain canonical finding IDs and flow through the
existing immutable task-revision path. Memory promotion uses the same registered
maker/reviewer separation plus exact source checks; agents cannot promote their
own candidates.

`tests/test_review.py` proves self-acceptance and missing evidence fail closed,
an independently incapable reviewer can accept, and the durable review records
maker, checker, checks, findings and independence. This changes no live
authority; A1+ operation remains activation-gated.
