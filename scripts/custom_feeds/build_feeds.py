#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自定义 RSS 生成器 —— 政策 + 行情
================================================================
把「没有 RSS 的政府网站」和「行情」转换成标准 RSS 2.0，喂给 TrendRadar。

【信源配置在哪里】
    就在 TrendRadar 自己的 config/config.yaml 的 rss.feeds 里，用自定义协议：

        - id: "policy-gov"
          name: "国务院·政策文件库"
          url: "policysrc:gov_search"

        - id: "policy-miit"
          name: "工信部·政务公开"
          url: "policysrc:https://www.miit.gov.cn/zwgk/index.html"

        - id: "market-quotes"
          name: "行情速览"
          url: "marketsrc:sh000001=上证指数,sz399001=深证成指,hkHSI=恒生指数"

    这样就能直接用 TrendRadar 官方的可视化配置编辑器
    （https://sansan0.github.io/TrendRadar/  → RSS 源面板）增删改，
    不需要任何额外的编辑器。

【本脚本做什么】
    1. 读 config/config.yaml，挑出 url 以 policysrc: / marketsrc: 开头的条目
    2. 抓取并合成 output/custom-feeds/policy.xml 与 market.xml
    3. 写一份「运行时配置」output/custom-feeds/config.runtime.yaml：
       把这些伪协议条目替换成 http://127.0.0.1:8899/*.xml
       （仓库里的 config.yaml 不会被改动）
    4. crawler 用 CONFIG_PATH 环境变量指向这份运行时配置

【协议说明】
    policysrc:gov_search[?categories=gongwen,bumenfile&per_page=20]
        中国政府网政策文件库官方 JSON 接口
    policysrc:<http(s) 列表页地址>
        任意政府/机构列表页，自动探测列表结构（无需写选择器）
    marketsrc:<code>[=<名称>][,<code>[=<名称>]...]
        腾讯行情接口代码。A股 sh600519 / sz000001；A股指数 sh000001；
        港股 hk00700；港股指数 hkHSI/hkHSTECH；美股 usAAPL；
        美股指数 usINX/usIXIC/usDJI。不写名称则自动取。
    bilisrc:<up主 uid>[?limit=10]
        B 站 UP 主投稿更新。uid 是空间地址里那串数字：space.bilibili.com/<uid>
        走官方 API + WBI 签名，境外 IP 直连可用，无需 cookie / 代理 / yt-dlp。

依赖: requests, beautifulsoup4, lxml, pyyaml
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import re
import sys
import time
import urllib.parse
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs
from xml.sax.saxutils import escape

import requests
import yaml
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}
CST = dt.timezone(dt.timedelta(hours=8))

POLICY_SCHEME = "policysrc:"
MARKET_SCHEME = "marketsrc:"
BILI_SCHEME = "bilisrc:"
GOV_API = "https://sousuo.www.gov.cn/search-gov/data"
TENCENT_API = "https://qt.gtimg.cn/q="
SERVE_BASE = "http://127.0.0.1:8899"

# 伪协议 -> (类别, 输出文件名, RSS 标题, RSS link)
SCHEME_MAP = {
    POLICY_SCHEME: ("policy", "policy.xml", "政策发布", "https://www.gov.cn/zhengce/"),
    MARKET_SCHEME: ("market", "market.xml", "行情速览", "https://gu.qq.com/"),
    BILI_SCHEME:   ("bili",   "bili.xml",   "B站关注",  "https://www.bilibili.com/"),
}
SCHEME_OF_KIND = {kind: scheme for scheme, (kind, *_) in SCHEME_MAP.items()}

ARTICLE_EXT = re.compile(r"\.(?:s?html?|shtml|jsp|aspx|php)(?:\?|$)", re.I)
SKIP_HREF = re.compile(r"(?:^|/)(?:index|default)\.(?:s?html?)$|^javascript:|^mailto:|^#", re.I)

# 页面页脚 / 导航 / 备案号等噪音链接
JUNK_TITLE = re.compile(
    r"ICP备|公网安备|版权所有|网站地图|联系我们|关于我们|主办单位|承办单位|"
    r"技术支持|无障碍|网站声明|隐私政策|简体|繁體|^English$|^登录$|^注册$|"
    r"^首页$|门户网站|政府网站找错|违法和不良信息|举报电话|^http", re.I)


