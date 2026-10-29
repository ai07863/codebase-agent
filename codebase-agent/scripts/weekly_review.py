#!/usr/bin/env python
"""Shadow-mode weekly review: metrics + bad cases from history.db.

Usage:
    python scripts/weekly_review.py --days 7
    python scripts/weekly_review.py --days 7 --out reports/week.md
"""
import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _percentile(sorted_vals, p):
    if not sorted_vals:
        return None
    i = min(len(sorted_vals) - 1, int(round((len(sorted_vals) - 1) * p)))
    return sorted_vals[i]


def _pct(num, total):
    return "-" if not total else f"{num / total * 100:.0f}%"


def _pct_str(v):
    return "-" if v is None else f"{v * 100:.0f}%"


def _fmt(v, suffix=""):
    return "-" if v is None else f"{v}{suffix}"


def _load(db_path, days):
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        traces = [dict(r) for r in con.execute(
            "SELECT * FROM query_traces WHERE ts >= ? ORDER BY id", (since,))]
        fbs = [dict(r) for r in con.execute(
            "SELECT * FROM answer_feedback WHERE ts >= ? ORDER BY id", (since,))]
    finally:
        con.close()
    return traces, fbs


def _files(raw, n=3):
    try:
        items = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    out = []
    for it in items[:n]:
        if isinstance(it, dict):
            out.append(str(it.get("file_path") or it.get("name") or "?"))
        else:
            out.append(str(it))
    return out


def build_report(traces, fbs, days):
    n = len(traces)
    lat = sorted(t["llm_latency_ms"] for t in traces if t.get("llm_latency_ms") is not None)
    errors = sum(1 for t in traces if not t.get("llm_ok"))
    fallbacks = sum(1 for t in traces if t.get("fallback"))
    cached = sum(1 for t in traces if t.get("cached"))
    cost = sum(t.get("cost_est") or 0 for t in traces)
    ctx = [t["context_tokens_est"] for t in traces if t.get("context_tokens_est") is not None]
    routes = {}
    for t in traces:
        k = t.get("route") or "unknown"
        routes[k] = routes.get(k, 0) + 1
    up = sum(1 for f in fbs if (f.get("rating") or 0) > 0)
    down = sum(1 for f in fbs if (f.get("rating") or 0) < 0)
    good = (up / (up + down)) if (up + down) else None

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    lines = [f"# 影子模式周报（近 {days} 天）", "",
             f"时间范围：{start:%Y-%m-%d} ~ {end:%Y-%m-%d}", "", "## 指标", "",
             "| 指标 | 值 |", "|---|---|",
             f"| 查询数 | {n} |",
             f"| 成功数 / 成功率 | {n - errors} / {_pct(n - errors, n)} |",
             f"| 缓存命中 | {cached} |",
             f"| LLM 错误 | {errors} |",
             f"| 降级回答 | {fallbacks} |",
             f"| 延迟 P50 / P95 (ms) | {_fmt(_percentile(lat, 0.5))} / {_fmt(_percentile(lat, 0.95))} |",
             f"| 平均上下文 token | {_fmt(round(sum(ctx) / len(ctx)) if ctx else None)} |",
             f"| 估算成本 (USD) | {cost:.4f} |",
             f"| 好评 / 差评 | {up} / {down} |",
             f"| 好评率 | {_pct_str(good)} |",
             f"| 路由分布 | {', '.join(f'{k}:{v}' for k, v in sorted(routes.items())) or '-'} |"]

    index = {}
    for t in traces:
        index[(t.get("conversation_id"), t.get("question"))] = t

    bad = [f for f in fbs if (f.get("rating") or 0) < 0]
    lines += ["", f"## 坏例（👎 {len(bad)} 条）", ""]
    if not bad:
        lines.append("本周没有差评。")
    for f in bad:
        t = index.get((f.get("conversation_id"), f.get("question"))) or {}
        files = _files(t.get("retrieved"))
        lines.append(f"- **{f.get('question') or '(无问题)'}**")
        lines.append(f"  - 仓库 `{f.get('repo') or t.get('repo') or '-'}`，时间 {f.get('ts')}")
        lines.append(
            f"  - 路由 `{t.get('route') or '-'}`，延迟 {_fmt(t.get('llm_latency_ms'))} ms，"
            f"降级 {'是' if t.get('fallback') else '否'}"
        )
        lines.append(f"  - 召回：{', '.join(files) if files else '-'}")
        if f.get("comment"):
            lines.append(f"  - 备注：{f.get('comment')}")

    failed = [t for t in traces if not t.get("llm_ok") or t.get("fallback")]
    lines += ["", f"## 失败 / 降级（{len(failed)} 条）", ""]
    if not failed:
        lines.append("本周没有失败或降级。")
    for t in failed[:10]:
        reason = t.get("llm_error") or ("降级返回" if t.get("fallback") else "-")
        lines.append(f"- {t.get('question') or '(无问题)'} — `{reason}`")

    slow = sorted((t for t in traces if t.get("llm_latency_ms") is not None),
                  key=lambda t: t["llm_latency_ms"], reverse=True)[:5]
    lines += ["", "## 最慢 5 条", ""]
    if not slow:
        lines.append("本周没有耗时记录。")
    for t in slow:
        lines.append(f"- {t['llm_latency_ms']} ms — {t.get('question') or '(无问题)'}")

    lines += ["", "## 下周只改一件事", "", "- （填写）", ""]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Shadow-mode weekly review from history.db")
    ap.add_argument("--db", default=os.getenv("HISTORY_DB", "./data/history.db"))
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    if not Path(args.db).exists():
        print(f"找不到数据库：{args.db}", file=sys.stderr)
        return 1
    try:
        traces, fbs = _load(args.db, args.days)
    except sqlite3.OperationalError as exc:
        print(f"数据库缺少表（先运行一次服务生成）：{exc}", file=sys.stderr)
        return 1
    text = build_report(traces, fbs, args.days)
    print(text)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"\n已写入 {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())