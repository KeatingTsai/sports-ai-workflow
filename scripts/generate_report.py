# -*- coding: utf-8 -*-
"""
工作流第 3 步:把结构化数据 + 异动 flag 喂给 LLM,生成运营日报。

两种运行模式,自动切换:
  1. 有 ANTHROPIC_API_KEY -> 真打 Claude API(默认 claude-sonnet-4-6,够写日报又便宜)
  2. 没 key -> 走离线模板渲染 fallback,保证 clone 即跑、可演示

提示词不写死在代码里,从 templates/prompt_日报生成.md 读,
口径(无 emoji / RTP 思维 / 异动转风控)集中在模板,运营可自行改。

输入: data/odds_snapshots_<date>.json + data/anomalies_<date>.json
输出: data/report_<date>.md
"""
import sys, os, json, argparse
from collections import defaultdict

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "..", "data")
TPL_DIR = os.path.join(HERE, "..", "templates")
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")


def aggregate(matches):
    by_sport = defaultdict(lambda: {"handle": 0.0, "bets": 0, "matches": 0})
    total_handle = 0.0
    total_bets = 0
    for m in matches:
        s = by_sport[m["sport"]]
        s["handle"] += m["handle_usdt"]
        s["bets"] += m["bet_count"]
        s["matches"] += 1
        total_handle += m["handle_usdt"]
        total_bets += m["bet_count"]
    return {
        "total_handle": round(total_handle, 2),
        "total_bets": total_bets,
        "match_count": len(matches),
        "by_sport": {k: {"handle": round(v["handle"], 2), "bets": v["bets"],
                         "matches": v["matches"]} for k, v in by_sport.items()},
    }


def build_prompt(date, agg, anomalies):
    tpl_path = os.path.join(TPL_DIR, "prompt_日报生成.md")
    with open(tpl_path, encoding="utf-8") as f:
        tpl = f.read()
    payload = {
        "date": date,
        "summary": agg,
        "anomalies": anomalies,
    }
    return tpl.replace("{{DATA_JSON}}", json.dumps(payload, ensure_ascii=False, indent=2))


def call_claude(prompt):
    """有 key 才走;用标准库 urllib,不引第三方。失败回 None 让上层 fallback。"""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    import urllib.request
    body = json.dumps({
        "model": MODEL,
        "max_tokens": 2000,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=body,
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        })
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return "".join(b.get("text", "") for b in data.get("content", []))
    except Exception as e:
        print("[warn] Claude API 调用失败, 退回离线模板: {}".format(e))
        return None


def offline_render(date, agg, anomalies):
    """无 key 时的确定性日报渲染:结构与 LLM 版一致,方便离线演示与对照。"""
    L = []
    L.append("# 体育数据运营日报 — {}".format(date))
    L.append("")
    L.append("## 一、今日大盘摘要")
    L.append("- 覆盖赛事 {} 场,总投注额 {:,.0f} USDT,总投注 {:,} 笔。".format(
        agg["match_count"], agg["total_handle"], agg["total_bets"]))
    top_sport = max(agg["by_sport"].items(), key=lambda kv: kv[1]["handle"])
    L.append("- 投注额最高品类:{},贡献 {:,.0f} USDT。".format(top_sport[0], top_sport[1]["handle"]))
    L.append("- 异动盘口 {} 个,其中高优先 {} 个,已按严重度排序待核。".format(
        len(anomalies), sum(1 for a in anomalies if a["top_severity"] == "high")))
    L.append("")
    L.append("## 二、分品类表现")
    L.append("| 品类 | 赛事数 | 投注额 USDT | 投注笔数 |")
    L.append("|---|---|---|---|")
    for sp, v in sorted(agg["by_sport"].items(), key=lambda kv: -kv[1]["handle"]):
        L.append("| {} | {} | {:,.0f} | {:,} |".format(sp, v["matches"], v["handle"], v["bets"]))
    L.append("")
    L.append("## 三、赔率异动 / 可疑盘口预警")
    if not anomalies:
        L.append("今日无触发规则的异动盘口。")
    else:
        sev_cn = {"high": "高", "mid": "中", "low": "低"}
        for a in anomalies:
            L.append("### [{}] {} {} — {}".format(
                sev_cn[a["top_severity"]], a["sport"], a["league"], a["match"]))
            L.append("- 开赛 {} · 投注额 {:,.0f} USDT".format(a["start_time"], a["handle_usdt"]))
            for fl in a["flags"]:
                L.append("  - {}({}):{}".format(fl["rule"], sev_cn[fl["severity"]], fl["reason"]))
            L.append("")
    L.append("## 四、风控关注与建议")
    high = [a for a in anomalies if a["top_severity"] == "high"]
    if high:
        L.append("- {} 个高优先盘口建议即时复核:{}。".format(
            len(high), "、".join(a["match"] for a in high[:5])))
        L.append("- 含 R2 反向线动 / R5 少笔大额者,转风控核查关联账号与资金来源。")
    else:
        L.append("- 今日无高优先风险盘口,常规监控即可。")
    L.append("")
    L.append("> 本报告由 AI 工作流自动生成(离线模板模式)。配置 ANTHROPIC_API_KEY 后切换为 Claude 撰写的自然语言叙述版。")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="2026-06-11")
    args = ap.parse_args()

    with open(os.path.join(DATA_DIR, "odds_snapshots_{}.json".format(args.date)), encoding="utf-8") as f:
        snap = json.load(f)
    with open(os.path.join(DATA_DIR, "anomalies_{}.json".format(args.date)), encoding="utf-8") as f:
        anom = json.load(f)

    agg = aggregate(snap["matches"])
    prompt = build_prompt(args.date, agg, anom["anomalies"])

    report = call_claude(prompt)
    mode = "Claude API ({})".format(MODEL)
    if report is None:
        report = offline_render(args.date, agg, anom["anomalies"])
        mode = "离线模板"

    out = os.path.join(DATA_DIR, "report_{}.md".format(args.date))
    with open(out, "w", encoding="utf-8") as f:
        f.write(report)
    print("[report] 模式={} -> {}".format(mode, os.path.relpath(out, HERE)))


if __name__ == "__main__":
    main()