def _registrable(host: str) -> str:
    """取可注册域名，用于判断链接是否属于同一站点（gov.cn / com.cn 等按三级算）。"""
    host = (host or "").lower().split(":")[0]
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    if parts[-2] in ("gov", "com", "org", "edu", "net", "ac") and parts[-1] == "cn":
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def log(*a) -> None:
    print(*a, flush=True)


# ---------------------------------------------------------------- 抓取
def fetch(url: str, timeout: int = 25, retries: int = 2,
          referer: str | None = None, encoding: str | None = None) -> str | None:
    err = ""
    headers = dict(HEADERS)
    if referer:
        headers["Referer"] = referer
    for i in range(retries + 1):
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code == 200:
                if encoding:
                    r.encoding = encoding
                elif not r.encoding or r.encoding.lower() == "iso-8859-1":
                    r.encoding = r.apparent_encoding or "utf-8"
                return r.text
            err = f"HTTP {r.status_code}"
        except Exception as e:                      # noqa: BLE001
            err = f"{type(e).__name__}: {str(e)[:60]}"
        if i < retries:
            time.sleep(1.5 * (i + 1))
    log(f"    [warn] 抓取失败 {url}  ({err})")
    return None


# ---------------------------------------------------------------- 列表探测
def _article_like(title: str, href: str, base_host: str = "") -> bool:
    if not (8 <= len(title) <= 120):
        return False
    if JUNK_TITLE.search(title):
        return False
    # 标题必须含中文或足够长，挡掉纯代码/纯链接标题
    if not re.search(r"[\u4e00-\u9fa5]", title) and len(title) < 16:
        return False
    if SKIP_HREF.search(urlparse(href).path or ""):
        return False
    # 同站校验：挡掉页脚里指向其它部委/网站的外链
    if base_host and _registrable(urlparse(href).netloc) != base_host:
        return False
    if ARTICLE_EXT.search(href):
        return True
    return href.count("/") >= 3


def detect_items(soup: BeautifulSoup, base_url: str, min_items: int = 3):
    base_host = _registrable(urlparse(base_url).netloc)
    best, best_key = [], (-1, 0)
    for el in soup.find_all(["ul", "div", "table", "tbody", "dl"]):
        links = el.find_all("a", href=True)
        if len(links) < min_items:
            continue
        picked = []
        for a in links:
            title = a.get_text(" ", strip=True)
            href = urljoin(base_url, a["href"])
            if not href.startswith("http") or not _article_like(title, href, base_host):
                continue
            picked.append((title, href, a.find_parent(["li", "tr", "dd", "div"]) or a))
        if len(picked) < min_items:
            continue
        key = (len(picked), -len(links))
        if key > best_key:
            best_key, best = key, picked
    return best


# ---------------------------------------------------------------- 日期
_DATE_RES = [
    re.compile(r"(20\d{2})\s*[-/年.]\s*(\d{1,2})\s*[-/月.]\s*(\d{1,2})"),
    re.compile(r"(20\d{2})\s*[-/年]\s*(\d{1,2})\s*月?"),
]
_URL_DATE_RES = [
    re.compile(r"/(20\d{2})-(\d{2})/(\d{2})/"),
    re.compile(r"/(20\d{2})(\d{2})/"),
    re.compile(r"/(20\d{2})/(\d{2})/"),
]


def parse_date(text: str, url: str) -> dt.datetime:
    for rx, src in [(r, text) for r in _DATE_RES] + [(r, url) for r in _URL_DATE_RES]:
        m = rx.search(src or "")
        if not m:
            continue
        g = [int(x) for x in m.groups()]
        try:
            return dt.datetime(g[0], g[1], g[2] if len(g) > 2 else 1, 9, 0, tzinfo=CST)
        except ValueError:
            pass
    return dt.datetime.now(CST)


# ---------------------------------------------------------------- RSS
def build_rss(items, title: str, link: str, description: str = "") -> str:
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<rss version="2.0"><channel>',
             f"<title>{escape(title)}</title>",
             f"<link>{escape(link)}</link>",
             f"<description>{escape(description or title)}</description>",
             f"<lastBuildDate>{format_datetime(dt.datetime.now(CST))}</lastBuildDate>",
             "<language>zh-cn</language>"]
    for it in items:
        parts += ["<item>",
                  f"<title>{escape(it['title'])}</title>",
                  f"<link>{escape(it['link'])}</link>",
                  f'<guid isPermaLink="true">{escape(it["link"])}</guid>',
                  f"<pubDate>{format_datetime(it['date'])}</pubDate>",
                  f"<description>{escape(it.get('desc', ''))}</description>",
                  f"<source>{escape(it.get('source', ''))}</source>",
                  "</item>"]
    parts.append("</channel></rss>")
    return "\n".join(parts)


