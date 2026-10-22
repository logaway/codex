#!/usr/bin/env python3
"""
deckforge_cli.py — skill 的命令行入口。所有输出都是 JSON，方便读取后再决定下一步。

    python3 scripts/deckforge_cli.py contracts  [--styles DIR]
    python3 scripts/deckforge_cli.py show NAME  [--styles DIR]
    python3 scripts/deckforge_cli.py style FILE [--base NAME] [--name NAME] [--styles DIR]
    python3 scripts/deckforge_cli.py validate deck.json
    python3 scripts/deckforge_cli.py render deck.json --out DIR [--contract NAME]
                                    [--styles DIR] [--preview] [--strict]

退出码：0 成功；1 内容或检查未通过（看输出里的 errors）；2 用法错误。
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# 打包后 deckforge 在 scripts/ 旁边；在源码仓库里则在仓库根目录
for p in (HERE, os.path.abspath(os.path.join(HERE, "..", "..", ".."))):
    if os.path.isdir(os.path.join(p, "deckforge")):
        sys.path.insert(0, p)
        break

from deckforge import pipeline, style  # noqa: E402


def out(obj, ok=True):
    print(json.dumps(obj, ensure_ascii=False, indent=1))
    sys.exit(0 if ok else 1)


def main():
    ap = argparse.ArgumentParser(description="deckforge：LLM 只写内容，程序计算全部几何")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("contracts", help="列出设计规范及适用场景")
    c.add_argument("--styles", default="./styles", help="从参考文件提取的规范所在目录")

    sh = sub.add_parser("show", help="输出一套规范的完整 JSON（手写新规范时从它复制）")
    sh.add_argument("name")
    sh.add_argument("--styles", default="./styles")

    s = sub.add_parser("style", help="从参考图片 / Excel 提取设计规范")
    s.add_argument("file")
    s.add_argument("--base", help="字号层级继承自哪个内置规范；不填按深浅自动选")
    s.add_argument("--name")
    s.add_argument("--styles", default="./styles")

    v = sub.add_parser("validate", help="只校验 deck.json 内容")
    v.add_argument("deck")

    r = sub.add_parser("render", help="排版、几何检查、输出 PPTX")
    r.add_argument("deck")
    r.add_argument("--out", default="./deck-out")
    r.add_argument("--contract", help="覆盖 deck.json 里 meta.contract")
    r.add_argument("--styles", default="./styles")
    r.add_argument("--preview", action="store_true", help="用 LibreOffice 渲染 review.png")
    r.add_argument("--strict", action="store_true", help="P1 级几何问题也算失败")
    a = ap.parse_args()

    if a.cmd == "contracts":
        out(pipeline.list_contracts(a.styles))

    if a.cmd == "show":
        c = pipeline.load_contract(a.name, a.styles)
        if c is None:
            out({"ok": False, "error": f"规范 '{a.name}' 不存在"}, ok=False)
        out(c)

    if a.cmd == "style":
        try:
            out(style.extract_style(a.file, a.styles, base=a.base, name=a.name))
        except (ValueError, OSError) as e:
            out({"ok": False, "error": str(e)}, ok=False)

    deck = json.load(open(a.deck, encoding="utf-8"))
    if a.cmd == "validate":
        _, errors = pipeline.check_deck(deck)
        out({"ok": not errors, "errors": errors}, ok=not errors)

    res = pipeline.render_deck(deck, out_dir=a.out, contract=a.contract,
                               preview=a.preview, strict=a.strict,
                               contracts_dir=a.styles)
    res.pop("svgs", None)
    res["findings"] = [f for f in res.get("findings", []) if f["level"] != "P2"]
    out(res, ok=res["ok"])


if __name__ == "__main__":
    main()
