# ai-infra observer removal

This bundle does not install or activate anything. If a separately approved
shadow deployment occurs, rollback is:

1. stop `city2-producer-observer-ai-infra.service` if it is running;
2. preserve `/var/lib/city2-producer-observer-ai-infra/observation.json` for
   review, then remove that state only under the approved evidence policy;
3. remove the unit, the two `/etc/city2/producer/ai-infra.*.json` manifests and
   `/opt/city2/lib/city2` payload;
4. run `systemctl daemon-reload` and prove the producer aggregate, schedule,
   database and existing downstream outputs are unchanged.

No rollback step edits the producer tree or restores OpenClaw.
