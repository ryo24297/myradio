"""Share cards: what a link to an episode looks like on SNS and in chat apps.

SNS read a page's meta tags without running its JavaScript, and ignore the part of a link after "#", so the player
(index.html#<date>/<lang>) looks the same for every episode. This makes, for each episode and language,
  share/<date>-<lang>.jpg   a 1200x630 card: the station, the date, the episode title, its topics, the character
  share/<date>-<lang>.html  a small page whose Open Graph / Twitter tags show that card, title and topics; a person
                            who opens it goes straight on to that episode in the player
The player's share button hands out the share/....html link.

usage: python3 tools/share.py [STATION_DIR] [--url BASE_URL] [--font FONT] [--all]
  STATION_DIR  the station folder (default: this repository)
  --url        where the station is published, e.g. https://you.github.io/station/ (default: station.json "url").
               Cards need a full URL to show on SNS
  --font       a font with Japanese (default: env SHARE_FONT, else fonts/NotoSansJP.ttf in the station folder);
               Noto Sans JP (SIL OFL): https://github.com/google/fonts/tree/main/ofl/notosansjp
  --all        make every card again (default: only the missing ones)
  --front      also put the tags into index.html, so a link to the station itself shows a card (the newest episode's).
               tools/publish.sh does this in the copy it publishes; main's index.html stays as it is
Needs Pillow; an SVG logo also needs resvg-py (without it the card has no logo).
"""
import datetime, html, io, json, os, re, sys
from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 630
INK, CAM, TEXT, MUTED, YELLOW, TEAL = (12, 14, 20), (22, 26, 38), (242, 243, 247), (141, 147, 168), (255, 208, 40), (63, 224, 220)
WEEK_JA = "月火水木金土日"


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def font(path, size, weight):
    f = ImageFont.truetype(path, size)
    try: f.set_variation_by_axes([weight])
    except Exception: pass   # not a variable font
    return f


def wrap(draw, text, f, width, max_lines):
    """lines of text that fit the width: Latin words stay whole, Japanese breaks between characters (not before 、。)"""
    tokens = re.findall(r"[A-Za-z0-9][\w.\-'’:/+&]*|\s+|.", text)
    lines, cur = [], ""
    for t in tokens:
        if draw.textlength(cur + t, font=f) <= width or not cur.strip() or t in "、。，．・」』）)!?！？ー":
            cur += t
        else:
            lines.append(cur.rstrip()); cur = t.lstrip()
    if cur.strip(): lines.append(cur.rstrip())
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        while lines[-1] and draw.textlength(lines[-1] + "…", font=f) > width: lines[-1] = lines[-1][:-1]
        lines[-1] += "…"
    return lines


def fit(draw, text, f, width):
    if draw.textlength(text, font=f) <= width: return text
    while text and draw.textlength(text + "…", font=f) > width: text = text[:-1]
    return text + "…"


def logo_image(path, height):
    """the station logo in yellow (an SVG logo is drawn with resvg-py if it is there)"""
    if not path or not os.path.exists(path): return None
    try:
        if path.endswith(".svg"):
            import resvg_py
            png = resvg_py.svg_to_bytes(svg_path=path, height=height * 2)
            im = Image.open(io.BytesIO(bytes(png))).convert("RGBA")
        else:
            im = Image.open(path).convert("RGBA")
    except Exception as e:
        print(f"logo: skipped ({type(e).__name__})"); return None
    im = im.resize((round(im.width * height / im.height), height), Image.LANCZOS)
    solid = Image.new("RGBA", im.size, YELLOW + (255,)); solid.putalpha(im.getchannel("A"))
    return solid


def date_text(d, lang):
    t = datetime.date.fromisoformat(d)
    if lang == "ja": return f"{t.year}年{t.month}月{t.day}日（{WEEK_JA[t.weekday()]}）"
    return t.strftime("%a, %b ") + f"{t.day}, {t.year}"


