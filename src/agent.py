"""LLM Agent implementations for commerce task execution.

Supports OpenAI (tool-use) and Anthropic (tool-use) backends.
Each agent executes a shopping task by calling Mock Commerce API tools.
"""

import json
import time
import traceback
from dataclasses import dataclass, field, asdict
from typing import Optional, Any

from src.config import AGENT_MAX_TURNS, AGENT_TEMPERATURE
from src.mock_api import (
    MockCommerceAPI, TOOL_DEFINITIONS_OPENAI, TOOL_DEFINITIONS_ANTHROPIC,
)


@dataclass
class AgentAction:
    """A single action taken by the agent."""
    turn: int
    tool_name: str
    tool_input: dict
    tool_output: Any
    reasoning: Optional[str] = None


@dataclass
class AgentResult:
    """Complete result of an agent's task execution."""
    success: bool
    purchased_items: list[dict]    # items the agent tried to purchase
    total_price: int
    actions: list[AgentAction]
    final_message: str
    error: Optional[str] = None
    total_latency_ms: float = 0.0


SYSTEM_PROMPT = """You are a shopping assistant agent. Your job is to complete the user's purchase request by:
1. Searching the product catalog to find suitable products
2. Comparing options based on the user's criteria
3. Making a purchase decision and completing the transaction

You have access to three tools:
- search_products: Search and filter the product catalog
- get_product: Get details on a specific product
- purchase: Complete a purchase

Important rules:
- Follow the user's instructions exactly, including any budget limits, brand preferences, quantity requirements, and quality criteria
- Only purchase products that match ALL of the user's stated criteria
- If no products match all criteria, report this to the user instead of purchasing something that doesn't match
- Complete the purchase in a single transaction
"""


def _dispatch_tool(api: MockCommerceAPI, name: str, args: dict) -> Any:
    """Route a tool call to the mock API."""
    if name == "search_products":
        return api.search_products(**args)
    elif name == "get_product":
        return api.get_product(**args)
    elif name == "purchase":
        return api.purchase(**args)
    else:
        return {"error": f"Unknown tool: {name}"}


def _serialize_tool_output(output: Any) -> str:
    """Convert tool output to string for LLM consumption."""
    if hasattr(output, "__dataclass_fields__"):
        return json.dumps(asdict(output), ensure_ascii=False)
    return json.dumps(output, ensure_ascii=False, default=str)


def run_agent_openai(
    user_intent: str,
    model_id: str,
    api: MockCommerceAPI,
) -> AgentResult:
    """Run a shopping task using OpenAI's tool-use API."""
    import openai

    client = openai.OpenAI()
    start = time.monotonic()
    actions = []
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_intent},
    ]

    purchased_items = []
    total_price = 0
    final_message = ""

    try:
        for turn in range(AGENT_MAX_TURNS):
            response = client.chat.completions.create(
                model=model_id,
                messages=messages,
                tools=TOOL_DEFINITIONS_OPENAI,
                temperature=AGENT_TEMPERATURE,
            )
            choice = response.choices[0]

            # If no tool calls, agent is done
            if choice.finish_reason == "stop" or not choice.message.tool_calls:
                final_message = choice.message.content or ""
                break

            # Process tool calls
            messages.append(choice.message)
            for tc in choice.message.tool_calls:
                fn_name = tc.function.name
                fn_args = json.loads(tc.function.arguments)
                result = _dispatch_tool(api, fn_name, fn_args)
                result_str = _serialize_tool_output(result)

                actions.append(AgentAction(
                    turn=turn,
                    tool_name=fn_name,
                    tool_input=fn_args,
                    tool_output=json.loads(result_str) if isinstance(result_str, str) else result_str,
                    reasoning=choice.message.content,
                ))

                # Track purchases
                if fn_name == "purchase" and hasattr(result, "success") and result.success:
                    purchased_items = result.items
                    total_price = result.total_price

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_str,
                })
        else:
            final_message = "Max turns reached without completing task."

    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        return AgentResult(
            success=False, purchased_items=[], total_price=0,
            actions=actions, final_message="",
            error=f"{type(e).__name__}: {e}\n{traceback.format_exc()}",
            total_latency_ms=elapsed,
        )

    elapsed = (time.monotonic() - start) * 1000
    return AgentResult(
        success=len(purchased_items) > 0,
        purchased_items=purchased_items,
        total_price=total_price,
        actions=actions,
        final_message=final_message,
        total_latency_ms=elapsed,
    )


def run_agent_anthropic(
    user_intent: str,
    model_id: str,
    api: MockCommerceAPI,
) -> AgentResult:
    """Run a shopping task using Anthropic's tool-use API."""
    import anthropic

    client = anthropic.Anthropic()
    start = time.monotonic()
    actions = []
    messages = [{"role": "user", "content": user_intent}]

    purchased_items = []
    total_price = 0
    final_message = ""

    try:
        for turn in range(AGENT_MAX_TURNS):
            response = client.messages.create(
                model=model_id,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=messages,
                tools=TOOL_DEFINITIONS_ANTHROPIC,
                temperature=AGENT_TEMPERATURE,
            )

            # Process response content blocks
            tool_uses = []
            text_parts = []
            for block in response.content:
                if block.type == "text":
                    text_parts.append(block.text)
                elif block.type == "tool_use":
                    tool_uses.append(block)

            if response.stop_reason == "end_turn" or not tool_uses:
                final_message = " ".join(text_parts)
                break

            # Build assistant message with all content blocks
            messages.append({"role": "assistant", "content": response.content})

            # Process each tool use
            tool_results = []
            for tu in tool_uses:
                fn_name = tu.name
                fn_args = tu.input
                result = _dispatch_tool(api, fn_name, fn_args)
                result_str = _serialize_tool_output(result)

                actions.append(AgentAction(
                    turn=turn,
                    tool_name=fn_name,
                    tool_input=fn_args,
                    tool_output=json.loads(result_str) if isinstance(result_str, str) else result_str,
                    reasoning=" ".join(text_parts) if text_parts else None,
                ))

                if fn_name == "purchase" and hasattr(result, "success") and result.success:
                    purchased_items = result.items
                    total_price = result.total_price

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": result_str,
                })

            messages.append({"role": "user", "content": tool_results})
        else:
            final_message = "Max turns reached without completing task."

    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        return AgentResult(
            success=False, purchased_items=[], total_price=0,
            actions=actions, final_message="",
            error=f"{type(e).__name__}: {e}\n{traceback.format_exc()}",
            total_latency_ms=elapsed,
        )

    elapsed = (time.monotonic() - start) * 1000
    return AgentResult(
        success=len(purchased_items) > 0,
        purchased_items=purchased_items,
        total_price=total_price,
        actions=actions,
        final_message=final_message,
        total_latency_ms=elapsed,
    )


def run_agent(
    user_intent: str,
    provider: str,
    model_id: str,
    api: MockCommerceAPI,
) -> AgentResult:
    """Unified agent entry point."""
    if provider == "openai":
        return run_agent_openai(user_intent, model_id, api)
    elif provider == "anthropic":
        return run_agent_anthropic(user_intent, model_id, api)
    else:
        raise ValueError(f"Unknown provider: {provider}")
