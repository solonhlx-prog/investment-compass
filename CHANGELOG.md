# Changelog

## [1.6.0] - 2026-07-01

### 架构重构
- **平台解耦**：将 WorkBuddy 专用 Skill 协议重构为平台无关的 AI Agent 技能包
- 新增 `agent.md`：通用系统提示词，可作为任何 Agent 框架的系统提示加载
- `SKILL.md` 降级为 WorkBuddy 平台适配层（薄封装，核心逻辑委托给 agent.md）
- 数据 L3 降级从平台特定引用（`westock-data / wb-finance-skill`）改为通用描述（`外部金融数据接口 / 网络搜索`）

### 代码改进
- 新增 `scripts/config.py`：共享配置模块，消除 `data.py` 和 `daily.py` 的 `.env` 加载重复逻辑
- 修复 `daily.py` 硬编码输出路径 `D:/BaiduSyncdisk/赛博英雄传/outputs/` → 环境变量 `REPORT_OUTPUT_DIR`，默认 `项目根目录/outputs/`
- `daily.py` 补齐函数类型注解和 docstring
- `data.py` 引入 `config.py`，消除重复代码

### 文档
- 重写 `README.md`：定位从「WorkBuddy Skill」转为「平台无关的 AI Agent 技能包」，新增适配指南（Claude Code / Cursor / OpenAI Agents SDK / LangChain 等）
- 新增 `CHANGELOG.md`（本文件）
- 新增 `requirements.txt`

### 配置
- `.env.example` 默认 `DATA_MODE` 从 `tt` 改为 `websearch`（零配置优先）
- 新增 `.github/ISSUE_TEMPLATE/`（bug_report + feature_request）

---

## [1.5.0] - 2026-07-01

### Added
- 每日工作流（四步一条龙）：择时判定 → 策略制定 → B1选股 → 输出TOP5日报
- 日报模板优化：7章→5章结构

### Changed
- `scripts/daily.py`：实现完整四步自动工作流
- `scripts/data.py`：补充 `fetch_index_daily()` 指数数据获取

---

## [1.4.0] - 2026-06-30

### Added
- 双线趋势系统（`knowledge/06-trend-system.md`）：白线/黄线/三道防线/五种玩法/牛绳理论
- B1选股增加六维筛选 + 双线过滤

---

## [1.3.0] - 2026-06-29

### Added
- 多空叙事翻译层：技术指标 → 态势语言
- 周度态势周报模板
- 领地翻译规则表（15种信号映射）

---

## [1.2.0] - 2026-06-28

### Added
- 一次性问诊模式：一轮问完关键信息，不反复追问
- 守门员模式升级：仓位/成本前置检查，软性提醒

---

## [1.1.0] - 2026-06-27

### Added
- Harness 层：安全底线 + 输出自检 + 降级策略
- 选股类输出特殊约束（开头+结尾双提示）

---

## [1.0.0] - 2026-06-26

### Added
- 初始版本
- 三层架构：择时 → 配置 → 风控+执行
- 5 个知识模块
- Tushare 数据层（三级降级）
- WorkBuddy Skill 协议适配
