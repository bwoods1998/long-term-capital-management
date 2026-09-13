# Portfolio cloud supervisor

Independent Cloudflare Worker and Durable Object. Runs once a minute, checks the Sail credit balance and guest progress, maintains bounded spending authority, recovers the fixed service process, and sends owner email. It neither generates research nor places orders.

The API is private. `ADMIN_TOKEN`, `BACKUP_TOKEN` and `SAIL_API_KEY` are Wrangler secrets; do not put their values in configuration or Git. The backup token can only upload immutable checksummed artifacts to private R2 storage. It cannot read backups or control the service.

In `available_credit` mode, fresh Sail credit funds research after outstanding requests, existing epoch reservations and the remaining host resource allowance are accounted for. There is no fixed weekly or rehearsal inference cap; top-ups create new headroom automatically. The controller refreshes the host allowance from provider rates and resource ceilings, treats it as a reserve rather than a dollar stop, and derives funding runway from observed spending. Missing billing or resource data closes new admission while cleanup remains available. Explicit research windows, the final deadline and owner pause still apply; older fixed-budget enrollments retain their original rules.

- `GET /v1/status`: configuration, health and notification receipts.
- `GET /v1/transport-check`: private, read-only checks of provider connectivity.
- `POST /v1/configure`: enroll one immutable, tested service contract.
- `POST /v1/replace`: archive a paused, parked, backed-up enrollment and atomically enroll a verified stopped replacement. Requires the prior service identity, new configuration and matching readiness/backup receipt; retries preserve that operation.
- `POST /v1/release`: authorize reviewed runtime code on the same stopped, backed-up Sailbox. Archives the prior manifest and preserves configuration, journals, outstanding requests and spending policy. Resumption is explicit.
- `POST /v1/pause` / `/v1/resume`: control the enrolled service.
- `PUT /v1/backups/<service>/<snapshot>/<sha256>.gz`: private backup upload.

Run offline checks with `node --test control-plane/test/*.test.mjs`. Deploy with `wrangler deploy --config control-plane/wrangler.jsonc`. See [operations](../docs/OPERATIONS.md) for enrollment, recovery and limits.
