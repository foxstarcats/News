"""RSSからニュース候補を集め、選ばれた記事の本文を取得する。"""

from __future__ import annotations

import calendar
import html
import re
import time
from concurrent.futures import ThreadPoolExecutor

import feedparser
import requests
import trafilatura

USER_AGENT = "Mozilla/5.0 (compatible; ai-news-podcast/1.0)"


def _clean(text: str, limit: int) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", html.unescape(text)).strip()
    return text[:limit]


def _published_ts(entry) -> float | None:
    for key in ("published_parsed", "updated_parsed"):
        value = entry.get(key)
        if value:
            return calendar.timegm(value)
    return None


def _fetch_feed(feed: dict) -> list[dict]:
    try:
        resp = requests.get(feed["url"], headers={"User-Agent": USER_AGENT}, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  [skip] {feed['name']}: {e}")
        return []
    parsed = feedparser.parse(resp.content)
    items = []
    for entry in parsed.entries:
        link = entry.get("link")
        title = _clean(entry.get("title", ""), 200)
        if not link or not title:
            continue
        items.append({
            "source": feed["name"],
            "title": title,
            "link": link,
            "summary": _clean(entry.get("summary", ""), 300),
            "published": _published_ts(entry),
        })
    print(f"  {feed['name']}: {len(items)}件")
    return items


def collect_candidates(feeds: list[dict], lookback_hours: float, used_links: set[str],
                       max_candidates: int) -> list[dict]:
    """新しい順に、まだ紹介していない記事を候補として返す。"""
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = pool.map(_fetch_feed, feeds)
    cutoff = time.time() - lookback_hours * 3600
    per_feed = max(5, max_candidates // max(1, len(feeds)) + 3)  # 1サイトに偏らないよう上限
    seen = set(used_links)
    items = []
    for batch in results:
        count = 0
        for item in batch:
            if item["link"] in seen or count >= per_feed:
                continue
            # 日付のない記事は新着扱い。古い記事は除外
            if item["published"] is not None and item["published"] < cutoff:
                continue
            seen.add(item["link"])
            items.append(item)
            count += 1
    items.sort(key=lambda i: i["published"] or time.time(), reverse=True)
    items = items[:max_candidates]
    for idx, item in enumerate(items):
        item["id"] = idx
    return items


def fetch_article_text(url: str, limit: int = 4000) -> str:
    """記事本文を抽出する。取得できなければ空文字。"""
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
        resp.raise_for_status()
        text = trafilatura.extract(resp.text, include_comments=False, include_tables=False) or ""
    except Exception as e:  # 1記事の失敗で全体を止めない
        print(f"  [本文取得失敗] {url}: {e}")
        return ""
    return re.sub(r"\n{3,}", "\n\n", text).strip()[:limit]


def fetch_articles(items: list[dict]) -> list[dict]:
    with ThreadPoolExecutor(max_workers=6) as pool:
        bodies = list(pool.map(lambda i: fetch_article_text(i["link"]), items))
    for item, body in zip(items, bodies):
        item["body"] = body or item["summary"]
    return items
