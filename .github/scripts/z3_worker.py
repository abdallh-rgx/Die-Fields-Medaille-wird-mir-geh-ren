import os, sys, json, time, signal, subprocess, random
from datetime import datetime, timezone
import z3

STATE_DIR   = os.environ.get("STATE_DIR", "state")
TIME_BUDGET = int(os.environ.get("TIME_BUDGET", "17400"))
CHECKPOINT  = int(os.environ.get("CHECKPOINT", "1080"))
CYCLE       = os.environ.get("CYCLE", "0")
REPO        = os.environ.get("REPO", "")
GH_TOKEN    = os.environ.get("GH_TOKEN", "")

os.makedirs(STATE_DIR, exist_ok=True)
START = time.time()
SHUTDOWN = {"flag": False}

def on_sigterm(signum, frame):
    SHUTDOWN["flag"] = True

signal.signal(signal.SIGTERM, on_sigterm)
signal.signal(signal.SIGINT, on_sigterm)

def elapsed() -> float:
    return time.time() - START

def remaining() -> float:
    return TIME_BUDGET - elapsed()

def load_state() -> dict:
    path = os.path.join(STATE_DIR, "worker.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"cycle": int(CYCLE), "completed": {}, "results": {}, "errors": []}

def save_state(state: dict) -> None:
    state["last_saved"] = datetime.now(timezone.utc).isoformat()
    state["cycle"] = int(CYCLE)
    state["elapsed_seconds"] = int(elapsed())
    path = os.path.join(STATE_DIR, "worker.json")
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, path)

def git_commit_and_push(msg: str) -> bool:
    try:
        subprocess.run(["git", "add", "state/"], check=True, capture_output=True, timeout=60)
        diff = subprocess.run(["git", "diff", "--cached", "--quiet"], capture_output=True)
        if diff.returncode == 0:
            return True
        subprocess.run(["git", "commit", "-m", msg + " [skip ci]"], check=True, capture_output=True, timeout=60)
        for attempt in range(5):
            r = subprocess.run(["git", "push", "origin", "HEAD:state"], capture_output=True, timeout=120)
            if r.returncode == 0:
                return True
            subprocess.run(["git", "fetch", "origin", "state"], capture_output=True, timeout=60)
            subprocess.run(["git", "rebase", "origin/state"], capture_output=True, timeout=60)
            time.sleep(random.uniform(2, 8))
        return False
    except Exception:
        return False

def solve_task(k: int, mul_max: int, timeout_ms: int) -> list:
    solver = z3.Solver()
    solver.set("timeout", timeout_ms)
    n = mul_max
    a = [z3.Int(f"a_{i}") for i in range(n)]
    b = [z3.Int(f"b_{i}") for i in range(n)]
    for i in range(n):
        solver.add(a[i] >= 1, a[i] <= k - 1)
        solver.add(b[i] >= 0, b[i] <= mul_max)
    solver.add(z3.Sum([a[i] * b[i] for i in range(n)]) == k)
    solver.add(z3.Sum(b) <= mul_max)

    sols = []
    while solver.check() == z3.sat:
        m = solver.model()
        expr = []
        for i in range(n):
            ai, bi = m[a[i]].as_long(), m[b[i]].as_long()
            if bi > 0:
                expr.append(f"(z^{ai})^{bi}")
        sols.append(" * ".join(expr))
        solver.add(z3.Or(
            [a[i] != m[a[i]].as_long() for i in range(n)] +
            [b[i] != m[b[i]].as_long() for i in range(n)]))
        if len(sols) > 300:
            break
    return sols

def next_task(state: dict, k_max: int, mul_max: int) -> tuple:
    for k in range(2, k_max + 1):
        searched_at = state["completed"].get(str(k), -1)
        if searched_at < mul_max:
            return (k, mul_max)
    return (k_max + 2, mul_max)

def main():
    state = load_state()
    last_commit = time.time()

    while not SHUTDOWN["flag"]:
        if remaining() < 60:
            break

        if time.time() - last_commit >= CHECKPOINT:
            save_state(state)
            git_commit_and_push(f"cycle {CYCLE}: checkpoint")
            last_commit = time.time()

        try:
            cycle_int = int(CYCLE)
            k_max = 16 + cycle_int * 2
            mul_max = 3 + cycle_int // 3
            k, mul = next_task(state, k_max, mul_max)
        except Exception as e:
            state["errors"].append(f"next_task: {e}")
            time.sleep(5)
            continue

        task_timeout = min(120_000, int(remaining() * 1000) - 5_000)
        if task_timeout < 10_000:
            break

        try:
            sols = solve_task(k, mul, timeout_ms=task_timeout)
            state["results"][str(k)] = {
                "k": k, "mul_max": mul,
                "solutions": sols,
                "duration_s": round(time.time() - last_commit, 1),
            }
            state["completed"][str(k)] = mul
        except Exception as e:
            state["errors"].append(f"k={k}: {e}")

    save_state(state)
    git_commit_and_push(f"cycle {CYCLE}: final")
    sys.exit(0)

if __name__ == "__main__":
    main()
