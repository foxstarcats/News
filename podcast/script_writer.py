"""Claude でニュースを選び、2人の対話台本を作る。

呼び出し方は config.yaml の llm.backend で切り替える:
  claude_code … Claude のサブスクリプション（Pro/Max など）で Claude Code CLI を使う（追加費用なし）
  api         … Claude API キーを使う（従量課金）
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile

FALLBACK_BETA = "server-side-fallback-2026-07-01"

SELECT_SCHEMA = {
    "type": "object",
    "properties": {
        "selected_ids": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["selected_ids"],
    "additionalProperties": False,
}

SCRIPT_SCHEMA = {
    "type": "object",
    "properties": {
        "episode_title": {"type": "string"},
        "episode_summary": {"type": "string"},
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "speaker": {"type": "string", "enum": ["host", "guest"]},
                    "text": {"type": "string"},
                },
                "required": ["speaker", "text"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["episode_title", "episode_summary", "lines"],
    "additionalProperties": False,
}


def _call_json(llm: dict, effort: str, system: str, user: str, schema: dict) -> dict:
    if llm.get("backend", "claude_code") == "api":
        return _call_api(llm["api_model"], effort, system, user, schema)
    last_error = None
    for _ in range(2):  # 一時的な失敗に備えて1回だけ再試行
        try:
            return _call_cli(llm["cli_model"], effort, system, user, schema)
        except (RuntimeError, json.JSONDecodeError, subprocess.TimeoutExpired) as e:
            print(f"  [再試行] {e}")
            last_error = e
    raise RuntimeError(f"台本の作成に失敗しました: {last_error}")


def _call_cli(model: str, effort: str, system: str, user: str, schema: dict) -> dict:
    """Claude Code CLI（サブスクリプション認証）で構造化JSONを受け取る。"""
    exe = shutil.which("claude")
    if not exe:
        raise SystemExit("claude コマンドが見つかりません（npm install -g @anthropic-ai/claude-code）")
    cmd = [exe, "-p", "--output-format", "json", "--tools", "", "--no-session-persistence",
           "--model", model, "--effort", effort,
           "--json-schema", json.dumps(schema), "--system-prompt", system]
    # 空のAPIキーがあるとサブスクリプション認証より優先されてしまうため除く
    env = {k: v for k, v in os.environ.items()
           if not (k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN") and not v)}
    # プロジェクトの設定や CLAUDE.md を読み込まないよう、空のフォルダで実行する
    with tempfile.TemporaryDirectory() as cwd:
        proc = subprocess.run(cmd, input=user, capture_output=True, text=True,
                              encoding="utf-8", cwd=cwd, env=env, timeout=1200)
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"CLI の出力を読めません: {proc.stdout[:300]} {proc.stderr[:300]}")
    if out.get("is_error"):
        raise RuntimeError(f"CLI エラー: {out.get('result')}")
    data = out.get("structured_output")
    if data is None:  # 念のため本文からJSONを取り出す
        text = out.get("result", "")
        data = json.loads(text[text.find("{"): text.rfind("}") + 1])
    print(f"  model={model} {out.get('duration_ms', 0) / 1000:.0f}s")
    return data


def _call_api(model: str, effort: str, system: str, user: str, schema: dict) -> dict:
    """Claude API で構造化JSONを受け取る。拒否時は既定のフォールバックモデルに切り替わる。"""
    import anthropic

    client = anthropic.Anthropic()
    with client.beta.messages.stream(
        model=model,
        max_tokens=64000,
        betas=[FALLBACK_BETA],
        fallbacks="default",
        system=system,
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": user}],
    ) as stream:
        message = stream.get_final_message()

    if message.stop_reason == "refusal":
        raise RuntimeError(f"Claude がリクエストを拒否しました: {message.stop_details}")
    if message.stop_reason == "max_tokens":
        raise RuntimeError("出力が長すぎて途中で切れました")

    # フォールバックが起きた場合は、最後に応答したモデルのテキストを使う
    texts: list[str] = []
    for block in message.content:
        if block.type == "fallback":
            texts = []
        elif block.type == "text":
            texts.append(block.text)
    u = message.usage
    print(f"  tokens: in={u.input_tokens} out={u.output_tokens} model={message.model}")
    return json.loads("".join(texts))


def select_topics(cfg: dict, candidates: list[dict]) -> list[dict]:
    n = cfg["episode"]["topics"]
    listing = "\n".join(
        f"[{c['id']}] ({c['source']}) {c['title']} — {c['summary'][:150]}" for c in candidates
    )
    system = "あなたはAI・IT分野に詳しいポッドキャストの編集者です。"
    user = f"""以下は直近のニュース候補です。今日の番組で取り上げる記事を{n}本選んでください。

