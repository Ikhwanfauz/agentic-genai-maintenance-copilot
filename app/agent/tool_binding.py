from collections.abc import Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool


def bind_investigation_tools(
    model: BaseChatModel,
    tools: Sequence[BaseTool],
) -> Runnable:
    return model.bind_tools(
        list(tools),
        parallel_tool_calls=False,
    )