# ---------------------------------------------------------------- 政策采集
def _collect_gov_search(payload: str, name: str, seen: set, items: list, cutoff) -> int:
    qs = {}
    if "?" in payload:
        qs = {k: v[0] for k, v in parse_qs(payload.split("?", 1)[1]).items()}
    cats = [c.strip() for c in (qs.get("categories") or "gongwen,bumenfile").split(",") if c.strip()]
    params = {"t": qs.get("t", "zhengcelibrary"), "q": "", "timetype": "timeqb",
              "sort": "pubtime", "sortType": "1", "searchfield": "title",
              "p": 1, "n": int(qs.get("per_page", 20))}
    try:
        r = requests.get(GOV_API, params=params,
                         headers={**HEADERS, "Referer": "https://www.gov.cn/"}, timeout=25)
        j = r.json()
    except Exception as e:                          # noqa: BLE001
        log(f"    [warn] 政策接口失败: {type(e).__name__}: {str(e)[:60]}")
        return 0
    cat_map = ((j.get("searchVO") or {}).get("catMap") or {})
    added = 0
    for cat in cats:
        bucket = (cat_map.get(cat) or {}).get("listVO") or []
        if not bucket:
            log(f"    [warn] 分类 {cat} 无数据")
            continue
        for it in bucket:
            link = (it.get("url") or "").strip()
            title = (it.get("title") or "").strip()
            if not link or not title or link in seen:
                continue
            ts = it.get("ptime")
            date = (dt.datetime.fromtimestamp(ts / 1000, CST) if ts
                    else parse_date(it.get("pubtimeStr", ""), link))
            if cutoff and date < cutoff:
                continue
            doc_no = (it.get("pcode") or "").strip()
            seen.add(link)
            items.append({"title": (f"{doc_no} {title}" if doc_no else title)[:180],
                          "link": link, "date": date, "source": name,
                          "desc": (it.get("summary") or "").strip()[:300]})
            added += 1
    return added


def _collect_html(payload: str, name: str, seen: set, items: list, cutoff) -> int:
    body = fetch(payload)
    if not body:
        return 0
    soup = BeautifulSoup(body, "lxml")
    picked = detect_items(soup, payload)
    if not picked:
        log("    [warn] 未探测到列表（该站可能是 JS 渲染或有反爬），跳过")
        return 0
    added = 0
    for title, href, container in picked:
        if href in seen:
            continue
        date = parse_date(container.get_text(" ", strip=True), href)
        if cutoff and date < cutoff:
            continue
        seen.add(href)
        items.append({"title": title, "link": href, "date": date, "source": name, "desc": ""})
        added += 1
    log(f"    探测到 {len(picked)} 条，纳入 {added} 条")
    return added


def collect_policy(entries: list, max_age_days: int, max_items: int) -> list:
    items, seen = [], set()
    cutoff = (dt.datetime.now(CST) - dt.timedelta(days=max_age_days)) if max_age_days else None
    for feed_id, name, payload in entries:
        log(f"  - {name}  [{feed_id}]")
        if payload.startswith("http"):
            _collect_html(payload.strip(), name, seen, items, cutoff)
        else:
            log(f"    纳入 {_collect_gov_search(payload, name, seen, items, cutoff)} 条")
    items.sort(key=lambda x: x["date"], reverse=True)
    return items[:max_items]


# ---------------------------------------------------------------- B站 UP 主
# WBI 签名用的混淆表（B 站前端固定值）
_WBI_TAB = [46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
            33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
            61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
            36, 20, 34, 44, 52]


def _wbi_sign(params: dict, img_key: str, sub_key: str) -> dict:
    """B站 WBI 签名：img_key+sub_key 按固定表重排成 mixin key，再对排序后的 query 做 md5。"""
    mixin = "".join((img_key + sub_key)[i] for i in _WBI_TAB)[:32]
    p = dict(params)
    p["wts"] = round(time.time())
    p = dict(sorted(p.items()))
    p = {k: "".join(c for c in str(v) if c not in "!'()*") for k, v in p.items()}
    query = urllib.parse.urlencode(p)
    p["w_rid"] = hashlib.md5((query + mixin).encode()).hexdigest()
    return p


