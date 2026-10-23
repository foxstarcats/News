"""ポッドキャスト用RSS（feed.xml）と簡単な視聴ページ（index.html）を作る。"""

from __future__ import annotations

import html
from email.utils import format_datetime
from datetime import datetime
from xml.sax.saxutils import escape, quoteattr


def show_notes(ep: dict) -> str:
    lines = [ep["summary"], "", "紹介したニュース:"]
    for t in ep.get("topics", []):
        lines.append(f"・{t['title']}（{t['source']}） {t['link']}")
    lines += ["", "音声: VOICEVOX:四国めたん / VOICEVOX:ずんだもん"]
    return "\n".join(lines)


def _fmt_duration(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def build_feed(cfg: dict, episodes: list[dict], base_url: str) -> str:
    p = cfg["podcast"]
    cover = f"{base_url}cover.png"
    items = []
    for ep in episodes:
        notes = show_notes(ep)
        items.append(f"""    <item>
      <title>{escape(ep['title'])}</title>
      <description>{escape(notes)}</description>
      <itunes:summary>{escape(notes)}</itunes:summary>
      <enclosure url={quoteattr(base_url + ep['file'])} length="{ep['bytes']}" type="audio/mpeg"/>
      <guid isPermaLink="false">{escape(ep['guid'])}</guid>
      <pubDate>{format_datetime(datetime.fromisoformat(ep['published']))}</pubDate>
      <itunes:duration>{_fmt_duration(ep['duration'])}</itunes:duration>
      <itunes:explicit>false</itunes:explicit>
    </item>""")
    now = format_datetime(datetime.now().astimezone())
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{escape(p['title'])}</title>
    <link>{escape(base_url)}</link>
    <atom:link href={quoteattr(base_url + 'feed.xml')} rel="self" type="application/rss+xml"/>
    <description>{escape(p['description'])}</description>
    <language>{escape(p['language'])}</language>
    <lastBuildDate>{now}</lastBuildDate>
    <itunes:author>{escape(p['author'])}</itunes:author>
    <itunes:summary>{escape(p['description'])}</itunes:summary>
    <itunes:image href={quoteattr(cover)}/>
    <image><url>{escape(cover)}</url><title>{escape(p['title'])}</title><link>{escape(base_url)}</link></image>
    <itunes:category text="Technology"/>
    <itunes:explicit>false</itunes:explicit>
    <itunes:type>episodic</itunes:type>
    <itunes:block>Yes</itunes:block>
{chr(10).join(items)}
  </channel>
</rss>
"""


def build_index(cfg: dict, episodes: list[dict], base_url: str) -> str:
    p = cfg["podcast"]
    cards = []
    for ep in episodes:
        topics = "".join(
            f'<li><a href="{html.escape(t["link"])}">{html.escape(t["title"])}</a>'
            f' <small>{html.escape(t["source"])}</small></li>'
            for t in ep.get("topics", [])
        )
        cards.append(f"""<article>
  <h2>{html.escape(ep['title'])}</h2>
  <p class="meta">{ep['published'][:10]} ・ {int(ep['duration'] // 60)}分</p>
  <audio controls preload="none" src="{html.escape(ep['file'])}"></audio>
  <p>{html.escape(ep['summary'])}</p>
  <ul>{topics}</ul>
</article>""")
    feed_url = base_url + "feed.xml"
    return f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex">
<title>{html.escape(p['title'])}</title>
<style>
:root{{--bg:#f7f7f5;--fg:#1d1d1f;--muted:#6b6b70;--card:#fff;--accent:#2f6fde}}
@media (prefers-color-scheme:dark){{:root{{--bg:#151517;--fg:#ececef;--muted:#9a9aa2;--card:#212125;--accent:#7aa7ff}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:16px/1.7 system-ui,sans-serif}}
main{{max-width:720px;margin:0 auto;padding:24px 16px}}
img{{width:96px;height:96px;border-radius:16px;float:left;margin-right:16px}}
header{{overflow:hidden;margin-bottom:16px}} h1{{font-size:1.4rem;margin:8px 0}}
article{{background:var(--card);border-radius:14px;padding:16px;margin:16px 0}}
h2{{font-size:1.05rem;margin:0}} .meta,small{{color:var(--muted)}} audio{{width:100%}}
a{{color:var(--accent)}} code{{word-break:break-all;font-size:.85rem}}
</style></head><body><main>
<header><img src="cover.png" alt=""><h1>{html.escape(p['title'])}</h1>
<p>{html.escape(p['description'])}</p></header>
<p>ポッドキャストアプリに次のURLを登録すると、新しい回が自動で届きます:<br><code>{html.escape(feed_url)}</code></p>
{''.join(cards)}
</main></body></html>
"""
