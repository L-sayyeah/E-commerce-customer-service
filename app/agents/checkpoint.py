from typing import Any

from langgraph.checkpoint.mysql.asyncmy import AsyncMySaver

from app.core.config import settings

_checkpointer_cm: Any = None
_checkpointer: Any = None


async def init_agent_checkpointer() -> Any:
    global _checkpointer_cm, _checkpointer

    if not settings.langgraph_checkpoint_enabled:
        _checkpointer = None
        return None

    if settings.langgraph_checkpoint_backend == "mysql":
        _checkpointer_cm = AsyncMySaver.from_conn_string(
            settings.langgraph_checkpoint_db_uri
        )
        _checkpointer = await _checkpointer_cm.__aenter__()
        await _checkpointer.setup()
        return _checkpointer


def get_agent_checkpointer() -> Any:
    return _checkpointer


async def close_agent_checkpointer() -> None:
    global _checkpointer_cm, _checkpointer

    if _checkpointer_cm is not None:
        await _checkpointer_cm.__aexit__(None, None, None)

    _checkpointer_cm = None
    _checkpointer = None
