#!/usr/bin/env python3
"""
svg_polish_checker.py — 把"看起来不专业"翻译成可定位的坐标级问题。

与 spec_lock 类型的检查器互补：
  spec_lock 管"取值是否来自白名单"（颜色/图标/字体）
  本脚本管"几何与排版关系是否成立"（溢出/对齐/层级/密度/一致性）

纯标准库，无依赖。用法：
    python3 svg_polish_checker.py page1.svg page2.svg ...
    python3 svg_polish_checker.py deck/*.svg --grid 8 --json report.json
"""

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict

NS = "{http://www.w3.org/2000/svg}"

# ---------------------------------------------------------------- 可调阈值
DEFAULTS = {
    "grid": 8,                  # 版心网格步长，所有 x/y 应吸附其上
    "grid_tolerance": 0,        # 允许偏离网格的像素，专业排版应为 0
    "min_type_ratio": 1.8,      # 页面最大字号 / 正文字号，低于此层级不足
    "max_font_sizes": 6,        # 单页允许出现的不同字号数量
    "max_hues": 4,              # 单页允许出现的不同色相（不含中性色）
    "min_gap": 16,              # 相邻元素最小间距
    "safe_margin": 48,          # 内容距画布边缘最小留白
    "overflow_slack": 2,        # 文字撑出容器的容忍像素
    "density_spread": 0.18,     # 跨页墨量差异上限（页面之间松紧不一）
    "margin_spread": 8,         # 跨页左边距差异上限
}

# CJK 全角区间：这些字符宽度约等于字号，拉丁字符约 0.52 倍
CJK = [(0x1100, 0x115F), (0x2E80, 0xA4CF), (0xAC00, 0xD7A3),
       (0xF900, 0xFAFF), (0xFE30, 0xFE6F), (0xFF00, 0xFF60),
       (0xFFE0, 0xFFE6), (0x3000, 0x303F)]

NEUTRAL_SAT = 0.12   # 饱和度低于此值视为中性色，不计入色相预算


def is_cjk(ch):
    o = ord(ch)
    return any(a <= o <= b for a, b in CJK)


def text_width(s, size, letter_spacing=0.0):
    """估算文本宽度。用于溢出检测，误差 ~5%，足够判断撑没撑破。"""
    w = 0.0
    for ch in s:
        if is_cjk(ch):
            w += size
        elif ch.isdigit():
            w += size * 0.55
        elif ch.isupper():
            w += size * 0.62
        elif ch == " ":
            w += size * 0.28
        else:
            w += size * 0.52
    return w + max(0, len(s) - 1) * letter_spacing


def hex_to_hsl(c):
    c = c.strip().lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    if len(c) != 6:
        return None
    r, g, b = (int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))
    mx, mn = max(r, g, b), min(r, g, b)
    l = (mx + mn) / 2
    if mx == mn:
        return (0.0, 0.0, l)
    d = mx - mn
    s = d / (2 - mx - mn) if l > 0.5 else d / (mx + mn)
    if mx == r:
        h = ((g - b) / d + (6 if g < b else 0)) / 6
    elif mx == g:
        h = ((b - r) / d + 2) / 6
    else:
        h = ((r - g) / d + 4) / 6
    return (h * 360, s, l)


def num(el, attr, default=0.0):
    v = el.get(attr)
    if v is None:
        return default
    m = re.match(r"^-?[\d.]+", v.strip())
    return float(m.group()) if m else default


class Finding:
    def __init__(self, level, code, msg, hint=""):
        self.level, self.code, self.msg, self.hint = level, code, msg, hint

    def __str__(self):
        tail = f"\n         └─ {self.hint}" if self.hint else ""
        return f"  [{self.level}] {self.code:<22} {self.msg}{tail}"

    def as_dict(self):
        return {"level": self.level, "code": self.code,
                "msg": self.msg, "hint": self.hint}


