#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自定义 RSS 生成器 —— 政策 + 行情
================================================================
读取 config/custom_feeds.yaml，生成标准 RSS 2.0 文件，供 TrendRadar 消费。

用法:
    python scripts/custom_feeds/build_feeds.py \
        --config config/custom_feeds.yaml \
        --out output/custom-feeds

设计要点:
  * 政策源两种类型：
      - gov_search : 中国政府网「政策文件库」官方 JSON 接口（最稳，推荐）
      - html       : 通用列表页，自动探测列表结构，无需手写选择器
  * 行情源用腾讯行情接口 qt.gtimg.cn，覆盖 A股/港股/美股/指数，
    零重依赖（不需要 akshare / yfinance），且在境外 GitHub Actions 上实测可用。
    注意：东方财富接口（push2.eastmoney.com）在境外会被断开，故不使用。
  * 单个源失败不影响整体，跳过并在日志中报告。
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
from urllib.parse import urljoin, urlparse
from xml.sax.saxutils import escape

import requests
import yaml
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}
CST = dt.timezone(dt.timedelta(hours=8))          # 中国标准时间
ARTICLE_EXT = re.compile(r"\.(?:s?html?|shtml|jsp|aspx|php)(?:\?|$)", re.I)
SKIP_HREF = re.compile(r"(?:^|/)(?:index|default)\.(?:s?html?)$|^javascript:|^mailto:|^#", re.I)


def log(*a) -> None:
    print(*a, flush=True)


# ---------------------------------------------------------------- 抓取
def fetch(url: str, timeout: int = 25, retries: int = 2,
          referer: str | None = None, encoding: str | None = None) -> str | None:
    """带重试与编码猜测的 GET。失败返回 None（不抛异常）。"""
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
    return href.count("/") >= 3          # 无扩展名但路径够深，也当文章


def detect_items(soup: BeautifulSoup, base_url: str, min_items: int = 3):
    """
    自动探测列表结构。返回 [(title, abs_url, container_element), ...]
    打分: 文章型链接越多越好；总链接越少越好（以排除整页导航）。
    """
    best: list = []
    best_key = (-1, 0)
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
            container = a.find_parent(["li", "tr", "dd", "div"]) or a
            picked.append((title, href, container))
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
    for rx in _DATE_RES:
        m = rx.search(text or "")
        if m:
            g = [int(x) for x in m.groups()]
            try:
                return dt.datetime(g[0], g[1], g[2] if len(g) > 2 else 1, 9, 0, tzinfo=CST)
            except ValueError:
                pass
    for rx in _URL_DATE_RES:
        m = rx.search(url or "")
        if m:
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


# ---------------------------------------------------------------- 政策
def _collect_gov_search(src: dict, seen: set, items: list, cutoff) -> int:
    """
    中国政府网「政策文件库」JSON 接口（sousuo.www.gov.cn）。
    分类 catMap: gongwen 国务院公文 / bumenfile 部门文件 / otherfile 其他 / gongbao 公报
    """
    params = {
        "t": src.get("t", "zhengcelibrary"), "q": "", "timetype": "timeqb",
        "sort": "pubtime", "sortType": "1", "searchfield": "title",
        "p": 1, "n": int(src.get("per_page", 20)),
    }
    try:
        r = requests.get(src["url"], params=params,
                         headers={**HEADERS, "Referer": "https://www.gov.cn/"}, timeout=25)
        j = r.json()
    except Exception as e:                           # noqa: BLE001
        log(f"    [warn] 接口失败: {type(e).__name__}: {str(e)[:60]}")
        return 0
    cat_map = ((j.get("searchVO") or {}).get("catMap") or {})
    added = 0
    for cat in src.get("categories") or ["gongwen"]:
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
            items.append({
                "title": (f"{doc_no} {title}" if doc_no else title)[:180],
                "link": link, "date": date,
                "source": src.get("name", "国务院政策文件库"),
                "desc": (it.get("summary") or "").strip()[:300],
            })
            added += 1
    return added