def _collect_bilibili(payload: str, name: str, seen: set, items: list, cutoff,
                      default_limit: int = 20) -> int:
    """
    抓 B 站 UP 主投稿列表（官方接口 + WBI 签名）。

    实测结论（2026-09，从 GitHub Actions 美国 IP 测 13 条路径）：
      * 网页版空间页（含 yt-dlp 走的网页路径）被 B 站 WAF 拦死，
        境外 IP 一律 HTTP 412 Precondition Failed；套 Cloudflare WARP 换 IP 也无效。
      * 但 **WBI 签名的官方 API** `x/space/wbi/arc/search` 境外 IP 直连即可用
        （code=0），无需 cookie、无需代理。
    所以这里用 API，不用 yt-dlp，也不依赖任何额外二进制。

    payload 形如:  65564239        或        65564239?limit=5
    """
    uid = payload.split("?", 1)[0].strip()
    limit = default_limit
    if "?" in payload:
        qs = {k: v[0] for k, v in parse_qs(payload.split("?", 1)[1]).items()}
        try:
            limit = max(1, min(50, int(qs.get("limit", default_limit))))
        except (TypeError, ValueError):
            pass
    if not uid.isdigit():
        log(f"    [warn] UP 主 uid 必须是纯数字，收到 {uid!r}")
        return 0

    headers = {**HEADERS, "Referer": f"https://space.bilibili.com/{uid}/video",
               "Origin": "https://space.bilibili.com"}
    try:
        nav = requests.get("https://api.bilibili.com/x/web-interface/nav",
                           headers=headers, timeout=20).json()
    except Exception as e:                          # noqa: BLE001
        log(f"    [warn] 取 WBI 密钥失败: {type(e).__name__}: {str(e)[:60]}")
        return 0
    wbi = ((nav.get("data") or {}).get("wbi_img")) or {}
    img_key = (wbi.get("img_url") or "").rsplit("/", 1)[-1].split(".")[0]
    sub_key = (wbi.get("sub_url") or "").rsplit("/", 1)[-1].split(".")[0]
    if not (img_key and sub_key):
        log("    [warn] 未能解析 WBI 密钥，跳过")
        return 0

    vlist = []
    for attempt in range(3):
        params = _wbi_sign({"mid": uid, "ps": limit, "pn": 1, "order": "pubdate",
                            "platform": "web", "web_location": "1550101"},
                           img_key, sub_key)
        try:
            resp = requests.get("https://api.bilibili.com/x/space/wbi/arc/search",
                                params=params, headers=headers, timeout=25)
        except Exception as e:                      # noqa: BLE001
            log(f"    [warn] 投稿接口网络异常: {type(e).__name__}: {str(e)[:60]}")
            time.sleep(5 * (attempt + 1))
            continue

        if resp.status_code != 200:
            log(f"    [warn] 接口 HTTP {resp.status_code}（风控页），"
                f"{5 * (attempt + 1)}s 后重试")
            time.sleep(5 * (attempt + 1))
            continue

        try:
            j = resp.json()
        except ValueError:
            log(f"    [warn] 接口返回非 JSON（HTTP {resp.status_code}），"
                f"{5 * (attempt + 1)}s 后重试")
            time.sleep(5 * (attempt + 1))
            continue

        code = j.get("code")
        if code == 0:
            vlist = ((j.get("data") or {}).get("list") or {}).get("vlist") or []
            break
        if code in (-799, -412, -509, -352):        # 限流 / 风控，退避重试
            log(f"    [warn] 接口限流 code={code} {j.get('message')}，"
                f"{5 * (attempt + 1)}s 后重试")
            time.sleep(5 * (attempt + 1))
            continue
        log(f"    [warn] 投稿接口失败 code={code} msg={j.get('message')}")
        return 0

    if not vlist:
        log("    [warn] 三次尝试均未取到投稿（B站风控），本次跳过该源")
        return 0

    added = 0
    for v in vlist:
        bvid = v.get("bvid") or ""
        title = (v.get("title") or "").strip()
        if not bvid or not title:
            continue
        link = f"https://www.bilibili.com/video/{bvid}"
        if link in seen:
            continue
        ts = v.get("created")
        date = dt.datetime.fromtimestamp(ts, CST) if ts else dt.datetime.now(CST)
        if cutoff and date < cutoff:
            continue
        seen.add(link)
        bits = []
        if v.get("author"):
            bits.append(str(v["author"]))
        try:
            m, s = divmod(int(v.get("length") or 0), 60)
            if m or s:
                bits.append(f"时长 {m}:{s:02d}")
        except (TypeError, ValueError):
            pass
        if v.get("play"):
            bits.append(f"播放 {v['play']}")
        items.append({"title": title[:180], "link": link, "date": date,
                      "source": name, "desc": " · ".join(bits)})
        added += 1
    log(f"    接口返回 {len(vlist)} 条，纳入 {added} 条")
    return added


