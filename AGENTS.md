# AGENTS.md — myradio の局を開く・運用する AI へ

このリポジトリは「局」です。`index.html`（プレーヤー）が、局の中身（`station.json`、`episodes/`、`character/`、音声）を読んで、HTML の番組として再生します。ビルドの仕組みはありません。置いてあるものを読むだけです。

## 新しい局を開くとき

1. `station.json` を書き換える：`name`、`description`（どんな配信か）、`logo`（なければ null）、`language`、`schedule`、`credits`（声や素材の利用条件で必要なクレジットは必ず入れる）。`comments` はお手本の局のものなので、消すか、自分のリポジトリの値に書き換える（下の「コメント欄」）
2. `logo.svg` を差し替える（お手本のロゴは残さない）。キャラ（`character/`）は、お手本のキャラをそのまま使ってもよい（公序良俗に反しない使い方なら自由。README の「ライセンス」）。別のキャラにするなら下の「キャラパック」
3. `episodes/` のお手本の回を消し、`episodes.json` を `[]` にする
4. 最初の回を作る（下の「台本」「声」）
5. `station.json` の `url` に公開先（`https://<you>.github.io/<repo>/`）を書き、`tools/publish.sh` で公開し、GitHub の Settings → Pages で `gh-pages` ブランチを配信元にする
6. `README.md` を自分の局の紹介に書き換える。冒頭の画像 `docs/screen.jpg` はお手本の局（ものラジオ）の放送画面なので、自分の局の放送画面のスクリーンショットに差し替えるか、画像の行ごと消す。「ON AIR」バッジの局名（`Mono Radio`）とリンク先も自分の局にする

## 台本（episodes/<YYYY-MM-DD>-<言語>.json）

決まりの詳細は [docs/formats.md](docs/formats.md)。要点：

- 話す文は `{"say": 読み上げ用, "show": 字幕用}`。`say` は TTS が読み間違えない形（日本語なら英字の名前をカタカナに）、`show` はふつうの表記
- ニュースごとに `label`（見出し）、`points`（要点）、`lines`（話す文）、`url`（出典）。出典は必ず付ける
- `lines_timed`（文ごとの開始・終了の秒）と `segments`（パートの区切り）は、声を作ったときに書く。声と食い違うと字幕やスライドがずれる
- 事実は出典に書いてあることだけ。URL は実在を確かめたものだけ
- 台本は公開される。台本の元になった資料が個人あての内容でも、その人に関わること（取り組んでいること、予定など）は入れない
- 言語ごとに 1 つ（`-ja`、`-en`）。別の言語を足すときは `station.json` の `languages` と `i18n` も足す

## 声（audio/<YYYY-MM-DD>-<言語>.mp3）

- 1 回分の声を 1 本のファイルにし、`lines_timed` をその秒に合わせる。好きな TTS でよい（OpenAI 形式の `/v1/audio/speech` を呼ぶ形にしておくと差し替えやすい）
- 音声は **git に入れない**（`.gitignore` 済み）。`tools/publish.sh` が直近 `station.json` の `audio.keep_days` 日分だけを `gh-pages` に載せる
- 別の場所に置くなら、台本の JSON に `"audio": "<URL>"` を書く

## 共有カード（share/）

- `tools/publish.sh` が公開のたびに作る（Pillow のある python を `SHARE_PYTHON` に、フォントを `SHARE_FONT` に）。手で作るなら `python3 tools/share.py --url <公開先>` で、回ごと・言語ごとに SNS 用のカード画像（1200×630）と、そのカードを見せる小さなページを作る。Pillow と、日本語の入ったフォント（Noto Sans JP など）が要る
- プレーヤーの「共有」ボタンは、そのページへのリンクを渡す（ページを開いた人は、その回のプレーヤーへそのまま移る）

## キャラパック（character/）

- `character/character.json` に種類と素材を書く（[docs/formats.md](docs/formats.md)）
- `"type": "sprites"`：背景が透明な絵 1 枚（口を閉じて正面）と、口（半開き・開き）や目（まばたき・左右を見る）の小さな差分画像。差分は 1 枚目の絵を画像編集で描き直して作り、変わった範囲（口のまわり・目のまわり）だけを切り出す。奥行きの画像（depth）があると、顔の向きや髪の揺れが付く
- `"type": "clips"`：黙っているときの静止画と、話しているときの短い映像
- 口は、プレーヤーが再生しながら声の大きさに合わせて動かす（音声がこのサイトにあるとき）。音声を別のサイトに置くなら、台本に `mouth` を入れる
- 権利のはっきりした素材だけを使う。AI で作ったキャラはそう書く

## やってはいけないこと

- 音声を main にコミットしない（履歴に残り続ける）
- 他人のサイトの画像を保存してリポジトリに入れない。リンクカードは、そのサイトが共有用に出している画像（OGP）の URL を JSON に書くだけ
- 声や素材のクレジットを消さない
- 秘密の情報（API キー、メールアドレス、家のネットワークの名前）を JSON やツールに書かない

## コメント欄（任意）

回ごとのコメント欄は giscus（GitHub Discussions）で出す。

1. リポジトリの Settings → Features で Discussions をオンにし、`Comments` カテゴリを **Announcement** の形式で作る（新しいスレッドは管理者と giscus だけが立てられ、ほかの人はコメントだけできる）
2. giscus のアプリ（https://github.com/apps/giscus）を、このリポジトリだけに入れる
3. https://giscus.app でリポジトリとカテゴリの ID を調べ、`station.json` の `comments.giscus` に書く
4. `giscus.json` の `origins` を自分の公開先（`https://<you>.github.io`）にする。ほかのサイトが、このリポジトリにコメントを書きこめないようにするため
