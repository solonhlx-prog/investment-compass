# 投研罗盘 · A股散户入门级智能投研助手

> *「不预测，只应对。不替你做决定，只帮你判断方向。」*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.6.0-green)]()
[![Python](https://img.shields.io/badge/Python-3.9+-blue)]()

<br>

**平台无关的 AI Agent 投研技能包。三层架构（择时→配置→风控→执行），六个知识模块按需加载。**

适用于任何支持系统提示词 + 工具调用的 AI Agent 框架（Claude Code、Cursor、Copilot、Cline、OpenAI Agents SDK、LangChain、CrewAI 等）。

<br>

[快速开始](#快速开始) · [五大功能](#五大功能) · [项目结构](#项目结构) · [框架说明](#框架说明) · [适配指南](#适配指南) · [免责声明](#免责声明)

---

## 五大功能

投研罗盘是一个 AI Agent 技能包，加载后 Agent 自动按规则响应，无需 CLI。

### 1. 日报分析

市场复盘，5 章结构：盘面一眼 → 今日发生了什么 → 多日节奏还原 → 涨跌结构拆解 → 关键信号与叙事连续性。

```
触发方式：用户说「日报」「复盘」「今天行情怎么样」
数据来源：Tushare API (L1) → 本地 Parquet (L2) → 网络搜索 (L3)
```

### 2. 个股分析

逐票深度分析，7 个维度：基本面三数 → 均线排列 → 走势结构 → 关键位(附距离%) → 指标全景 → 波段纪律法评估 → 多空判断。

```
触发方式：用户说「分析XX」「XX能不能买」「帮我看看600519」
```

### 3. 选股分析

全市场/行业 B1 六维筛选 + 双线过滤，按综合评分排名。

| 维度 | 阈值 | 排除逻辑 |
|------|------|---------|
| J 值 | ≤ -8 | 超卖确认 |
| 量比 | < 0.85 | 抛压未枯竭 |
| 乖离 MA20 | < -3% | 安全边际不足 |
| 10日跌幅 | > -25% | 排除崩盘 |
| 股价 | > 3 元 | 排除仙股 |
| 双线过滤 | 白线 > 黄线 | 主力不在 = 不碰 |

```
触发方式：用户说「证券行业选股」「B1选股」「TOP N」
```

### 4. 组合诊断

持仓结构评估 + 角色分工检查（曼城4231阵型）+ 仓位合理性分析。

```
触发方式：用户说「帮我看看持仓」「仓位是不是太重了」「持仓诊断」
```

### 5. 风控规则

按当前市场状态给出止损位、仓位上限、出货信号识别规则。

```
触发方式：用户说「止损设在哪」「单票仓位上限」「出货信号怎么看」
```

---

## 快速开始

### 方式一：零配置（网络搜索模式）

```bash
git clone https://github.com/solonhlx-prog/investment-compass.git
```

将 `agent.md` 作为系统提示词加载到你的 AI Agent 即可使用。Agent 通过网络搜索获取行情数据，无需任何 API Key。

### 方式二：启用实时行情（Tushare API）

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置数据源
cp .env.example .env
# 编辑 .env, 填入你的 Tushare Token (前往 https://tushare.pro/user/token 注册)

# 3. 将 DATA_MODE 改为 tt
# DATA_MODE=tt
```

### 方式三：使用本地数据缓存

如果已有本地 K 线数据（Parquet 格式），在 `.env` 中配置路径即可跳过 API 调用：

```ini
STOCK_DATA_DIR=/path/to/your/stock_data
```

支持的数据结构：

```
{STOCK_DATA_DIR}/
  daily_raw/               # 日线数据（每只股票一个 .parquet）
    601456.SH.parquet       # 需含 trade_date/open/high/low/close/vol 列
    000001.SZ.parquet
  stock_basic/              # 股票基本信息
    stock_list.parquet       # 需含 ts_code/name 列
```

### 三级数据降级

```
需要数据时 → L1 Tushare API → L2 本地 Parquet → L3 网络搜索
              ✅ 实时行情        ✅ 历史缓存          ✅ 零配置
```

---

## 项目结构

```
投研罗盘/
├── agent.md                     # 核心系统提示词（平台无关）
├── SKILL.md                     # WorkBuddy 平台适配层
├── README.md                    # 本文件
├── LICENSE                      # MIT 许可证
├── CHANGELOG.md                 # 版本演进日志
├── requirements.txt             # Python 依赖
├── .env.example                 # 数据源配置模板
├── .gitignore
├── docs/
│   └── first-principles.md      # 第一性原理总结
├── scripts/
│   ├── config.py                # 共享配置（.env 加载）
│   ├── data.py                  # 数据访问层（三级降级）
│   └── daily.py                 # 每日四步工作流
├── knowledge/                   # 知识模块（6 个）
│   ├── 01-timing.md             # 择时：活跃市值/市场阶段/BBI方向
│   ├── 02-allocation.md         # 配置：曼城4231/仓位分级/ABC建仓
│   ├── 03-risk.md               # 风控：止损铁律/防卖飞/出货五式
│   ├── 04-execution.md          # 执行：波段纪律法/B1-B2-B3/四块砖
│   ├── 05-indicators.md         # 指标：KDJ/MACD/BBI/量比/均线
│   └── 06-trend-system.md       # 双线：白线黄线/五种玩法/牛绳理论
└── .github/
    └── ISSUE_TEMPLATE/
```

---

## 框架说明

### 设计哲学：Agent-Native

投研罗盘不是传统的"库"或"API"，而是一个**为 AI Agent 设计的技能包**。核心文件 `agent.md` 就是 Agent 的系统提示词——它定义了 Agent 的思考方式、输出格式、行为边界和质量标准。

```
agent.md (大脑) + knowledge/ (记忆) + scripts/ (手)
```

### 三层架构

```
择时 → 配置 → 风控 + 执行
```

| 层 | 目标 | 核心模块 |
|----|------|---------|
| **择时** | 判断市场阶段，定仓位上限 | 01-timing：活跃市值/BBI方向 |
| **配置** | 构建组合，角色分工 | 02-allocation：曼城4231/仓位分级/ABC建仓 |
| **风控+执行** | 买入有规则，持有有纪律，卖出有信号 | 03-risk + 04-execution + 06-trend-system |

### 三阶段防御机制

1. **守门员模式**：个股分析前检查仓位/成本信息，缺则提示但不拦截
2. **一次性问诊**：缺关键信息时一轮问完，不反复追问
3. **多空叙事**：技术指标 → 态势语言翻译层，数字+翻译缺一不可

### 核心战法：波段纪律法

保守型波段交易纪律系统。低吸(B1) → 半仓锁利 → 窄止损 → 不追高 → 积小胜。

### 双线趋势系统

| 线 | 公式 | 功能 |
|----|------|------|
| 白线 | `EMA(EMA(CLOSE, 10), 10)` | 短期成本线 |
| 黄线 | `(MA14 + MA28 + MA57 + MA114) / 4` | 长期成本线，主力入场标志 |

- 白线 > 黄线 = 下跌是洗盘 → 做多
- 白线 < 黄线 = 上涨是反弹 → 只看不做
- 白线死叉黄线 = 无条件清仓

---

## 适配指南

### Claude Code

```bash
# 在项目目录下启动 Claude Code
claude --system-prompt agent.md
```

### Cursor / Copilot

将 `agent.md` 的内容配置为自定义指令（Custom Instructions / .cursorrules）。

### OpenAI Agents SDK

```python
from agents import Agent

with open("agent.md", "r", encoding="utf-8") as f:
    system_prompt = f.read()

agent = Agent(
    name="InvestmentCompass",
    instructions=system_prompt,
    tools=[...],  # 注册 scripts/ 下的 Python 函数作为工具
)
```

### LangChain / CrewAI

```python
# 将 agent.md 作为 agent 的 system_message
# 将 scripts/ 下的函数注册为 @tool
```

### 通用适配原则

任何 AI Agent 框架只需满足三个条件：

1. **能读取 `agent.md` 作为系统提示词**
2. **能执行 Python 脚本或调用网络搜索**（二选一即可）
3. **能读取 `knowledge/` 目录下的 Markdown 文件**（按需加载）

---

## 知识来源

基于公开投资策略知识体系蒸馏：
- 技术分析实战讲稿（约 200 万字）
- 交易心理与纪律系列
- 波段交易战法体系

蒸馏逻辑：去角色 → 留规则 → 补实战。6 个知识模块按三层架构编排，按需加载。

---

## 免责声明

> ⚠️ **功能演示声明：此项目仅做策略框架的功能演示。所有分析结果不代表对具体股票的任何推荐或投资建议。投资决策请自行判断，盈亏自负。**

此技能包基于公开语料蒸馏的框架规则，**不构成任何投资建议**。金融市场风险极高，任何基于历史信息的交易框架都可能失效。交易纪律的知行合一是最大瓶颈，框架可以提供规则但无法替你执行止损。

**理解不等于模仿。投资有风险，入市需谨慎。**

---

## 社区

- 🐛 [提交 Bug](../../issues)
- 💡 [功能建议](../../issues)
- 🤝 [GitHub Discussions](../../discussions) — 用法交流、策略讨论

---

<div align="center">

*先扎马步，再学招式，然后建立适合自己的体系。*

<br>

MIT License

</div>
