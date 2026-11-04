import os, sys, json, time, signal, argparse
from datetime import datetime, timezone
import z3

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--shard", type=int, required=True)
    p.add_argument("--total-shards", type=int, required=True)
    p.add_argument("--cycle", type=int, required=True)
    p.add_argument("--state-dir", default="state")
    p.add_argument("--time-budget", type=int, default=17400)
    return p.parse_args()

def solve_task(k, mul_max, timeout_ms):
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

def main():
    args = parse_args()
    state_dir = args.state_dir
    os.makedirs(state_dir, exist_ok=True)
    shard_path = os.path.join(state_dir, f"shard-{args.shard}.json")

    if os.path.exists(shard_path):
        state = json.load(open(shard_path))
    else:
        state = {"shard_id": args.shard, "completed": {}, "results": {}, "errors": []}

    k_max = 16 + args.cycle * 2
    mul_max = 3 + args.cycle // 3
    my_ks = [k for k in range(2, k_max + 1)
             if k % args.total_shards == args.shard]

    start = time.time()
    shutdown = {"flag": False}

    def on_sigterm(signum, frame):
        shutdown["flag"] = True

    signal.signal(signal.SIGTERM, on_sigterm)
    signal.signal(signal.SIGINT, on_sigterm)

    def elapsed():
        return time.time() - start

    def remaining():
        return args.time_budget - elapsed()

    for k in my_ks:
        if shutdown["flag"]:
            break
        if remaining() < 60:
            break
        if state["completed"].get(str(k), -1) >= mul_max:
            continue

        task_timeout = min(120_000, int(remaining() * 1000) - 5_000)
        if task_timeout < 10_000:
            break

        try:
            sols = solve_task(k, mul_max, task_timeout)
            state["results"][str(k)] = {
                "k": k,
                "mul_max": mul_max,
                "solutions": sols,
                "duration_s": round(elapsed(), 1),
            }
            state["completed"][str(k)] = mul_max
            print(f"shard {args.shard}: k={k} -> {len(sols)} solutions", flush=True)
        except Exception as e:
            state["errors"].append(f"k={k}: {e}")

    state["last_run"] = datetime.now(timezone.utc).isoformat()
    state["bounds"] = {"k_max": k_max, "mul_max": mul_max, "cycle": args.cycle}
    json.dump(state, open(shard_path, "w"), indent=2)
    print(f"shard {args.shard}: completed {len(state['completed'])} k values", flush=True)

if __name__ == "__main__":
    main()
