# JSON の決まり（この局のプレーヤーが読む形）

局どうしでそろえる必要はありません。ここに書いてあるのは、このリポジトリの `index.html` が読む形です。形を変えたら、プレーヤーも合わせて直してください。

## station.json（`myradio/station-1`）

| 欄 | 中身 |
|---|---|
| `format` | `"myradio/station-1"` |
| `name` | 局の名前 |
| `description` | どんな配信か（1〜2 文） |
| `logo` | ロゴの画像（なければ `null`） |
| `url` | 局を公開している場所（`https://you.github.io/station/`）。共有カード（`tools/share.py`）が SNS に画像を見せるのに要る |
| `repo` | 局のリポジトリ（`https://github.com/you/station`）。オープニングの局名を押すと、このアドレスがコピーされる |
| `language` | おもな言語（`"ja"` など） |
| `languages` | 回を出している言語の並び（`["ja", "en"]`）。2 つ以上あると、プレーヤーに言語の切り替えが出る |
| `tagline` | 番組の短い副題（オープニングに出る） |
| `schedule` | `{"every": "day", "time": "06:10", "timezone": "Asia/Tokyo"}` など。いつごろ新しい回が出るか |
| `episodes` | 回の一覧のファイル（`"episodes.json"`） |
| `character` | `{"pack": "character/character.json", "thumbnail": …, "note": …}` |
| `credits` | 表示するクレジットの並び（声や素材の利用条件で必要なものは必ず）。ページの下に出る |
| `caster` | （任意）キャラの枠の右下に小さく出す名札。キャラの名前や、声の名前（例：`声：COEIROINK:リリンちゃん`）など短く。書かなければ何も出ない。言語で変えるときは `i18n` にも |
| `audio` | `{"dir": "audio", "keep_days": 30}`（`tools/publish.sh` が使う） |
| `weather` | （任意）`true` で、ニュース中のキャラの左に今日の天気を出す。場所は見る人のブラウザのタイムゾーンからおおまかに決め、地名を押すと、ほかの都市か、見る人の現在地（このときだけブラウザが許可を聞く）を選べる。天気は Open-Meteo（キー不要、クレジット表示が条件） |
| `comments` | （任意）回ごとのコメント欄。`{"giscus": {"repo", "repoId", "category", "categoryId"}}`。同じ日の回（言語ちがいも）で 1 つの GitHub Discussions のスレッドを使い、最初のコメントで giscus が自動で立てる。見る人が「コメント」を開くまで giscus.app は読みこまない。値は https://giscus.app で調べられる。書かなければコメント欄は出ない |
| `i18n` | 言語ごとに差し替える欄：`{"en": {"name", "tagline", "description", "credits", "caster"}}`（声が言語で違えば、クレジットも言語ごとに） |

## episodes.json

新しい順の一覧。日付ごとに、ある言語の題と長さ：`[{"date": "2026-11-04", "ja": {"title": "…", "seconds": 79.5}, "en": {"title": "…", "seconds": 77.3}}, …]`

1 つの言語だけの局は、`[{"date": "2026-11-04", "title": "…", "seconds": 79.5}, …]` でもよい（そのときのファイル名は言語なしの `<日付>.json`、`<日付>.mp3`）。

## episodes/<YYYY-MM-DD>-<言語>.json（ものラジオの形：`monoradio/news-1`）

言語ごとに 1 つ（`2026-11-04-ja.json`、`2026-11-04-en.json`）。声は `audio/<日付>-<言語>.mp3`。`lang` 欄にその言語が入る。

| 欄 | 中身 |
|---|---|
| `format`、`date`、`title` | 形の名前、日付、番組タイトル |
| `opening`、`closing` | 話す文の並び |
| `news[]` | `label`（見出し）、`points`（要点の並び）、`lines`（話す文の並び）、`url`（出典）、`link`（リンクカード） |
| `news[].details` | （任意）`points` と同じ並びの、要点ごとのくわしい説明（ない要点は `null`）。画面の要点を押すと、その下に説明が開く（ないときは「詳細なし」） |
| `highlight` | （任意）締めで取り上げる「今日の注目」が `news` の何番目か（0 から）。締めの画面にそのニュースの画像が出る |
| 話す文 | `{"say": "読み上げ用", "show": "字幕用"}` |
| `news[].link` | `{"url", "title", "site", "description", "image", "icon"}`。`image` はそのサイトが共有用に出している画像（OGP）の URL。保存はしない。開けなかったときは `status`（404 など）。出典以外の記事を使ったときは `found_by: "search"` で、元の出典は `news[].source_link` |
| `seconds` | 声の長さ（秒） |
| `lines_timed[]` | `{"start", "end", "show", "part"}`：文ごとの開始・終了の秒（声に合わせる） |
| `segments[]` | `{"kind": "opening" \| "news" \| "closing", "index", "start", "end"}`：パートの区切り |
| `audio` | （任意）声の URL。なければ `audio/<日付>.mp3` |
| `mouth` | （任意）`{"fps": 30, "levels": "0012210…"}`：口の開き具合（0 閉じ・1 半開き・2 開き）を 1 コマ 1 文字で。ふだんは要らない（音声がこのサイトにあれば、プレーヤーが再生しながら声の大きさから作る）。音声を別のサイトに置くときに使う |
| `made_at` | 作った時刻（音声のキャッシュ避けにも使う） |

## character/character.json（`myradio/character-1`）

種類は 2 つあります。

### `"type": "sprites"`（差分画像。ものラジオはこちら）

```json
{
 "format": "myradio/character-1",
 "type": "sprites",
 "size": [896, 768],
 "background": "#161a26",
 "base": "base.png",
 "depth": "depth.png",
 "parts": {"mouth_half": {"src": "mouth_half.png", "x": 430, "y": 318}, "...": {}},
 "mouth": {"1": "mouth_half", "2": "mouth_open"},
 "eye": {"blink": "blink", "half": "half_blink"},
 "expressions": {"smile": {"mouth": "smile_mouth"}}
}
```

- `base`：口を閉じて正面を見ている、背景が透明な絵
- `parts`：`base` の `x`, `y` の位置に重ねる小さな画像。口の画像は口のまわりだけ、目の画像は目のまわりだけにしておくと、口と目を自由に組み合わせられる
- `mouth`：口の開き具合（1 = 半開き、2 = 開き）に使う画像
- `eye`：まばたき（`blink` 閉じた目、`half` 半目。`half` があると「半目→閉じ→半目」と滑らかになる）。`left`・`right` に左右を見る目の画像を書くと、リンクカードのほうを目で追う（なくてもよい。ないときは正面のまま）
- `expressions`：表情ごとに、使う目と口の画像（`{"eye", "mouth"}`、片方だけでもよい）。いまはエンディングで `smile` を使う
- `depth`（任意）：奥行きの白黒画像（手前ほど白い）。顔の向き、呼吸、後ろ髪の揺れに使う。キャラの中での「奥から何番目か」の割合（いちばん奥 0、いちばん手前 1、背景 0）で入れておくと、どの深度推定モデルで作っても同じように動く
- `background`：キャラの後ろの色

### `"type": "clips"`（短い映像をつなぐ）

```json
{"format": "myradio/character-1", "type": "clips", "idle": "idle.webp", "talk": ["u1.mp4", "u2.mp4"], "background": "#161a26"}
```

- `idle`：黙っているときの静止画。`talk`：話しているあいだ流す短い映像（始めと終わりを `idle` と同じ姿勢にする）
