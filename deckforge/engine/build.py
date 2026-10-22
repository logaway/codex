#!/usr/bin/env python3
"""
build.py — 把「內容 IR + 設計契約」編譯成 SVG 頁面。

設計前提：LLM 不寫任何坐標。它只產出「這頁是什麼形狀、裡面有什麼字」，
所有幾何（欄寬、間距、行高、換行、字號降級、縱向配置）由本腳本計算。

架構要點：Canvas 只累積 display list（後端無關的圖元），SVG 字串在最後
才生成。這讓「先排版、再整體挪動」成為可能 —— 縱向節奏就靠這個。
"""

import argparse
import json
import os
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.abspath(__file__))
CONTRACTS = os.path.join(HERE, "..", "contracts")

CJK_RANGES = [(0x1100, 0x115F), (0x2E80, 0xA4CF), (0xAC00, 0xD7A3),
              (0xF900, 0xFAFF), (0xFE30, 0xFE6F), (0xFF00, 0xFF60),
              (0xFFE0, 0xFFE6), (0x3000, 0x303F)]
NO_LINE_START = "，。、；：？！）』」》〉】…—·%"
NO_LINE_END = "（『「《〈【"
ROLES = ("display", "lead", "metric", "h2", "h3", "body", "eyebrow", "caption")


def is_cjk(ch):
    o = ord(ch)
    return any(a <= o <= b for a, b in CJK_RANGES)


def char_w(ch, size):
    if is_cjk(ch):
        return size
    if ch.isdigit():
        return size * 0.55
    if ch.isupper():
        return size * 0.62
    if ch == " ":
        return size * 0.28
    return size * 0.52


def measure(s, size, tracking=0.0):
    return sum(char_w(c, size) for c in s) + max(0, len(s) - 1) * tracking


def wrap(text, size, max_w, tracking=0.0):
    tokens, buf = [], ""
    for ch in text:
        if is_cjk(ch) or ch in NO_LINE_START or ch in NO_LINE_END:
            if buf:
                tokens.append(buf); buf = ""
            tokens.append(ch)
        elif ch == " ":
            if buf:
                tokens.append(buf); buf = ""
            tokens.append(" ")
        else:
            buf += ch
    if buf:
        tokens.append(buf)

    lines, cur, cur_w = [], "", 0.0
    for tok in tokens:
        w = measure(tok, size, tracking)
        if cur_w + w > max_w and cur:
            if tok in NO_LINE_START:
                lines.append(cur + tok); cur, cur_w = "", 0.0; continue
            if cur[-1] in NO_LINE_END:
                moved = cur[-1]
                lines.append(cur[:-1])
                cur, cur_w = moved + tok, measure(moved + tok, size, tracking)
                continue
            lines.append(cur)
            cur, cur_w = tok.lstrip(), w
        else:
            cur += tok; cur_w += w
    if cur.strip():
        lines.append(cur)
    return lines