選び方:
- AI関連を中心に、開発者・ビジネスパーソンが知っておくべきIT全般のニュースも混ぜる
- 話題の重要度・新規性・会話の盛り上がりやすさを重視する
- 同じ出来事を報じた記事が複数あれば1本だけ選ぶ
- AI・IT以外（芸能、一般事件、セール情報など）は選ばない
- 重要度の高い順に並べる

候補:
{listing}"""
    data = _call_json(cfg["llm"], "low", system, user, SELECT_SCHEMA)
    by_id = {c["id"]: c for c in candidates}
    picked = [by_id[i] for i in data["selected_ids"] if i in by_id]
    return picked[:n]


def write_script(cfg: dict, articles: list[dict], date_label: str) -> dict:
    host = cfg["voices"]["host"]["name"]
    guest = cfg["voices"]["guest"]["name"]
    minutes = cfg["episode"]["target_minutes"]
    chars = int(minutes * 330)
    show = cfg["podcast"]["title"]

    system = f"""あなたは人気ポッドキャスト「{show}」の放送作家です。
音声合成で読み上げる、2人の掛け合いの台本を書きます。

登場人物:
- host = {host}: 解説役。ニュースの要点を分かりやすく説明し、背景や業界への影響を語る。落ち着いた丁寧語で、ときどきお嬢様っぽい口調（「〜ですわね」）が混じる。
- guest = {guest}: 聞き役・ツッコミ役。素朴な疑問を投げ、リスナー目線の感想を言う。語尾は「〜のだ」「〜なのだ」。

台本のルール:
- 耳で聴くだけで分かるように書く。URL・記号・絵文字・箇条書き・マークダウンは使わない
- 英語の固有名詞や略語はカタカナで書く（例: OpenAI→オープンエーアイ、GPU→ジーピーユー、GitHub→ギットハブ）。音声合成が正しく読めるようにするため
- 1つのセリフは長くても120文字程度。長い説明は2〜3回に分け、相づちを挟む
- 冒頭は日付（{date_label}）を入れた挨拶と今日のラインナップ紹介、最後は締めの挨拶
- 各ニュースで「何が起きたか」「なぜ重要か」「2人の所感・意見」を話す。単なる読み上げにせず、賛否や今後の予想など会話として盛り上げる
- 事実は与えられた記事の内容だけに基づく。記事にない数字や事実を作らない。推測や意見は意見だと分かる言い方にする
- 全体で日本語およそ{chars}文字（約{minutes}分）

episode_summary は番組説明欄に載せる2〜3文の要約です。"""

    parts = []
    for i, a in enumerate(articles, 1):
        parts.append(f"## ニュース{i}: {a['title']}\n出典: {a['source']}\n\n{a['body']}")
    user = "今日取り上げるニュースです。この順番で台本を書いてください。\n\n" + "\n\n".join(parts)

    script = _call_json(cfg["llm"], cfg["llm"]["effort"], system, user, SCRIPT_SCHEMA)
    script["lines"] = [l for l in script["lines"] if l["text"].strip()]
    return script