class Page:
    """解析一页 SVG，抽出用于几何判断的最小模型。"""

    def __init__(self, path, cfg):
        self.path, self.cfg = path, cfg
        self.findings = []
        root = ET.parse(path).getroot()

        vb = (root.get("viewBox") or "0 0 1280 720").split()
        self.W, self.H = float(vb[2]), float(vb[3])

        self.texts, self.rects, self.circles = [], [], []
        self._walk(root)

        self.font_sizes = [t["size"] for t in self.texts]
        self.colors = self._collect_colors(root)

    def _walk(self, node, depth=0):
        for el in node.iter():
            tag = el.tag.replace(NS, "")
            if tag == "text":
                content = "".join(el.itertext()).strip()
                if not content:
                    continue
                size = num(el, "font-size", 16)
                anchor = el.get("text-anchor", "start")
                ls = num(el, "letter-spacing", 0)
                w = text_width(content, size, ls)
                x = num(el, "x")
                x0 = x - w if anchor == "end" else x - w / 2 if anchor == "middle" else x
                y = num(el, "y")
                self.texts.append({
                    "s": content, "size": size, "x": x, "y": y,
                    "bbox": (x0, y - size * 0.8, x0 + w, y + size * 0.2),
                    "anchor": anchor, "weight": el.get("font-weight", "400"),
                })
            elif tag == "rect":
                w, h = num(el, "width"), num(el, "height")
                self.rects.append({
                    "x": num(el, "x"), "y": num(el, "y"), "w": w, "h": h,
                    "bbox": (num(el, "x"), num(el, "y"),
                             num(el, "x") + w, num(el, "y") + h),
                    "fill": el.get("fill", ""),
                })
            elif tag == "circle":
                cx, cy, r = num(el, "cx"), num(el, "cy"), num(el, "r")
                self.circles.append({"cx": cx, "cy": cy, "r": r})

    def _collect_colors(self, root):
        raw = ET.tostring(root, encoding="unicode")
        return [c.lower() for c in re.findall(r"#[0-9a-fA-F]{3,6}\b", raw)]

    # ------------------------------------------------------------ P0 检查
    def check_overflow(self):
        """文字是否撑破了它所在的容器 —— 用户最直观的'做工粗糙'。"""
        slack = self.cfg["overflow_slack"]
        for t in self.texts:
            host = self._container_of(t)
            if not host:
                continue
            hx0, hy0, hx1, hy1 = host["bbox"]
            tx0, ty0, tx1, ty1 = t["bbox"]
            if tx1 > hx1 - slack:
                over = tx1 - hx1
                self.findings.append(Finding(
                    "P0", "TEXT_OVERFLOW",
                    f'"{t["s"][:18]}…" 右侧超出容器 {over:.0f}px '
                    f"(文字 {tx1:.0f} > 容器 {hx1:.0f})",
                    f'缩短到 {int((hx1 - tx0 - slack) / t["size"])} 字以内，'
                    f"或换行，不要缩字号救场"))
            if ty1 > hy1 - slack:
                self.findings.append(Finding(
                    "P0", "TEXT_OVERFLOW_V",
                    f'"{t["s"][:18]}…" 底部超出容器 {ty1 - hy1:.0f}px'))

    def check_canvas(self):
        m = self.cfg["safe_margin"]
        for t in self.texts:
            x0, y0, x1, y1 = t["bbox"]
            if x0 < 0 or x1 > self.W or y0 < 0 or y1 > self.H:
                self.findings.append(Finding(
                    "P0", "OUT_OF_CANVAS",
                    f'"{t["s"][:18]}…" 超出画布 ({x0:.0f},{y0:.0f})-({x1:.0f},{y1:.0f})'))
            elif x0 < m or x1 > self.W - m:
                self.findings.append(Finding(
                    "P1", "MARGIN_VIOLATION",
                    f'"{t["s"][:14]}…" 侵入 {m}px 安全边距'))

    # ------------------------------------------------------------ P1 检查
    def check_grid(self):
        """未吸附网格是'哪里怪怪的'最主要来源 —— 人眼极敏感，语言极难描述。"""
        g, tol = self.cfg["grid"], self.cfg["grid_tolerance"]
        off = []
        for t in self.texts:
            for axis, v in (("x", t["x"]), ("y", t["y"])):
                d = min(v % g, g - v % g)
                if d > tol:
                    off.append((t["s"][:12], axis, v, d))
        for r in self.rects:
            for axis, v in (("x", r["x"]), ("y", r["y"])):
                d = min(v % g, g - v % g)
                if d > tol:
                    off.append((f'rect{r["w"]:.0f}×{r["h"]:.0f}', axis, v, d))
        if off:
            worst = sorted(off, key=lambda o: -o[3])[:4]
            detail = "; ".join(f'{o[0]}@{o[1]}={o[2]:.0f}(偏{o[3]:.0f})' for o in worst)
            self.findings.append(Finding(
                "P1", "OFF_GRID",
                f"{len(off)} 处坐标未吸附 {g}px 网格 → {detail}",
                f"所有 x/y 取 {g} 的整数倍。这一条通常单独就能让画面'干净'起来"))

    def check_type_ramp(self):
        """标题与正文字号拉不开 = 整页'一团灰'，没有视觉焦点。"""
        if not self.font_sizes:
            return
        sizes = sorted(set(self.font_sizes))
        top = max(sizes)
        small = [s for s in self.font_sizes if s < top]
        if not small:
            return          # 整頁只有一級字（如 statement 頁），層級無從談起
        # 正文 = 承載文字最多的那一級，而不是文字框最多的那一級。表格與進度頁
        # 每行一個短小的 h3 標籤配一段正文，按文字框個數算會打平甚至選成標籤，
        # 把 1.89× 的版面誤報成 1.62×
        chars = Counter()
        for t in self.texts:
            if t["size"] < top:
                chars[t["size"]] += len(t["s"])
        body = chars.most_common(1)[0][0]
        ratio = top / body if body else 0
        if ratio < self.cfg["min_type_ratio"]:
            self.findings.append(Finding(
                "P1", "WEAK_HIERARCHY",
                f"最大字号 {top:.0f} / 正文 {body:.0f} = {ratio:.2f}×，"
                f"低于 {self.cfg['min_type_ratio']}×",
                f"把标题提到 {body * 2.6:.0f}px 以上，或把正文压到 "
                f"{top / 2.6:.0f}px 以下。层级不足是'不高级'的头号成因"))
        # 只看頭尾比值會漏掉階梯中間的斷層：副標題掉到正文級別，撐不住上面的大字
        for a, b in zip(sizes[::-1], sizes[::-1][1:]):
            if b / a > 2.4:
                self.findings.append(Finding(
                    "P1", "RAMP_GAP",
                    f"字號階梯在 {a:.0f} → {b:.0f} 之間跳了 {b / a:.1f}×",
                    "中間補一級（如 lead 角色）。比值達標不代表階梯連續，"
                    "斷層會讓副標題讀起來像註腳"))
                break
        if len(sizes) > self.cfg["max_font_sizes"]:
            self.findings.append(Finding(
                "P1", "TOO_MANY_SIZES",
                f"单页 {len(sizes)} 种字号 {[int(s) for s in sizes]}，"
                f"上限 {self.cfg['max_font_sizes']}",
                "收敛到一条固定阶梯，如 52/24/16/13"))

    def check_palette(self):
        hues = []
        for c in set(self.colors):
            hsl = hex_to_hsl(c)
            if hsl and hsl[1] > NEUTRAL_SAT:
                hues.append(round(hsl[0] / 30) * 30)
        distinct = len(set(hues))
        if distinct > self.cfg["max_hues"]:
            self.findings.append(Finding(
                "P1", "PALETTE_SPRAWL",
                f"{distinct} 个不同色相（中性色不计），上限 {self.cfg['max_hues']}",
                "一个强调色 + 中性灰阶。每个卡片配一个专属颜色是典型 AI 味"))

    def check_spacing(self):
        """相邻元素间距不等 —— 用户说不出，但一眼觉得'没排过'。"""
        gaps = []
        boxes = sorted([r for r in self.rects if r["w"] > 40 and r["h"] > 40],
                       key=lambda r: (round(r["y"] / 20), r["x"]))
        for a, b in zip(boxes, boxes[1:]):
            if abs(a["y"] - b["y"]) < 20:                  # 同一行
                gap = b["x"] - (a["x"] + a["w"])
                if gap >= 0:
                    gaps.append(gap)
        if len(set(round(g) for g in gaps)) > 1:
            self.findings.append(Finding(
                "P1", "UNEVEN_GUTTER",
                f"同排元素间距不一致：{[round(g) for g in gaps]}",
                "同排间距必须完全相等；宽度不等的卡片是最常见元凶"))
        if gaps and min(gaps) < self.cfg["min_gap"]:
            self.findings.append(Finding(
                "P1", "TIGHT_GAP",
                f"最小间距 {min(gaps):.0f}px < {self.cfg['min_gap']}px"))

        widths = [r["w"] for r in self.rects if r["w"] > 200 and r["h"] > 100]
        if len(set(round(w) for w in widths)) > 1 and len(widths) > 1:
            self.findings.append(Finding(
                "P1", "UNEQUAL_CARDS",
                f"同级卡片宽度不等：{[round(w) for w in widths]}",
                "并列关系的元素必须等宽，否则读者会误以为它们权重不同"))

    def check_text_collision(self):
        """文字压文字 / 贴太近 —— 渲染出来最刺眼，但纯看代码发现不了。"""
        cols = defaultdict(list)
        for t in self.texts:
            cols[round(t["bbox"][0] / 40)].append(t)     # 按左边界归列
        for group in cols.values():
            group.sort(key=lambda t: t["y"])
            for a, b in zip(group, group[1:]):
                gap = b["bbox"][1] - a["bbox"][3]
                if gap < 0:
                    self.findings.append(Finding(
                        "P0", "TEXT_COLLISION",
                        f'"{a["s"][:12]}" 与 "{b["s"][:12]}" 重叠 {-gap:.0f}px'))
                # 同段落的連續行（同字號、同左界）本來就該緊；只有不同元素
                # 之間才需要留呼吸。用同一個閾值會逼出鬆散的行距。
                same_para = abs(a["size"] - b["size"]) < 0.5 and \
                    abs(a["bbox"][0] - b["bbox"][0]) < 2
                need = a["size"] * 0.06 if same_para else max(a["size"], b["size"]) * 0.35
                if gap < need and gap >= 0:
                    self.findings.append(Finding(
                        "P1", "TEXT_CRAMPED",
                        f'"{a["s"][:12]}" 与 "{b["s"][:12]}" 仅隔 {gap:.0f}px',
                        f'至少留 {need:.0f}px'))

    def check_icon_scale(self):
        radii = [c["r"] for c in self.circles]
        if len(set(round(r) for r in radii)) > 1:
            self.findings.append(Finding(
                "P1", "ICON_SCALE_DRIFT",
                f"同类图标尺寸不一：r={[round(r) for r in radii]}",
                "图标尺寸锁死为单一值"))

    def check_slop_patterns(self):
        """硬编码黑名单：一眼 AI 生成的视觉套路。"""
        raw = open(self.path, encoding="utf-8").read()
        if "linearGradient" in raw and raw.count("stop-color") >= 4:
            self.findings.append(Finding(
                "P2", "GRADIENT_SLOP",
                "使用了多组渐变",
                "渐变是最强的'AI 生成'信号之一，除非风格文件明确要求，改为纯色"))
        # 分隔线（1px 中性色）是正当排版；色条是套路。区别在饱和度与厚度。
        strips = []
        for r in self.rects:
            thin = (2 <= r["h"] <= 6 and r["w"] > 120) or (2 <= r["w"] <= 8 and r["h"] > 20)
            if not thin:
                continue
            hsl = hex_to_hsl(r["fill"]) if r["fill"].startswith("#") else None
            saturated = (hsl and hsl[1] > NEUTRAL_SAT) or r["fill"].startswith("url(")
            if saturated:
                strips.append(r)
        if len(strips) >= 3:
            self.findings.append(Finding(
                "P2", "ACCENT_STRIP_SLOP",
                f"{len(strips)} 处装饰性色条/顶边",
                "'圆角卡片 + 彩色顶条'是模板感最重的组合，删掉后靠留白和字号建立层级"))
        ui_faces = ("Inter", "Roboto", "Helvetica", "Arial", "system-ui")
        big = [t for t in self.texts if t["size"] > 40]
        raw_big = [el for el in re.findall(r"<text[^>]*>", raw)
                   if any(f'font-size="{int(t["size"])}"' in el for t in big)]
        if any(f in el for el in raw_big for f in ui_faces):
            self.findings.append(Finding(
                "P2", "DISPLAY_FONT_DEFAULT",
                "展示級字號使用了 UI 無襯線體",
                "大字號換一款有性格的字體，正文再用 UI 體"))

    # ------------------------------------------------------------ 工具
    def _container_of(self, t):
        """找出包住该文字锚点的最小矩形，作为它的容器。"""
        cx = (t["bbox"][0] + t["bbox"][2]) / 2
        cy = t["y"] - t["size"] * 0.3
        best = None
        for r in self.rects:
            x0, y0, x1, y1 = r["bbox"]
            if x1 - x0 >= self.W * 0.95:      # 整页背景不算容器
                continue
            if r["h"] < t["size"]:            # 细条不算容器
                continue
            if x0 <= cx <= x1 and y0 <= cy <= y1:
                area = r["w"] * r["h"]
                if best is None or area < best[0]:
                    best = (area, r)
        return best[1] if best else None

    def ink_density(self):
        """墨量：非背景元素覆盖面积占比，用于跨页松紧一致性。"""
        area = 0.0
        for t in self.texts:
            x0, y0, x1, y1 = t["bbox"]
            area += (x1 - x0) * (y1 - y0)
        for r in self.rects:
            if r["w"] < self.W * 0.95:
                area += r["w"] * r["h"] * 0.35
        return area / (self.W * self.H)

    def left_margin(self):
        xs = [t["bbox"][0] for t in self.texts if t["anchor"] == "start"]
        return min(xs) if xs else 0

    def run(self):
        for fn in (self.check_overflow, self.check_canvas, self.check_grid,
                   self.check_type_ramp, self.check_palette, self.check_spacing,
                   self.check_icon_scale, self.check_text_collision, self.check_slop_patterns):
            fn()
        return self.findings


