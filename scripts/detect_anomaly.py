# -*- coding: utf-8 -*-
"""
工作流第 2 步:赔率异动 / 可疑盘口规则引擎。

为什么规则在前、AI 在后:
明确能量化的违规(赔率急跌、反向线动、投注集中)用规则抓,
稳定、可解释、零成本;规则抓不到的语义判断才交给 LLM 解读。
这是《数据产品经理》质检系统「规则兜底 + 模型补语义」的同一套思路。

每条规则输出一个 flag dict,带:类型 / 严重度 / 触发值 / 一句话理由。
后续 LLM 只负责把这些 flag 翻成运营听得懂的话,不负责判定「有没有异常」。

输入: data/odds_snapshots_<date>.json
输出: data/anomalies_<date>.json
"""
import sys, os, json, argparse

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "..", "data")

# 规则阈值集中放这里,运营可直接改,不用动代码逻辑
THRESHOLDS = {
    "steam_drop_pct": 0.15,        # 主队赔率较开盘下跌 >15% = 资金急涌(steam move)
    "reverse_line_gap": 0.10,      # 投注压一边 >65% 但该边赔率反向上升 = 反向线动
    "handle_concentration": 0.80,  # 单盘口主/客投注占比 >80% = 投注高度集中
    "big_handle_usdt": 120_000,    # 单场投注额 >12 万 USDT = 大额关注
    "low_count_high_handle": 200,  # 投注额大但笔数 < 200 = 少数账号大额(疑大户/对打)
}

SEVERITY_ORDER = {"high": 0, "mid": 1, "low": 2}


def pct_change(old, new):
    if not old:
        return 0.0
    return (new - old) / old


def detect(match, th):
    flags = []
    op, cu = match["opening"], match["current"]
    home_drop = pct_change(op["home"], cu["home"])     # 负值 = 下跌
    away_drop = pct_change(op["away"], cu["away"])
    hp = match["handle_home_pct"]
    handle = match["handle_usdt"]
    cnt = match["bet_count"]

    # R1 赔率急跌(steam move)
    if home_drop <= -th["steam_drop_pct"] or away_drop <= -th["steam_drop_pct"]:
        side = "主胜" if home_drop <= away_drop else "客胜"
        drop = min(home_drop, away_drop)
        flags.append({
            "rule": "R1_赔率急跌",
            "severity": "high",
            "side": side,
            "value": round(drop * 100, 1),
            "reason": "{}赔率较开盘下跌 {:.1f}%,资金短时急涌,留意内幕/操盘".format(side, abs(drop) * 100),
        })

    # R2 反向线动(钱压主队,主队赔率却反升)
    if hp >= 0.65 and home_drop >= th["reverse_line_gap"]:
        flags.append({
            "rule": "R2_反向线动",
            "severity": "high",
            "side": "主胜",
            "value": round(home_drop * 100, 1),
            "reason": "{:.0f}% 投注额压主队,主队赔率反升 {:.1f}%,疑 sharp money 在另一边".format(hp * 100, home_drop * 100),
        })

    # R3 投注高度集中
    conc = max(hp, 1 - hp)
    if conc >= th["handle_concentration"]:
        flags.append({
            "rule": "R3_投注集中",
            "severity": "mid",
            "side": "主胜" if hp >= 0.5 else "客胜",
            "value": round(conc * 100, 1),
            "reason": "单边投注占比 {:.0f}%,盘口风险敞口集中".format(conc * 100),
        })

    # R4 大额关注
    if handle >= th["big_handle_usdt"]:
        flags.append({
            "rule": "R4_大额盘口",
            "severity": "mid",
            "side": "-",
            "value": round(handle, 0),
            "reason": "单场投注额 {:,.0f} USDT,超大额关注线".format(handle),
        })

    # R5 少数账号大额(疑大户对打 / 业务安全)
    if handle >= th["big_handle_usdt"] * 0.5 and cnt < th["low_count_high_handle"]:
        flags.append({
            "rule": "R5_少笔大额",
            "severity": "high",
            "side": "-",
            "value": cnt,
            "reason": "投注额 {:,.0f} USDT 仅 {} 笔,人均极高,疑大户或对打,转风控核查".format(handle, cnt),
        })

    return flags


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="2026-06-11")
    args = ap.parse_args()

    src = os.path.join(DATA_DIR, "odds_snapshots_{}.json".format(args.date))
    with open(src, encoding="utf-8") as f:
        snap = json.load(f)

    th = THRESHOLDS
    results = []
    for m in snap["matches"]:
        flags = detect(m, th)
        if flags:
            top = min(flags, key=lambda x: SEVERITY_ORDER[x["severity"]])
            results.append({
                "match_id": m["match_id"],
                "sport": m["sport"],
                "league": m["league"],
                "match": "{} vs {}".format(m["home"], m["away"]),
                "start_time": m["start_time"],
                "handle_usdt": m["handle_usdt"],
                "top_severity": top["severity"],
                "flags": flags,
            })

    results.sort(key=lambda r: (SEVERITY_ORDER[r["top_severity"]], -r["handle_usdt"]))
    out = os.path.join(DATA_DIR, "anomalies_{}.json".format(args.date))
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"date": args.date, "thresholds": th, "anomalies": results},
                  f, ensure_ascii=False, indent=2)

    n_high = sum(1 for r in results if r["top_severity"] == "high")
    print("[detect] 命中 {} 个盘口异动 (high {}) -> {}".format(
        len(results), n_high, os.path.relpath(out, HERE)))


if __name__ == "__main__":
    main()
