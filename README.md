# AI 工作流落地包 — 体育数据日报 + 赔率异动监控

> 把体育运营团队「每天人工拼日报」这件重复工作,拆成 SOP → 规则引擎 + Claude 自动化 → 可复用模板库,一条端到端工作流覆盖取数、异动监控、风控预警、日报撰写、自动推送。

打开 [`AI工作流_Demo報告.html`](AI工作流_Demo報告.html) 看全貌。

## 设计主张:规则在前,AI 在后

能量化的违规(赔率急跌、反向线动、投注集中)用规则引擎抓——稳定、可解释、零成本;规则抓不到的语义叙述才交给 LLM。**AI 不判定「有没有异常」,只把规则命中的 flag 翻成运营听得懂的话**,判定权留在规则与风控。这是工作流可信、可交接的关键,也是《数据产品经理》质检系统「规则兜底 + 模型补语义」的同一套思路。

## 目录

```
AI工作流_体育日报赔率监控/
├── AI工作流_Demo報告.html          # 门面:面试官视角的落地报告(嵌入真实产出)
├── README.md
├── scripts/                        # 四支纯标准库脚本,clone 即跑
│   ├── fetch_odds.py               # S1 取数(真环境换 API,返回结构不变下游零改)
│   ├── detect_anomaly.py           # S2 异动规则引擎(阈值集中可热改)
│   ├── generate_report.py          # S3 LLM 写日报(缺 key 自动离线兜底)
│   └── run_pipeline.py             # 编排:一键跑完 S1→S2→S3
├── templates/                      # 可复用资产库
│   ├── SOP_体育数据日报.md          # 触发/流程/质检/交接培训
│   ├── prompt_日报生成.md           # 日报提示词模板(口径写死在模板)
│   └── prompt_异动解读.md           # 单盘口深度解读提示词
├── workflows/
│   └── n8n_体育日报_workflow.json   # 可 import 进 n8n 的可视化调度版
└── data/                           # 运行产出(快照/异动/日报),可重跑覆盖
```

## 怎么重跑

环境:Windows + PowerShell + Python 3.13,**零第三方依赖**(只用标准库)。

```powershell
cd scripts
python -X utf8 run_pipeline.py --date 2026-06-11
```

产出落在 `data/`:`odds_snapshots_<date>.json`(快照)、`anomalies_<date>.json`(异动)、`report_<date>.md`(日报)。

接真 LLM:设环境变量 `ANTHROPIC_API_KEY` 后,日报自动从离线模板切换为 Claude(默认 `claude-sonnet-4-6`)撰写版,口径与结构不变。接真数据:只替换 `fetch_odds.py` 的 `fetch_snapshots()`,保持返回结构,下游两步不用改。

## 同一套骨架可搬到的场景

取数→规则兜底→LLM 补语义→推送→人工复核的骨架不变,换 S1 取数源 + S2 规则 + S3 提示词即可:用户工单分类、运营周报自动生成、异常行为风控告警。每接一个新场景,就是 JD 要求的「每周至少落地 1 个可复用 AI 工作流」。
