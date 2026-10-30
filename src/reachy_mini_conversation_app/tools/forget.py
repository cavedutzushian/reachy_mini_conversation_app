import logging
from typing import Any

from reachy_mini_conversation_app.config import config
from reachy_mini_conversation_app.memory import forget_memory_fact
from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies


logger = logging.getLogger(__name__)


class Forget(Tool):
    """Remove one long-term memory fact."""

    name = "forget"
    description = (
        "Remove a previously saved fact from long-term memory. Call this when the user asks you to forget something, "
        "or when saved information becomes obsolete. Prefer the exact memory_id shown in saved memory context. "
        "If no id is available, copy a phrase from the saved fact into query without translating it."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "memory_id": {
                "type": "string",
                "description": "The exact memory_id of the fact to remove, copied from saved memory context.",
            },
            "query": {
                "type": "string",
                "description": (
                    "A short search phrase that should be present in the fact to remove. Matching is case-insensitive."
                ),
            },
        },
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> dict[str, Any]:
        """Forget one memory fact by id or query."""
        if not config.MEMORY_ENABLED:
            return {"error": "Memory is disabled"}

        memory_id = kwargs.get("memory_id")
        if memory_id is not None:
            if not isinstance(memory_id, str) or not memory_id.strip():
                logger.warning("forget: invalid memory_id")
                return {"error": "memory_id must be a non-empty string"}
            result = forget_memory_fact(deps.instance_path, fact_id=memory_id.strip())
            no_match = "no memory matched the supplied memory_id; nothing was removed"
        else:
            query = kwargs.get("query")
            if not isinstance(query, str) or not query.strip():
                logger.warning("forget: empty query")
                return {"error": "query must be a non-empty string"}
            result = forget_memory_fact(deps.instance_path, query=query)
            no_match = f'no memory matched "{query}"; nothing was removed'

        if result.removed is None:
            logger.info("Tool call: forget no_match")
            return {"error": no_match}

        response: dict[str, Any] = {
            "removed": result.removed.text,
            "memory_id": result.removed.id,
        }
        if len(result.candidates) > 1:
            response["other_matches"] = [fact.text for fact in result.candidates[1:]]

        logger.info("Tool call: forget memory_id=%s", result.removed.id)
        return response