def collect_policy(cfg: dict) -> list:
    items, seen = [], set()
    max_age = int(cfg.get("max_age_days", 0) or 0)
    cutoff = dt.datetime.now(CST) - dt.timedelta(days=max_age) if max_age else None

    for src in cfg.get("sources", []):
        if not src.get("enabled", True):
            log(f"  - {src.get('name')}  [跳过: enabled=false]")
            continue
        name, url = src.get("name", src.get("id", "?")), src.get("url", "")
        base = src.get("base") or url
        log(f"  - {name}")
        if src.get("type") == "gov_search":
            log(f"    纳入 {_collect_gov_search(src, seen, items, cutoff)} 条")
            continue
        body = fetch(url)
        if not body:
            continue
        soup = BeautifulSoup(body, "lxml")
        picked = []
        if src.get("item_selector"):
            for el in soup.select(src["item_selector"]):
                a = el.find("a", href=True)
                if a and len(a.get_text(strip=True)) >= 6:
                    picked.append((a.get_text(" ", strip=True),
                                   urljoin(base, a["href"]), el))
        if not picked:
            picked = detect_items(soup, base)
        if not picked:
            log("    [warn] 未探测到列表，跳过（可在配置里手填 item_selector）")
            continue
        added = 0
        for title, href, container in picked:
            if href in seen:
                continue
            date = parse_date(container.get_text(" ", strip=True), href)
            if cutoff and date < cutoff:
                continue
            seen.add(href)
            items.append({"title": title, "link": href, "date": date,
                          "source": name, "desc": ""})
            added += 1
        log(f"    探测到 {len(picked)} 条，纳入 {added} 条")

    items.sort(key=lambda x: x["date"], reverse=True)
    return items[: int(cfg.get("max_items", 40))]


# ---------------------------------------------------------------- 行情
def collect_market(cfg: dict) -> list:
    """
    腾讯行情接口 qt.gtimg.cn。
    返回行格式: v_<code>="<市场>~<名称>~<代码>~<现价>~<昨收>~<今开>~...~<涨跌额>[31]~<涨跌幅%>[32]~..."
    代码规则: A股 sh600519 / sz000001；A股指数 sh000001 / sz399001；
              港股 hk00700；港股指数 hkHSI / hkHSTECH；美股 usAAPL
    """
    quotes = cfg.get("quotes") or []
    if not quotes:
        log("    [warn] 未配置 quotes，跳过")
        return []
    items, now = [], dt.datetime.now(CST)
    codes = [str(q["code"]).strip() for q in quotes if q.get("code")]
    name_of = {str(q["code"]).strip(): (q.get("name") or q["code"]) for q in quotes if q.get("code")}

    ok = 0
    for i in range(0, len(codes), 30):               # 分批，避免 URL 过长
        batch = codes[i:i + 30]
        url = "https://qt.gtimg.cn/q=" + ",".join(batch)
        body = fetch(url, referer="https://gu.qq.com/", encoding="gbk", retries=1)
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
            name = name_of.get(code) or f[1]
            arrow = "▲" if pct > 0 else ("▼" if pct < 0 else "—")
            items.append({
                "title": f"{name} {last:,.2f} {arrow}{abs(pct):.2f}%",
                "link": f"https://gu.qq.com/{code}",
                "date": now,
                "source": "腾讯行情",
                "desc": f"{name}（{code}）最新 {last:,.2f}，昨收 {prev:,.2f}，涨跌幅 {pct:+.2f}%",
            })
            ok += 1
    log(f"  - 腾讯行情: 成功 {ok}/{len(codes)} 条")
    return items[: int(cfg.get("max_items", 40))]


# ---------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/custom_feeds.yaml")
    ap.add_argument("--out", default="output/custom-feeds")
    args = ap.parse_args()

    cfg_path = Path(args.config)
    if not cfg_path.exists():
        log(f"[error] 找不到配置文件 {cfg_path}")
        return 1
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    written = []
    pol = cfg.get("policy") or {}
    if pol.get("enabled", True):
        log("[政策] 开始收集")
        items = collect_policy(pol)
        f = pol.get("feed") or {}
        (out_dir / "policy.xml").write_text(
            build_rss(items, f.get("title", "政策发布"),
                      f.get("link", "https://www.gov.cn/zhengce/"), "政策发布聚合"),
            encoding="utf-8")
        written.append(("policy.xml", len(items)))
        log(f"[政策] 写入 policy.xml，共 {len(items)} 条")

    mkt = cfg.get("market") or {}
    if mkt.get("enabled", True):
        log("[行情] 开始收集")
        items = collect_market(mkt)
        f = mkt.get("feed") or {}
        (out_dir / "market.xml").write_text(
            build_rss(items, f.get("title", "行情速览"),
                      f.get("link", "https://gu.qq.com/"), "行情速览"),
            encoding="utf-8")
        written.append(("market.xml", len(items)))
        log(f"[行情] 写入 market.xml，共 {len(items)} 条")

    log("")
    log("=== 汇总 ===")
    for name, n in written:
        log(f"  {name:<14} {n} 条")
    log(f"输出目录: {out_dir.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
