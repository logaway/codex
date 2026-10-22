"""
style.py — 从用户上传的参考文件（图片 / Excel）提取设计规范。

用户说不清想要什么样式，但几乎都能拿出一张「我喜欢这个」的截图或一份品牌
规范表。这里把它变成一份 contract JSON，而不是让模型「参考这张图的风格」——
后者是建议，前者是排版引擎必须执行的数值。

能从文件里可靠读出的只有：配色、（截图的）页边距、（Excel 的）字体名。
字号层级不从参考里取，继承自基础规范：层级比例是专业感的主要来源，
从一张截图里反推字号误差太大，不如保住一个已校准的阶梯。

所有颜色都过一遍对比度校正，并把改动逐条记下来告诉用户 —— 品牌浅黄做小字
不可读，静默改掉用户会以为我们拿错了颜色。
"""

import colorsys
import copy
import json
import os
import re
import xml.etree.ElementTree as ET

BUILTIN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "contracts")
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")
EXCEL_EXT = (".xlsx", ".xlsm")

# 最低对比度。正文按 WCAG AA；muted 与 accent 用于小号辅助文字，取 3.0 ——
# 再高就会把大多数品牌色改得面目全非。
MIN_CONTRAST = {"ink": 7.0, "body": 4.5, "muted": 3.0, "accent": 3.0}


# ---------------------------------------------------------------- 颜色工具

def to_hex(rgb):
    return "#{:02X}{:02X}{:02X}".format(*(max(0, min(255, round(c))) for c in rgb))


def to_rgb(hx):
    h = hx.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def luminance(hx):
    def ch(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(c) for c in to_rgb(hx))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def saturation(hx):
    r, g, b = (c / 255 for c in to_rgb(hx))
    _, l, s = colorsys.rgb_to_hls(r, g, b)
    return s if 0.12 < l < 0.9 else 0.0     # 近黑近白的「饱和度」没有意义


def mix(a, b, t):
    """a 与 b 之间取 t（0 = a，1 = b）。"""
    return to_hex([x + (y - x) * t for x, y in zip(to_rgb(a), to_rgb(b))])


def is_dark(hx):
    return luminance(hx) < 0.2


def ensure_contrast(fg, bg, target):
    """保持色相，只调明度，直到对比度达标。返回 (新颜色, 是否改动)。"""
    if contrast(fg, bg) >= target:
        return fg, False
    r, g, b = (c / 255 for c in to_rgb(fg))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    step = 0.02 if is_dark(bg) else -0.02
    while 0 <= l <= 1:
        l += step
        cand = to_hex([c * 255 for c in colorsys.hls_to_rgb(h, max(0, min(1, l)), s)])
        if contrast(cand, bg) >= target:
            return cand, True
    return ("#FFFFFF" if is_dark(bg) else "#000000"), True


# ---------------------------------------------------------------- 图片

def from_image(path):
    """返回 {tokens, margin_x, sources, notes}。"""
    from PIL import Image, ImageOps

    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    W, H = im.size
    # 最近邻缩放：不产生混合色。中位切分量化会把小字号的强调色和周围灰色
    # 平均成一个图里根本不存在的颜色
    scale = min(1.0, 1600 / max(W, H))
    small = im.resize((max(1, round(W * scale)), max(1, round(H * scale))),
                      Image.Resampling.NEAREST)
    colors = _buckets(small)

    tokens, sources, notes = {}, {}, ["截图取色是近似值（小字号会被抗锯齿冲淡）。"
                                      "需要精确的品牌色，请提供色值或品牌规范 Excel"]
    share_bg, bg = colors[0]
    tokens["bg"] = bg
    sources["bg"] = f"图片中占比最大的颜色（{share_bg:.0%}）"
    if share_bg < 0.3:
        notes.append("参考图背景不是大面积纯色（可能是照片或渐变），背景色仅供参考")

    visible = [(s, c) for s, c in colors[1:] if s >= 0.002]
    if visible:
        s, ink = max(visible, key=lambda x: contrast(x[1], bg))
        tokens["ink"] = ink
        sources["ink"] = "与背景对比度最高的颜色"

    accent = _accent(colors[1:], bg)
    if accent:
        tokens["accent"] = accent
        sources["accent"] = "图片中最显眼的彩色"
    else:
        notes.append("参考图里没有明显的彩色，强调色沿用基础规范")

    margin_x = None
    if 1.5 <= W / H <= 1.9:              # 只有幻灯片比例的截图才推断页边距
        margin_x = _content_left(small, bg)
        if margin_x is not None:
            sources["margin.x"] = f"截图内容左边界（{margin_x:.1%} 画布宽）"
    else:
        notes.append("图片不是 16:9 幻灯片截图，页边距沿用基础规范")
    return {"tokens": tokens, "margin_ratio": margin_x, "sources": sources,
            "notes": notes, "fonts": {}}


