"""1日分のエピソードを作り、配信用フォルダ（site/）を更新する。

使い方:
  python -m podcast.generate --site-dir site            # 本番
  python -m podcast.generate --site-dir site --sample   # 台本をサンプルにして音声と配信だけ試す
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import yaml

from . import feed, news, tts

ROOT = Path(__file__).resolve().parent.parent
JST = timezone(timedelta(hours=9))
WEEKDAYS = "月火水木金土日"


def load_json(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_pages(cfg: dict, site: Path, episodes: list[dict], base_url: str) -> None:
    (site / "feed.xml").write_text(feed.build_feed(cfg, episodes, base_url), encoding="utf-8")
    (site / "index.html").write_text(feed.build_index(cfg, episodes, base_url), encoding="utf-8")
    shutil.copyfile(ROOT / "assets" / "cover.png", site / "cover.png")
    (site / ".nojekyll").touch()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site-dir", default="site")
    ap.add_argument("--config", default=str(ROOT / "config.yaml"))
    ap.add_argument("--force", action="store_true", help="今日の回があっても作り直す")
    ap.add_argument("--sample", action="store_true", help="Claude を使わずサンプル台本で試す")
    ap.add_argument("--rebuild-feed", action="store_true", help="新しい回は作らずRSSとページだけ作り直す")
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    site = Path(args.site_dir)
    (site / "episodes").mkdir(parents=True, exist_ok=True)
    # ドメインは小文字にそろえる。パス（リポジトリ名）は大文字小文字を区別するのでそのまま
    url = urlsplit(os.environ.get("SITE_BASE_URL", "http://localhost:8000/"))
    base_url = urlunsplit(url._replace(netloc=url.netloc.lower()))
    if not base_url.endswith("/"):
        base_url += "/"
    engine_url = os.environ.get("VOICEVOX_URL", "http://127.0.0.1:50021")

    now = datetime.now(JST)
    stamp = now.strftime("%Y%m%d")
    date_label = f"{now.month}月{now.day}日 {WEEKDAYS[now.weekday()]}曜日"

    episodes = load_json(site / "episodes.json", [])
    state = load_json(site / "state.json", {"used_links": []})
    if args.rebuild_feed:
        write_pages(cfg, site, episodes, base_url)
        print(f"RSSとページを作り直しました（{len(episodes)}回分）")
        return 0
    if any(ep["guid"] == stamp for ep in episodes) and not args.force:
        print(f"{stamp} の回は作成済みです（作り直す場合は --force）")
        return 0

    # 1. 台本を用意する
    if args.sample:
        script = load_json(ROOT / "podcast" / "sample_script.json", None)
        articles = []
    else:
        from . import script_writer

        print("ニュースを収集中...")
        n = cfg["news"]
        candidates = news.collect_candidates(n["feeds"], n["lookback_hours"],
                                             set(state["used_links"]), n["max_candidates"])
        print(f"  候補 {len(candidates)}件")
        if len(candidates) < 3:
            print("新しいニュースが少ないため、今日は作成をスキップします")
            return 0
        print("取り上げるニュースを選定中...")
        picked = script_writer.select_topics(cfg, candidates)
        for a in picked:
            print(f"  - {a['title']} ({a['source']})")
        print("記事本文を取得中...")
        articles = news.fetch_articles(picked)
        print("台本を作成中...")
        script = script_writer.write_script(cfg, articles, date_label)
        print(f"  {script['episode_title']} / {len(script['lines'])}セリフ")

    # 2. 音声を作る
    print("音声を合成中...")
    rel = f"episodes/{stamp}.mp3"
    duration = tts.render_episode(script, cfg, engine_url, str(site / rel))
    save_json(site / "episodes" / f"{stamp}.json", script)

    # 3. エピソード一覧・RSS・ページを更新する
    episode = {
        "guid": stamp,
        "title": f"{now.month}/{now.day} {script['episode_title']}",
        "summary": script["episode_summary"],
        "file": rel,
        "bytes": (site / rel).stat().st_size,
        "duration": round(duration, 1),
        "published": now.isoformat(timespec="seconds"),
        "topics": [{"title": a["title"], "source": a["source"], "link": a["link"]} for a in articles],
    }
    episodes = [ep for ep in episodes if ep["guid"] != stamp]
    episodes.insert(0, episode)
    keep = cfg["podcast"]["keep_episodes"]
    for old in episodes[keep:]:
        for suffix in (".mp3", ".json"):
            (site / "episodes" / f"{old['guid']}{suffix}").unlink(missing_ok=True)
    episodes = episodes[:keep]

    state["used_links"] = ([a["link"] for a in articles] + state["used_links"])[:2000]
    save_json(site / "episodes.json", episodes)
    save_json(site / "state.json", state)
    write_pages(cfg, site, episodes, base_url)

    print(f"完了: {episode['title']}（{duration / 60:.1f}分, {episode['bytes'] / 1e6:.1f}MB）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
