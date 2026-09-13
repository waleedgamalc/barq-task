# Log analysis


## 1. UTC interval and line counts

Time range covers all three log files: 2026-08-20 11:00:00 to 2026-08-20 11:29:57 UTC.

| File | Total lines | Malformed | Duplicate | Valid unique |
|---|---|---|---|---|
| access.log | 726 | 1 | 5 | 720 |
| error.log | 68 | 0 (see note) | 0 | 67 usable |
| application.log | 730 | 1 | 2 | 727 |

Note on error.log: all 68 lines parse as plain text (no JSON), but one line is not an
error at all. It is a `[notice]` log rotation message, not an `[error]` entry:
```
2026/08/20 11:30:00 [notice] 31#31: log collector rotated stream
```
So error.log has 67 real error entries, not 68.

"Malformed" = a line that failed `json.loads()`. "Duplicate" = an exact repeat of
a full line already seen (byte-for-byte), for example `lab-000181` and `lab-000421`
in application.log, and one repeat in access.log.

## 2. Distinct client requests and deduplication

720 distinct client requests reached NGINX (access.log, after removing 5 exact
duplicate lines and 1 malformed line).

Deduplication rules used:
- Drop exact duplicate lines before parsing (same request_id, same timestamp,
  same everything. These are logging bugs, not two real requests).
- In application.log, only count lines where `event == "http_request"` as a
  request. `event == "dependency_error"` lines share the same request_id as
  the request they belong to, but they are a second log entry about the same
  request, not a second request. Counting both would double the number of
  requests.
- Retries: access.log sometimes shows a comma-separated upstream field, e.g.
  `"172.23.0.12:8080, 172.23.0.11:8080"`. This is one client request that NGINX
  retried against a second backend after the first one failed. It is counted
  once, not twice. 19 requests had this pattern.

## 3. Final client status counts and error rate

From access.log (720 valid unique lines; this is the denominator, since it
represents what the client actually received):

| Status | Count |
|---|---|
| 200 | 615 |
| 503 | 47 |
| 502 | 40 |
| 404 | 10 |
| 504 | 8 |

Error rate (status >= 500) = (47 + 40 + 8) / 720 = 95 / 720 ≈ **13.2%**

404s are not counted as errors here. They are client requests to a path that
does not exist (`/missing`), which is expected behavior, not a system failure.

## 4. Failures by path, time window and backend

By path (application.log, http_request events with status >= 400):
```
/ready:    23
/counter:  16
/missing:  10   (expected 404s, not real failures)
/records:   8
```

By backend (application.log):
```
app-02: 29 failed requests
app-01: 28 failed requests
```
Roughly even. Both backends were affected, which matches a shared dependency
(redis/postgres) rather than a single broken container.

Time windows (four separate incidents, not one continuous outage):

| Window (UTC) | Source | Cause | Count |
|---|---|---|---|
| 11:05:02 – 11:09:57 | error.log | Connection refused to app-02 (172.23.0.12) | 59 |
| 11:12:09 – 11:15:52 | application.log | Redis TimeoutError | 31 |
| 11:20:07 – 11:21:45 | application.log | Postgres InvalidPassword | 16 |
| 11:25:14 – 11:26:47 | error.log | Upstream timeout on /records only | 8 |

## 5. Latency (median and p95)

Using `request_time` from access.log (unit: seconds, as stated in logs/README.md),
across all 720 valid client requests, sorted ascending:

- Median (50th percentile): **0.054s**
- p95 (95th percentile, nearest-rank method: index = floor(0.95 × n)): **2.001s**

The large gap between median and p95 is expected: most requests are fast
(normal health/instance/counter calls), but the p95 is pulled up by the
503/504 failures, which take ~2 seconds each before failing (matches the
`duration_ms: 2025.0` seen on the Redis timeout entries in application.log).

## 6. Retried requests

19 requests show a comma-separated upstream in access.log, meaning NGINX
retried a second backend after the first attempt failed. All 19 of these
ended with a final status of 200. Every retry succeeded on the second
attempt.

Example: `lab-000606`, first attempt to 172.23.0.12 timed out (504 in
error.log), second attempt would be logged separately per this rule if it
succeeded on the same client request; if not part of the 19-retry set, it
counts as a plain failed request instead.

## 7. Incident timeline (cross-referenced across all three logs)

```
11:00 – 11:04   Normal traffic, all 200s
11:05 – 11:09   app-02 (172.23.0.12) refuses all connections
                -> error.log: "connect() failed (111: Connection refused)"
                -> access.log: same request_ids return 502
                -> application.log: NOT present (app-02 process never
                   received the request. NGINX rejected it before reaching
                   the app)
11:10 – 11:11   Recovered, all 200s
11:12 – 11:15   Both app-01 and app-02 report Redis TimeoutError
                -> application.log: dependency_error + http_request 503
                   on /ready and /counter
11:16 – 11:19   Recovered, all 200s
11:20 – 11:21   Both app-01 and app-02 report Postgres InvalidPassword
                -> application.log: dependency_error + http_request 503
                   on /ready and /records
11:22 – 11:24   Recovered, all 200s
11:25 – 11:26   /records only, both backends, times out (not refused)
                -> error.log: "upstream timed out (110: Operation timed out)"
                -> access.log: 504
11:27 – 11:29   Recovered, all 200s
```