def check_deck(pages, cfg):
    """跨页一致性 —— 单页都合格但连起来仍然不专业，问题通常在这里。"""
    out = []
    dens = [p.ink_density() for p in pages]
    if len(dens) > 1 and (max(dens) - min(dens)) > cfg["density_spread"]:
        lo, hi = pages[dens.index(min(dens))], pages[dens.index(max(dens))]
        out.append(Finding(
            "P1", "DECK_DENSITY_SWING",
            f"页面松紧差异 {max(dens) - min(dens):.0%}："
            f"{lo.path} 最空 {min(dens):.0%}，{hi.path} 最满 {max(dens):.0%}",
            "拆分或合并内容，让每页墨量落在同一区间。翻页时忽空忽满是'不专业'的强信号"))

    margins = [p.left_margin() for p in pages]
    if len(margins) > 1 and (max(margins) - min(margins)) > cfg["margin_spread"]:
        out.append(Finding(
            "P1", "DECK_MARGIN_DRIFT",
            f"左边距在页间漂移 {min(margins):.0f}–{max(margins):.0f}px",
            "版心左边界全 deck 锁死为同一个值"))

    all_sizes = sorted({int(s) for p in pages for s in p.font_sizes})
    if len(all_sizes) > cfg["max_font_sizes"] + 2:
        out.append(Finding(
            "P2", "DECK_RAMP_SPRAWL",
            f"全 deck 出現 {len(all_sizes)} 種字號 {all_sizes}",
            "字號階梯應是 deck 級常量。不同版式可以只用其中一部分，"
            "但不該引入階梯以外的新字號"))
    return out


