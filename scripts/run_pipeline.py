# -*- coding: utf-8 -*-
"""
工作流编排:fetch -> detect -> report 一键跑完。
这是「代码版的 n8n workflow」,workflows/n8n_体育日报_workflow.json 是同一条流程的可视化可调度版。

用法:
    python run_pipeline.py --date 2026-06-11
"""
import sys, os, argparse, subprocess

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))


def run(step, date):
    print("\n=== {} ===".format(step))
    r = subprocess.run([sys.executable, "-X", "utf8", os.path.join(HERE, step), "--date", date])
    if r.returncode != 0:
        sys.exit("步骤 {} 失败".format(step))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="2026-06-11")
    args = ap.parse_args()
    for step in ("fetch_odds.py", "detect_anomaly.py", "generate_report.py"):
        run(step, args.date)
    print("\n完成。日报见 data/report_{}.md".format(args.date))


if __name__ == "__main__":
    main()