def card(station, st, ep, lang, char, logo, fpath):
    im = Image.new("RGB", (W, H), INK)
    grid = Image.new("RGBA", (W, H), (0, 0, 0, 0)); g = ImageDraw.Draw(grid)
    for x in range(0, W, 48): g.line([(x, 0), (x, H)], fill=(255, 255, 255, 9))
    for y in range(0, H, 48): g.line([(0, y), (W, y)], fill=(255, 255, 255, 9))
    im.paste(grid, (0, 0), grid)
    d = ImageDraw.Draw(im)
    x0, right = 64, 650

    # station: logo, name, a short bar under it; then the tagline and the date
    x = x0
    if logo: im.paste(logo, (x, 50), logo); x += logo.width + 14
    d.text((x, 44), st("name"), font=font(fpath, 38, 800), fill=YELLOW)
    d.rectangle([x0, 102, x0 + 110, 106], fill=YELLOW)
    y = 124
    if st("tagline"): d.text((x0, y), st("tagline"), font=font(fpath, 24, 700), fill=TEAL); y += 36
    d.text((x0, y), date_text(ep["date"], lang), font=font(fpath, 24, 600), fill=MUTED); y += 54

    # the episode title, then its topics
    ft = font(fpath, 48, 800)
    for line in wrap(d, ep["title"], ft, right - x0, 3):
        d.text((x0, y), line, font=ft, fill=TEXT); y += 62
    y += 14
    fn, fl = font(fpath, 22, 800), font(fpath, 25, 600)
    for j, n in enumerate(ep["news"]):
        if y > H - 64: break
        d.text((x0, y + 2), f"{j + 1:02d}", font=fn, fill=YELLOW)
        d.text((x0 + 44, y), fit(d, n["label"], fl, right - x0 - 44), font=fl, fill=TEXT); y += 38

    # the character, in her camera frame
    cw, chh = 456, 391   # the camera's 896:768
    cx, cy = W - 64 - cw, 112
    cam = Image.new("RGB", (cw, chh), CAM)
    if char:
        c = char.copy(); c.thumbnail((cw, chh), Image.LANCZOS)
        cam.paste(c, ((cw - c.width) // 2, chh - c.height), c)
    im.paste(cam, (cx, cy))
    L, t = 30, 4
    box = lambda a, b, c, e: d.rectangle([min(a, c), min(b, e), max(a, c), max(b, e)], fill=YELLOW)
    for ax, ay, sx, sy in [(cx - 10, cy - 10, 1, 1), (cx + cw + 10, cy - 10, -1, 1),
                           (cx - 10, cy + chh + 10, 1, -1), (cx + cw + 10, cy + chh + 10, -1, -1)]:
        box(ax, ay, ax + sx * L, ay + sy * t)   # the arm along the top / bottom
        box(ax, ay, ax + sx * t, ay + sy * L)   # the arm along the side
    d.text((cx + 16, cy + 12), "● LIVE", font=font(fpath, 18, 800), fill=TEXT)

    # a progress bar along the bottom, as on the player
    d.rectangle([0, H - 8, W, H], fill=(30, 33, 42)); d.rectangle([0, H - 8, int(W * .38), H], fill=YELLOW)
    return im


def page(st, ep, lang, stem, target, base):
    desc = " / ".join(f"{j + 1:02d} {n['label']}" for j, n in enumerate(ep["news"]))
    url = lambda p: base + p if base else p
    e = lambda s: html.escape(s, quote=True)
    locale = {"ja": "ja_JP", "en": "en_US"}.get(lang, lang)
    return f"""<!doctype html>
<html lang="{e(lang)}">
<head>
<meta charset="utf-8">
<title>{e(ep['title'])} | {e(st('name'))}</title>
<meta name="description" content="{e(desc)}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="{e(st('name'))}">
<meta property="og:title" content="{e(ep['title'])}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:image" content="{e(url(f'share/{stem}.jpg'))}">
<meta property="og:image:width" content="{W}">
<meta property="og:image:height" content="{H}">
<meta property="og:url" content="{e(url(f'share/{stem}.html'))}">
<meta property="og:locale" content="{locale}">
<meta name="twitter:card" content="summary_large_image">
<meta http-equiv="refresh" content="0; url={e(target)}">
<script>location.replace({json.dumps(target)})</script>
</head>
<body><a href="{e(target)}">{e(ep['title'])}</a></body>
</html>
"""


def front(root, station, base, newest):
    """the station's own page (index.html): its name and description, with the newest episode's card"""
    ix = os.path.join(root, "index.html")
    if not newest or not os.path.exists(ix): return
    e = lambda s: html.escape(s or "", quote=True)
    lang = station.get("language", "ja")
    locale = {"ja": "ja_JP", "en": "en_US"}.get(lang, lang)
    tags = f"""<!-- share:front -->
<meta name="description" content="{e(station.get('description'))}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{e(station.get('name'))}">
<meta property="og:title" content="{e(station.get('name'))}{(' | ' + e(station['tagline'])) if station.get('tagline') else ''}">
<meta property="og:description" content="{e(station.get('description'))}">
<meta property="og:image" content="{e(base + f'share/{newest}.jpg')}">
<meta property="og:image:width" content="{W}">
<meta property="og:image:height" content="{H}">
<meta property="og:url" content="{e(base)}">
<meta property="og:locale" content="{locale}">
<meta name="twitter:card" content="summary_large_image">
<!-- /share:front -->
"""
    s = re.sub(r"<!-- share:front -->.*?<!-- /share:front -->\n?", "", open(ix).read(), flags=re.S)
    open(ix, "w").write(s.replace("</head>", tags + "</head>", 1))
    print(f"share: index.html shows {newest}")


def main():
    args = [a for i, a in enumerate(sys.argv[1:], 1) if not a.startswith("--") and sys.argv[i - 1] not in ("--url", "--font")]
    root = os.path.abspath(args[0] if args else os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    station = json.load(open(os.path.join(root, "station.json")))
    base = arg("--url", station.get("url") or "")
    if base and not base.endswith("/"): base += "/"
    if not base: print("note: no --url / station.json url: SNS need a full URL for the card image")
    fpath = arg("--font", os.environ.get("SHARE_FONT", os.path.join(root, "fonts", "NotoSansJP.ttf")))
    pack = station.get("character", {}).get("pack")
    char = None
    if pack and os.path.exists(os.path.join(root, pack)):
        cj = json.load(open(os.path.join(root, pack)))
        if cj.get("base"): char = Image.open(os.path.join(root, os.path.dirname(pack), cj["base"])).convert("RGBA")
    os.makedirs(os.path.join(root, "share"), exist_ok=True)
    made, newest = 0, None
    for entry in json.load(open(os.path.join(root, station.get("episodes", "episodes.json")))):   # newest first
        date = entry["date"]
        langs = [k for k in entry if k != "date" and isinstance(entry[k], dict)] or [None]
        for lang in langs:
            stem = f"{date}-{lang}" if lang else date
            if not ("--all" in sys.argv) and os.path.exists(os.path.join(root, "share", f"{stem}.html")): continue
            ep = json.load(open(os.path.join(root, "episodes", f"{stem}.json")))
            L = lang or ep.get("lang") or station.get("language", "ja")
            st = lambda k: station.get("i18n", {}).get(L, {}).get(k, station.get(k))
            logo = logo_image(os.path.join(root, station["logo"]) if station.get("logo") else None, 40)
            card(station, st, ep, L, char, logo, fpath).save(os.path.join(root, "share", f"{stem}.jpg"), quality=88, optimize=True)
            target = f"../#{date}/{lang}" if lang else f"../#{date}"
            open(os.path.join(root, "share", f"{stem}.html"), "w").write(page(st, ep, L, stem, target, base))
            made += 1
        if newest is None:
            pick = station.get("language") if station.get("language") in langs else langs[0]
            stem = f"{date}-{pick}" if pick else date
            if os.path.exists(os.path.join(root, "share", f"{stem}.jpg")): newest = stem
    print(f"share: {made} made")
    if "--front" in sys.argv and base: front(root, station, base, newest)


if __name__ == "__main__":
    main()
