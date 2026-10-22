"""
chain.py — 不用 agent 时的固定链：需求文字 → deck 内容 → PPTX。

    from deckforge import create_deck_chain
    chain = create_deck_chain(ChatOpenAI(model=...), contract="exec-brief")
    result = chain.invoke("把 Q3 复盘做成 6 页，给管理层，15 分钟")

任何支持 with_structured_output 的 LangChain 聊天模型都可以，包括本地模型。
不要求模型一次写对：机器先修能修的，剩下的把具体错误回喂给模型，最多 rounds 轮。
"""

import json

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableLambda

from . import pipeline
from .engine.deckschema import LIMITS
from .schema import Deck, to_dict

SYSTEM = """你把演示文稿需求整理成结构化的 deck 内容。你只负责内容，不负责任何视觉和坐标。

规则：
1. 第 1 页必须是 title。
2. 每页 title 必须是结论式标题——用完整句子陈述该页结论，不是话题标签。
   好：「超额部分有七成不可复制」  坏：「业绩归因」
3. 先判断每页信息的结构再选版式：有先后才用 timeline，真对立才用 compare，
   数字是论据就用 metrics。至少换用两种版式，不要整份都用 points。
4. statement 是全篇的转折点，最多用一两次。
5. 严格遵守字数上限（中文按字计），超出会被截断：
{limits}
6. 不确定的数字不要编造，宁可不写。
7. meta.contract 固定为 "{contract}"。"""

FEWSHOT_IN = "把 Q3 业务复盘做成 4 页，给管理层，重点是营收达标但获客成本恶化。"
FEWSHOT_OUT = {
    "meta": {"contract": "exec-brief", "org": "NORTHWIND", "date": "Q3 2026"},
    "pages": [
        {"shape": "title", "eyebrow": "Q3 复盘", "title": "营收达标，但增长质量下滑",
         "subtitle": "三个需要在 Q4 前决策的问题"},
        {"shape": "metrics", "eyebrow": "整体表现", "title": "营收超额 4%，获客成本同步恶化",
         "items": [{"label": "营收", "value": "104%", "unit": "达成率",
                    "note": "超额主要来自两笔大单。"},
                   {"label": "获客成本", "value": "+31%", "unit": "同比",
                    "note": "远高于营收增速。"}]},
        {"shape": "compare", "eyebrow": "归因", "title": "超额部分有七成不可复制",
         "sides": [{"label": "可复制", "heading": "来自产品与流程",
                    "rows": ["老客扩容带来的自然增长", "续约率回升至 89%"]},
                   {"label": "不可复制", "heading": "来自一次性因素",
                    "rows": ["两笔年度框架单提前确认", "季末加大折扣换取的签约"]}]},
        {"shape": "statement", "eyebrow": "建议", "text": "先收折扣权限，再谈华东加投。",
         "attribution": "顺序反过来会让毛利进一步恶化"}]}


def create_deck_author(llm, contract="editorial-report", rounds=3):
    """需求文字 → 通过校验的 deck dict。超过 rounds 轮仍不通过时抛 ValueError。"""
    structured = llm.with_structured_output(Deck)
    limits = "\n".join(f"   {k}: {v} 字" for k, v in LIMITS.items())
    system = SYSTEM.format(limits=limits, contract=contract)

    def author(brief):
        msgs = [SystemMessage(system),
                HumanMessage(FEWSHOT_IN),
                AIMessage(json.dumps(FEWSHOT_OUT, ensure_ascii=False)),
                HumanMessage(brief)]
        errors = []
        for _ in range(rounds):
            try:
                deck = to_dict(structured.invoke(msgs))
            except Exception as e:    # 结构化输出解析失败也当作一轮可修复的错误
                deck, errors = None, [f"输出不符合格式：{e}"]
            else:
                deck.setdefault("meta", {})["contract"] = contract
                deck, errors = pipeline.check_deck(deck)
                if not errors:
                    return deck
            msgs += [AIMessage(json.dumps(deck, ensure_ascii=False) if deck else ""),
                     HumanMessage("上面的输出有以下问题，修正后重新输出完整内容：\n"
                                  + "\n".join("- " + e for e in errors))]
        raise ValueError(f"{rounds} 轮修复后仍未通过校验：{errors}")

    return RunnableLambda(author, name="deck_author")


def create_deck_chain(llm, contract="editorial-report", out_dir=None,
                      preview=False, rounds=3):
    """需求文字 → pipeline.render_deck 的结果 dict（含 pptx 路径、告警、禁止清单）。"""
    render = RunnableLambda(
        lambda deck: pipeline.render_deck(deck, out_dir=out_dir, preview=preview),
        name="render_deck")
    return create_deck_author(llm, contract, rounds) | render
