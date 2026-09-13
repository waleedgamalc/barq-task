import json
import re
from collections import Counter

# ---------------------------------------------------------------------------
# Part 1: total lines, invalid json, duplicate ids in access.log / application.log
# ---------------------------------------------------------------------------

def analyze(fname):
    total = 0
    bad = 0
    ids = []
    with open(fname) as f:
        for line in f:
            total += 1
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                ids.append(d.get("request_id"))
            except json.JSONDecodeError:
                bad += 1
    print(f"{fname}: total_lines={total} invalid_json={bad} parsed={len(ids)} unique_ids={len(set(ids))}")

analyze("logs/access.log")
analyze("logs/application.log")


# ---------------------------------------------------------------------------
# Part 2: show examples of duplicated request_ids in application.log
# ---------------------------------------------------------------------------

app_ids = []
with open("logs/application.log") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
            app_ids.append(d.get("request_id"))
        except json.JSONDecodeError:
            pass

id_counts = Counter(app_ids)
duplicated = {k: v for k, v in id_counts.items() if v > 1}
print("Number of duplicated logs", len(duplicated))

sample_ids = list(duplicated.keys())[:3]
print("Examples:", sample_ids)

with open("logs/application.log") as f:
    for line in f:
        line = line.strip()
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if d.get("request_id") in sample_ids:
            print(line)


# ---------------------------------------------------------------------------
# Part 3: application.log, clean count of http_request vs dependency_error
# ---------------------------------------------------------------------------

seen_full_lines = set()
app_events = []

with open("logs/application.log") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        if line in seen_full_lines:
            continue  # exact duplicate line -> skip
        seen_full_lines.add(line)
        try:
            d = json.loads(line)
            app_events.append(d)
        except json.JSONDecodeError:
            continue

http_requests = [e for e in app_events if e.get("event") == "http_request"]
dep_errors = [e for e in app_events if e.get("event") == "dependency_error"]

print("total unique lines:", len(seen_full_lines))
print("http_request events:", len(http_requests))
print("dependency_error events:", len(dep_errors))
print("by instance:", Counter(e.get("instance_id") for e in http_requests))
print("by status:", Counter(e.get("status") for e in http_requests))


# ---------------------------------------------------------------------------
# Part 4: dependency_error timeline (redis vs postgres)
# ---------------------------------------------------------------------------

dep_errors_sorted = sorted(dep_errors, key=lambda e: e["timestamp"])
print("First error:", dep_errors_sorted[0]["timestamp"])
print("Last error:", dep_errors_sorted[-1]["timestamp"])
print("Number of errors:", len(dep_errors_sorted))

by_minute = Counter(e["timestamp"][:16] for e in dep_errors_sorted)  # yyyy-mm-ddThh:mm
for minute, count in sorted(by_minute.items()):
    print(minute, count)

redis_errors = [e for e in dep_errors_sorted if e.get("dependency") == "redis"]
postgres_errors = [e for e in dep_errors_sorted if e.get("dependency") == "postgres"]
print("Redis errors:", len(redis_errors), redis_errors[0]["timestamp"], "->", redis_errors[-1]["timestamp"])
print("Postgres errors:", len(postgres_errors), postgres_errors[0]["timestamp"], "->", postgres_errors[-1]["timestamp"])


# ---------------------------------------------------------------------------
# Part 5: error.log parsing (connection refused / upstream timeout)
# ---------------------------------------------------------------------------

pattern = re.compile(
    r'^(\d{4}/\d{2}/\d{2} \d{2}:\d{2}):\d{2} \[error\].*?'
    r'request_id=([\w-]+).*?request: "(\w+) ([^\s"]+)'
)

nginx_errors = []
with open("logs/error.log") as f:
    for line in f:
        m = pattern.search(line)
        if m:
            minute, req_id, method, path = m.groups()
            nginx_errors.append({"minute": minute, "request_id": req_id, "path": path})
        else:
            print("UNMATCHED LINE:", line.strip())

print("Total matched errors:", len(nginx_errors))
by_minute_nginx = Counter(e["minute"] for e in nginx_errors)
for minute, count in sorted(by_minute_nginx.items()):
    print(minute, count)

for e in nginx_errors:
    if e["minute"] in ("2026/08/20 11:05", "2026/08/20 11:25"):
        print(e)

with open("logs/error.log") as f:
    for line in f:
        if "11:05:0" in line or "11:25:" in line or "11:26:" in line:
            print(line.strip())


# ---------------------------------------------------------------------------
# Part 6: access.log status distribution, upstream IPs, specific request_ids
# ---------------------------------------------------------------------------

seen_access = set()
access_records = []
with open("logs/access.log") as f:
    for line in f:
        line = line.strip()
        if not line or line in seen_access:
            continue
        seen_access.add(line)
        try:
            d = json.loads(line)
            access_records.append(d)
        except json.JSONDecodeError:
            continue

print("Unique valid access.log records:", len(access_records))
print("Status distribution:", Counter(r.get("status") for r in access_records))

upstream_ips = Counter(r.get("upstream") for r in access_records)
print("Top upstream IPs:", upstream_ips.most_common(5))

for rid in ["lab-000122", "lab-000606"]:
    match = [r for r in access_records if r.get("request_id") == rid]
    print(rid, "->", match)


# ---------------------------------------------------------------------------
# Part 7: confirm IP-to-instance mapping (correlation between the two logs)
# ---------------------------------------------------------------------------

app_by_id = {}
with open("logs/application.log") as f:
    for line in f:
        try:
            d = json.loads(line.strip())
            if d.get("event") == "http_request":
                app_by_id[d["request_id"]] = d["instance_id"]
        except:
            continue

access_by_id = {}
with open("logs/access.log") as f:
    for line in f:
        try:
            d = json.loads(line.strip())
            access_by_id[d["request_id"]] = d.get("upstream")
        except:
            continue

common = [rid for rid in app_by_id if rid in access_by_id][:5]
for rid in common:
    print(rid, "instance:", app_by_id[rid], "upstream:", access_by_id[rid])