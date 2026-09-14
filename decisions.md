# Decisions

## 1. Restart policy: `unless-stopped` over `always`
Chosen so a deliberate manual `docker compose stop` is respected, while
crashes/OOM kills still auto-recover. Alternative considered: `always`
(rejected,  would fight manual stops).

## 2. Resource limits sized by expected role, not equal across services
postgres got the highest limit (1.0 CPU / 512M) due to read/write DB load;
app-01/app-02 (0.5/256M) just serve HTTP; redis (0.3/128M) and nginx
(0.3/64M) are lightest. Limitation: values are estimates for lab-scale
traffic, not based on real load testing.

## 3. Redis persistence disabled (`--save "" --appendonly no`)
The counter is treated as ephemeral/non-critical state. Trade-off: counter
resets on redis restart. Alternative: enable AOF/RDB if counter accuracy
across restarts becomes a requirement.

## 4. Fixed app-side config instead of changing postgres/redis defaults
When ports/passwords didn't match, the app's config was corrected to match
postgres/redis's real values, not the other way around, since postgres and
redis were already using their standard defaults.

## 5. Plain-SQL format for backups (not custom/binary)
Chosen for readability and easy verification in this assessment, at the
cost of larger file size and slower restore versus `pg_dump --format=custom`.
Acceptable trade-off at this data scale.

## 6. Non-root user for app containers
Dockerfile already created a dedicated `app` user (uid 10001); removed a
stray `USER root` override so containers actually run as non-root,
matching the task's "avoid root/privileged operation" requirement.

## 7. Load-balancing verified via `/instance`, not sticky sessions
No `ip_hash` or session affinity used — NGINX default round-robin is
sufficient since the app is stateless per-request (state lives in
postgres/redis, not in-process).