"""Allow-listed AI tools.

External execution is intentionally absent in this phase. This registry makes
that constraint explicit and gives later phases one controlled extension point.
"""

TOOLS = {
    "memory_context": {
        "description": "Read authenticated user profile context.",
        "read_only": True,
        "external": False,
    },
}


def available_tools() -> list[dict]:
    return [{"name": name, **metadata} for name, metadata in TOOLS.items()]


def assert_no_external_tool(tool_name: str) -> None:
    tool = TOOLS.get(tool_name)
    if not tool:
        raise ValueError(f"Tool '{tool_name}' is not registered")
    if tool.get("external") or not tool.get("read_only"):
        raise PermissionError("External or write-capable AI tools are disabled")

