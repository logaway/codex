#!/usr/bin/env python3
"""把 skills/deckforge 打包成自包含的 skill：附带 deckforge 包，装上就能用。

    python3 tools/build_skill.py            # → dist/deckforge/ 与 dist/deckforge.skill

skill 源文件只放流程、文档和 CLI；deckforge 包只在仓库根目录维护一份，打包时才复制进去，
避免两份代码各改各的。
"""

import os
import shutil
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "skills", "deckforge")
PKG = os.path.join(ROOT, "deckforge")
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")


def build(dist=os.path.join(ROOT, "dist")):
    out = os.path.join(dist, "deckforge")
    shutil.rmtree(out, ignore_errors=True)
    # evals 是开发用的测试用例，不随 skill 分发
    shutil.copytree(SRC, out, ignore=shutil.ignore_patterns("evals", "__pycache__", "*.pyc"))
    shutil.copytree(PKG, os.path.join(out, "scripts", "deckforge"), ignore=IGNORE)

    archive = os.path.join(dist, "deckforge.skill")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for base, _, files in os.walk(out):
            for f in sorted(files):
                p = os.path.join(base, f)
                z.write(p, os.path.relpath(p, dist))
    return out, archive


if __name__ == "__main__":
    out, archive = build(*sys.argv[1:2])
    print(out)
    print(archive)
