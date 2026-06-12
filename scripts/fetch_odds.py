# -*- coding: utf-8 -*-
"""
工作流第 1 步:拉取体育赛事赔率 + 投注分布快照。

真实环境里这一步是打盘口商 / 自家交易后台的 API;
这里用「确定性 mock provider」(固定 seed,按日期可复现)模拟,
让整条工作流 clone 即跑、无需任何凭证或网络。

要接真数据:把 fetch_snapshots() 换成真实 HTTP 调用,
保持返回结构(match dict 列表)不变即可,后续两步不用改。

输出: data/odds_snapshots_<date>.json
"""
import sys, os, json, random, argparse
from datetime import datetime, timedelta

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "..", "data")

# 盘口池:体育 / 联赛 / 对阵(够真实即可,非实战数据)
FIXTURES = [
    ("足球", "英超", "Arsenal", "Chelsea"),
    ("足球", "英超", "Man City", "Liverpool"),
    ("足球", "西甲", "Real Madrid", "Sevilla"),
    ("足球", "意甲", "Inter", "Napoli"),
    ("足球", "德甲", "Bayern", "Dortmund"),
    ("足球", "法甲", "PSG", "Monaco"),
    ("篮球", "NBA", "Lakers", "Celtics"),
    ("篮球", "NBA", "Warriors", "Nuggets"),
    ("篮球", "NBA", "Bucks", "Heat"),
    ("篮球", "欧篮", "Real Madrid", "Barcelona"),
    ("网球", "ATP", "Alcaraz", "Sinner"),
    ("网球", "ATP", "Djokovic", "Zverev"),
    ("电竞", "LOL-LPL", "JDG", "BLG"),
    ("电竞", "LOL-LPL", "TES", "WBG"),
    ("电竞", "CS2", "NAVI", "Vitality"),
    ("电竞", "Dota2", "Spirit", "Falcons"),
    ("足球", "英冠", "Leeds", "Norwich"),
    ("篮球", "CBA", "Liaoning", "Zhejiang"),
    ("网球", "WTA", "Swiatek", "Sabalenka"),
    ("电竞", "Valorant", "EDG", "T1"),
]


def _seed_for(date_str):
    # 用日期做 seed,同一天结果稳定可复现
    return int(date_str.replace("-", ""))


def fetch_snapshots(date_str):
    """模拟「开盘 + 临场」两次快照。返回 match dict 列表。"""
    rng = random.Random(_seed_for(date_str))
    base_day = datetime.strptime(date_str, "%Y-%m-%d")
    matches = []
    for i, (sport, league, home, away) in enumerate(FIXTURES):
        mid = "M{:04d}".format(i + 1)
        start = base_day + timedelta(hours=rng.randint(12, 23), minutes=rng.choice([0, 15, 30, 45]))

        # 开盘 1X2 赔率(隐含概率归一前)
        o_home = round(rng.uniform(1.5, 3.6), 2)
        o_draw = round(rng.uniform(2.8, 4.2), 2) if sport == "足球" else None
        o_away = round(rng.uniform(1.6, 4.5), 2)

        # 临场漂移:多数小幅,少数被埋的「异动」
        drift = rng.random()
        if drift < 0.12:                       # ~12% 制造剧烈下跌(steam move)
            mv = rng.uniform(0.18, 0.34)
            c_home = round(o_home * (1 - mv), 2)
            c_away = round(o_away * (1 + mv * 0.5), 2)
        elif drift < 0.20:                     # ~8% 反向线动(handle 压主队但赔率反升)
            c_home = round(o_home * (1 + rng.uniform(0.08, 0.16)), 2)
            c_away = round(o_away * (1 - rng.uniform(0.05, 0.10)), 2)
        else:                                  # 正常小幅波动
            c_home = round(o_home * (1 + rng.uniform(-0.05, 0.05)), 2)
            c_away = round(o_away * (1 + rng.uniform(-0.05, 0.05)), 2)
        c_draw = round(o_draw * (1 + rng.uniform(-0.04, 0.04)), 2) if o_draw else None

        # 投注额 / 笔数 / 主队投注占比
        handle = round(rng.uniform(3_000, 90_000), 2)
        bet_count = rng.randint(40, 2200)
        # 异动盘口故意做出「钱压一边」
        if drift < 0.20:
            handle = round(handle * rng.uniform(1.8, 3.2), 2)
            home_pct = rng.uniform(0.68, 0.86)
        else:
            home_pct = rng.uniform(0.35, 0.65)

        matches.append({
            "match_id": mid,
            "sport": sport,
            "league": league,
            "home": home,
            "away": away,
            "start_time": start.strftime("%Y-%m-%d %H:%M"),
            "opening": {"home": o_home, "draw": o_draw, "away": o_away},
            "current": {"home": c_home, "draw": c_draw, "away": c_away},
            "handle_usdt": handle,
            "bet_count": bet_count,
            "handle_home_pct": round(home_pct, 3),
            "handle_away_pct": round(1 - home_pct, 3),
        })
    return matches


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="2026-06-11", help="YYYY-MM-DD")
    args = ap.parse_args()

    os.makedirs(DATA_DIR, exist_ok=True)
    snaps = fetch_snapshots(args.date)
    out = os.path.join(DATA_DIR, "odds_snapshots_{}.json".format(args.date))
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"date": args.date, "matches": snaps}, f, ensure_ascii=False, indent=2)

    total_handle = sum(m["handle_usdt"] for m in snaps)
    print("[fetch] {} 场赛事, 总投注额 {:,.0f} USDT -> {}".format(
        len(snaps), total_handle, os.path.relpath(out, HERE)))


if __name__ == "__main__":
    main()
