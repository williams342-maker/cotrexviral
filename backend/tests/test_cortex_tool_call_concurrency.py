"""Regression test for the Cortex production-timeout incident
(2026-02-28). The original bug wrapped an already-async coroutine with
`asyncio.to_thread(lambda: asyncio.run(...))`, which:
  1. Created a fresh event loop per call,
  2. Held threads from Python's default executor for the entire
     LLM call duration,
  3. Under concurrent prod load, exhausted the default ~32-thread
     pool and caused every subsequent request to hang until ingress
     timed it out.

This test asserts:
  - The implementation calls `_execute_completion` directly via `await`
    (no nested event-loop pattern in the executable path).
  - N concurrent `cortex_tool_call` invocations complete in roughly
    max(individual_duration), not sum (proves real async parallelism).
"""
import asyncio
import ast
import inspect
import time

from cortex import llm_provider


def _executable_source(fn) -> str:
    """Return the function source with all docstrings + comments stripped
    so the regression check ignores explanatory text that mentions the
    forbidden pattern by name."""
    src = inspect.getsource(fn)
    tree = ast.parse(src)
    # Strip docstrings from the function and any inner clauses.
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module)):
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                node.body.pop(0)
    # ast.unparse drops Python comments — we don't need the unrolled
    # source, just want to know what executes.
    return ast.unparse(tree)


def test_cortex_tool_call_does_not_wrap_in_asyncio_run():
    src = _executable_source(llm_provider.cortex_tool_call)
    assert "asyncio.to_thread" not in src, (
        "cortex_tool_call must not wrap _execute_completion in to_thread"
    )
    assert "asyncio.run(" not in src, (
        "cortex_tool_call must not create a nested event loop"
    )
    assert "await chat._execute_completion(" in src, (
        "cortex_tool_call must await _execute_completion directly"
    )


def test_cortex_tool_call_concurrent_parallelism():
    """5 concurrent calls should complete in ~max(latency), not sum.

    If someone re-introduces the to_thread+asyncio.run wrap, the
    default executor pool will serialize and this will run ~5x slower,
    failing the assertion.
    """
    schema = {
        "type": "object",
        "properties": {"mood": {"type": "string"}},
        "required": ["mood"],
    }

    async def one(i: int):
        return await llm_provider.cortex_tool_call(
            system="Classify the mood in one word.",
            user_text=f"Sentence {i}: the rain is coming down.",
            tool={"name": "mood", "description": "classify", "parameters": schema},
            session_id=f"concurrency-{i}",
            user_id="regression",
        )

    async def run_all():
        return await asyncio.gather(
            *[one(i) for i in range(5)], return_exceptions=True
        )

    start = time.monotonic()
    results = asyncio.run(run_all())
    duration = time.monotonic() - start

    for r in results:
        assert not isinstance(r, Exception), f"call failed: {r!r}"

    # With true async parallelism, 5 calls should finish well under
    # 5×latency. 18s comfortably accepts claude-sonnet-4-5 latency
    # under load but firmly rejects the serialized thread-pool
    # regression (which took ~20-30s in the original incident).
    assert duration < 18, (
        f"5 concurrent cortex_tool_call took {duration:.1f}s — "
        "thread-pool serialization regression suspected"
    )
