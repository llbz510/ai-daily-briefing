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
