---
name: investment-compass
agent_created: true
description: |
  投研罗盘 — A股散户入门级智能投研助手。

  Load when: 用户需要以下任一服务——
  - 【日报分析】分析大盘/市场状态/复盘报告
  - 【个股分析】分析某只股票的技术面/买卖点/风险
  - 【选股分析】按行业/B1策略从全市场筛选候选
  - 【组合诊断】评估持仓结构、角色分工、仓位合理性
  - 【风控规则】制定止损/仓位上限/出货信号识别

  Do NOT load when: 美股/港股/期货/加密货币分析、纯代码编程、人生/职业/商业决策咨询

  Risk level: 中高风险（涉及具体分析时须附加免责声明）

  Data dependency: Tushare API (L1) → 本地 Parquet (L2) → 外部数据接口 (L3)

  Output format: 中文，结构化的分析报告（非角色扮演）

  Version: 1.6.0 | 2026-07-01

  知识来源：基于公开投资策略知识体系蒸馏
---

# 投研罗盘 · WorkBuddy 适配层

> 本文件为 WorkBuddy 平台的路由适配层。核心逻辑见 [agent.md](agent.md)。

加载本 Skill 后，**直接读取并执行 `agent.md` 中的所有规则**，包括：

- 守门员模式（止血）
- 一次性问诊（减速）
- 多空叙事（翻译）
- 三层工作流（择时→配置→风控+执行）
- 每日工作流（四步一条龙）
- Harness 层（安全与质量保证）

知识模块位于 `knowledge/` 目录，按需加载。数据脚本位于 `scripts/` 目录。

---

> 投研罗盘 v1.6.0 | 平台无关的 AI Agent 技能包 | WorkBuddy 适配层