def check_files(files, grid=DEFAULTS["grid"]):
    """main() 的函式版：回傳 {檔名: [finding], "__deck__": [...], "tally": {...}}。"""
    cfg = dict(DEFAULTS, grid=grid)
    pages, report = [], {}
    for f in files:
        p = Page(f, cfg)
        p.run()
        pages.append(p)
        report[f] = [x.as_dict() for x in p.findings]
    deck = check_deck(pages, cfg)
    report["__deck__"] = [x.as_dict() for x in deck]
    allf = [x for p in pages for x in p.findings] + deck
    tally = Counter(x.level for x in allf)
    report["tally"] = {k: tally[k] for k in ("P0", "P1", "P2")}
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--grid", type=int, default=DEFAULTS["grid"])
    ap.add_argument("--json")
    ap.add_argument("--strict", action="store_true",
                    help="P1 也算失败（默认只有 P0 阻断）")
    a = ap.parse_args()

    cfg = dict(DEFAULTS, grid=a.grid)
    pages, report = [], {}

    for f in a.files:
        p = Page(f, cfg)
        p.run()
        pages.append(p)
        report[f] = [x.as_dict() for x in p.findings]
        head = f"{f}  ·  墨量 {p.ink_density():.0%}  ·  左边距 {p.left_margin():.0f}px"
        print("\n" + head)
        print("─" * len(head))
        if p.findings:
            for x in sorted(p.findings, key=lambda i: i.level):
                print(x)
        else:
            print("  ✓ 无问题")

    deck = check_deck(pages, cfg)
    if deck:
        print("\n跨页一致性")
        print("─" * 10)
        for x in deck:
            print(x)
        report["__deck__"] = [x.as_dict() for x in deck]

    allf = [x for p in pages for x in p.findings] + deck
    tally = Counter(x.level for x in allf)
    print(f"\n合计  P0 {tally['P0']}  ·  P1 {tally['P1']}  ·  P2 {tally['P2']}")

    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)

    fail = tally["P0"] + (tally["P1"] if a.strict else 0)
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
