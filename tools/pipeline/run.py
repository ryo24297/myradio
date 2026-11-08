#!/usr/bin/env python3
"""ものラジオ: 毎朝の回を作る。 取得 -> 台本(Claude) -> 声(TTS) -> episodes/ に書き出し。

usage:
  python tools/pipeline/run.py                 # 今日の回を作る
  python tools/pipeline/run.py --date 2026-11-08
  python tools/pipeline/run.py --no-audio      # 台本だけ(声と時間配置は作らない)
  python tools/pipeline/run.py --dry-run       # 取得だけして候補を表示

環境変数:
  LLM_PROVIDER       gemini(既定) | claude
  GEMINI_API_KEY     LLM_PROVIDER=gemini のとき必須。GEMINI_MODEL で モデル変更(既定 gemini-3.8-flash)
  ANTHROPIC_API_KEY  LLM_PROVIDER=claude のとき必須。CLAUDE_MODEL でモデル変更
  TTS_PROVIDER       edge(既定) | openai
  TTS_VOICE          edge: ja-JP-NanamiNeural など / openai: voice 名
  OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_TTS_MODEL   TTS_PROVIDER=openai のとき
"""
import argparse, datetime, json, os, re, subprocess, sys, tempfile, time
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
JST = ZoneInfo("Asia/Tokyo")
UA = "Mozilla/5.0 (compatible; MonoRadioBot/0.1)"


