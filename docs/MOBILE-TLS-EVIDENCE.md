# Private mobile TLS evidence

Date: 2026-08-06 UTC

## Root cause

The pinned Buzz mobile release validates imported credentials before storage.
In release mode, the transferred relay URL must use `https://`; private IP
literals are also rejected. Buzz Desktop transfers the HTTP form of its active
workspace relay URL in the encrypted pairing payload. A Desktop workspace
opened through the transition `ws://` endpoint therefore transferred an HTTP
URL even when its NIP-11-discovered `/pair` transport used WSS.

The source behavior was verified at the pinned Buzz commit recorded in
`infra/buzz/SOURCE.md`, in the mobile pairing provider and Desktop pairing
command. No client validation was weakened or patched.

## Change

- A second digest-pinned Nginx ingress routes the main relay and exact `/pair`.
- Its only host publication is loopback.
- Tailscale Serve terminates a publicly trusted certificate on one declared
  non-default port and forwards only to that loopback ingress.
- Existing direct Tailscale relay and pairing ports remain temporarily available
  so Desktop can transition without a flag-day outage; the coordinator now uses
  WSS.
- The upgrade transaction preserves the existing tenant rather than allowing
  Buzz startup to seed a second empty community under the new authority.
- City2 never invokes Funnel, never resets unrelated Serve state and refuses a
  conflicting route instead of replacing it.
- The proxy preserves the relay's 500 MiB media ceiling rather than inheriting
  Nginx's narrower request-body default, and streams request bodies instead of
  spooling large media uploads into proxy tmpfs.

## Live checks

The deployed path passed:

- certificate and hostname verification with the system trust store;
- HTTPS relay readiness and NIP-11 retrieval;
- NIP-11 exact WSS pairing URL and NIP-43 declaration;
- main-relay and pairing WebSocket `101` upgrades;
- pairing bare-GET `426` and non-GET `403` boundaries;
- release-compatible HTTPS DNS URL shape without an IP literal;
- exact Tailscale Serve route verification;
- no all-interface listener on the TLS port;
- exactly one retained community with the original 12 channels and two members;
- authenticated WSS channel discovery for the coordinator's `control`, `city2`
  and `ops` memberships;
- all relay containers healthy and the coordinator active on WSS.

The disposable proof also covers tenant-preserving host migration, both ingress
paths, signed owner round-trip,
outsider rejection, aligned backup, destructive restore, recovered message and
complete random-project cleanup.

## Remaining client gate

Successful iPhone credential import is not claimed here. Buzz Desktop must first
reconnect the active City2 workspace through the new HTTPS/WSS community
endpoint, then generate a fresh **Settings → Mobile** pairing session. The phone
must remain on the same tailnet. That final client result is owner-observed.
