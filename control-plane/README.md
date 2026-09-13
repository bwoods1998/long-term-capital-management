# Portfolio cloud supervisor

Independent Cloudflare Worker and Durable Object. Runs once a minute, checks the Sail credit balance and guest progress, maintains bounded spending authority, recovers the fixed service process, and sends owner email. It neither generates research nor places orders.

The API is private. `ADMIN_TOKEN`, `BACKUP_TOKEN` and `SAIL_API_KEY` are Wrangler secrets; do not put their values in configuration or Git. The backup token can only upload immutable checksummed artifacts to private R2 storage. It cannot read backups or control the service.

- `GET /v1/status`: configuration, health and notification receipts.
- `POST /v1/configure`: enroll one immutable, tested service contract.
- `POST /v1/pause` / `/v1/resume`: control the enrolled service.
- `PUT /v1/backups/<service>/<snapshot>/<sha256>.gz`: private backup upload.

Run offline checks with `node --test control-plane/test/*.test.mjs`. Deploy with `wrangler deploy --config control-plane/wrangler.jsonc`. See [operations](../docs/OPERATIONS.md) for enrollment, recovery and limits.