def log(*a):
    print(*a, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- 1. 取得
def fetch_candidates(cfg, now):
    import feedparser, requests

    cutoff = now - datetime.timedelta(hours=36)
    seen, result = set(), {}
    for cat in cfg["categories"]:
        if not cat.get("enabled", True):
            continue
        items = []
        for feed in cat["feeds"]:
            try:
                r = requests.get(feed, headers={"User-Agent": UA}, timeout=20)
                parsed = feedparser.parse(r.content)
            except Exception as e:  # 1つの取得元が落ちても全体は止めない
                log(f"[warn] feed失敗 {feed}: {e}")
                continue
            for e in parsed.entries:
                link = e.get("link")
                if not link or link in seen:
                    continue
                t = e.get("published_parsed") or e.get("updated_parsed")
                if t:
                    dt = datetime.datetime(*t[:6], tzinfo=datetime.timezone.utc)
                    if dt < cutoff.astimezone(datetime.timezone.utc):
                        continue
                else:
                    dt = None
                seen.add(link)
                summary = re.sub(r"<[^>]+>", "", e.get("summary", ""))[:400]
                items.append({"title": e.get("title", "").strip(), "url": link,
                              "summary": summary.strip(), "time": dt.isoformat() if dt else None,
                              "site": parsed.feed.get("title", "")})
        items.sort(key=lambda x: x["time"] or "", reverse=True)
        result[cat["id"]] = items[: cat.get("max_items", 2) * 4]
        log(f"[fetch] {cat['label']}: {len(result[cat['id']])}件")
    return result


def og_link(url, fallback_title="", site=""):
    """記事の共有用画像(OGP)のURLを取る。画像自体は保存しない。"""
    import requests
    link = {"url": url, "title": fallback_title, "site": site, "description": "", "image": None, "icon": None}
    try:
        html = requests.get(url, headers={"User-Agent": UA}, timeout=15).text[:200000]
        for key, prop in (("title", "og:title"), ("description", "og:description"),
                          ("image", "og:image"), ("site", "og:site_name")):
            m = (re.search(r'<meta[^>]+property=["\']%s["\'][^>]+content=["\']([^"\']*)' % prop, html, re.I)
                 or re.search(r'<meta[^>]+content=["\']([^"\']*)["\'][^>]+property=["\']%s["\']' % prop, html, re.I))
            if m and m.group(1):
                link[key] = m.group(1)
    except Exception as e:
        log(f"[warn] OGP取得失敗 {url}: {e}")
    return link


# ---------------------------------------------------------------- 2. 台本
SYSTEM = """あなたは朝のニュースラジオ「ものラジオ」の台本作家です。与えられた記事候補だけを元に、日本語の台本をJSONで作ります。
守ること:
- 事実は候補の title/summary に書かれていることだけ。推測・補完・数値の創作は禁止。
- 各ニュースの url は候補の url をそのまま使う。候補にないURLは絶対に書かない。
- 話す文は {"say": 読み上げ用, "show": 字幕用}。say は読み間違えない形(英字の名前・製品名はカタカナ、数字は読みやすく)。show はふつうの表記。1文は短く(40字前後)。
- 1ニュースあたり lines は2〜3文、points は2〜3個(各20字以内)、details は points と同数(各60字以内の補足、書けなければ null)。
- カテゴリごとの style と枚数上限を守る。重要度の高いものを選ぶ。重複は1本にまとめる。
- opening は日付・曜日のあいさつと、きょうの本数の紹介(2文)。closing は注目の1本への言及と、あいさつ(2文)。
- 話す文は必ず {"say": "...", "show": "..."} のオブジェクト。文字列だけの配列は不可。例: "opening": [{"say": "おはようございます、ものラジオです。", "show": "おはようございます、ものラジオです。"}]
- 出力はJSONのみ。説明文やコードフェンスは付けない。
スキーマ:
{"title": "回のタイトル(25字以内)", "opening": [話す文...], "closing": [話す文...], "highlight": 注目ニュースのnews内番号(0始まり),
 "news": [{"category": "カテゴリid", "label": "見出し(20字以内)", "points": [...], "details": [...], "lines": [話す文...], "url": "候補のurl"}]}"""


def build_prompt(cfg, cands, now):
    youbi = "月火水木金土日"[now.weekday()]
    parts = [f"日付: {now.year}年{now.month}月{now.day}日({youbi}曜日)",
             f"全体の上限: {cfg['episode']['max_total_items']}本 / 目標の長さ: 約{cfg['episode']['target_seconds']}秒", ""]
    for cat in cfg["categories"]:
        if not cat.get("enabled", True) or not cands.get(cat["id"]):
            continue
        parts.append(f"## カテゴリ id={cat['id']} 「{cat['label']}」 最大{cat.get('max_items', 2)}本 style: {cat.get('style', '')}")
        for i, c in enumerate(cands[cat["id"]]):
            parts.append(f"- ({i}) {c['title']} | {c['summary']} | {c['url']}")
        parts.append("")
    return "\n".join(parts)


GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
BAD_MODELS = set()


def gemini_models(key):
    """使える Flash 系モデルを API の一覧から集める(軽いもの・安定版を優先)。"""
    import requests
    try:
        r = requests.get(f"{GEMINI_BASE}/models?pageSize=200", headers={"x-goog-api-key": key}, timeout=20)
        names = [m["name"].split("/")[-1] for m in r.json().get("models", [])
                 if "generateContent" in m.get("supportedGenerationMethods", [])]
    except Exception as e:
        log(f"[warn] モデル一覧を取れませんでした: {e}")
        return []
    bad = ("image", "tts", "audio", "live", "embedding", "robotics", "computer", "thinking", "exp", "preview", "customtools")
    flash = [n for n in names if "flash" in n and not any(b in n for b in bad)]
    flash.sort(key=lambda n: ("lite" not in n, n), reverse=False)   # lite を先に
    return flash


def gemini_try(model, prompt, key, tries=2):
    """1つのモデルで試す。成功すれば本文、失敗なら None。"""
    import requests
    url = f"{GEMINI_BASE}/models/{model}:generateContent"
    use_thinking = (os.environ.get("GEMINI_THINKING") or "low") != "off"
    for attempt in range(tries):
        g = {"responseMimeType": "application/json", "temperature": 0.4, "maxOutputTokens": 8192}
        if use_thinking:
            g["thinkingConfig"] = {"thinkingLevel": os.environ.get("GEMINI_THINKING") or "low"}
        body = {"systemInstruction": {"parts": [{"text": SYSTEM}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": g}
        try:
            r = requests.post(url, headers={"x-goog-api-key": key}, json=body, timeout=(15, 60))
        except requests.exceptions.RequestException as e:
            log(f"[warn] {model}: {type(e).__name__}(試行{attempt + 1})")
            time.sleep(3)
            continue
        if r.status_code == 400 and use_thinking and "thinking" in r.text.lower():
            use_thinking = False
            continue
        if r.status_code == 200:
            try:
                return "".join(p.get("text", "") for p in r.json()["candidates"][0]["content"]["parts"])
            except (KeyError, IndexError):
                log(f"[warn] {model}: 応答が空")
                return None
        log(f"[warn] {model}: HTTP {r.status_code}(試行{attempt + 1}) {r.text[:120]!r}")
        if r.status_code in (404, 403, 401):   # このモデルは使えない
            return None
        time.sleep(3)
    return None


def llm_complete(prompt):
    """LLM_PROVIDER で台本の生成元を切り替える: gemini(既定) | claude"""
    provider = (os.environ.get("LLM_PROVIDER") or "gemini")
    if provider == "gemini":
        key = os.environ["GEMINI_API_KEY"]
        first = os.environ.get("GEMINI_MODEL")
        order = ([first] if first else []) + [m for m in gemini_models(key) if m != first]
        order = [m for m in order if m not in BAD_MODELS][:6]
        log(f"[llm] モデル候補: {order}")
        for model in order:
            text = gemini_try(model, prompt, key)
            if text:
                log(f"[llm] 使用モデル: {model}")
                return text
            BAD_MODELS.add(model)   # 同じ実行中は二度と試さない
        raise RuntimeError("Gemini の全モデルで失敗しました(混雑中の可能性。時間をおいて再実行してください)")
    if provider == "claude":
        import anthropic
        msg = anthropic.Anthropic().messages.create(
            model=os.environ.get("CLAUDE_MODEL") or "claude-sonnet-5-5", max_tokens=6000, system=SYSTEM,
            messages=[{"role": "user", "content": prompt}])
        return "".join(b.text for b in msg.content if b.type == "text")
    raise SystemExit(f"未対応の LLM_PROVIDER: {provider}")


def generate_script(cfg, cands, now):
    prompt = build_prompt(cfg, cands, now)
    allowed = {c["url"]: (cat, c) for cat, cs in cands.items() for c in cs}
    last_err = None
    for attempt in range(3):
        text = llm_complete(prompt).strip()
        text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
        try:
            script = normalize_script(json.loads(text))
            validate_script(script, allowed)
            return script, allowed
        except Exception as e:
            last_err = e
            log(f"[warn] 台本の検証に失敗(試行{attempt + 1}): {e}")
            prompt += f"\n\n前回の出力は次の理由で不正でした。直して再出力: {e}"
    raise SystemExit(f"台本を作れませんでした: {last_err}")


def _line(x):
    if isinstance(x, str):
        return {"say": x, "show": x}
    if isinstance(x, dict):
        say = x.get("say") or x.get("text") or x.get("show")
        show = x.get("show") or x.get("text") or x.get("say")
        if say and show:
            return {"say": str(say), "show": str(show)}
    return x


def normalize_script(s):
    """モデルによる形の揺れ(文字列だけの文など)を直す。"""
    if not isinstance(s, dict):
        raise ValueError("JSONの最上位がオブジェクトではない")
    for k in ("opening", "closing"):
        if isinstance(s.get(k), (str, dict)):
            s[k] = [s[k]]
        s[k] = [_line(x) for x in s.get(k) or []]
    for n in s.get("news") or []:
        if isinstance(n.get("lines"), (str, dict)):
            n["lines"] = [n["lines"]]
        n["lines"] = [_line(x) for x in n.get("lines") or []]
        if isinstance(n.get("points"), str):
            n["points"] = [n["points"]]
        if isinstance(n.get("details"), list) and len(n["details"]) != len(n.get("points") or []):
            n.pop("details")   # 数が合わない補足は捨てる
    return s


def validate_script(s, allowed):
    def line_ok(l):
        return isinstance(l, dict) and l.get("say") and l.get("show")
    assert s.get("title") and s["opening"] and s["closing"] and s["news"], "必須項目が足りない"
    assert all(line_ok(l) for l in s["opening"] + s["closing"]), "opening/closing の形が不正"
    for n in s["news"]:
        assert n["url"] in allowed, f"候補にないURL: {n['url']}"
        assert n["label"] and n["points"] and n["lines"] and all(line_ok(l) for l in n["lines"]), "newsの形が不正"
        if n.get("details") is not None:
            assert len(n["details"]) == len(n["points"]), "details と points の数が違う"
    h = s.get("highlight")
    assert h is None or 0 <= h < len(s["news"]), "highlight が範囲外"


# ---------------------------------------------------------------- 3. 声
def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, **kw)


def duration(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)])
    return float(out.stdout.decode().strip())


def tts_one(text, out_path):
    provider = (os.environ.get("TTS_PROVIDER") or "edge")
    if provider == "edge":
        import asyncio, edge_tts
        voice = (os.environ.get("TTS_VOICE") or "ja-JP-NanamiNeural")
        asyncio.run(edge_tts.Communicate(text, voice).save(str(out_path)))
    elif provider == "openai":
        import requests
        base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        r = requests.post(f"{base}/audio/speech", timeout=120,
                          headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
                          json={"model": os.environ.get("OPENAI_TTS_MODEL", "gpt-4o-mini-tts"),
                                "voice": (os.environ.get("TTS_VOICE") or "alloy"), "input": text, "response_format": "mp3"})
        r.raise_for_status()
        out_path.write_bytes(r.content)
    else:
        raise SystemExit(f"未対応の TTS_PROVIDER: {provider}")


def synthesize(script, out_mp3):
    """1文ずつ合成し、長さを足して字幕の時刻を決める。最後に1本へ連結して音量をそろえる。"""
    GAP, LEAD = 0.25, 0.6
    groups = [("opening", None, script["opening"])]
    groups += [("news", i, n["lines"]) for i, n in enumerate(script["news"])]
    groups += [("closing", None, script["closing"])]
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        silence = td / "gap.mp3"
        run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", str(GAP),
             "-c:a", "libmp3lame", "-b:a", "64k", str(silence)])
        lead = td / "lead.mp3"
        run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", str(LEAD),
             "-c:a", "libmp3lame", "-b:a", "64k", str(lead)])
        files, timed, segments = [lead], [], []
        t, k = LEAD, 0
        for part, (kind, idx, lines) in enumerate(groups):
            seg_start = t
            for line in lines:
                f = td / f"s{k:03d}.mp3"
                for attempt in range(3):
                    try:
                        tts_one(line["say"], f)
                        break
                    except Exception as e:
                        if attempt == 2:
                            raise
                        log(f"[warn] TTS再試行: {e}")
                        time.sleep(2)
                d = duration(f)
                timed.append({"start": round(t, 3), "end": round(t + d, 3), "show": line["show"], "part": part})
                files += [f, silence]
                t += d + GAP
                k += 1
            segments.append({"kind": kind, "index": idx, "start": round(seg_start, 3), "end": round(t, 3)})
        lst = td / "list.txt"
        lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in files), encoding="utf8")
        out_mp3.parent.mkdir(parents=True, exist_ok=True)
        # 連結 + ラウドネス正規化(-16 LUFS)。filterは長さを変えない。
        run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
             "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "24000", "-c:a", "libmp3lame", "-b:a", "64k", str(out_mp3)])
    return timed, segments, round(duration(out_mp3), 2)


