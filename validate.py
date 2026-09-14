#!/usr/bin/env python3
"""
validate.py

Checks the running environment and prints PASS/FAIL for each check.
Exits with a non-zero status if any check fails.
"""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import urllib.error

BASE_URL = f"http://localhost:{os.environ.get('PUBLIC_PORT', '8080')}"
MAX_WAIT = 30
SLEEP_INTERVAL = 2

fail_count = 0


def ok(msg):
    print(f"PASS: {msg}")


def bad(msg):
    global fail_count
    print(f"FAIL: {msg}")
    fail_count += 1


def http_get(path, timeout=3):
    
    url = f"{BASE_URL}{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception:
        return None, None


def wait_for_condition(description, check_fn):
    
    waited = 0
    while waited < MAX_WAIT:
        if check_fn():
            ok(f"{description} (after {waited}s)")
            return True
        time.sleep(SLEEP_INTERVAL)
        waited += SLEEP_INTERVAL
    bad(f"{description} (timed out after {MAX_WAIT}s)")
    return False


def check_endpoint(path, expected_status):
    status, _ = http_get(path)
    if status == expected_status:
        ok(f"GET {path} -> {status}")
    else:
        bad(f"GET {path} -> got {status}, expected {expected_status}")


def check_port_closed(port, name):
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    try:
        result = sock.connect_ex(("127.0.0.1", port))
        if result == 0:
            bad(f"{name} port {port} is reachable from host (should NOT be published)")
        else:
            ok(f"{name} port {port} is not reachable from host")
    finally:
        sock.close()


def main():
    print("== 1. Public access on NGINX ==")
    wait_for_condition(
        f"NGINX responds on {BASE_URL}/",
        lambda: http_get("/")[0] == 200,
    )

    print("\n== 2. Required endpoints return expected status ==")
    check_endpoint("/", 200)
    check_endpoint("/health", 200)
    check_endpoint("/instance", 200)
    check_endpoint("/records", 200)
    check_endpoint("/counter", 200)

    print("\n== 3. Dependency readiness (/ready must report postgres+redis ready) ==")
    wait_for_condition(
        "/ready returns 200 (postgres+redis ready)",
        lambda: http_get("/ready")[0] == 200,
    )

    status, body = http_get("/ready")
    try:
        data = json.loads(body) if body else {}
    except json.JSONDecodeError:
        data = {}
    deps = data.get("dependencies", {})
    if deps.get("postgres") == "ready" and deps.get("redis") == "ready":
        ok("/ready body reports both dependencies ready")
    else:
        bad(f"/ready body does not report both dependencies ready: {body}")

    print("\n== 4. Both backends serve traffic through NGINX (load balancing) ==")
    seen = set()
    for _ in range(8):
        _, body = http_get("/instance")
        try:
            data = json.loads(body) if body else {}
            seen.add(data.get("instance_id"))
        except json.JSONDecodeError:
            continue

    if "app-01" in seen and "app-02" in seen:
        ok("Both app-01 and app-02 served requests through NGINX")
    else:
        bad(f"Did not see both backends respond (seen: {seen})")

    print("\n== 5. Prohibited host ports (postgres, redis must NOT be reachable from host) ==")
    check_port_closed(5432, "postgres")
    check_port_closed(6379, "redis")

    print("\n== 6. Only NGINX's public port is exposed ==")
    try:
        result = subprocess.run(
            ["docker", "compose", "ps", "--format", "{{.Service}} {{.Ports}}"],
            capture_output=True, text=True, timeout=10,
        )
        print(result.stdout.strip())
        bad_lines = [
            line for line in result.stdout.splitlines()
            if not line.startswith("nginx") and ("0.0.0.0" in line or "127.0.0.1" in line)
        ]
        if not bad_lines:
            ok("No non-nginx service publishes a host port")
        else:
            bad("A non-nginx service publishes a host port")
    except Exception as e:
        bad(f"Could not check docker compose ports: {e}")

    print("\n======================================")
    if fail_count == 0:
        print("RESULT: ALL CHECKS PASSED")
        sys.exit(0)
    else:
        print(f"RESULT: {fail_count} CHECK(S) FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()