# codex · deckforge

AI 生成 PPT 时，**LLM 只写内容，所有几何由程序计算**。可以作为 LangChain 工具、LangChain 链，或 Deep Agents skill 调用。

为什么要这样分工：模型手写坐标时，三张并列卡片会写成 368/368/395 宽，间距不落在网格上。代码里看不出问题，读者却会觉得"不专业"。
这里模型只输出 `{"shape": "metrics", "items": [...]}` 这样的结构化内容，栏宽、行高、换行、纵向留白都由排版引擎计算，然后导出**原生可编辑**的 PPTX（文字框和形状，不是图片）。

## 安装

```bash
pip install -e ".[langchain]"          # 渲染预览图另需 libreoffice + poppler-utils + Pillow
```

## 用法一：作为 agent 的工具

```python
from langchain.agents import create_agent
from deckforge import get_deck_tools

agent = create_agent(model, tools=get_deck_tools(out_dir="./decks"), system_prompt=...)
```

| 工具 | 作用 |
|---|---|
| `list_deck_contracts` | 列出设计规范及适用场景，让模型按场景（不是话题）选择 |
| `validate_deck` | 只校验内容：版式、条数、字数上限 |
| `render_deck` | 排版、几何检查，输出 PPTX |

工具不会把异常抛给 agent，而是返回具体错误（如"第 2 页 items 有 6 项，上限 4"），agent 改完再调一次。修复循环就是 agent 自身的循环，不需要另外编排。
完整示例见 `examples/agent_example.py`。

## 用法二：固定链（需求文字 → PPTX）

```python
from deckforge import create_deck_chain
chain = create_deck_chain(llm, contract="exec-brief", out_dir="./decks/q3")
res = chain.invoke("把 Q3 复盘做成 6 页，给管理层，15 分钟……")
res["pptx"], res["warnings"], res["avoid"]
```

任何支持 `with_structured_output` 的聊天模型都可以，包括本地模型：模型只需要填字段，不需要算坐标。校验失败时会把具体错误回喂给模型，默认最多重试 3 轮。见 `examples/chain_example.py`。

## 用法三：Deep Agents skill

`skills/deck-forge/SKILL.md` 是标准的 skill 目录（带 frontmatter），可以放进 Deep Agents 的 skills 目录，配合上面的工具使用。

## 设计规范

`deckforge/contracts/*.json` 是机器可读的设计系统：配色、字号层级、边距、网格，以及 `avoid` 禁止清单。

| 规范 | 适合 |
|---|---|
| `editorial-report` | 复盘、评审，需要细读或打印 |
| `exec-brief` | 给决策者，5 分钟，数字是主角 |
| `technical-deck` | 架构评审，投影，深色、信息密 |
| `stat-callout` | 战略汇报，一页一个大数字 |
| `review-scorecard` | 季度/客户评审，目标与偏差 |

要匹配公司品牌，就复制一份 JSON，把参考稿里的真实色值、字号、边距填进去。标题字号与正文字号的比例保持在 2.5 倍以上。

## 目录

```
deckforge/
  schema.py      Pydantic 内容模型（给 tool calling / structured output）
  pipeline.py    校验 → 排版 → 几何检查 → PPTX → 预览
  tools.py       LangChain 工具
  chain.py       LangChain 链（需求 → deck → PPTX，带修复循环）
  engine/        排版引擎、检查器、PPTX 导出（标准库 + python-pptx）
  contracts/     设计规范
skills/deck-forge/SKILL.md
```

## 测试

```bash
pip install -e ".[dev]" && pytest
```
