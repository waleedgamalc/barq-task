# AI usage disclosure

AI tool used: Claude (Anthropic), chat-based, guided Q&A style — Claude
asked leading questions, I ran the commands and reported real output back,
Claude helped interpret results and write docs/scripts based on that
actual output.

## Where it was used

- **Docker/NGINX debugging (Part 1/2):** Claude asked diagnostic
  questions; I ran `docker compose logs`, `curl`, `grep`, `docker exec`
  commands myself and found root causes (nginx port mismatch, app host
  binding, nginx host↔container port, redis/postgres port+password
  mismatches, INSTANCE_ID copy-paste bug, postgres volume path, exposed
  ports, non-root user, missing restart/resource limits). All fixes and
  retests were applied and verified on my own machine.
- **Log analysis (Part 1):** I wrote and ran the Python analysis snippets
  myself against `logs/`; Claude helped interpret patterns (duplicate
  lines, event types, correlation via request_id) and organize results
  into `log_analysis.md`.
- **Scripts (`analyze_logs.py`, `validate.py`, `failure_test.py`,
  `backup.sh`, `restore.sh`):** Drafted by Claude based on the task
  requirements, then run and verified by me on the actual environment;
  output pasted back and checked against expected PASS/FAIL behavior
  (including forcing real failures, e.g. stopping app-02, to confirm the
  scripts correctly detect failure, not just success).
- **Documentation (`troubleshooting.md`, `log_analysis.md`,
  `decisions.md`, `security_review.md`, this file, `README.md`):**
  Drafted by Claude from the real commands/output I provided during the
  session, reviewed and edited by me.

## Verification

Every root cause and fix in `troubleshooting.md` is backed by command
output I ran and pasted in, not assumed. Every script was executed on my
own machine before being accepted, including deliberately breaking things
(stopping a backend, deleting DB rows) to confirm failure paths work, not
just the success path.