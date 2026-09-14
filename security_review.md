# Security review

## 1. Plaintext DB password in `config/app.env`
Committed to the repo in plaintext. Risk: anyone with repo access sees the
real credential. Production fix: use a secrets manager or Docker secrets,
keep only `.env.example` with placeholders in the repo.

## 2. Root DB user used by the app
`barq_app` has full rights on `barq_tasks`. Production fix: least-privilege
DB role, scoped grants per table/operation.

## 3. No TLS on the public endpoint
NGINX serves plain HTTP on 8080. Production fix: TLS termination
(cert-manager/Let's Encrypt or an upstream load balancer with TLS).

## 4. No rate limiting / no WAF on NGINX
Public endpoint has no protection against abuse or basic flood attacks.
Production fix: `limit_req` in NGINX or an edge WAF.

## 5. No authentication on `/records` (write endpoint)
Anyone can POST records. Production fix: API key or auth middleware before
write endpoints go live outside a lab environment.

## 6. Images pinned by digest, but base OS packages not scanned
`python:3.12-slim-bookworm`, `postgres:16-alpine`, etc. are pinned by
sha256, which is good, but no CVE scanning is run against them.
Improvement: add Trivy/Grype scan step in CI (the task's optional extra
credit item).

## 7. No centralized logging/monitoring
Logs stay inside each container's stdout; nothing is shipped to a
central store or alerting system. Production fix: log shipping
(e.g. Loki/ELK) plus basic alerting on error-rate spikes.

## 8. Single point of failure: one postgres, one redis instance
No replica/failover for either. If the postgres container's host dies,
the volume goes with it (single-host storage). Production fix: managed
DB service or a replicated setup with off-host backups.

## 9. Backups stored locally, not off-site
`backup.sh` writes to `./backups/` on the same host as the data. Risk:
a host-level disaster destroys both live data and backups together.
Production fix: ship backups to remote/object storage on a schedule.

## 10. `docker exec` used for backup/restore requires host/Docker access
Anyone with Docker access to the host can dump or overwrite the database
directly, bypassing the app entirely. Acceptable for this lab assessment;
in production this would need to be restricted (e.g. via a dedicated
backup service account, not open host access).