# ---------------------------------------------------------------- 4. 書き出し
def write_episode(cfg, script, allowed, date, timed, segments, seconds, cats_by_id):
    lang = cfg["episode"]["language"]
    for n in script["news"]:
        cat, cand = allowed[n["url"]]
        n["link"] = og_link(n["url"], cand["title"], cand["site"])
        n["category_label"] = cats_by_id.get(n.pop("category", cat), "")
        if n.get("details") is None:
            n.pop("details", None)
    ep = {"format": "monoradio/news-1", "date": date, "lang": lang, **script}
    if timed:
        ep.update({"seconds": seconds, "lines_timed": timed, "segments": segments})
    ep["made_at"] = datetime.datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S")
    path = ROOT / "episodes" / f"{date}-{lang}.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(ep, ensure_ascii=False, indent=1), encoding="utf8")

    idx_path = ROOT / "episodes.json"
    idx = json.loads(idx_path.read_text(encoding="utf8")) if idx_path.exists() else []
    entry = next((e for e in idx if e["date"] == date), None)
    if not entry:
        entry = {"date": date}
        idx.append(entry)
    entry[lang] = {"title": script["title"], "seconds": seconds}
    idx.sort(key=lambda e: e["date"], reverse=True)
    idx_path.write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf8")
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--config", default=str(ROOT / "config" / "topics.json"))
    ap.add_argument("--no-audio", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    cfg = json.loads(Path(a.config).read_text(encoding="utf8"))
    now = datetime.datetime.now(JST)
    if a.date:
        now = datetime.datetime.fromisoformat(a.date).replace(tzinfo=JST, hour=6)
    date = now.strftime("%Y-%m-%d")

    cands = fetch_candidates(cfg, now)
    if a.dry_run:
        print(json.dumps(cands, ensure_ascii=False, indent=1))
        return
    if not any(cands.values()):
        raise SystemExit("候補記事が1件も取れませんでした")
    script, allowed = generate_script(cfg, cands, now)
    timed = segments = None
    seconds = 0
    if not a.no_audio:
        timed, segments, seconds = synthesize(script, ROOT / "audio" / f"{date}-{cfg['episode']['language']}.mp3")
    cats_by_id = {c["id"]: c["label"] for c in cfg["categories"]}
    p = write_episode(cfg, script, allowed, date, timed, segments, seconds, cats_by_id)
    log(f"[done] {p} ({seconds}秒, {len(script['news'])}本)")


if __name__ == "__main__":
    main()
