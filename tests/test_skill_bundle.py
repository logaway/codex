import json
import os
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from build_skill import build  # noqa: E402
from test_deckforge import DECK  # noqa: E402


def test_bundle_is_self_contained(tmp_path):
    out, archive = build(str(tmp_path / "dist"))
    names = zipfile.ZipFile(archive).namelist()
    assert "deckforge/SKILL.md" in names
    assert "deckforge/scripts/deckforge/engine/build.py" in names
    assert not any("/evals/" in n or "__pycache__" in n for n in names)

    # 在仓库外、隔离模式下运行，确认用的是包内附带的 deckforge
    work = tmp_path / "work"
    work.mkdir()
    (work / "deck.json").write_text(json.dumps(DECK, ensure_ascii=False), encoding="utf-8")
    cli = os.path.join(out, "scripts", "deckforge_cli.py")
    r = subprocess.run([sys.executable, "-I", cli, "render", "deck.json", "--out", "o"],
                       cwd=work, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["ok"]

    r = subprocess.run([sys.executable, "-I", cli, "show", "exec-brief"],
                       cwd=work, capture_output=True, text=True)
    assert json.loads(r.stdout)["name"] == "exec-brief"

    r = subprocess.run([sys.executable, "-I", cli, "validate", "deck.json"],
                       cwd=work, capture_output=True, text=True)
    assert r.returncode == 0
