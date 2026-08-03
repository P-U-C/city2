# City fleet

`config/fleet.json` is City2's declared source of truth for the inherited City
producer/data plane. It records stable contracts—not captured database state.

## Current declaration

- `clawd`: control host; PfTerminal, City2 and downstream consumers.
- `worker-1`: producer host, trying `city-worker-peptides` first and the
  `city-worker-lan` fallback second.
- 14 active sector producers, each with its own Unix user, corpus root, SQLite
  database, `/etc/cron.d` file and aggregate log.
- `swell-checker`: active under `ubuntu` with its existing user crontab.
- `peptide-corpus`: parked legacy evidence. It has no installed cron and its
  last durable output was observed on 2026-05-15; do not count it as active.

## Commands

```bash
./city2 fleet --offline
./city2 fleet
./city2 fleet --json
```

The live command tries aliases serially—never as a burst—then makes one
multiplexed SSH connection to `worker-1`, runs one read-only root probe and
reports the selected alias plus:

- host disk headroom;
- Unix user, runtime root and schedule presence;
- database existence, size and freshness;
- aggregate-log presence.

No cron contents, Git remotes, environment values or credentials are returned.
The command does not alter producers.

Exit codes:

- `0`: healthy;
- `1`: warning only, such as low disk headroom;
- `2`: a producer contract is broken or stale.

## Changes

Changing a fleet entry does not migrate its producer. A real producer change
must still follow the City2 activation loop: inspect live state, update the
manifest and implementation together, validate, run the live probe, review and
record rollback evidence.
