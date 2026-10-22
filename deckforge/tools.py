"""
tools.py — 把 deck 流水线暴露成 LangChain 工具。

    from deckforge import get_deck_tools
    agent = create_agent(model, tools=get_deck_tools(out_dir="./out"))

分工：agent 的 LLM 只负责内容（每页是什么版式、写什么、标题是什么结论），
工具负责全部几何。工具不会抛异常给 agent，而是把具体错误放在返回值里，
agent 改完内容再调一次即可 —— 这就是修复循环，不需要额外编排。
"""

import json
import os
import uuid
from typing import Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from . import pipeline, style
from .schema import Deck, to_dict


class RenderArgs(BaseModel):
    deck: Deck = Field(description="演示文稿内容。只写内容和版式，不写任何坐标、尺寸、颜色")


class ContractArgs(BaseModel):
    pass


class ValidateArgs(BaseModel):
    deck: Deck


def _summary(res):
    """返回给 LLM 的文本。路径和数字要短，告警和禁止清单要全 —— 那是它下一步要读的。"""
    keep = ("ok", "errors", "contract", "pptx", "preview", "tally",
            "warnings", "findings", "avoid")
    out = {k: res[k] for k in keep if res.get(k) not in (None, [], {})}
    if "findings" in out:
        out["findings"] = [f for f in out["findings"] if f["level"] in ("P0", "P1")]
    if res.get("ok"):
        out["next"] = ("PPTX 已生成。逐条检查 warnings 与 avoid；标题若被提示像标签，"
                       "改写后再渲染一次。告诉用户这是高质量初稿，建议人工微调。")
    else:
        out["next"] = "按 errors 修改 deck 后重新调用 render_deck。"
    return json.dumps(out, ensure_ascii=False, indent=1)


def _validation_error(e):
    """Pydantic 报错原文太长，压成「位置: 原因」逐行返回，让 agent 能对着改。"""
    lines = [f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}"
             for err in e.errors()[:10]]
    return "deck 结构不合法，按以下位置修改后重试：\n" + "\n".join(lines)


class StyleArgs(BaseModel):
    file_path: str = Field(description="用户上传的参考文件路径：幻灯片截图、品牌海报、logo 图片，或品牌规范 Excel")
    base_contract: Optional[str] = Field(
        None, description="字号层级与间距从哪个内置规范继承，按场景选；不填则按参考的深浅自动选")
    name: Optional[str] = Field(None, description="给提取出的样式起名（小写英文与连字符）")


def get_deck_tools(out_dir="./decks", preview=False, strict=False,
                   styles_dir=None, uploads_dir=None):
    """返回 [list_deck_contracts, extract_style, validate_deck, render_deck]。

    out_dir      每次渲染在其下新建一个子目录，避免并发调用互相覆盖
    preview      额外用 LibreOffice 把 PPTX 渲染成 review.png（需要 soffice 与 pdftoppm）
    strict       P1 级几何问题也视为失败
    styles_dir   从参考文件提取的设计规范存放处，默认 out_dir/styles
    uploads_dir  设置后，extract_style 只读取这个目录下的文件。路径来自模型，
                 生产环境应当设置，免得被诱导去读服务器上的任意文件
    """
    styles_dir = styles_dir or os.path.join(out_dir, "styles")

    def list_deck_contracts() -> str:
        return json.dumps(pipeline.list_contracts(styles_dir), ensure_ascii=False, indent=1)

    def extract_style(file_path: str, base_contract: Optional[str] = None,
                      name: Optional[str] = None) -> str:
        path = os.path.realpath(file_path)
        if uploads_dir and os.path.commonpath(
                [path, os.path.realpath(uploads_dir)]) != os.path.realpath(uploads_dir):
            return json.dumps({"ok": False, "error": "只能读取用户上传目录中的文件"},
                              ensure_ascii=False)
        if not os.path.isfile(path):
            return json.dumps({"ok": False, "error": f"文件不存在：{file_path}"},
                              ensure_ascii=False)
        try:
            rep = style.extract_style(path, styles_dir, base=base_contract, name=name)
        except Exception as e:      # 损坏的图片 / Excel：告诉 agent 原因，让它问用户
            return json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"},
                              ensure_ascii=False)
        rep = {"ok": True, **rep,
               "next": f"在 deck 的 meta.contract 中填 \"{rep['name']}\"。"
                       "把 from_file、adjustments、notes 用一两句话告诉用户，"
                       "尤其是被调整过的颜色和需要安装的字体。"}
        return json.dumps(rep, ensure_ascii=False, indent=1)

    def validate_deck(deck: Deck) -> str:
        _, errors = pipeline.check_deck(to_dict(deck))
        return json.dumps({"ok": not errors, "errors": errors}, ensure_ascii=False)

    def render_deck(deck: Deck) -> str:
        run_dir = os.path.join(out_dir, uuid.uuid4().hex[:8])
        res = pipeline.render_deck(to_dict(deck), out_dir=run_dir, preview=preview,
                                   strict=strict, contracts_dir=styles_dir)
        return _summary(res)

    return [
        StructuredTool.from_function(
            list_deck_contracts, name="list_deck_contracts", args_schema=ContractArgs,
            description="列出可用的设计规范及其适用场景（use_when/not_when），含已从参考文件提取的。"
                        "做 PPT 前先调用，按受众和场景选规范，不要按话题选。"),
        StructuredTool.from_function(
            extract_style, name="extract_style", args_schema=StyleArgs,
            description="用户上传了图片或 Excel 作为样式/风格参考时调用：从中提取配色、"
                        "页边距、字体，生成一套新的设计规范并返回其 name。"
                        "用户给了参考就优先用它，而不是内置规范。"),
        StructuredTool.from_function(
            validate_deck, name="validate_deck", args_schema=ValidateArgs,
            handle_validation_error=_validation_error,
            description="只校验 deck 内容（版式、条数、字数上限），不出文件。"),
        StructuredTool.from_function(
            render_deck, name="render_deck", args_schema=RenderArgs,
            handle_validation_error=_validation_error,
            description="把 deck 内容排版成原生可编辑的 PPTX，并做几何检查。"
                        "第 1 页必须是 title；每页标题写结论而不是标签；至少用两种版式；"
                        "statement 全篇最多一两次。返回 errors 时按其修改后重试。"),
    ]
