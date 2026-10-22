"""用 LangChain agent 调用 deckforge 工具生成 PPT。

    pip install -e ".[langchain]" langchain langchain-anthropic
    python examples/agent_example.py

换成任何支持 tool calling 的模型都可以（OpenAI、通义、DeepSeek、本地 vLLM 等）。
"""

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model

from deckforge import get_deck_tools

SYSTEM = """你帮用户做演示文稿。流程：
1. 用户上传了图片或 Excel 作为样式参考，就调用 extract_style 并使用它返回的规范名；
   否则调用 list_deck_contracts，按受众和场景（不是话题）选设计规范。
2. 先想清楚每页是什么信息结构，再选版式；每页标题写结论，不写标签。
3. 调用 render_deck。返回 errors 就按错误修改内容后重试。
4. 交付时把 pptx 路径告诉用户，说明这是高质量初稿，建议人工微调。
你只负责内容，绝不输出坐标、尺寸、颜色。"""

agent = create_agent(
    init_chat_model("anthropic:claude-sonnet-5-5"),
    tools=get_deck_tools(out_dir="./decks", uploads_dir="./uploads"),
    system_prompt=SYSTEM,
)

result = agent.invoke({"messages": [{
    "role": "user",
    "content": "把 Q3 销售复盘做成 6 页给管理层，15 分钟。营收达成 104%，"
               "但获客成本同比 +31%，华东续约率 81% 低于其他大区的 90%。"
               "样式参考我们的品牌规范：./uploads/brand.xlsx"}]})
print(result["messages"][-1].content)
