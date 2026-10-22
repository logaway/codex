"""
schema.py — deck 的 Pydantic 模型，给 LLM 的 tool calling / structured output 用。

这里只描述结构（有哪些版式、每种版式有哪些字段），刻意不放字数和条数上限：
那些由 engine/deckschema.py 校验，它能给出「第 2 页 items 有 6 项，上限 4」
这种模型拿得动的具体错误，而 Pydantic 的报错对模型来说太抽象。

注意：没有任何坐标、宽度、字号字段。几何全部由排版引擎计算。
"""

from typing import Annotated, List, Literal, Optional, Union

from pydantic import BaseModel, Field

Contract = Literal["editorial-report", "exec-brief", "technical-deck",
                   "stat-callout", "review-scorecard"]

ACTION_TITLE = "结论式标题：用完整句子陈述本页结论，不要写话题标签（好：「华东增速已放缓到3%」；坏：「市场分析」）"


class _Page(BaseModel):
    eyebrow: Optional[str] = Field(None, description="短引语，2–6 个汉字")
    stamp: Optional[str] = Field(None, description="右上角标记，如「草稿」「机密」")


class TitlePage(_Page):
    shape: Literal["title"]
    title: str = Field(description="封面标题，14 字以内")
    subtitle: Optional[str] = None


class Metric(BaseModel):
    label: str
    value: str = Field(description="短数字，如 42%、¥2.4M，不要写句子")
    unit: Optional[str] = None
    note: Optional[str] = Field(None, description="一两句背景")


class MetricsPage(_Page):
    shape: Literal["metrics"]
    title: str = Field(description=ACTION_TITLE)
    items: List[Metric] = Field(description="2–4 个关键数字")


class Point(BaseModel):
    heading: str
    body: Optional[str] = None


class PointsPage(_Page):
    shape: Literal["points"]
    title: str = Field(description=ACTION_TITLE)
    items: List[Point] = Field(description="2–4 个同等权重的并列要点")


class Side(BaseModel):
    label: str
    heading: str
    rows: List[str] = Field(description="2–5 条，每条一行")


class ComparePage(_Page):
    shape: Literal["compare"]
    title: str = Field(description=ACTION_TITLE)
    sides: List[Side] = Field(description="正好 2 侧：前/后、我方/对手、可复制/一次性")


class Step(BaseModel):
    when: Optional[str] = None
    heading: str
    body: Optional[str] = None


class TimelinePage(_Page):
    shape: Literal["timeline"]
    title: str = Field(description=ACTION_TITLE)
    steps: List[Step] = Field(description="2–5 个有先后意义的阶段")


class StatementPage(_Page):
    shape: Literal["statement"]
    text: str = Field(description="一句核心主张，30 字以内。全篇最多用一两次")
    attribution: Optional[str] = None


class TablePage(_Page):
    shape: Literal["table"]
    title: str = Field(description=ACTION_TITLE)
    columns: List[str] = Field(description="2–5 列")
    rows: List[List[str]] = Field(description="最多 8 行，每行列数等于 columns")
    weights: Optional[List[int]] = Field(None, description="各列相对宽度")


class Stage(BaseModel):
    label: str
    state: Literal["done", "current", "next"] = "next"
    note: Optional[str] = None


class PipelinePage(_Page):
    shape: Literal["pipeline"]
    title: str = Field(description=ACTION_TITLE)
    stages: List[Stage] = Field(description="2–6 个阶段，只能有一个 current")


Page = Annotated[Union[TitlePage, MetricsPage, PointsPage, ComparePage,
                       TimelinePage, StatementPage, TablePage, PipelinePage],
                 Field(discriminator="shape")]


class Meta(BaseModel):
    contract: Contract = Field(
        "editorial-report",
        description="设计规范。按场景选，不按话题选：先调用 list_deck_contracts 看 use_when")
    org: Optional[str] = Field(None, description="左上角机构名")
    date: Optional[str] = Field(None, description="右上角日期或状态")
    footer: Optional[str] = None


class Deck(BaseModel):
    """一份演示文稿的内容。第 1 页必须是 title，至少换用两种版式。"""
    meta: Meta = Field(default_factory=Meta)
    pages: List[Page]


def to_dict(deck):
    """Deck 模型 → 引擎吃的 dict，去掉 None 字段（引擎会把多余字段当错误）。"""
    if isinstance(deck, BaseModel):
        return deck.model_dump(exclude_none=True)
    return deck
