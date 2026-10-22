"""deckforge — 让 LLM 只写内容、由程序算全部几何的 PPT 生成工具，可作为 LangChain 工具调用。"""

from .pipeline import check_deck, list_contracts, render_deck
from .schema import Deck

__all__ = ["Deck", "check_deck", "list_contracts", "render_deck",
           "get_deck_tools", "create_deck_author", "create_deck_chain"]


def __getattr__(name):
    # LangChain 是可选依赖：只用 render_deck 的场景不需要安装它
    if name == "get_deck_tools":
        from .tools import get_deck_tools
        return get_deck_tools
    if name in ("create_deck_author", "create_deck_chain"):
        from . import chain
        return getattr(chain, name)
    raise AttributeError(name)
