#!/usr/bin/env python3

# failure_test.py



import json
import os
import sys
import subprocess
import time
import urllib.request
import urllib.error

BASE_URL = f"http://localhost:{os.environ.get('PUBLIC_PORT', '8080')}"
MAX_WAIT = 30
SLEEP_INTERVAL = 2
REQUESTS_PER_PHASE = 10

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


def docker_compose(*args):
    result = subprocess.run(
        ["docker", "compose", *args],
        capture_output=True, text=True, timeout=30,
    )
    return result.returncode, result.stdout, result.stderr


def send_traffic(label, count):
    """Send `count` requests to /instance and return (successes, failures, instances_seen)."""
    successes = 0
    failures = 0
    seen = set()
    for _ in range(count):
        status, body = http_get("/instance")
        if status == 200:
            successes += 1
            try:
                data = json.loads(body)
                seen.add(data.get("instance_id"))
            except json.JSONDecodeError:
                pass
        else:
            failures += 1
        time.sleep(0.2)
    print(f"[{label}] {count} requests -> {successes} succeeded, {failures} failed, "
          f"instances seen: {seen or 'none'}")
    return successes, failures, seen


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


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("app-01", "app-02"):
        print("Usage: python3 failure_test.py <app-01|app-02>")
        sys.exit(2)

    target = sys.argv[1]
    other = "app-02" if target == "app-01" else "app-01"

    print(f"== Baseline: traffic before stopping {target} ==")
    base_ok, base_fail, base_seen = send_traffic("baseline", REQUESTS_PER_PHASE)
    if target in base_seen and other in base_seen:
        ok(f"Baseline load balancing confirmed (saw both {target} and {other})")
    else:
        bad(f"Baseline did not see both backends (seen: {base_seen})")

    print(f"\n== Stopping {target} ==")
    rc, out, err = docker_compose("stop", target)
    if rc == 0:
        ok(f"docker compose stop {target} succeeded")
    else:
        bad(f"docker compose stop {target} failed: {err.strip()}")
        sys.exit(1)

    print(f"\n== Traffic during failure (only {other} should serve requests) ==")
    fail_ok, fail_fail, fail_seen = send_traffic("during-failure", REQUESTS_PER_PHASE)

    if other in fail_seen and target not in fail_seen:
        ok(f"Only {other} served requests while {target} was stopped")
    else:
        bad(f"Unexpected instances seen during failure: {fail_seen}")

    if fail_ok > 0:
        ok(f"Service remained available during failure ({fail_ok}/{REQUESTS_PER_PHASE} succeeded)")
    else:
        bad("Service did not remain available during failure (0 successful requests)")

    print(f"\n== Restoring {target} ==")
    rc, out, err = docker_compose("start", target)
    if rc == 0:
        ok(f"docker compose start {target} succeeded")
    else:
        bad(f"docker compose start {target} failed: {err.strip()}")
        sys.exit(1)

    wait_for_condition(
        f"{target} becomes healthy again",
        lambda: target in docker_compose("ps", target)[1] and "healthy" in docker_compose("ps", target)[1],
    )

    print(f"\n== Traffic after recovery (both backends should serve again) ==")
    recovered = False
    waited = 0
    recovery_seen = set()
    while waited < MAX_WAIT:
        _, _, recovery_seen = send_traffic("after-recovery", REQUESTS_PER_PHASE)
        if target in recovery_seen and other in recovery_seen:
            recovered = True
            break
        time.sleep(SLEEP_INTERVAL)
        waited += SLEEP_INTERVAL

    if recovered:
        ok(f"{target} is serving requests again alongside {other} (recovery confirmed)")
    else:
        bad(f"{target} did not resume serving requests within {MAX_WAIT}s "
            f"(seen: {recovery_seen})")

    print("\n======================================")
    print(f"Baseline:        {base_ok}/{REQUESTS_PER_PHASE} ok, saw {base_seen}")
    print(f"During failure:  {fail_ok}/{REQUESTS_PER_PHASE} ok, saw {fail_seen}")
    print(f"After recovery:  saw {recovery_seen}")

    if fail_count == 0:
        print("RESULT: FAILURE TEST PASSED")
        sys.exit(0)
    else:
        print(f"RESULT: {fail_count} CHECK(S) FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()