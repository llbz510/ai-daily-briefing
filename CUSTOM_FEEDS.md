# 自定义信源指南（政策 + 行情）

> 本仓库基于 [TrendRadar](https://github.com/sansan0/TrendRadar) v6.10.0，
> 在它原有的热榜 + RSS 能力之上，额外接入了**政府政策发布**和**行情**两类信源。
>
> **所有信源都在同一个地方管理** —— 用 TrendRadar 官方的可视化编辑器点点点即可。

---

## 为什么需要这一层

政府网站**不提供 RSS**（实测 12 个部委站点，0 个有可用 feed），
而 TrendRadar 抓取自定义源的方式只有 RSS。所以中间需要一个转换器：

```
你在编辑器里改的 config/config.yaml
        ↓
  scripts/custom_feeds/build_feeds.py     ← 转换器
        ↓
  policy.xml / market.xml（标准 RSS 2.0）
        ↓
  TrendRadar 抓取 → 关键词筛选 → AI 分析 → 飞书推送
```

**关键点**：转换器只产出 `output/custom-feeds/config.runtime.yaml`（已 gitignore），
通过 TrendRadar 原生的 `CONFIG_PATH` 环境变量生效。
**仓库里的 `config/config.yaml` 一个字节都不会被程序改写。**

---

## 可视化编辑器使用导览

**打开方式**（二选一，完全等价）：

- 在线：<https://sansan0.github.io/TrendRadar/>
- 本地：双击本仓库的 `docs/index.html`

### 界面布局

```
┌───────────────────────────────────────────────────────────────────┐
│ ⚙ TrendRadar 可视化配置编辑器  🛡数据仅存本地  [EN] 加载官网最新配置 [复制配置] │
├────────────────────────────────┬──────────────────────────────────┤
│  源码编辑器（左半屏，深色）       │  可视化面板（右半屏，浅色）         │
│                                │  配置模块 │ 版本检测 │ ↺重置      │
│  [config.yaml] ←当前 tab       │ ┌──────────────────────────────┐ │
│  [frequency_words.txt]         │ │1.基础 2.热榜 3.RSS订阅 4.报告 …│ │
│  [timeline.yaml]               │ └──────────────────────────────┘ │
│   ↑ 把文件拖到这里即可导入       │   表单区（开关/输入框/下拉框）     │
└────────────────────────────────┴──────────────────────────────────┘
```

左右**双向联动**：改右边表单左边源码立刻变，反之亦然。

### ⚠️ 第一步：先把仓库里你那份配置导进去

编辑器打开时显示的是 **TrendRadar 官方默认模板**，直接改会把你现有设置冲掉。

**正确做法 —— 把文件从资源管理器拖到左边编辑器区域：**

| 拖哪个文件 | 先点哪个 tab |
|---|---|
| `config/config.yaml` | 左边点 `config.yaml` 标签，再拖进去 |
| `config/frequency_words.txt` | 点 `frequency_words.txt` 标签，再拖 |
| `config/timeline.yaml` | 点 `timeline.yaml` 标签，再拖 |

拖进去会提示「已加载: config.yaml」，并自动校验 YAML 语法。

> ❗ **不要点「加载官网最新配置」** —— 那是加载 TrendRadar 官方最新模板，会**覆盖掉你现有的全部设置**。它只在「从零开始」或「对比官方版本」时才有用。

### 第二步：在右边 13 个模块里改

| 模块 | 能改什么 | 建议 |
|---|---|---|
| 1. 基础设置 | 时区 | 保持 `Asia/Shanghai` |
| 2. 数据源 - 热榜平台 | 勾选监控哪些热榜 | 按需增减 |
| **3. 数据源 - RSS 订阅** | ⭐ **政策源 / 行情源 / 任意 RSS** | 见本文档其余章节 |
| 4. 报告模式 | 当日汇总 / 当前榜单 / 增量推送 | 日报用 `daily` |
| 4.5 筛选策略 / 4.6 AI 智能筛选 | 筛选方式 | 保持 `keyword` |
| 5. 推送内容控制 | 报告里显示哪些区块 | 需要时开「独立展示区」 |
| 6. 推送通知 | 各推送渠道 | **保持空白**（走 GitHub Secrets） |
| 7. 存储配置 | 本地 / S3 | 保持 `auto` |
| 8. AI 模型配置 | 模型名等 | ⚠️ **改了不生效**，被 `AI_MODEL` Secret 覆盖 |
| **9. AI 分析功能** | 是否分析 RSS 等 | ⚠️ `include_rss` 必须为 `true` |
| 10. AI 翻译功能 | 翻译范围 | 保持 |
| 11. 高级设置 | 分批大小等 | 保持默认 |

### 第三步：把结果拿回仓库

点右上角 **「复制配置」** → 提示「已复制!」→ **内容进入剪贴板**（注意：**不是下载文件**）。

然后推荐用 GitHub 网页直接改：

1. 打开 <https://github.com/llbz510/ai-daily-briefing/blob/main/config/config.yaml>
2. 右上角 **✏️ 铅笔**
3. **全选 → 删除 → 粘贴**
4. 拉到底点 **Commit changes**

### 第四步：等生效

- **定时任务**：每天北京时间 **08:00** 自动跑
- **想立刻看效果**：Actions → Get Hot News → **Run workflow**

### 小贴士

| 事项 | 说明 |
|---|---|
| 改动自动存浏览器 | localStorage，关掉再开还在 |
| 左边可直接改源码 | 批量改（如 RSS 源）时更快 |
| 「版本检测」 | 对比官方最新版本，只提示不自动改 |
| ↺ 重置 | **会丢你的改动，慎点** |
| 隐私 | 纯本地运行，配置（含 webhook）不会上传到任何服务器 |

---

## 快速上手：加一个政策源

### 第 1 步 · 打开可视化编辑器

👉 **https://sansan0.github.io/TrendRadar/**

（也可以本地打开本仓库的 `docs/index.html`，完全等价，不需要联网上传任何数据）

### 第 2 步 · 找到「RSS 源列表」

在 `config.yaml` 面板里往下滚，找到 **RSS 源列表** 区域。
你会看到当前所有订阅源，其中就包括已经配好的政策源和行情源。

### 第 3 步 · 点「添加」按钮，填三个字段

弹出「**添加 RSS 源**」窗口：

| 字段 | 填什么 | 例子 |
|---|---|---|
| 源 ID（唯一标识，英文） | 随便起，英文，别和已有的重复 | `policy-mof` |
| 显示名称 | 推送里显示的名字 | `财政部·政策法规` |
| **RSS URL** | **这里填伪协议**（见下文速查表） | `policysrc:https://www.mof.gov.cn/zhengwuxinxi/zhengcefabu/` |

> 「最大文章年龄」留空即可 —— 转换器已经做过时效过滤。

### 第 4 步 · 导出并替换

点编辑器的**导出**按钮 → 下载 `config.yaml` → 覆盖到本仓库的 `config/config.yaml` → commit。

**下一次定时任务（每小时 :33）就会自动带上新源。**

### 其他操作

| 想做什么 | 怎么做 |
|---|---|
| **临时停用某个源** | 点该条目右侧的**眼睛图标**（会打上「已禁用」标记） |
| **修改** | 点**铅笔图标** |
| **删除** | 点**垃圾桶图标** |

> ✅ 编辑器改 RSS 源用的是**逐行文本替换**，不会破坏文件里的注释和其他配置，可以放心用。

---

## URL 协议速查

### `policysrc:` —— 政策源

| 写法 | 说明 |
|---|---|
| `policysrc:gov_search` | **国务院政策文件库**（官方 JSON 接口，最权威，推荐保留） |
| `policysrc:gov_search?categories=gongwen` | 只要国务院公文 |
| `policysrc:gov_search?categories=bumenfile&per_page=20` | 只要部门文件，取 20 条 |
| `policysrc:https://某政府站/列表页` | **任意列表页** —— 自动探测列表结构，不用写选择器 |

### `bilisrc:` —— B站 UP 主

| 写法 | 说明 |
|---|---|
| `bilisrc:65564239` | 抓该 UP 主最新 20 条投稿 |
| `bilisrc:65564239?limit=5` | 只要最新 5 条（最多 50） |

> uid 是空间地址里那串数字：`space.bilibili.com/`**`65564239`** `/video`
>
> 走 B 站官方 API + WBI 签名，**境外 IP 直连可用，不需要 cookie、代理或 yt-dlp**（见「已知坑 7」）。

`categories` 可选值（逗号分隔，可组合）：

| 值 | 含义 |
|---|---|
| `gongwen` | 国务院公文（国令、国发、国办发…） |
| `bumenfile` | 各部委文件 |
| `otherfile` | 其他文件 |
| `gongbao` | 国务院公报 |

### `marketsrc:` —— 行情源

格式：`marketsrc:代码1=名称1,代码2=名称2,...`（名称可省略，会自动从接口取）

**代码写法：**

| 类型 | 前缀 | 例子 |
|---|---|---|
| A股个股 | `sh` / `sz` | `sh600519` 贵州茅台、`sz000001` 平安银行 |
| A股指数 | `sh` / `sz` | `sh000001` 上证指数、`sz399001` 深证成指、`sz399006` 创业板指、`sh000688` 科创50、`sh000300` 沪深300、`sh000905` 中证500 |
| 港股个股 | `hk` | `hk00700` 腾讯控股、`hk09988` 阿里巴巴 |
| 港股指数 | `hk` | `hkHSI` 恒生指数、`hkHSTECH` 恒生科技指数 |
| 美股个股 | `us` | `usAAPL` 苹果、`usNVDA` 英伟达、`usMSFT` 微软 |
| 美股指数 | `us` | `usINX` 标普500、`usIXIC` 纳斯达克、`usDJI` 道琼斯 |

> 可以配多条 `marketsrc:` 条目，转换器会把它们**合并成一个行情源**（不会重复抓取）。

---

## 当前已接入的信源

### 政策

| 名称 | 来源 | 状态 |
|---|---|---|
| 国务院·政策文件库 | 官方 JSON 接口 | ✅ 稳定 |
| 工信部·政务公开 | HTML 自动探测 | ✅ 稳定 |
| 证监会·主动公开目录 | HTML 自动探测 | ✅ 稳定 |
| 网信办·网信发布 | HTML 自动探测 | ✅ 稳定 |
| 国家统计局·最新发布 | HTML 自动探测 | ✅ 稳定 |
| 中国人民银行·法规 | HTML 自动探测 | ✅ 稳定 |

### 行情

腾讯行情接口，A股指数 6 个 + 港股指数 2 个 + 美股指数 2 个 + 自选个股 5 个。

### B站 UP 主

| 名称 | uid | 说明 |
|---|---|---|
| B站·IT咖啡馆 | 65564239 | 「Github一周热点」系列，约每周一期 |

> 这类源放在**独立展示区**（`display.standalone.rss_feeds`），绕过关键词筛选，保证不漏。

---

## 本地自测（改完源想先验证）

在仓库目录下：

```powershell
# 首次需要建虚拟环境
python -m venv .venv
.\.venv\Scripts\activate
pip install requests beautifulsoup4 lxml pyyaml

# 跑全部自定义源
python scripts/custom_feeds/build_feeds.py --config config/config.yaml --out output/custom-feeds

# 只测某一个源（推荐，快）
python scripts/custom_feeds/build_feeds.py --config config/config.yaml --out output/custom-feeds --only policy-mof
```

输出会逐条告诉你：

```
  - 财政部·政策法规  [policy-mof]
    探测到 42 条，纳入 18 条
```

- **「纳入 0 条」** → 探测到了列表但日期都超龄，正常
- **「未探测到列表」** → 该站可能是 JS 渲染或有反爬，见下方排查
- **「抓取失败」** → 网络或站点不可达

---

## 常见问题

### Q: 加了源但抓不到，报「未探测到列表」

按可能性排查：

1. **页面是 JS 渲染的**（内容不在初始 HTML 里）—— 常见于 gov.cn 的政策页。
   解决办法：找这个站的**直接列表接口**（可参考国务院政策文件库的做法），或换一个传统的列表页。
2. **站点有反爬** —— 典型表现是返回几十到几百字节的空壳页。已知有反爬的：
   发改委、财政部、科技部、国家数据局。这类站点**在境内境外都一样抓不到**，不是网络问题。
3. **列表页地址写错了** —— 政府站的栏目页经常改版，去站上点进「政策文件」「通知公告」栏目，
   复制浏览器地址栏的真实 URL。

### Q: 为什么不用 akshare / yfinance 取行情？

试过。结论：

- **akshare** 的东方财富系列接口在境外 GitHub Actions 上会被直接断开连接
  （`RemoteDisconnected`），而 GitHub Actions 的 runner 在美国。
- **yfinance** 可用，但依赖较重，且 A股覆盖面不如腾讯。
- **腾讯行情接口** `qt.gtimg.cn` 只需一次 HTTP GET，免依赖，A股/港股/美股/指数全覆盖，
  实测在 Actions 上 15/15 全部成功。

### Q: 转换器会不会改坏我的 config.yaml？

不会。它只**读** `config/config.yaml`，把结果写到 `output/custom-feeds/config.runtime.yaml`，
再由 workflow 通过 `CONFIG_PATH` 环境变量指给 TrendRadar。

### Q: 政策/行情条目会走关键词筛选和 AI 分析吗？

会。它们走的是 TrendRadar 标准的 RSS 管线，和热榜新闻**完全同等对待** ——
关键词筛选、AI 分析、翻译、飞书推送，一个不少。

日志里能看到：

```
[RSS] 抓取完成: 4 个源成功, 0 个失败, 共 135 条
[RSS] 关键词分组统计：37/87 条匹配
[推送] 准备发送：热榜 60 条 + RSS 37 条，合计 97 条
```

---

## 怎么挑新信源（伯乐思维）

加源前先问三个问题：

1. **它是权威一手发布吗？** 优先直连官方发布渠道，不要用二手转述。
2. **它更新频率和你的需求匹配吗？** 一年发几条的栏目不值得单独加源。
3. **它能稳定抓吗？** 没有反爬、不是 JS 渲染、URL 结构稳定。

**建议顺序**：官方 JSON 接口 > 传统 HTML 列表页 > RSS > 需要绕过的站点。

---

## 相关文件

| 文件 | 作用 |
|---|---|
| `config/config.yaml` | **信源配置（用编辑器改这个）** |
| `scripts/custom_feeds/build_feeds.py` | 转换器：伪协议 → 标准 RSS |
| `.github/workflows/crawler.yml` | 定时任务：生成源 → 本地服务 → 跑爬虫 → 推送 |
| `config/frequency_words.txt` | 关键词（决定哪些内容会被推送） |
| `docs/index.html` | TrendRadar 官方配置编辑器的本地副本 |

---

## 当前生产配置

### 推送节奏

- 每天 **北京时间 08:00** 跑一次（`cron: "0 0 * * *"`，UTC 时间）
- 报告模式 `daily`（当日汇总）
- 推送渠道：飞书

### 与 TrendRadar 默认值的关键差异

| 配置 | 当前值 | 为什么改 |
|---|---|---|
| `report.mode` | `daily` | 默认 `current` 会反复推当前榜单，一天推 24 次还大量重复 |
| `ai_analysis.include_rss` | `true` | **默认 `false`，会导致政策/行情完全不进 AI 分析** |
| `display.regions.standalone` | `true` | 让行情绕过关键词筛选，一条不漏 |
| `display.standalone.rss_feeds` | `["market-quotes"]` | 指定独立展示哪个源 |
| `schedule.enabled` | `false` | 用固定 cron 代替调度系统，行为更好预测 |

### 关键词

`config/frequency_words.txt` 在原有科技/品牌词之外，新增 4 组：

| 词组 | 作用 |
|---|---|
| 政策发布 | 匹配部委/机构名，精准度最高 |
| 政策文件类型 | 印发/通知/意见/办法/条例…（较宽，**嫌吵可整组删除**） |
| 宏观数据 | 降准/降息/LPR/CPI/PPI/社融/北向资金… |
| 资本市场 | 主要指数名 |

### 已接入的政策源

| 源 | 更新频率 | 备注 |
|---|---|---|
| 国务院·政策文件库 | 高 | 官方 JSON 接口，标题自带文号 |
| 工信部·政务公开 | 高 | |
| 网信办·网信发布 | 高 | |
| 国家统计局·最新发布 | 高 | |
| 证监会·政策解读 | **低（约季度）** | 该栏目更新慢，**长期 0 条属正常行为，不是故障** |

**已剔除的源及原因：**

- **中国人民银行·法规** —— 返回的是《民法典》《刑法修正案》等静态法规库（最新一条 1900+ 天前），对日报无价值；央行其它 5 个候选栏目页均无法解析。
- **证监会·主动公开目录** —— 该栏目所有 `zfxxgk_zdgk.shtml` 页面的正文是 JS 渲染的，抓到的只是通用侧栏，会产出 `xx省社会信用管理办法（XX年x月x日xxxx令第X号）` 这类**模板占位文字**。已换到「政策解读」栏目。

---

---

## 推送时间与可靠性 ⚠️ 重要

### 当前设计

| 项 | 值 |
|---|---|
| 触发频率 | **每小时第 23 分**（`cron: "23 * * * *"`） |
| 推送窗口 | **北京时间 06:00 – 11:00** |
| 窗口内第 1 次运行 | 采集 + AI 分析 + 推送 |
| 同日窗口内后续运行 | 采集，**跳过分析和推送**（不重复打扰、不重复扣 API 费用） |
| 窗口外运行 | **只采集**，不分析、不推送 |

### 为什么窗口开这么宽（5 小时）？

因为 **GitHub Actions 的定时任务非常不准**。实测本仓库：

| cron 计划 | 实际执行（北京时间） | 延迟 |
|---|---|---|
| 每小时 :33 | 01:46 / 05:06 / 07:29 / 09:26 / 14:19 | 计划 13 次**只跑了 5 次** |
| 每天 00:00 UTC | 09-20 **12:17** | 晚 4h17m |
| 每天 00:00 UTC | 09-21 **12:15** | 晚 4h15m |

原因是多方面的，且是 GitHub 已知问题：

- **`00:00 UTC` 是全球最拥堵的 cron 时刻** —— GitHub 官方文档明确提醒，
  整点（尤其一天开始时）负载最高，任务会被延迟
- 免费/公开仓库的定时任务优先级低，延迟可能达**数小时**
- 部分计划直接**被丢弃**（不是取消，是根本没创建）

社区同类报告：
[Reliability issues with GitHub actions, with cron based schedule](https://stackoverflow.com/questions/79534419/reliability-issues-with-github-actions-with-cron-based-schedule) ·
[cron job · community discussion #194300](https://github.com/orgs/community/discussions/194300) ·
[GitHub Actionsの実行遅延をCloud Schedulerで解消する](https://tech.pepabo.com/2026/05/11/cloud-workflows-github-actions-trigger/)

**所以策略是：让运行频率足够高（每小时），再用一个宽窗口去接住它。**
只要 06:00–11:00 之间有任何一次运行落地，日报就会发出——实测这一天里
07:29 和 09:26 各落地了一次，完全够用。

**代价**：推送时间会在 06:00–11:00 之间浮动，不保证整点。

### 如果要精确到点（可选）

GitHub 自己的 cron 做不到。需要**外部定时器**在精确时间调用 `workflow_dispatch`：

```bash
curl -X POST \
  -H "Authorization: Bearer <细粒度PAT，仅需 Actions: write>" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/llbz510/ai-daily-briefing/actions/workflows/crawler.yml/dispatches \
  -d '{"ref":"main"}'
```

免费可用：cron-job.org（网页配置，无需服务器）、Cloudflare Workers Cron Trigger。

`workflow_dispatch` 触发的运行**启动很快**（实测 10 秒内开始，2-3 分钟完成），
不受定时调度延迟影响。代价是要在第三方服务里存一个 PAT。

> 用这条路时，记得把窗口留宽一点做兜底（外部触发失败时 GitHub 的定时还能救）。

### 状态缓存（不要删）

`crawler.yml` 里有一个 `Restore crawler state` 步骤，用 `actions/cache` 缓存 `output/`。

**它是「窗口内只推一次」能生效的前提。** TrendRadar 的 `once.push` 去重
依赖存储后端记录状态，而 GitHub Actions 每次都是全新检出——不缓存的话，
窗口内每次运行都会重复推送一次。

日志里能看到判定结果：

```
[AI]   调度器: 时间段 早间日报 今天已分析过，跳过
[推送] 调度器: 时间段 早间日报 今天已推送过，跳过
```

### 想改推送时间

打开可视化编辑器 → **timeline.yaml** 面板 → 找 `custom` 预设下的
`morning_push` 时间段，改 `start` / `end`（24 小时制，北京时间）。

> 建议窗口**不要窄于 3 小时**，否则可能因为延迟而整天不推送。

---

## 已知坑（改配置前先看）

### 1. 运行时配置必须和原配置放在同一目录 ⚠️

`build_feeds.py` 会生成 `config/config.runtime.yaml`，crawler 通过 `CONFIG_PATH` 环境变量指向它。

**这个文件必须和 `config.yaml` 在同一目录。** 因为 TrendRadar 用 `Path(CONFIG_PATH).parent` 去定位 `timeline.yaml` —— 放到别处会报：

```
未知的预设模板: 'morning_evening'，可选值: , custom
```

**并且整个分析流程会中断、通知一条都发不出去**，而 GitHub Actions 依然显示绿色成功。踩过一次，切记。

### 2. AI 模型名在编辑器里改不生效

`config.yaml` 的 `ai.model` 会被 GitHub Secrets 的 `AI_MODEL` 覆盖。要换模型请改 Secret。

模型名必须是 **`厂商/模型`** 格式（litellm 要求），例如 `deepseek/deepseek-flash`。写成裸模型名会报 `LLM Provider NOT provided`。

### 3. 定时工作流的心跳（已自动处理）

GitHub 会在仓库连续 **60 天无提交**时自动禁用定时工作流。而 TrendRadar 的 Actions 版不向仓库提交任何内容，所以 `crawler.yml` 里放了一个心跳步骤：超过 45 天没提交就自动提交 `.github/.heartbeat`，保持仓库活跃。**不需要你干预。**

### 4. 某个政策源返回 0 条时先别慌

政策是低频的。某个部委 3 个月没发新政策，那个源就是 0 条，**这是正确行为**。

本地跑一下就能看清每个源的情况：

```powershell
python scripts/custom_feeds/build_feeds.py --config config/config.yaml --out output/custom-feeds
```

输出会逐条告诉你「探测到 N 条，纳入 M 条」。

### 5. 政府网站改版很常见

如果某个源突然从 N 条变成 0 条，多半是该站栏目页改版了。去站上点进对应栏目，复制浏览器地址栏的真实 URL，替换配置里的 `url:` 即可。

### 6. 自动探测抓到垃圾怎么办

列表页的**页脚/侧栏链接**可能被误抓。生成器已有两道防线：

1. **同站校验** —— 挡掉指向其它部委/网站的外链（如页脚的备案号、兄弟单位链接）
2. **噪音词过滤** —— 挡掉含 ICP备 / 公网安备 / 版权所有 / 网站地图 等字样的条目

仍抓不干净时，可以在该源配置里手填选择器（在 `build_feeds.py` 的 `detect_items` 调用处传入，或改用更精确的栏目页 URL）。

### 7. B站信源：网页被 412 封，但 API 能用 ⚠️

**踩坑记录（2026-09，从 GitHub Actions 美国 IP 实测 13 条路径）**

| 路径 | 结果 |
|---|---|
| yt-dlp 抓空间页 / 视频页 | ❌ `HTTP 412 Precondition Failed` |
| 套 Cloudflare WARP 换出口 IP | ❌ 仍 412（CF 的 IP 也被封） |
| RSSHub 公共实例 ×10 | ❌ 全部 403 / 503 / 超时 / 连不上 |
| 官方 API（不带 WBI 签名） | ❌ `-799 请求过于频繁` |
| **官方 API + WBI 签名** | ✅ **`code=0`，直连可用** |

**结论**：被 WAF 拦的是**网页**（yt-dlp 走的路径），**API 没事**。
所以 `bilisrc:` 用的是 `x/space/wbi/arc/search` + WBI 签名，纯 `requests` 实现。

**两个必须保持的实现细节：**

1. **必须用同一个 `requests.Session()`** —— B 站会通过 `/x/web-interface/nav`
   下发 `buvid3` 指纹 cookie，投稿接口靠它过风控。用裸 `requests.get()`
   每次都是新会话，cookie 丢失 → `-352 风控校验失败` 或 `HTTP 412`。
2. **必须带退避重试** —— 即使实现正确，B 站仍会间歇性返回 `-352`。
   实测第 1、2 次失败、第 3 次成功是常态。代码里做了 3 次尝试（5s / 10s / 15s 退避）。

**如果哪天 B 站彻底封了 API**：日志里会出现「三次尝试均未取到投稿（B站风控）」，
该源当次返回 0 条，**不影响其它源和推送**（已验证）。此时可以考虑：
配 cookie、换代理，或把这个源先 `enabled: false` 关掉。
