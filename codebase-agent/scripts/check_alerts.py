"""检查服务指标，异常时以非零码退出（可配合 cron / CI / 计划任务）。

用法：
    python scripts/check_alerts.py
    python scripts/check_alerts.py --url http://127.0.0.1:8000 --days 1
"""

import argparse
import json
import sys
import urllib.request


def fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.load(resp)


def main() -> None:
    ap = argparse.ArgumentParser(description="CodeBase Agent 指标告警检查")
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--days", type=int, default=1)
    ap.add_argument("--min-success", type=float, default=0.95)
    ap.add_argument("--max-p95-ms", type=float, default=30000)
    ap.add_argument("--min-good-rate", type=float, default=0.8)
    ap.add_argument("--min-feedback", type=int, default=5,
                    help="反馈数达到该值才检查好评率")
    ap.add_argument("--max-fallback-rate", type=float, default=0.2,
                    help="降级回答占比上限")
    args = ap.parse_args()

    m = fetch_json(f"{args.url}/metrics/summary?days={args.days}")
    problems = []

    if m.get("queries") and m.get("success_rate") is not None and m["success_rate"] < args.min_success:
        problems.append(f"成功率 {m['success_rate']:.0%} < {args.min_success:.0%}")

    if m.get("latency_p95_ms") is not None and m["latency_p95_ms"] > args.max_p95_ms:
        problems.append(f"P95 延迟 {m['latency_p95_ms']}ms > {args.max_p95_ms}ms")

    feedback_total = (m.get("feedback_up") or 0) + (m.get("feedback_down") or 0)
    if feedback_total >= args.min_feedback and m.get("feedback_good_rate") is not None \
            and m["feedback_good_rate"] < args.min_good_rate:
        problems.append(f"好评率 {m['feedback_good_rate']:.0%} < {args.min_good_rate:.0%}")

    if m.get("budget_used_pct") is not None and m["budget_used_pct"] >= 1.0:
        problems.append(f"成本已超预算 ({m['budget_used_pct']:.0%})")

    fallback_rate = (m.get("fallbacks") or 0) / m["queries"] if m.get("queries") else 0
    if fallback_rate > args.max_fallback_rate:
        problems.append(f"降级率 {fallback_rate:.0%} > {args.max_fallback_rate:.0%}")

    summary = (
        f"queries={m.get('queries')} success={m.get('success_rate')} "
        f"p95={m.get('latency_p95_ms')}ms llm_errors={m.get('llm_errors')} "
        f"fallbacks={m.get('fallbacks')} cost={m.get('cost_total')} "
        f"feedback={m.get('feedback_up')}/{m.get('feedback_down')}"
    )

    if problems:
        for problem in problems:
            print(f"ALERT: {problem}")
        print(summary)
        sys.exit(1)

    print(f"OK: {summary}")


if __name__ == "__main__":
    main()