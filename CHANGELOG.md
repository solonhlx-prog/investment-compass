# Changelog

## [2.0.0] - 2026-07-08

### 重构：B1 选股引擎 v2.0 — 连续型评分 + 17特征四层金字塔

#### P0：补齐6个核心特征 + 连续评分骨架
- 新增突破检测 `find_breakthrough_info()`：识别黄线/白线突破点，计算放量突破比
- 新增上涨期定位 `find_up_phase_info()`：定位最高点+最大阳量+累计涨幅
- 新增金叉检测 `find_golden_cross_days()`：斐波那契多窗口(8/13/21/34/55)评分
- 新增6个连续型评分函数：F1放量突破比(0-25)、F2突破类型(0-10)、F4顶部缩量比(0-15)、F10小阴小阳度(0-15)、F11选股缩量比(0-15)、F12金叉后天数(0-15)
- 全特征改为连续型评分（阈值型→连续型），消除同分僵局
- 硬过滤精简为4关：无突破/J>14/白<黄(含Z哥缓存修正)/蜈蚣图>上限

#### P1：补齐5个路径质量特征
- F3累计涨幅(0-10)、F5回调深度比(0-10)、F6支撑偏离度(0-10)、F7缩量趋势斜率(0-10)、F8堆量比(0-10)

#### P2：F13 J值清洗深度 + 蜈蚣图上下文感知
- 新增F13 J值清洗深度(0-10)：金叉后J值最大→选股日的回落幅度
- 蜈蚣图上下文感知：缩量状态放宽阈值+15；阈值60→70；边界用 `>` 替代 `>=`

#### 关键修复
- **关3双线修正**：本地数据无 close_adj 导致 MA114 黄线偏高→关3检测时自动查Z哥缓存用预计算白/黄线
- **关4蜈蚣误杀**：B1窄幅震荡的"长影线+十字星"触发蜈蚣假阳性→提升阈值+上下文感知

#### 验证
- 10个完美案例通过率：0/10(v1.7) → 10/10(v2.0)
- 单日期全市场排名：华纳药厂 #1/180

### 变更文件
- `scripts/screening.py`：重构为~1400行，17特征+4硬过滤+区分特征层
- `scripts/config.py`：J阈值-8→14，新增 min_total_score，centipede_max 60→70
- `scripts/daily.py`：输出格式适配新字段
- `docs/`：新增4份分析报告（对比分析、验证报告、门槛悖论、特征设计）

---

## [1.7.0] - 2026-07-07

### 新增：B1 选股引擎 P0 移植（来自 Z哥体系）
- 新增 `scripts/screening.py`：独立、平台无关的 B1 量化选股引擎，集成三大 P0 能力：
  - **P0-1 参数可配置化**：原硬编码阈值（J阈值/量比/乖离/跌幅/沙漏/蜈蚣图等）全部抽至 `config.B1_PARAMS`，支持 `.env` 覆盖（新增 12 个 `B1_*` 环境变量）
  - **P0-2 MDC 多维验证**：对候选做七层打分（麒麟阶段 + 布林下轨 + 资金流 + RSI6 + ADX + 缩量 + 绿砖排除），输出置信度 0.1~0.98
  - **P0-3 硬过滤**：蜈蚣图（五因子，总分≥60 一票否决）+ 沙漏审美（五因子，总分<50 一票否决）
- 忠实移植 Z哥核心算法：`compute_kdj/bbi/bollinger/rsi/adx_dmi/dual_line`、`detect_kirin_stage`、`detect_centipede_pattern`、`calculate_sandglass_score`、`verify_b1_mdc`
- 数据不足时逐层降级（麒麟≥60日 / 硬过滤≥20日 / ADX≥15日），绝不抛异常
- websearch 模式无本地 Parquet 时整管线优雅跳过，附明确提示

### 代码改进
- `daily.py` 的 `step_screening()` 内联六维筛选逻辑重构为调用 `screening.screen_universe()`，代码量减少 ~70%，可维护性提升
- 选股输出新增 MDC/麒麟/沙漏维度字段，日报 JSON 与控制台打印同步增强

### 文档
- `README.md` 选股分析章节重写，标注 P0 四关管线；项目结构补充 `screening.py`；版本徽章升至 1.7.0
- `knowledge/04-execution.md` 第二节新增「B1 量化筛选管线（P0 移植）」专节
- `.env.example` 补充 12 个 `B1_*` 可调参数注释

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
