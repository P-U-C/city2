# City2 agent contract

This repository is operated through PfTerminal. Treat these instructions as the
project-level contract for every interactive, Telegram and headless run.

## Mission

Build City2 as a reliable human/agent operating system:

- PfTerminal is the execution, review and operational harness.
- Buzz is the private communication, identity and signed-audit plane.
- Existing cron, SQLite, Git and corpus producers remain the data plane until a
  measured migration explicitly replaces one.
- OpenClaw is legacy evidence only. Do not depend on, repair through, import
  from or mutate `~/.openclaw` as part of City2 work.

## Source of truth

1. `docs/ARCHITECTURE.md`
2. `docs/COMPANY-OS-SPEC.md` for the accepted target and milestone gates
3. `docs/MIGRATION.md`
4. `docs/SECURITY.md`
5. `docs/OPERATIONS.md`
6. `config/fleet.json` for the declared City producer fleet
7. Code and tests in this repository

Host-wide truth still belongs in `/home/ubuntu/RUNBOOK.md`; verify live state
before changing an external producer or service.

## Work loop

For every substantive change:

1. Define the objective, constraints, success criteria and stop conditions.
2. Inspect current code, runtime evidence and prior failed attempts.
3. State the weakest valid hypothesis sufficient to explain the evidence and
   the smallest reversible action that can test it.
4. Implement only that scope and measure the result.
5. Record what improved, worsened or remains uncertain; revise the hypothesis
   before another pass.
6. Repeat until the success criteria are verified or a stop condition is met.
7. Run `./city2 validate` and the narrowest relevant runtime test, then broaden
   checks in proportion to risk.
8. Review the diff, scan it for secrets, and record outcome, evidence, changes,
   checks and any remaining gate.

"Weakest" means least specific, not shortest: do not assert or encode more than
the evidence requires. Never convert failed attempts into a false one-pass
success, repeat an unchanged failed approach, or loop merely to keep context
alive.

## Hard boundaries

- Never print, commit or send secrets, private Nostr keys, recovery material,
  wallet material, tokens, passwords or `.env` contents.
- Provider keys originate in PfTerminal's encrypted vault and are transferred
  only through the reviewed RAM-backed systemd-credential flow.
- The human owner key stays on the human-controlled device; this repo accepts
  only public `npub` or public hex.
- No public relay exposure. Bind to loopback or Tailscale unless Chad explicitly
  approves a reviewed TLS/public-ingress change.
- No autonomous publishing, financial action, third-party messaging, producer
  schedule changes or production deployment without an explicit instruction.
- Do not rely on Buzz workflow approval suspension as a security boundary.
- Do not commit generated binaries, backups, runtime databases or agent state.

## Commands

- `./city2 doctor` — read-only project and host capability report.
- `./city2 validate` — offline static/contract checks.
- `./city2 fleet` — one-SSH, read-only producer and host health probe.
- `./city2 fleet --offline` — validate the declared fleet without host access.
- `./city2 agent "..."` — start a PfTerminal headless turn in this repo.
- `./city2 review` — use PfTerminal to review uncommitted changes.
- `./city2 core <command>` — operate an explicitly selected local Core ledger.
- `./city2 buzz <command>` — explicit Buzz relay lifecycle wrapper.
- `./scripts/build-buzz-tools.sh` — reproduce pinned local tools.

Do not bypass `./city2` for normal operations unless debugging the wrapper
itself.