def _buckets(img):
    """按 4 bit/通道分桶统计真实像素色，返回 [(占比, 桶内平均色)]，占比降序。"""
    acc = {}
    for n, (r, g, b) in img.getcolors(maxcolors=img.width * img.height):
        k = (r >> 4, g >> 4, b >> 4)
        a = acc.setdefault(k, [0, 0, 0, 0])
        a[0] += n; a[1] += r * n; a[2] += g * n; a[3] += b * n
    total = sum(a[0] for a in acc.values())
    out = [(a[0] / total, to_hex((a[1] / a[0], a[2] / a[0], a[3] / a[0])))
           for a in acc.values()]
    return sorted(out, reverse=True)


def _accent(colors, bg):
    """先按色相聚类找出最显眼的彩色族，再在族内取最「实」的那个。

    强调色常常只出现在小字号的眉标上，整页只占千分之一的像素，而且被抗锯齿
    拆散成十几个深浅不一的桶。所以门槛按色相族的总量算，不按单个桶算；
    族内取离背景最远、又不是零星杂点的那个 —— 那是字芯，不是晕边。"""
    groups = {}
    for share, c in colors:
        if saturation(c) < 0.35 or contrast(c, bg) < 1.1:
            continue
        r, g, b = (x / 255 for x in to_rgb(c))
        hue = int(colorsys.rgb_to_hls(r, g, b)[0] * 12) % 12
        groups.setdefault(hue, []).append((share, c))
    if not groups:
        return None
    best = max(groups.values(), key=lambda g: sum(s * saturation(c) for s, c in g))
    if sum(s for s, _ in best) < 0.0003:
        return None
    top = max(s for s, _ in best)
    solid = [c for s, c in best if s >= top * 0.15]
    return max(solid, key=lambda c: contrast(c, bg))


def _content_left(img, bg):
    """左侧第一列「有内容」的位置占画布宽的比例。贴边（满版色块）时返回 None。"""
    w, h = img.size
    br, bgc, bb = to_rgb(bg)
    px = img.load()
    for x in range(w):
        hits = sum(1 for y in range(h)
                   if abs(px[x, y][0] - br) + abs(px[x, y][1] - bgc)
                   + abs(px[x, y][2] - bb) > 60)
        if hits >= max(2, h * 0.01):
            ratio = x / w
            return ratio if 0.03 <= ratio <= 0.15 else None
    return None


# ---------------------------------------------------------------- Excel

HEX_RE = re.compile(r"#?\b([0-9A-Fa-f]{6})\b")
RGB_RE = re.compile(r"(?:rgb)?\s*\(?\s*(\d{1,3})\s*[,，]\s*(\d{1,3})\s*[,，]\s*(\d{1,3})\s*\)?", re.I)

# 顺序有意义：先判断更具体的。「正文字体」是字体不是颜色，「标题色」是 ink。
ROLE_WORDS = [
    ("bg", ("背景", "底色", "background", "bg")),
    ("rule", ("分隔", "边框", "线条", "border", "rule", "divider", "line")),
    ("muted", ("辅助", "次要", "弱化", "注释", "灰", "muted", "secondary", "caption", "gray", "grey")),
    ("body", ("正文", "body")),
    ("accent", ("主色", "品牌", "强调", "主题色", "accent", "primary", "brand", "highlight")),
    ("ink", ("标题", "文字", "前景", "text", "ink", "heading", "title", "foreground")),
]
FONT_WORDS = ("字体", "font", "typeface")
HEADING_WORDS = ("标题", "heading", "title", "display", "headline")

# Office 自带主题的强调色：用户没改过主题时，这些不代表任何品牌
DEFAULT_THEME_ACCENTS = {"4472C4", "5B9BD5", "4F81BD", "156082", "0F9ED5", "1F497D"}


def parse_color(s):
    s = str(s).strip()
    m = HEX_RE.search(s)
    if m and ("#" in s or len(s) == 6):
        return "#" + m.group(1).upper()
    m = RGB_RE.fullmatch(s)
    if m and all(int(v) <= 255 for v in m.groups()):
        return to_hex([int(v) for v in m.groups()])
    return None


def role_for(label):
    low = label.lower()
    for role, words in ROLE_WORDS:
        if any(w in low for w in words):
            return role
    return None


def _cell_rgb(color):
    """openpyxl 颜色对象 → hex。主题色、索引色无法直接解析，返回 None。"""
    if color is None or getattr(color, "type", None) != "rgb":
        return None
    v = str(color.rgb)
    if not re.fullmatch(r"[0-9A-Fa-f]{8}", v) or v[:2] == "00" and v[2:] == "000000":
        return None
    return "#" + v[2:].upper()


