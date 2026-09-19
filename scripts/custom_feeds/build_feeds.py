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

依赖: requests, beautifulsoup4, lxml, pyyaml
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
import time
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
GOV_API = "https://sousuo.www.gov.cn/search-gov/data"
TENCENT_API = "https://qt.gtimg.cn/q="
SERVE_BASE = "http://127.0.0.1:8899"

ARTICLE_EXT = re.compile(r"\.(?:s?html?|shtml|jsp|aspx|php)(?:\?|$)", re.I)
SKIP_HREF = re.compile(r"(?:^|/)(?:index|default)\.(?:s?html?)$|^javascript:|^mailto:|^#", re.I)


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
def _article_like(title: str, href: str) -> bool:
    if not (8 <= len(title) <= 120):
        return False
    if SKIP_HREF.search(urlparse(href).path or ""):
        return False
    if ARTICLE_EXT.search(href):
        return True
    return href.count("/") >= 3


def detect_items(soup: BeautifulSoup, base_url: str, min_items: int = 3):
    best, best_key = [], (-1, 0)
    for el in soup.find_all(["ul", "div", "table", "tbody", "dl"]):
        links = el.find_all("a", href=True)
        if len(links) < min_items:
            continue
        picked = []
        for a in links:
            title = a.get_text(" ", strip=True)
            href = urljoin(base_url, a["href"])
            if not href.startswith("http") or not _article_like(title, href):
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
                         policy_url: str | None, market_url: str | None) -> bool:
    """把伪协议条目替换成本地 HTTP 地址；没有任何自定义源时返回 False。"""
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
        kind = ("policy" if url.startswith(POLICY_SCHEME)
                else "market" if url.startswith(MARKET_SCHEME) else None)
        if kind is None:
            out_feeds.append(f)
            continue
        if kind in seen_kind:                        # 同一类只保留第一条
            continue
        target = policy_url if kind == "policy" else market_url
        if not target:
            continue
        nf = dict(f)
        nf["url"] = target
        nf["max_age_days"] = 0                       # 生成器已做过时效过滤
        out_feeds.append(nf)
        seen_kind.add(kind)

    if not seen_kind:
        log("[运行时配置] 未发现 policysrc:/marketsrc: 条目，跳过生成")
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
def split_entries(feeds: list):
    pol, mkt = [], []
    for f in feeds or []:
        if not isinstance(f, dict) or f.get("enabled") is False:
            continue
        url = str(f.get("url", ""))
        fid, name = str(f.get("id", "?")), str(f.get("name", f.get("id", "?")))
        if url.startswith(POLICY_SCHEME):
            pol.append((fid, name, url[len(POLICY_SCHEME):].strip()))
        elif url.startswith(MARKET_SCHEME):
            mkt.append((fid, name, url[len(MARKET_SCHEME):].strip()))
    return pol, mkt


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
    pol_entries, mkt_entries = split_entries(feeds)
    log(f"发现自定义源: policysrc {len(pol_entries)} 个 / marketsrc {len(mkt_entries)} 个")

    only = {s.strip() for s in args.only.split(",") if s.strip()}
    if only:
        pol_entries = [e for e in pol_entries if e[0] in only]
        mkt_entries = [e for e in mkt_entries if e[0] in only]
        log(f"[调试模式] 只处理: {', '.join(sorted(only))} "
            f"(匹配到 policy {len(pol_entries)} / market {len(mkt_entries)})")
        if not pol_entries and not mkt_entries:
            log("[调试模式] 没有匹配的源，检查 id 是否写对")
            return 1

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    policy_url = market_url = None

    if pol_entries:
        log("")
        log("[政策] 开始收集")
        items = collect_policy(pol_entries, args.max_age_days, args.max_items)
        (out_dir / "policy.xml").write_text(
            build_rss(items, "政策发布", "https://www.gov.cn/zhengce/", "政策发布聚合"),
            encoding="utf-8")
        log(f"[政策] 写入 policy.xml，共 {len(items)} 条")
        policy_url = f"{args.serve_base}/policy.xml"

    if mkt_entries:
        log("")
        log("[行情] 开始收集")
        items = collect_market(mkt_entries, args.max_items)
        (out_dir / "market.xml").write_text(
            build_rss(items, "行情速览", "https://gu.qq.com/", "行情速览"),
            encoding="utf-8")
        log(f"[行情] 写入 market.xml，共 {len(items)} 条")
        market_url = f"{args.serve_base}/market.xml"

    log("")
    if only:
        log("[调试模式] 跳过运行时配置生成（不影响仓库配置）")
    else:
        write_runtime_config(cfg_path, out_dir / "config.runtime.yaml", policy_url, market_url)
    log(f"输出目录: {out_dir.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