# ---------------------------------------------------------------- 行情采集
def collect_market(entries: list, max_items: int) -> list:
    codes, alias = [], {}
    for _fid, _name, payload in entries:
        for tok in payload.split(","):
            tok = tok.strip()
            if not tok:
                continue
            if "=" in tok:
                c, a = tok.split("=", 1)
                c, a = c.strip(), a.strip()
                alias[c] = a
            else:
                c = tok
            if c and c not in codes:
                codes.append(c)
    if not codes:
        log("    [warn] marketsrc 未解析出任何代码")
        return []
    items, now, ok = [], dt.datetime.now(CST), 0
    for i in range(0, len(codes), 30):
        batch = codes[i:i + 30]
        body = fetch(TENCENT_API + ",".join(batch),
                     referer="https://gu.qq.com/", encoding="gbk", retries=1)
        if not body:
            continue
        for line in body.strip().split(";"):
            line = line.strip()
            if not line or "=" not in line:
                continue
            head, _, payload = line.partition("=")
            code = head.strip()
            if code.startswith("v_"):
                code = code[2:]
            f = payload.strip().strip('"').split("~")
            if len(f) < 33:
                continue
            try:
                last, prev, pct = float(f[3]), float(f[4]), float(f[32])
            except (TypeError, ValueError):
                continue
            if last == 0:
                continue
            name = alias.get(code) or f[1]
            arrow = "▲" if pct > 0 else ("▼" if pct < 0 else "—")
            items.append({
                "title": f"{name} {last:,.2f} {arrow}{abs(pct):.2f}%",
                "link": f"https://gu.qq.com/{code}", "date": now, "source": "腾讯行情",
                "desc": f"{name}（{code}）最新 {last:,.2f}，昨收 {prev:,.2f}，涨跌幅 {pct:+.2f}%",
            })
            ok += 1
    log(f"  - 腾讯行情: 成功 {ok}/{len(codes)} 条")
    return items[:max_items]


# ---------------------------------------------------------------- 运行时配置
def write_runtime_config(cfg_path: Path, out_path: Path,
                         url_by_kind: dict) -> bool:
    """
    把伪协议条目替换成本地 HTTP 地址；没有任何自定义源时返回 False。

    url_by_kind: {"policy": "http://127.0.0.1:8899/policy.xml", ...}
    同类只保留第一条（生成器已把它们合并成一个 RSS 文件，
    多条会指向同一个 URL 导致重复抓取）。
    """
    try:
        doc = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    except Exception as e:                          # noqa: BLE001
        log(f"[warn] 读取 {cfg_path} 失败: {e}")
        return False
    feeds = (((doc or {}).get("rss") or {}).get("feeds")) or []
    if not isinstance(feeds, list):
        return False

    out_feeds, seen_kind = [], set()
    for f in feeds:
        if not isinstance(f, dict):
            out_feeds.append(f)
            continue
        url = str(f.get("url", ""))
        kind = next((k for s, (k, *_) in SCHEME_MAP.items() if url.startswith(s)), None)
        if kind is None:
            out_feeds.append(f)
            continue
        if kind in seen_kind:                        # 同一类只保留第一条
            continue
        target = url_by_kind.get(kind)
        if not target:
            continue
        nf = dict(f)
        nf["url"] = target
        nf["max_age_days"] = 0                       # 生成器已做过时效过滤
        out_feeds.append(nf)
        seen_kind.add(kind)

    if not seen_kind:
        log("[运行时配置] 未发现 policysrc:/marketsrc:/bilisrc: 条目，跳过生成")
        return False

    doc["rss"]["feeds"] = out_feeds
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        yaml.safe_dump(doc, allow_unicode=True, sort_keys=False,
                       default_flow_style=False, width=1000),
        encoding="utf-8")
    log(f"[运行时配置] 已生成 {out_path}（替换 {len(seen_kind)} 类自定义源）")
    return True


