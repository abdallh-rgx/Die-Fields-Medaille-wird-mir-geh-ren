import json, os, glob, argparse
from datetime import datetime, timezone

def addition_chain_length(n):
    if n <= 1:
        return 0
    best = {1: 0}
    queue = [1]
    while queue and n not in best:
        curr = queue.pop(0)
        for prev in list(best.keys()):
            s = curr + prev
            if s <= n and s not in best:
                best[s] = best[curr] + 1
                queue.append(s)
    return best.get(n, n - 1)

def expression_cost(expr_str):
    if not expr_str:
        return None
    total, computed = 0, set()
    for term in expr_str.split(" * "):
        try:
            inner, b_str = term.rsplit("^", 1)
            b = int(b_str.rstrip(")"))
            a = int(inner.split("^")[1].rstrip(")"))
        except (ValueError, IndexError):
            return None
        if a not in computed:
            total += addition_chain_length(a)
            computed.add(a)
        if b > 1:
            total += b - 1
    return total

def binary_cost(k):
    return k.bit_length() - 1 + bin(k).count("1") - 1

def generate_leaderboard(best_data, sd):
    all_best = best_data["all_time_best"]
    if not all_best:
        return

    ranked = sorted(all_best.values(), key=lambda x: -x["saved_vs_binary"])[:10]
    ranked = [r for r in ranked if r["saved_vs_binary"] > 0]

    ks = sorted(int(k) for k in all_best.keys())
    max_k = max(ks)
    lines = [
        "# 🏆 Z3 Search Leaderboard",
        "",
        f"**Last updated:** {best_data.get('last_updated', 'N/A')}  ",
        f"**Total k solved:** {len(all_best)}  ",
        f"**Max k covered:** {max_k}",
        "",
        "## 🎯 Discoveries — Beat Binary Exponentiation",
        "",
    ]
    if ranked:
        lines.append("| k | Naive | Binary | Found | Saved | Expression |")
        lines.append("|---|-------|--------|-------|-------|------------|")
        for r in ranked:
            lines.append(
                f"| {r['k']} | {r['naive']} | {r['binary']} | {r['cost']} | "
                f"**+{r['saved_vs_binary']}** | `{r['expression']}` |"
            )
    else:
        lines.append("_No improvement over binary exponentiation found yet._")
    lines.append("")

    unsolved = [k for k in range(2, max_k + 1) if str(k) not in all_best]
    lines.append("## 📊 Coverage")
    lines.append("")
    lines.append(f"- k solved: **{len(all_best)}**")
    lines.append(f"- k range: 2 – {max_k}")
    lines.append(f"- gaps: {len(unsolved)}" +
                 (f" (first: {unsolved[:5]})" if unsolved else " — none"))
    lines.append("")

    lines.append("## 📋 All Results")
    lines.append("")
    lines.append("| k | Cost | vs Binary | Expression |")
    lines.append("|---|------|-----------|------------|")
    for k in ks:
        r = all_best[str(k)]
        sign = "+" if r["saved_vs_binary"] > 0 else ("=" if r["saved_vs_binary"] == 0 else "")
        lines.append(
            f"| {k} | {r['cost']} | {sign}{r['saved_vs_binary']} | `{r['expression']}` |"
        )
    open(os.path.join(sd, "LEADERBOARD.md"), "w").write("\n".join(lines))

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--state-dir", default="state")
    p.add_argument("--cycle", type=int, required=True)
    args = p.parse_args()
    sd = args.state_dir
    os.makedirs(sd, exist_ok=True)

    all_results = {}
    for f in glob.glob(os.path.join(sd, "shard-*.json")):
        shard = json.load(open(f))
        for k_str, data in shard.get("results", {}).items():
            if isinstance(data, dict):
                all_results.setdefault(int(k_str), []).extend(data.get("solutions", []))

    best_per_k = {}
    for k, sols in all_results.items():
        best, best_cost = None, float("inf")
        for s in sols:
            c = expression_cost(s)
            if c is not None and c < best_cost:
                best_cost, best = c, s
        if best is None:
            continue
        bc = binary_cost(k)
        best_per_k[str(k)] = {
            "k": k,
            "expression": best,
            "cost": best_cost,
            "naive": k - 1,
            "binary": bc,
            "saved_vs_naive": k - 1 - best_cost,
            "saved_vs_binary": bc - best_cost,
        }

    best_path = os.path.join(sd, "best.json")
    prev = json.load(open(best_path)) if os.path.exists(best_path) else {"all_time_best": {}}
    now = datetime.now(timezone.utc).isoformat()
    for k_str, data in best_per_k.items():
        old = prev["all_time_best"].get(k_str)
        if old is None or data["cost"] < old["cost"]:
            prev["all_time_best"][k_str] = data
    prev["last_updated"] = now
    prev["total_k"] = len(prev["all_time_best"])
    json.dump(prev, open(best_path, "w"), indent=2)

    generate_leaderboard(prev, sd)

    hist = os.path.join(sd, "history")
    os.makedirs(hist, exist_ok=True)
    json.dump({
        "cycle": args.cycle,
        "timestamp": now,
        "total_k": len(prev["all_time_best"]),
        "best": prev["all_time_best"],
    }, open(os.path.join(hist, f"cycle-{args.cycle:06d}.json"), "w"), indent=2)

if __name__ == "__main__":
    main()
