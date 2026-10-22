"""
pipeline.py — 一次跑完 校验 → 排版 → 几何检查 → PPTX →（可选）渲染预览。

LangChain 工具和链都只调用这里。所有失败都以结构化结果返回而不是抛异常：
调用方通常是一个 agent，具体的错误文本才是它能拿去修复的东西。
"""

import contextlib
import io
import json
import os
import subprocess
import tempfile

from .engine import build as _build
from .engine import check as _check
from .engine.deckschema import coerce, validate

CONTRACTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "contracts")


def list_contracts():
    """返回每个设计规范的选择依据（use_when / not_when / signature / avoid）。"""
    out = []
    for f in sorted(os.listdir(CONTRACTS_DIR)):
        if not f.endswith(".json"):
            continue
        d = json.load(open(os.path.join(CONTRACTS_DIR, f), encoding="utf-8"))
        out.append({k: d.get(k) for k in
                    ("name", "use_when", "not_when", "signature", "avoid")})
    return out


def check_deck(deck):
    """只做内容校验，不排版。返回 (修整后的 deck, 错误列表)。"""
    deck = coerce(json.loads(json.dumps(deck)))   # 深拷贝，不改调用方的对象
    return deck, validate(deck)


def render_deck(deck, out_dir=None, contract=None, pptx_name="deck.pptx",
                preview=False, strict=False):
    """把 deck dict 渲染成可编辑 PPTX。

    返回 dict：
      ok          是否产出了可交付的 PPTX
      errors      内容校验错误（非空时不排版，交给调用方修改后重试）
      warnings    文案层告警（标题像标签、文字被截断）——几何已保证正确
      findings    几何检查结果，含 P0/P1/P2 统计
      avoid       所选设计规范的禁止清单，交付前自查
      pptx / svgs / preview  产物路径
    """
    deck, errors = check_deck(deck)
    if contract:
        deck.setdefault("meta", {})["contract"] = contract
    name = deck.get("meta", {}).get("contract", "editorial-report")
    if not os.path.exists(os.path.join(CONTRACTS_DIR, name + ".json")):
        errors.append(f"设计规范 '{name}' 不存在。可用："
                      + ", ".join(c["name"] for c in list_contracts()))
    if errors:
        return {"ok": False, "errors": errors}

    out_dir = out_dir or tempfile.mkdtemp(prefix="deckforge-")
    os.makedirs(out_dir, exist_ok=True)
    pages_dir = os.path.join(out_dir, "pages")

    try:
        built = _build.build_deck(deck, pages_dir)
    except ValueError as e:
        return {"ok": False, "errors": [str(e)]}

    report = _check.check_files(built["pages"])
    tally = report.pop("tally")
    findings = [dict(f, page=os.path.basename(path))
                for path, fs in report.items() for f in fs]
    blocked = tally["P0"] + (tally["P1"] if strict else 0)

    result = {
        "ok": not blocked,
        "errors": [],
        "contract": built["contract"],
        "warnings": built["warnings"],
        "findings": findings,
        "tally": tally,
        "avoid": built["avoid"],
        "svgs": built["pages"],
    }
    if blocked:
        result["errors"] = ["几何检查未通过，请根据 findings 精简或调整内容后重试"]
        return result

    from .engine import topptx   # python-pptx 只在真正要出文件时才需要
    pptx_path = os.path.join(out_dir, pptx_name)
    with contextlib.redirect_stdout(io.StringIO()):
        topptx.convert(built["display_list"], pptx_path)
    result["pptx"] = pptx_path

    if preview:
        from .engine import verify
        png = os.path.join(out_dir, "review.png")
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                verify.verify(pptx_path, png)
            result["preview"] = png
        except (RuntimeError, OSError, subprocess.SubprocessError) as e:
            result["warnings"].append(f"预览渲染失败（不影响 PPTX）：{e}")
    return result
