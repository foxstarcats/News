# AI・ITニュース ラジオ（自動生成ポッドキャスト）

毎朝自動で最新のAI・ITニュースを集め、**四国めたん（解説役）× ずんだもん（聞き役）** が話し合うポッドキャストを作って、スマホのポッドキャストアプリに届けます。PCの電源は不要です（GitHub上で動きます）。

## しくみ

```
毎朝3時ごろ GitHub Actions が自動起動
  1. RSSで8サイトからニュースを収集（ITmedia AI+、GIGAZINE、TechCrunch など）
  2. Claude（あなたのサブスクリプション）が重要なニュースを6本選び、記事本文を読んで対話台本を作成
  3. VOICEVOX で2人の声を合成し、1本のMP3（約12分）に結合
  4. GitHub Pages に MP3 とポッドキャスト用RSSを公開
        ↓
スマホのポッドキャストアプリが新しい回を自動で受信
```

## ファイル構成

| ファイル | 役割 |
|---|---|
| `config.yaml` | 番組名・声・長さ・ニュース取得元などの設定（ここだけ触ればOK） |
| `podcast/news.py` | RSS収集と記事本文の取得 |
| `podcast/script_writer.py` | Claude でニュース選定と台本作成 |
| `podcast/tts.py` | VOICEVOX で音声合成してMP3にする |
| `podcast/feed.py` | ポッドキャスト用RSSと視聴ページの作成 |
| `podcast/generate.py` | 全体の流れ（メイン） |
| `.github/workflows/daily.yml` | 毎日の自動実行の設定 |

---

## セットアップ手順（初回のみ・約15分）

### 1. Claude の認証トークンを発行する（サブスクリプション利用・追加費用なし）
Claude の Pro / Max / Team / Enterprise プランで動かします。PC のターミナル（PowerShell）で:

```bash
npm install -g @anthropic-ai/claude-code
```

```bash
claude setup-token
```

ブラウザが開くので Claude アカウントでログインすると、`sk-ant-oat...` で始まるトークンが表示されます。コピーしておきます（一度しか表示されません。他人に見せないこと）。

### 2. GitHub にリポジトリを作る
1. https://github.com/new で新しいリポジトリを作成
   - 名前の例: `ai-news-radio`
   - **Public（公開）を選択**（無料で GitHub Pages を使うため。URLを知らない人には見つかりにくい設定にしてあります）
   - README などの追加はしない（空のまま作成）
2. このフォルダの中身をリポジトリにアップロード（Claude に「プッシュして」と頼めば代行できます）

### 3. トークンを登録する
リポジトリの **Settings → Secrets and variables → Actions → New repository secret**
- Name: `CLAUDE_CODE_OAUTH_TOKEN`
- Secret: 手順1でコピーしたトークン

※ トークンには有効期限があります。期限が切れて失敗するようになったら、手順1と3をやり直してください。

### 4. 初回を手動で実行する
**Actions** タブ → 左の「Daily podcast」→「Run workflow」→ 緑のボタン
- 10〜15分ほどで完了します。緑のチェックが付けば成功です。

### 5. GitHub Pages を有効にする
**Settings → Pages** → Source: 「Deploy from a branch」→ Branch: **`gh-pages`** / `(root)` → Save
- 1〜2分後、`https://<ユーザー名>.github.io/<リポジトリ名>/` で視聴ページが開けるようになります。

### 6. スマホで登録する
フィードURL: `https://<ユーザー名>.github.io/<リポジトリ名>/feed.xml`

- **iPhone（Apple Podcasts）**: 「ライブラリ」タブ → 右上の「…」→「URLで番組をフォロー」→ フィードURLを貼り付け
- **Android**: 「Pocket Casts」や「AntennaPod」などのアプリで、検索欄やフィード追加にフィードURLを貼り付け

これで、毎朝新しい回が自動で届きます。

---

## 費用の目安

| 項目 | 費用 |
|---|---|
| GitHub Actions / Pages | 無料（公開リポジトリ） |
| VOICEVOX | 無料（番組説明にクレジットを自動表記済み） |
| Claude | 加入中のプランの利用枠内（追加費用なし。1日2回の呼び出しのみ） |

**合計: 追加費用 0円**

利用枠を節約したい場合は、`config.yaml` の `cli_model` を `sonnet` にします。
Claude API キー（従量課金）で動かしたい場合は、`backend: "api"` にして、Secrets に `ANTHROPIC_API_KEY` を登録し、`daily.yml` の該当行のコメントを外します（Opus 5.5 で月 1,000〜1,800 円程度）。

## カスタマイズ例（`config.yaml`）

- 長さ: `target_minutes`（分）、扱うニュースの数: `topics`
- 声: `speaker_id`（例: 春日部つむぎ=8、青山龍星=13、冥鳴ひまり=14）。キャラクターを変えた場合は `podcast/script_writer.py` の口調設定と、`podcast/feed.py` のクレジット表記も合わせて変更
- 話す速さ: `speed`
- ニュース取得元: `feeds` に RSS の URL を追加・削除
- 配信時刻: `.github/workflows/daily.yml` の `cron`（UTC表記。`17 18 * * *` = 日本時間 3:17）

## ローカルでの動作確認（任意）

VOICEVOX を起動した状態で:

```bash
pip install -r requirements.txt
python -m podcast.generate --site-dir site --sample          # 台本はサンプル（APIキー不要）
python -m podcast.generate --site-dir site --force           # 本番と同じ（claude にログイン済みであること）
```

## 注意点

- 公開リポジトリのため、フィードURLを知っている人は聴けます。検索エンジンやポッドキャストのディレクトリには載らない設定（`noindex` / `itunes:block`）にしてあります。
- 番組は記事の要約と感想で構成しています。記事本文の丸読みはしません。
- GitHub の定期実行は、混雑で数時間遅れることがあります（そのため深夜3時台に設定しています）。
- 失敗した日は GitHub からメールで通知が届きます。Actions タブから再実行できます。
