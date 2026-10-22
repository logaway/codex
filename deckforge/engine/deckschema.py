#!/usr/bin/env python3
"""
deckschema.py — deck.json 的校驗與自動修整。

小模型會漏欄位、多給項目、把數字寫成句子。與其要求它一次寫對，不如機器
校驗後把具體錯誤回饋回去 —— 「第 2 頁 items 有 6 個，上限 4」比「請遵守
格式」有用得多。
"""

SHAPES = {
    "title":     {"req": ["title"], "opt": ["eyebrow", "subtitle", "stamp"]},
    "metrics":   {"req": ["title", "items"], "opt": ["eyebrow", "stamp"],
                  "list": ("items", 2, 4, ["label", "value"], ["unit", "note"])},
    "points":    {"req": ["title", "items"], "opt": ["eyebrow", "stamp"],
                  "list": ("items", 2, 4, ["heading"], ["body"])},
    "compare":   {"req": ["title", "sides"], "opt": ["eyebrow", "stamp"],
                  "list": ("sides", 2, 2, ["label", "heading"], ["rows"])},
    "timeline":  {"req": ["title", "steps"], "opt": ["eyebrow", "stamp"],
                  "list": ("steps", 2, 5, ["heading"], ["when", "body"])},
    "statement": {"req": ["text"], "opt": ["eyebrow", "attribution", "stamp"]},
    "table":     {"req": ["title", "columns", "rows"],
                  "opt": ["eyebrow", "weights", "stamp"]},
    "pipeline":  {"req": ["title", "stages"], "opt": ["eyebrow", "stamp"],
                  "list": ("stages", 2, 6, ["label"], ["state", "note"])},
}
STATES = ("done", "current", "next")

# 各角色的字數上限。超過就會被 build.py 截斷，不如在這裡先擋下來。
LIMITS = {"title": 24, "heading": 12, "label": 8, "value": 10, "unit": 14,
          "note": 44, "body": 90, "text": 30, "subtitle": 34,
          "attribution": 26, "eyebrow": 8, "row": 24}


def _len(s):
    return len(str(s))


def validate(deck):
    """回傳錯誤清單。空清單代表可以送進 build.py。"""
    errs = []
    if not isinstance(deck, dict):
        return ["最外層必須是物件，含 meta 與 pages"]
    pages = deck.get("pages")
    if not isinstance(pages, list) or not pages:
        return ["缺少 pages，或 pages 不是陣列"]

    shapes_seen = []
    for i, p in enumerate(pages, 1):
        tag = f"第 {i} 頁"
        if not isinstance(p, dict):
            errs.append(f"{tag}: 必須是物件"); continue
        sh = p.get("shape")
        if sh not in SHAPES:
            errs.append(f"{tag}: shape='{sh}' 無效。只能用：{', '.join(SHAPES)}")
            continue
        shapes_seen.append(sh)
        spec = SHAPES[sh]

        for k in spec["req"]:
            if not p.get(k):
                errs.append(f"{tag} ({sh}): 缺少必要欄位 '{k}'")

        for k in p:
            if k not in spec["req"] + spec["opt"] + ["shape"]:
                errs.append(f"{tag} ({sh}): 多餘欄位 '{k}'，請刪除")

        for k in ("title", "text", "subtitle", "attribution", "eyebrow"):
            if p.get(k) and _len(p[k]) > LIMITS[k]:
                errs.append(f"{tag}: '{k}' 有 {_len(p[k])} 字，上限 {LIMITS[k]}。請精簡")

        if "list" in spec:
            key, lo, hi, req_f, opt_f = spec["list"]
            items = p.get(key)
            if isinstance(items, list):
                if not lo <= len(items) <= hi:
                    errs.append(f"{tag}: {key} 有 {len(items)} 項，必須是 {lo}–{hi} 項")
                for j, it in enumerate(items, 1):
                    if not isinstance(it, dict):
                        errs.append(f"{tag}: {key}[{j}] 必須是物件"); continue
                    for f in req_f:
                        if not it.get(f):
                            errs.append(f"{tag}: {key}[{j}] 缺少 '{f}'")
                    for f in it:
                        if f not in req_f + opt_f:
                            errs.append(f"{tag}: {key}[{j}] 多餘欄位 '{f}'")
                        elif f in LIMITS and isinstance(it[f], str) \
                                and _len(it[f]) > LIMITS[f]:
                            errs.append(f"{tag}: {key}[{j}].{f} 有 {_len(it[f])} 字，"
                                        f"上限 {LIMITS[f]}")
                    if sh == "pipeline" and it.get("state") not in STATES + (None,):
                        errs.append(f"{tag}: stages[{j}].state 只能是 {STATES}")
                    if sh == "compare":
                        rows = it.get("rows") or []
                        if not 2 <= len(rows) <= 5:
                            errs.append(f"{tag}: sides[{j}].rows 需 2–5 條")
                        for r in rows:
                            if _len(r) > LIMITS["row"]:
                                errs.append(f"{tag}: sides[{j}] 有一條 {_len(r)} 字，"
                                            f"上限 {LIMITS['row']}")
            else:
                errs.append(f"{tag}: {key} 必須是陣列")

        if sh == "pipeline" and isinstance(p.get("stages"), list):
            cur = [s for s in p["stages"] if isinstance(s, dict)
                   and s.get("state") == "current"]
            if len(cur) > 1:
                errs.append(f"{tag}: 只能有一個 stage 是 current，現在有 {len(cur)} 個")

        if sh == "table":
            cols = p.get("columns") or []
            if not 2 <= len(cols) <= 5:
                errs.append(f"{tag}: columns 需 2–5 欄")
            for j, r in enumerate(p.get("rows") or [], 1):
                if not isinstance(r, list) or len(r) != len(cols):
                    errs.append(f"{tag}: rows[{j}] 的欄數需等於 columns 的 {len(cols)}")
            if len(p.get("rows") or []) > 8:
                errs.append(f"{tag}: rows 上限 8 列")

    if shapes_seen and shapes_seen[0] != "title":
        errs.append("第 1 頁必須是 title")
    if len(set(shapes_seen)) < 2 and len(shapes_seen) > 2:
        errs.append("整份 deck 只用了一種版式，讀起來會單調。至少換用兩種")
    return errs


def coerce(deck):
    """能機器修的先修掉，減少往返：截多餘項目、補 state、去空白。"""
    for p in deck.get("pages", []):
        if not isinstance(p, dict):
            continue
        spec = SHAPES.get(p.get("shape"))
        if not spec:
            continue
        if "list" in spec:
            key, lo, hi, _, _ = spec["list"]
            if isinstance(p.get(key), list) and len(p[key]) > hi:
                p[key] = p[key][:hi]
        if p.get("shape") == "table" and isinstance(p.get("rows"), list):
            p["rows"] = p["rows"][:8]
        if p.get("shape") == "pipeline":
            for st in p.get("stages", []):
                if isinstance(st, dict):
                    st.setdefault("state", "next")
        for k, v in list(p.items()):
            if isinstance(v, str):
                p[k] = v.strip()
    return deck
