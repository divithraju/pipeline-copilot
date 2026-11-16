"""LLM planner: plain English + data profile → validated Pipeline spec. One automatic repair retry."""
import json
import httpx
from pydantic import ValidationError
from .config import ANTHROPIC_API_KEY, PLANNER_MODEL
from .spec import Pipeline

SYSTEM = """You are a data engineer. Convert the user's request into a pipeline spec as JSON ONLY (no prose, no markdown).
Rules:
- Use only columns that exist in the profile (or that earlier steps create).
- Allowed step types: filter, select, rename, cast, derive, dedupe, aggregate.
- Expressions are single DuckDB SQL scalar expressions. No subqueries, no semicolons, no file or network functions.
- source.path must be exactly the path given. Name must be a snake_case identifier.
JSON schema:
"""


def _call(messages: list[dict]) -> str:
    r = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01"},
        json={"model": PLANNER_MODEL, "max_tokens": 1500,
              "system": SYSTEM + json.dumps(Pipeline.model_json_schema()), "messages": messages},
        timeout=60)
    r.raise_for_status()
    return "".join(b.get("text", "") for b in r.json()["content"])


def _parse(text: str) -> Pipeline:
    return Pipeline.model_validate_json(text[text.index("{"): text.rindex("}") + 1])


def plan(request: str, source_path: str, fmt: str, profile: dict, call=_call) -> Pipeline:
    if call is _call and not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    user = (f"Source: path={source_path} format={fmt}\nProfile: {json.dumps(profile, default=str)}\n"
            f"Request: {request}")
    msgs = [{"role": "user", "content": user}]
    text = call(msgs)
    try:
        return _parse(text)
    except (ValidationError, ValueError) as e:
        msgs += [{"role": "assistant", "content": text},
                 {"role": "user", "content": f"That spec was invalid: {e}\nReturn corrected JSON only."}]
        return _parse(call(msgs))