## 8. One correlated failed request and one successful request

**Failed request (`lab-000122`):**
```
access.log:      {"timestamp":"2026-08-20T11:05:02.503Z","request_id":"lab-000122",
                   "method":"GET","path":"/health","status":502,
                   "upstream":"172.23.0.12:8080","upstream_status":"502",
                   "request_time":0.003}
error.log:        2026/08/20 11:05:02 [error] ... connect() failed
                   (111: Connection refused) ... request_id=lab-000122
                   ... upstream: "http://172.23.0.12:8080/health"
application.log:  NOT FOUND
```
The request never reaches application.log at all. This is direct proof it is
a proxy/connectivity failure, not an application failure. The app process
never saw the request because NGINX could not open a TCP connection to it.

**Successful request (`lab-000005`):**
```
access.log:       {"timestamp":"2026-08-20T11:00:10.083Z","request_id":"lab-000005",
                    "method":"GET","path":"/ready","status":200,
                    "upstream":"172.23.0.11:8080","upstream_status":"200",
                    "request_time":0.083}
application.log:  {"timestamp":"2026-08-20T11:00:10.083Z","level":"INFO",
                    "event":"http_request","request_id":"lab-000005",
                    "instance_id":"app-01","method":"GET","path":"/ready",
                    "status":200,"duration_ms":83.0}
```
Same request_id and timestamp in both files, and `172.23.0.11` in access.log
matches `instance_id: app-01` in application.log, confirmed by checking
several other matching request_ids the same way (172.23.0.11 = app-01,
172.23.0.12 = app-02, consistent every time checked).

## 9. Proxy/connectivity issues vs dependency/application issues

**Proxy/connectivity (NGINX-level):**
- 11:05–11:09 (connection refused) and 11:25–11:26 (upstream timeout)
- Proof: these requests show up in error.log with NGINX-level error messages
  ("connect() failed", "upstream timed out") and are either **absent from
  application.log entirely** (connection refused case) or show no matching
  dependency_error entry (timeout case). The app process was never involved
  in producing the failure.

**Dependency/application (app-level):**
- 11:12–11:15 (Redis) and 11:20–11:21 (Postgres)
- Proof: these requests DO appear in application.log with an explicit
  `dependency_error` event naming the failing dependency (`redis` or
  `postgres`) and an `error_type` (`TimeoutError`, `InvalidPassword`). The
  app received the request, tried to reach its dependency, and reported
  the failure itself. NGINX simply forwarded the app's own 503 response.

## 10. What the logs do not prove / what to check next

The logs are historical evidence of a past incident, not a live system
state. They do not prove:
- Whether these same root causes are still present in the environment today
  (they were separately found and fixed live; see troubleshooting.md).
- What was physically wrong with app-02 during 11:05–11:09 (crash? restart?
  slow startup?). The logs only show the symptom (refused connections), not
  the cause on the container/host side (would need `docker logs`/`docker
  events` from that time, which are not part of this evidence set).
- Why /records specifically timed out at 11:25–11:26 (slow query? lock?
  connection pool exhaustion?). It would need database-side logs or slow query
  logs to confirm, not just the client-facing timeout.
- Whether any requests were lost outside the log window (11:00–11:30) or
  outside what NGINX/the app choose to log (e.g. requests that never reached
  NGINX at all due to an external network problem would not appear here).

In a running environment, next steps would be: check container restart
history for app-02 around 11:05, check Postgres/Redis server-side logs for
the same time windows, and check database query performance for `/records`
around 11:25.

## Commands / scripts

All analysis was done with small Python scripts against the raw files in
`logs/`, without modifying the originals. Key techniques used:
- `json.loads()` per line with try/except to separate valid JSON from
  malformed lines.
- A `seen` set of raw line strings to drop exact duplicate lines before
  parsing.
- Filtering by `event` field in application.log to avoid double-counting
  `dependency_error` alongside its matching `http_request`.
- Regex extraction of `request_id`, `path` and `upstream` IP from the
  plain-text error.log lines.
- Cross-referencing the same `request_id` across files (dictionary lookup)
  to confirm IP-to-instance mapping and produce the correlated examples
  above.

(See `analyze_logs.py` in the repo for the exact scripts and their output.)

## Results

See sections 1–6 above for counts, status distribution, latency and retry
results.

## Timeline and correlated examples

See sections 7 and 8 above.

## Conclusions and limits

See section 9 (root cause classification) and section 10 (limits of what
the logs prove) above. In short: the historical incident data shows four
separate, unrelated failures (NGINX connectivity, Redis, Postgres, and a
slow /records path) rather than one continuous outage, and the log format
made it possible to tell proxy-level failures apart from application-level
failures using only the request_id as a join key across all three files.