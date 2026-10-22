"""不用 agent，固定链：需求文字 → PPTX。适合批量生成或接入已有流水线。"""

from langchain_openai import ChatOpenAI

from deckforge import create_deck_chain

# 任何 OpenAI 兼容端点都行，包括本地 vLLM / Ollama
llm = ChatOpenAI(model="qwen3-32b", base_url="http://localhost:8000/v1", api_key="EMPTY")
chain = create_deck_chain(llm, contract="exec-brief", out_dir="./decks/q3")

res = chain.invoke("把 Q3 复盘做成 6 页，给管理层，15 分钟。营收达标但获客成本恶化。")
print(res["pptx"] if res["ok"] else res["errors"])
for w in res.get("warnings", []):
    print("!", w)
