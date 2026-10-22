# 接入 LangChain / agent 应用

用户要的不是做一份 PPT，而是"让我的 AI 应用能生成 PPT"时，读这份文档。

本技能打包的 `scripts/deckforge/` 就是完整的 Python 包，源码在 GitHub `logaway/codex` 仓库，可以用 `pip install -e ".[langchain,style]"` 安装。安装后有三种接入方式。

## 1. 作为 agent 的工具（推荐）

```python
from langchain.agents import create_agent
from deckforge import get_deck_tools

agent = create_agent(
    model,                                   # 任何支持 tool calling 的模型
    tools=get_deck_tools(out_dir="./decks", uploads_dir="./uploads"),
    system_prompt=SYSTEM,                    # 可以直接用本技能 SKILL.md 的流程部分
)
```

| 工具 | 作用 |
|---|---|
| `list_deck_contracts` | 列出设计规范（含已提取的） |
| `extract_style` | 从上传的图片 / Excel 提取规范，返回 name |
| `validate_deck` | 只校验内容 |
| `render_deck` | 排版、检查、输出 PPTX |

- 工具参数是 Pydantic 模型（`deckforge.schema.Deck`），8 种版式用 `shape` 字段区分，**没有任何几何字段**，模型想写坐标也写不进去
- 工具不会把异常抛给 agent，而是返回具体错误，agent 改完再调一次。修复循环就是 agent 自己的循环
- **生产环境务必设置 `uploads_dir`。** `extract_style` 的文件路径由模型传入，不限制目录的话，可能被提示词注入诱导去读服务器上的其他文件

## 2. 固定链（不用 agent）

```python
from deckforge import create_deck_chain, extract_style

rep = extract_style("uploads/brand.xlsx", contracts_dir="./styles")     # 可选
chain = create_deck_chain(llm, contract=rep["name"], contracts_dir="./styles", out_dir="./decks/q3")
res = chain.invoke("把 Q3 复盘做成 6 页，给管理层，15 分钟……")
res["pptx"], res["warnings"], res["avoid"]
```

任何支持 `with_structured_output` 的聊天模型都可以，包括本地 vLLM / Ollama。模型只需要填字段，不需要算坐标，所以小模型也能胜任。校验失败时会把具体错误回喂给模型，默认最多 3 轮。

## 3. Deep Agents

本技能目录本身就是标准 skill 格式（SKILL.md + frontmatter），可以直接放进 Deep Agents 的 skills 目录。agent 通过 shell 运行 `scripts/deckforge_cli.py`，和在 Claude 里用法一样。

## 不用 LangChain

`deckforge.render_deck(deck_dict, out_dir=..., contracts_dir=...)` 是纯 Python 函数，可以接进任何框架，返回值与 CLI 的 JSON 相同。