class Contract:
    def __init__(self, data):
        self.d = data
        self.grid = data["grid"]
        self.W = data["canvas"]["w"]; self.H = data["canvas"]["h"]
        self.mx = data["margin"]["x"]
        self.mtop = data["margin"]["top"]; self.mbot = data["margin"]["bottom"]
        self.gutter = data["gutter"]
        self.c = data["colors"]; self.f = data["fonts"]; self.t = data["type"]
        missing = [r for r in ROLES if r not in self.t]
        if missing:
            raise ValueError(f"契約 {data['name']} 缺少字級角色：{missing}")

    def snap(self, v):
        return round(v / self.grid) * self.grid

    @property
    def content_w(self):
        return self.W - self.mx * 2

    @property
    def band_bottom(self):
        return self.H - self.mbot - self.grid * 4

    def columns(self, n):
        tg = self.gutter * (n - 1)
        w = int((self.content_w - tg) // n // self.grid) * self.grid
        start = self.snap(self.mx + (self.content_w - (w * n + tg)) / 2)
        return [(start + i * (w + self.gutter), w) for i in range(n)], w

    def role(self, name):
        r = dict(self.t[name])
        r.setdefault("tracking", 0); r.setdefault("weight", 400)
        r.setdefault("font", "sans"); r.setdefault("color", "body")
        return r

    def lh(self, size, factor=None):
        """行距隨字號反向收緊 —— 大字用正文的行距會鬆散得像散開的標語。"""
        if factor is None:
            factor = max(1.16, 1.75 - size / 100)
        return self.snap(size * factor) or self.grid

    def advance(self, prev_role, next_role, extra=0):
        a = self.role(prev_role)["size"]; b = self.role(next_role)["size"]
        return self.snap(a * 0.2 + b * 0.8 + max(a, b) * 0.45 + extra + self.grid / 2)


class Canvas:
    """只累積 display list；SVG 最後才生成，因此可以事後整體挪動。"""

    def __init__(self, ct, meta=None):
        self.ct = ct; self.ops = []; self.warnings = []; self.meta = meta or {}

    def rect(self, x, y, w, h, fill, rx=0):
        self.ops.append({"op": "rect", "x": x, "y": y, "w": w, "h": h,
                         "fill": fill, "rx": rx})

    def rule(self, x, y, w):
        self.rect(x, y, w, 1, self.ct.c["rule"])

    def vrule(self, x, y, h):
        self.rect(x, y, 1, h, self.ct.c["rule"])

    def text(self, x, y, s, role, anchor="start", color=None):
        r = self.ct.role(role)
        self.ops.append({"op": "text", "x": x, "y": y, "s": s,
                         "font": self.ct.f[r["font"]], "size": r["size"],
                         "weight": r["weight"], "tracking": r["tracking"],
                         "anchor": anchor,
                         "fill": self.ct.c[color or r["color"]],
                         "w": measure(s, r["size"], r["tracking"])})

    def para(self, x, y, s, role, max_w, max_lines=None, color=None):
        r = self.ct.role(role); size = r["size"]
        lines = wrap(s, size, max_w, r["tracking"])
        if max_lines and len(lines) > max_lines:
            for sm in range(int(size) - 1, int(size * 0.85), -1):
                trial = wrap(s, sm, max_w, r["tracking"])
                if len(trial) <= max_lines:
                    size, lines = sm, trial; break
        if max_lines and len(lines) > max_lines:
            lines = lines[:max_lines]
            lines[-1] = lines[-1][:-1] + "…"
            self.warnings.append(
                f"文案過長已截斷：「{s[:22]}…」精簡到約 {int(max_lines * max_w / size)} 字")
        lh = self.ct.lh(size)
        fill = self.ct.c[color or r["color"]]
        for i, ln in enumerate(lines):
            self.ops.append({"op": "text", "x": x, "y": y + i * lh, "s": ln,
                             "font": self.ct.f[r["font"]], "size": size,
                             "weight": r["weight"], "tracking": 0,
                             "anchor": "start", "fill": fill,
                             "w": measure(ln, size)})
        return y + (len(lines) - 1) * lh

    def mark(self):
        return len(self.ops)

    def group(self, since):
        """把 since 之後的圖元標為同一視覺單元。

        stretch 以「層」為單位攤開間距，而方塊與它內部的文字是不同的 y。
        不分組的話標籤會被扯出容器 —— 這是引擎知道版式意圖的唯一方式。"""
        gid = f"g{since}"
        for o in self.ops[since:]:
            o.setdefault("g", gid)

    def extent(self, since):
        top = bot = None
        for o in self.ops[since:]:
            if o["op"] == "text":
                t, b = o["y"] - o["size"] * 0.82, o["y"] + o["size"] * 0.22
            else:
                t, b = o["y"], o["y"] + o["h"]
            top = t if top is None else min(top, t)
            bot = b if bot is None else max(bot, b)
        return (top or 0), (bot or 0)

    def settle(self, since, band_top, band_bottom, bias=0.42):
        """把 since 之後的內容在可用帶內重新配置。

        bias<0.5 讓內容略偏上 —— 完全置中會顯得漂浮，全靠上又留死白。
        這是「頂重」的解法，也是 Canvas 不能直接拼字串的原因。"""
        top, bot = self.extent(since)
        if bot <= top:
            return
        slack = (band_bottom - band_top) - (bot - top)
        if slack <= 0:
            return
        dy = self.ct.snap(band_top + slack * bias - top)
        for o in self.ops[since:]:
            o["y"] += dy

    def stretch(self, since, band_top, band_bottom, cap_mult=3.5):
        """把縱向餘裕攤進內容內部的層間距，而不是全部堆在末尾。

        settle 只搬運空白，總量不變 —— 內容少時整頁仍然顯得空。stretch 讓
        內容真正撐開版面，看起來是刻意的疏朗而非沒排滿。cap 防止拉過頭。"""
        # 分組過的圖元以組內最小 y 作為它的層，整組一起移動
        def level_of(o):
            if "g" in o:
                return round(min(q["y"] for q in self.ops[since:]
                                 if q.get("g") == o["g"]))
            return round(o["y"])

        levels = sorted({level_of(o) for o in self.ops[since:]})
        if len(levels) < 2:
            return
        top, bot = self.extent(since)
        slack = (band_bottom - band_top) - (bot - top)
        if slack <= self.ct.grid * 2:
            return
        gaps = len(levels) - 1
        extra = min(slack / gaps, self.ct.grid * cap_mult)
        extra = self.ct.snap(extra)
        if extra <= 0:
            return
        idx = {lv: i for i, lv in enumerate(levels)}
        for o in self.ops[since:]:
            o["y"] += extra * idx[level_of(o)]

    def svg(self):
        ct = self.ct; out = []
        for o in self.ops:
            if o["op"] == "rect":
                r = (f'<rect x="{o["x"]:.0f}" y="{o["y"]:.0f}" '
                     f'width="{o["w"]:.0f}" height="{o["h"]:.0f}"')
                if o["rx"]:
                    r += f' rx="{o["rx"]}"'
                out.append(r + f' fill="{o["fill"]}"/>')
            else:
                tr = f' letter-spacing="{o["tracking"]}"' if o["tracking"] else ""
                wt = f' font-weight="{o["weight"]}"' if o["weight"] != 400 else ""
                an = f' text-anchor="{o["anchor"]}"' if o["anchor"] != "start" else ""
                out.append(f'<text x="{o["x"]:.0f}" y="{o["y"]:.0f}" '
                           f'font-family="{o["font"]}" font-size="{o["size"]}"'
                           f'{wt}{tr}{an} fill="{o["fill"]}">{escape(o["s"])}</text>')
        return (f'<svg xmlns="http://www.w3.org/2000/svg" '
                f'viewBox="0 0 {ct.W} {ct.H}" width="{ct.W}" height="{ct.H}">\n'
                f'  <rect x="0" y="0" width="{ct.W}" height="{ct.H}" '
                f'fill="{ct.c["bg"]}"/>\n  ' + "\n  ".join(out) + "\n</svg>\n")


TOPIC_HINTS = ("概述", "介紹", "背景", "現狀", "分析", "總結", "情況",
               "overview", "introduction", "background", "summary", "analysis")


def audit_title(page, idx, warns):
    t = (page.get("title") or "").strip()
    if not t or page.get("shape") in ("title", "statement"):
        return
    low = t.lower()
    if len(t) <= 6 or any(low == h or low.endswith(h) for h in TOPIC_HINTS):
        warns.append(f"p{idx:02d}: 標題「{t}」像標籤而非結論。改寫成完整陳述該頁"
                     f"論點的句子（action title），讀者才能只看標題就跟上論證。")


def rail(cv, meta, page):
    """頂部軌道。參考級簡報幾乎都有 —— 它在內容之前就告訴讀者這是什麼文件。"""
    ct = cv.ct
    y = ct.snap(ct.mtop * 0.42)
    left = meta.get("org", "")
    right = page.get("stamp") or meta.get("date", "")
    if left:
        cv.text(ct.mx, y, left, "caption", color="muted")
    if right:
        cv.text(ct.W - ct.mx, y, right, "caption", anchor="end", color="muted")
    if left or right:
        cv.rule(ct.mx, ct.snap(y + ct.grid * 2), ct.content_w)
        return ct.snap(y + ct.grid * 7)
    return ct.mtop


def chrome(cv, page, meta, idx):
    ct = cv.ct; foot_y = ct.H - ct.mbot
    if meta.get("footer"):
        cv.text(ct.mx, foot_y, meta["footer"], "caption", color="muted")
    if page.get("shape") != "title":
        cv.text(ct.W - ct.mx, foot_y, f"{idx:02d}", "caption",
                anchor="end", color="muted")


def head(cv, page, y):
    ct = cv.ct
    if page.get("eyebrow"):
        cv.text(ct.mx, y, page["eyebrow"], "eyebrow", color="accent")
        y += ct.advance("eyebrow", "h2")
    if page.get("title"):
        y = cv.para(ct.mx, y, page["title"], "h2", ct.content_w, max_lines=2)
        y += ct.grid * 3
    # 分隔線是契約的決策；宣告 dividers=false 卻照畫等於違反自己的 avoid 清單
    if ct.d["rules"].get("dividers"):
        cv.rule(ct.mx, y, ct.content_w)
        return y + ct.grid * 6
    return y + ct.grid * 4


def page_title(cv, page):
    ct = cv.ct; rail(cv, cv.meta, page); m = cv.mark(); y = ct.mtop
    if page.get("eyebrow"):
        cv.text(ct.mx, y, page["eyebrow"], "eyebrow", color="accent")
        y += ct.advance("eyebrow", "display")
    y = cv.para(ct.mx, y, page["title"], "display", ct.content_w * 0.88, max_lines=2)
    if page.get("subtitle"):
        y += ct.advance("display", "lead")
        cv.para(ct.mx, y, page["subtitle"], "lead", ct.content_w * 0.66,
                max_lines=2, color="muted")
    cv.settle(m, ct.mtop, ct.band_bottom, bias=0.5)


def page_metrics(cv, page):
    ct = cv.ct; band = head(cv, page, rail(cv, cv.meta, page))
    items = page["items"][:4]; cols, w = ct.columns(len(items)); m = cv.mark()
    for i, (x, _) in enumerate(cols):
        it = items[i]; cy = band
        cv.text(x, cy, it.get("label", ""), "eyebrow", color="accent")
        cy += ct.advance("eyebrow", "metric")
        cv.text(x, cy, it["value"], "metric")
        cy += ct.advance("metric", "caption")
        if it.get("unit"):
            cv.text(x, cy, it["unit"], "caption", color="muted")
        cy += ct.advance("caption", "body", extra=ct.grid * 2)
        if it.get("note"):
            cv.para(x, cy, it["note"], "body", w, max_lines=4)
    if ct.d["rules"].get("dividers"):
        top, bot = cv.extent(m)
        top, bot = ct.snap(top), ct.snap(bot)
        for x, _ in cols[1:]:
            cv.vrule(ct.snap(x - ct.gutter / 2), top, bot - top)
    cv.stretch(m, band, ct.band_bottom)
    cv.settle(m, band, ct.band_bottom)


def page_points(cv, page):
    ct = cv.ct; band = head(cv, page, rail(cv, cv.meta, page))
    items = page["items"][:4]; cols, w = ct.columns(len(items)); m = cv.mark()
    for i, (x, _) in enumerate(cols):
        it = items[i]; cy = band
        if ct.d["rules"].get("index"):
            cv.text(x, cy, f"{i + 1:02d}", "eyebrow", color="accent")
            cy += ct.advance("eyebrow", "h3")
        cy = cv.para(x, cy, it["heading"], "h3", w, max_lines=2)
        cy += ct.advance("h3", "body", extra=ct.grid)
        cv.para(x, cy, it.get("body", ""), "body", w, max_lines=7)
    cv.stretch(m, band, ct.band_bottom)
    cv.settle(m, band, ct.band_bottom)


def page_compare(cv, page):
    ct = cv.ct; band = head(cv, page, rail(cv, cv.meta, page))
    cols, w = ct.columns(2); m = cv.mark()
    for i, (x, _) in enumerate(cols):
        side = page["sides"][i]; cy = band
        cv.text(x, cy, side["label"], "eyebrow", color="accent")
        cy += ct.advance("eyebrow", "h3")
        cy = cv.para(x, cy, side["heading"], "h3", w, max_lines=2)
        cy += ct.advance("h3", "body", extra=ct.grid * 2)
        rows = side.get("rows", [])[:5]
        base = ct.lh(ct.role("body")["size"]) + ct.grid * 2
        step = min(max(base, ct.snap((ct.band_bottom - cy) / max(len(rows), 1))),
                   base + ct.grid * 6)
        for row in rows:
            cv.para(x, cy, row, "body", w, max_lines=2)
            cy += step
    if ct.d["rules"].get("dividers"):
        top, bot = cv.extent(m)
        top, bot = ct.snap(top), ct.snap(bot)
        cv.vrule(ct.snap(cols[1][0] - ct.gutter / 2), top, bot - top)
    cv.stretch(m, band, ct.band_bottom, cap_mult=2.5)
    cv.settle(m, band, ct.band_bottom, bias=0.3)


def page_timeline(cv, page):
    ct = cv.ct; band = head(cv, page, rail(cv, cv.meta, page))
    steps = page["steps"][:5]; cols, w = ct.columns(len(steps)); m = cv.mark()
    axis = band + ct.advance("eyebrow", "h3")
    cv.rule(ct.mx, axis, ct.content_w)          # 時間軸的線是結構，不是裝飾
    for i, (x, _) in enumerate(cols):
        st = steps[i]
        cv.rect(x, ct.snap(axis - ct.grid / 2), ct.grid, ct.grid, ct.c["accent"])
        cv.text(x, band, st.get("when", ""), "eyebrow", color="accent")
        cy = axis + ct.advance("eyebrow", "h3", extra=ct.grid * 2)
        cy = cv.para(x, cy, st["heading"], "h3", w, max_lines=2)
        cy += ct.advance("h3", "body", extra=ct.grid)
        cv.para(x, cy, st.get("body", ""), "body", w, max_lines=6)
    cv.stretch(m, band, ct.band_bottom)
    cv.settle(m, band, ct.band_bottom)


def page_statement(cv, page):
    ct = cv.ct; rail(cv, cv.meta, page); m = cv.mark(); y = ct.mtop
    if page.get("eyebrow"):
        cv.text(ct.mx, y, page["eyebrow"], "eyebrow", color="accent")
        y += ct.advance("eyebrow", "display")
    y = cv.para(ct.mx, y, page["text"], "display", ct.content_w * 0.84, max_lines=3)
    if page.get("attribution"):
        y += ct.advance("display", "lead")
        cv.para(ct.mx, y, page["attribution"], "lead", ct.content_w * 0.6,
                max_lines=2, color="muted")
    cv.settle(m, ct.mtop, ct.band_bottom, bias=0.5)


def page_table(cv, page):
    """表格。欄寬由權重算出，列高等距 —— 全部是算術。"""
    ct = cv.ct; band = head(cv, page, rail(cv, cv.meta, page))
    cols = page["columns"]; rows = page["rows"][:8]
    weights = page.get("weights") or [2] + [1] * (len(cols) - 1)
    total = sum(weights)
    xs, w = [], []
    x = ct.mx
    for i, wt in enumerate(weights):
        cw = ct.snap(ct.content_w * wt / total) - (ct.grid * 2 if i else 0)
        xs.append(x); w.append(cw); x = ct.snap(x + ct.content_w * wt / total)
    m = cv.mark()
    y = band
    for i, c in enumerate(cols):
        cv.text(xs[i], y, c, "eyebrow", color="accent")
    y += ct.advance("eyebrow", "body", extra=ct.grid * 2)
    cv.rule(ct.mx, ct.snap(y - ct.grid * 4), ct.content_w)   # 表頭線要與首列留出空隙
    base = ct.lh(ct.role("body")["size"]) + ct.grid * 2
    step = min(max(base, ct.snap((ct.band_bottom - y) / max(len(rows), 1))),
               base + ct.grid * 8)
    for r_i, row in enumerate(rows):
        for i, cell in enumerate(row[:len(cols)]):
            role = "h3" if i == 0 else "body"
            cv.para(xs[i], y, str(cell), role, w[i], max_lines=2)
        y += step
        if r_i < len(rows) - 1:
            cv.rule(ct.mx, ct.snap(y - ct.grid * 3), ct.content_w)
    cv.settle(m, band, ct.band_bottom, bias=0.1)


def page_pipeline(cv, page):
    """階段管線。state: done / current / next 決定填色，強調色只給 current。"""
    ct = cv.ct; band = head(cv, page, rail(cv, cv.meta, page))
    stages = page["stages"][:6]
    cols, w = ct.columns(len(stages))
    m = cv.mark()
    h = ct.grid * 7
    for i, (x, _) in enumerate(cols):
        st = stages[i]
        g = cv.mark()
        state = st.get("state", "next")
        fill = {"current": ct.c["accent"], "done": ct.c["rule"]}.get(state)
        if fill:
            cv.rect(x, band, w, h, fill)
        else:
            cv.rect(x, band, w, 1, ct.c["rule"])
            cv.rect(x, ct.snap(band + h), w, 1, ct.c["rule"])
        label_col = "bg" if state == "current" else ("ink" if state == "done" else "muted")
        cv.text(x + ct.grid * 2, ct.snap(band + h * 0.64), st["label"], "h3",
                color=label_col)
        cv.group(g)
    y = ct.snap(band + h + ct.grid * 5)
    for i, (x, _) in enumerate(cols):
        st = stages[i]
        if st.get("note"):
            cv.para(x, y, st["note"], "body", w, max_lines=5)
    cv.stretch(m, band, ct.band_bottom)
    cv.settle(m, band, ct.band_bottom, bias=0.15)


SHAPES = {"title": page_title, "table": page_table, "pipeline": page_pipeline, "metrics": page_metrics, "points": page_points,
          "compare": page_compare, "timeline": page_timeline,
          "statement": page_statement}


def build_deck(deck, out_dir, contract_name=None):
    """build() 的函式版：吃 dict、不列印，回傳頁面路徑、告警與禁止清單。"""
    meta = deck.get("meta", {})
    name = contract_name or meta.get("contract", "editorial-report")
    ct = Contract(json.load(open(os.path.join(CONTRACTS, name + ".json"),
                                encoding="utf-8")))
    os.makedirs(out_dir, exist_ok=True)
    written, warns, pages_ops = [], [], []
    pages = deck["pages"]
    for i, page in enumerate(pages, 1):
        shape = page.get("shape")
        if shape not in SHAPES:
            raise ValueError(f"第 {i} 頁 shape='{shape}' 不存在。可用：{', '.join(SHAPES)}")
        cv = Canvas(ct, meta)
        audit_title(page, i, warns)
        SHAPES[shape](cv, page)
        chrome(cv, page, meta, i)
        path = os.path.join(out_dir, f"p{i:02d}-{shape}.svg")
        open(path, "w", encoding="utf-8").write(cv.svg())
        written.append(path)
        pages_ops.append({"shape": shape, "ops": cv.ops})
        warns += [f"p{i:02d}: {w}" for w in cv.warnings]

    json.dump({"canvas": {"w": ct.W, "h": ct.H}, "bg": ct.c["bg"],
               "pages": pages_ops},
              open(os.path.join(out_dir, "display-list.json"), "w",
                   encoding="utf-8"), ensure_ascii=False)
    return {"contract": name, "pages": written, "warnings": warns,
            "avoid": ct.d.get("avoid", []),
            "display_list": os.path.join(out_dir, "display-list.json")}


def build(deck_path, out_dir, contract_name=None):
    deck = json.load(open(deck_path, encoding="utf-8"))
    res = build_deck(deck, out_dir, contract_name)
    name, written, warns = res["contract"], res["pages"], res["warnings"]
    ct = Contract(json.load(open(os.path.join(CONTRACTS, name + ".json"),
                                encoding="utf-8")))
    print(f"契約 {name} · {len(written)} 頁 → {out_dir}")
    for p in written:
        print("  " + os.path.basename(p))
    if warns:
        print("\n內容告警（幾何已保證正確，以下是文案層問題）：")
        for w in warns:
            print("  ! " + w)
    if ct.d.get("avoid"):
        print(f"\n契約 {name} 的禁止清單 —— 交付前自查：")
        for a in ct.d["avoid"]:
            print("  × " + a)
    return written


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("deck"); ap.add_argument("--out", default="./pages")
    ap.add_argument("--contract")
    a = ap.parse_args()
    build(a.deck, a.out, a.contract)
