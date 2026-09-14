# BARQ Academy - DevOps Assessment

Flask app (2 instances) behind NGINX, with PostgreSQL and Redis.

## Setup

```bash
cp .env.example .env

```

## Build & start

```bash
docker compose up -d --build
docker compose ps      # all 5 containers should show Up/healthy
```

## Test

```bash
curl http://localhost:8080/
curl http://localhost:8080/health
curl http://localhost:8080/ready
curl http://localhost:8080/instance
curl http://localhost:8080/records
curl http://localhost:8080/counter

python3 validate.py    # full automated check, exits non-zero on failure
```

## Failure test

```bash
python3 failure_test.py app-01   # or app-02
```
Stops the given backend, proves the other keeps serving, restores it,
proves recovery.

## Backup / restore

```bash
./backup.sh                      
./restore.sh backups/<file>.sql   
```

## Stop

```bash
docker compose stop        # keeps containers/volumes
docker compose down        # removes containers, keeps named volumes
```

## Cleanup (full reset, deletes data)

```bash
docker compose down -v
rm -rf backups/*.sql
```

## Docs

- `troubleshooting.md` — investigation journal (8 issues found/fixed)
- `log_analysis.md` — historical log analysis, all template questions
- `decisions.md` — key design decisions and trade-offs
- `security_review.md` — known risks and production recommendations
- `AI_USAGE.md` — AI tool disclosure