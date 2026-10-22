#!/usr/bin/env python3
"""
verify.py — 渲染真正的 PPTX 並拼成聯絡表。

為什麼不看 SVG：SVG 可以完全正確而 PPTX 是壞的。字體替換會改變文字寬度，
文字框過窄就在錯誤的地方換行（"104%" 斷成兩行），而這在 SVG 裡看不出來。
交付的是 PPTX，就得看 PPTX。

需要 libreoffice 與 poppler-utils。
用法：
    python3 verify.py deck.pptx --out review.png
"""

import argparse
import glob
import os
import shutil
import subprocess
import tempfile

from PIL import Image


def verify(pptx_path, out_png, dpi=80, cols=2):
    for exe in ("soffice", "pdftoppm"):
        if not shutil.which(exe):
            raise RuntimeError(f"找不到 {exe}。需要 libreoffice 與 poppler-utils。")

    tmp = tempfile.mkdtemp(prefix="deckverify-")
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf",
                    os.path.abspath(pptx_path), "--outdir", tmp],
                   check=True, capture_output=True, timeout=300)
    pdf = glob.glob(os.path.join(tmp, "*.pdf"))
    if not pdf:
        raise RuntimeError("轉檔失敗，未產生 PDF。")
    subprocess.run(["pdftoppm", "-r", str(dpi), "-png", pdf[0],
                    os.path.join(tmp, "pg")], check=True, capture_output=True)

    imgs = [Image.open(f) for f in sorted(glob.glob(os.path.join(tmp, "pg-*.png")))]
    if not imgs:
        raise RuntimeError("未產生頁面圖。")
    w, h, gap = imgs[0].width, imgs[0].height, 12
    rows = (len(imgs) + cols - 1) // cols
    sheet = Image.new("RGB", (w * cols + gap * (cols - 1),
                              h * rows + gap * (rows - 1)), "#b0b0b0")
    for i, im in enumerate(imgs):
        sheet.paste(im, ((i % cols) * (w + gap), (i // cols) * (h + gap)))
    sheet.save(out_png)
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"{out_png} · {len(imgs)} 頁 · {sheet.size[0]}x{sheet.size[1]}")
    print("看這張圖，特別檢查：文字有沒有在不該換行的地方換行、"
          "數字有沒有被拆開、頁腳有沒有折行。")
    return out_png


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pptx")
    ap.add_argument("--out", default="review.png")
    ap.add_argument("--dpi", type=int, default=80)
    a = ap.parse_args()
    verify(a.pptx, a.out, a.dpi)