def from_excel(path):
    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=True)
    tokens, fonts, sources, notes = {}, {}, {}, []
    fills, font_colors = {}, {}
    scanned = 0

    for ws in wb.worksheets:
        for row in ws.iter_rows():
            labels = []
            for c in row:
                scanned += 1
                v = c.value
                fill = _cell_rgb(c.fill.fgColor) if c.fill and c.fill.fill_type == "solid" else None
                fc = _cell_rgb(c.font.color) if c.font else None
                if fill:
                    fills[fill] = fills.get(fill, 0) + 1
                if fc and v is not None:
                    font_colors[fc] = font_colors.get(fc, 0) + 1

                label = " ".join(labels)
                where = f"{ws.title}!{c.coordinate}"
                # 只认文本：数据表里的 123456 是数字，不是颜色
                col = parse_color(v) if isinstance(v, str) else None
                # 规范表的三种写法：「主色 | #B4351E」「主色 | RGB(180,53,30)」「主色 | 色块单元格」
                if col is None and v is None and fill and labels:
                    col = fill
                if col and labels:
                    if any(w in label.lower() for w in FONT_WORDS):
                        continue
                    role = role_for(label)
                    if role and role not in tokens:
                        tokens[role] = col
                        sources[role] = f"{where}「{label}」"
                    continue
                if v is not None and labels and any(w in label.lower() for w in FONT_WORDS):
                    slot = "heading" if any(w in label.lower() for w in HEADING_WORDS) else "body"
                    if slot not in fonts and isinstance(v, str) and not parse_color(v):
                        fonts[slot] = v.strip()
                        sources[f"font.{slot}"] = f"{where}「{label}」"
                    continue
                if isinstance(v, str) and v.strip():
                    labels.append(v.strip())
            if scanned > 50000:
                break

    theme = _theme(wb)
    if theme:
        if "accent" not in tokens and theme.get("accent"):
            tokens["accent"] = theme["accent"]
            sources["accent"] = "工作簿主题色 accent1"
        for slot in ("heading", "body"):
            if slot not in fonts and theme.get(slot):
                fonts[slot] = theme[slot]
                sources[f"font.{slot}"] = "工作簿主题字体"

    # 没有规范表时，从实际用到的单元格样式里取：表头填充色通常就是品牌色
    if "accent" not in tokens:
        cands = [(n, c) for c, n in fills.items() if saturation(c) >= 0.35]
        if cands:
            tokens["accent"] = max(cands)[1]
            sources["accent"] = f"单元格中最常用的彩色填充（{max(cands)[0]} 处）"
    if "ink" not in tokens:
        darks = [(n, c) for c, n in font_colors.items() if luminance(c) < 0.1]
        if darks:
            tokens["ink"] = max(darks)[1]
            sources["ink"] = "单元格中最常用的深色字体"

    if not tokens and not fonts:
        notes.append("Excel 里没有找到配色规范、自定义主题或彩色单元格，全部沿用基础规范")
    return {"tokens": tokens, "fonts": fonts, "margin_ratio": None,
            "sources": sources, "notes": notes}


def _theme(wb):
    raw = getattr(wb, "loaded_theme", None)
    if not raw:
        return None
    a = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
    root = ET.fromstring(raw)
    out = {}
    acc = root.find(f".//{a}clrScheme/{a}accent1/{a}srgbClr")
    if acc is not None:
        out["accent"] = "#" + acc.get("val").upper()
    for slot, tag in (("heading", "majorFont"), ("body", "minorFont")):
        f = root.find(f".//{a}fontScheme/{a}{tag}")
        if f is not None:
            # 中文品牌一般在 ea（东亚字体）里设定，优先取
            for kind in ("ea", "latin"):
                el = f.find(f"{a}{kind}")
                if el is not None and el.get("typeface"):
                    out[slot] = el.get("typeface")
                    break
    if out.get("accent", "").lstrip("#") in DEFAULT_THEME_ACCENTS:
        return None
    return out


# ---------------------------------------------------------------- 组装 contract

def _load(name, dirs):
    for d in dirs:
        p = os.path.join(d, name + ".json")
        if os.path.exists(p):
            return json.load(open(p, encoding="utf-8"))
    raise ValueError(f"基础规范 '{name}' 不存在")