# ---------------------------------------------------------------- main
def split_entries(feeds: list) -> dict:
    """按伪协议把 rss.feeds 拆成 {kind: [(id, name, payload), ...]}。"""
    out: dict = {k: [] for k, *_ in SCHEME_MAP.values()}
    for f in feeds or []:
        if not isinstance(f, dict) or f.get("enabled") is False:
            continue
        url = str(f.get("url", ""))
        fid, name = str(f.get("id", "?")), str(f.get("name", f.get("id", "?")))
        for scheme, (kind, *_) in SCHEME_MAP.items():
            if url.startswith(scheme):
                out[kind].append((fid, name, url[len(scheme):].strip()))
                break
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/config.yaml")
    ap.add_argument("--out", default="output/custom-feeds")
    ap.add_argument("--serve-base", default=SERVE_BASE)
    ap.add_argument("--max-age-days", type=int, default=14)
    ap.add_argument("--max-items", type=int, default=60)
    ap.add_argument("--only", default="",
                    help="调试用：只处理指定 id 的源（逗号分隔），例如 --only policy-gov")
    args = ap.parse_args()

    cfg_path = Path(args.config)
    if not cfg_path.exists():
        log(f"[error] 找不到 {cfg_path}")
        return 1
    try:
        doc = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except Exception as e:                          # noqa: BLE001
        log(f"[error] 解析 {cfg_path} 失败: {e}")
        return 1
    feeds = ((doc.get("rss") or {}).get("feeds")) or []
    entries = split_entries(feeds)
    log("发现自定义源: " + " / ".join(
        "%s %d 个" % (kind, len(v)) for kind, v in entries.items()))

    only = {s.strip() for s in args.only.split(",") if s.strip()}
    if only:
        entries = {k: [e for e in v if e[0] in only] for k, v in entries.items()}
        total = sum(len(v) for v in entries.values())
        log(f"[调试模式] 只处理: {', '.join(sorted(only))}（匹配到 {total} 个源）")
        if not total:
            log("[调试模式] 没有匹配的源，检查 id 是否写对")
            return 1

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    url_by_kind: dict = {}

    pol = entries.get("policy") or []
    if pol:
        log("")
        log("[政策] 开始收集")
        items = collect_policy(pol, args.max_age_days, args.max_items)
        (out_dir / "policy.xml").write_text(
            build_rss(items, "政策发布", "https://www.gov.cn/zhengce/", "政策发布聚合"),
            encoding="utf-8")
        log(f"[政策] 写入 policy.xml，共 {len(items)} 条")
        url_by_kind["policy"] = f"{args.serve_base}/policy.xml"

    mkt = entries.get("market") or []
    if mkt:
        log("")
        log("[行情] 开始收集")
        items = collect_market(mkt, args.max_items)
        (out_dir / "market.xml").write_text(
            build_rss(items, "行情速览", "https://gu.qq.com/", "行情速览"),
            encoding="utf-8")
        log(f"[行情] 写入 market.xml，共 {len(items)} 条")
        url_by_kind["market"] = f"{args.serve_base}/market.xml"

    bil = entries.get("bili") or []
    if bil:
        log("")
        log("[B站] 开始收集")
        items, seen = [], set()
        cutoff = (dt.datetime.now(CST) - dt.timedelta(days=args.max_age_days)
                  if args.max_age_days else None)
        for fid, name, payload in bil:
            log(f"  - {name}  [{fid}]")
            _collect_bilibili(payload, name, seen, items, cutoff)
        items.sort(key=lambda x: x["date"], reverse=True)
        items = items[:args.max_items]
        (out_dir / "bili.xml").write_text(
            build_rss(items, "B站关注", "https://www.bilibili.com/", "B站 UP 主更新"),
            encoding="utf-8")
        log(f"[B站] 写入 bili.xml，共 {len(items)} 条")
        url_by_kind["bili"] = f"{args.serve_base}/bili.xml"

    log("")
    if only:
        log("[调试模式] 跳过运行时配置生成（不影响仓库配置）")
    else:
        # 注意：必须与原配置放在同一目录！
        # TrendRadar 用 Path(CONFIG_PATH).parent 去定位 timeline.yaml，
        # 放到别处会导致「未知的预设模板」并中断整条流程。
        write_runtime_config(cfg_path, cfg_path.parent / "config.runtime.yaml",
                             url_by_kind)
    log(f"输出目录: {out_dir.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