def build_contract(found, base=None, name="custom", source=""):
    """把提取结果叠加到基础规范上，补齐派生色，校正对比度。

    返回 (contract, adjustments)。adjustments 是要告诉用户的改动说明。"""
    tok = found["tokens"]
    if base is None:
        base = "technical-deck" if tok.get("bg") and is_dark(tok["bg"]) else "editorial-report"
    ct = copy.deepcopy(_load(base, [BUILTIN_DIR]))
    c = ct["colors"]
    adjustments = []

    if "bg" in tok:
        c["bg"] = tok["bg"]
    if "ink" in tok:
        c["ink"] = tok["ink"]
    elif "bg" in tok and contrast(c["ink"], c["bg"]) < MIN_CONTRAST["ink"]:
        c["ink"] = "#F2F5F7" if is_dark(c["bg"]) else "#111111"
        adjustments.append(f"参考里没有可用的文字色，按背景深浅改用 {c['ink']}")

    # 背景或文字换了，基础规范里的中间色就不再成立，从 ink 与 bg 重新派生
    derived = "bg" in tok or "ink" in tok
    for role, t in (("body", 0.22), ("muted", 0.5), ("rule", 0.86)):
        if role in tok:
            c[role] = tok[role]
        elif derived:
            c[role] = mix(c["ink"], c["bg"], t)
    if "accent" in tok:
        c["accent"] = tok["accent"]

    for role in ("ink", "body", "muted", "accent"):
        new, changed = ensure_contrast(c[role], c["bg"], MIN_CONTRAST[role])
        if changed:
            adjustments.append(f"{role} {c[role]} 在背景 {c['bg']} 上对比度只有 "
                               f"{contrast(c[role], c['bg']):.1f}，已调整为 {new}"
                               f"（≥ {MIN_CONTRAST[role]}）")
            c[role] = new
    if contrast(c["rule"], c["bg"]) < 1.1:
        c["rule"] = mix(c["ink"], c["bg"], 0.86)

    fonts = found.get("fonts") or {}
    if fonts.get("body"):
        ct["fonts"]["sans"] = ct["fonts"]["serif"] = fonts["body"]
    if fonts.get("heading"):
        ct["fonts"]["heading"] = fonts["heading"]
        for role in ("display", "metric", "h2", "h3"):
            ct["type"][role]["font"] = "heading"

    if found.get("margin_ratio"):
        g = ct["grid"]
        ct["margin"]["x"] = max(48, min(160, round(found["margin_ratio"] * ct["canvas"]["w"] / g) * g))

    ct["name"] = name
    ct["use_when"] = f"用户指定的参考样式（来自 {source}）。用户给了参考就优先用它。"
    ct["not_when"] = {}
    ct["based_on"] = base
    ct["avoid"] = list(ct.get("avoid", [])) + ["引入参考稿配色以外的颜色"]
    return ct, adjustments


def safe_name(name):
    n = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")[:40]
    return n or "custom"


def extract_style(path, contracts_dir, base=None, name=None):
    """读参考文件 → 生成 contract → 存到 contracts_dir。返回给用户/agent 的报告。"""
    ext = os.path.splitext(path)[1].lower()
    if ext in IMAGE_EXT:
        found = from_image(path)
    elif ext in EXCEL_EXT:
        found = from_excel(path)
    elif ext == ".xls":
        raise ValueError("不支持旧版 .xls，请另存为 .xlsx 后再上传")
    else:
        raise ValueError(f"不支持的参考文件类型 {ext}。支持图片 {IMAGE_EXT} 与 Excel {EXCEL_EXT}")

    stem = os.path.splitext(os.path.basename(path))[0]
    name = safe_name(name or "ref-" + stem)
    builtin = {f[:-5] for f in os.listdir(BUILTIN_DIR) if f.endswith(".json")}
    if name in builtin:
        name = "ref-" + name                     # 不允许覆盖内置规范

    ct, adjustments = build_contract(found, base=base, name=name,
                                     source=os.path.basename(path))
    os.makedirs(contracts_dir, exist_ok=True)
    with open(os.path.join(contracts_dir, name + ".json"), "w", encoding="utf-8") as fh:
        json.dump(ct, fh, ensure_ascii=False, indent=2)

    taken = set(found["tokens"]) | {f"font.{k}" for k in found.get("fonts", {})}
    if found.get("margin_ratio"):
        taken.add("margin.x")
    return {
        "name": name,
        "based_on": ct["based_on"],
        "colors": ct["colors"],
        "fonts": ct["fonts"],
        "margin_x": ct["margin"]["x"],
        "from_file": {k: found["sources"][k] for k in sorted(taken) if k in found["sources"]},
        "inherited": "字号层级、网格、间距继承自 " + ct["based_on"],
        "adjustments": adjustments,
        "notes": found["notes"] + ([
            f"字体「{f}」需要在打开 PPT 的电脑上已安装，否则会被替换并重新换行"
            for f in {v for v in found.get("fonts", {}).values()}]),
    }
