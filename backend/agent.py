"""Campus Customs chat agents: PydanticAI on gpt-5.6-luna through Portkey.

Wiring:
- Shopping Assistant (main agent): prompts/prompt.md, the product tools in tools.py, and
  two delegation tools that hand questions to helper agents.
- Campus Guide (helper): the Campus Guide section of prompts/prompt.md. General Yale and New Haven questions,
  with web search. No database access.
- Style Advisor (helper): the Style Advisor section of prompts/prompt.md. Outfit, weather and gift advice.
  No database access, no tools.

Helpers only ever receive the question the main agent writes. They never see the
shopper's name, account, chat history or the database.
main.py calls run_chat().
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from pydantic_ai import Agent, RunContext, WebSearchTool
from pydantic_ai.capabilities import NativeTool
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    NativeToolCallPart,
    TextPart,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import UsageLimits

from models import (
    AGENT_REQUEST_LIMIT,
    AGENT_TIME_LIMIT_SECONDS,
    AgentOutput,
    ChatDeps,
    ChatReply,
    ChatTurn,
    CurrentProduct,
    PageContext,
    ProductCard,
    ShopperContext,
)
from tools import ALL_TOOLS, get_product

HERE = Path(__file__).resolve().parent
PROMPT_PATH = HERE / "prompts" / "prompt.md"

# The API key lives in .env at the project root (next to README.md).
load_dotenv(HERE.parent / ".env")
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

MODEL_NAME = "gpt-5.6-luna"
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"
MAX_CARDS = 4
# Caps model calls per message (helpers included), so a run can't loop forever.
USAGE_LIMITS = UsageLimits(request_limit=AGENT_REQUEST_LIMIT)
MAX_HELPER_QUESTION = 500

SHOPPING_ASSISTANT = "Shopping Assistant"
CAMPUS_GUIDE = "Campus Guide"
STYLE_ADVISOR = "Style Advisor"

logger = logging.getLogger("uvicorn.error")


@dataclass
class ChatOutcome:
    """Everything main.py needs after one reply: what to show, save and log."""

    reply: ChatReply
    product_ids: list[str]
    tools_used: list[str]
    outcome: str


def _model() -> OpenAIResponsesModel:
    api_key = os.getenv("PORTKEY_API_KEY")
    if not api_key:
        raise RuntimeError("PORTKEY_API_KEY is missing. Copy .env.example to .env and add your key.")
    provider = OpenAIProvider(base_url=PORTKEY_BASE_URL, api_key=api_key)
    return OpenAIResponsesModel(MODEL_NAME, provider=provider)


def _prompts() -> dict[str, str]:
    """Split prompts/prompt.md into the Shopping Assistant's prompt and each helper's.

    Helper sections start with a line like "# Helper Agent: Campus Guide". Everything
    before the first one is the Shopping Assistant's system prompt.
    """
    text = PROMPT_PATH.read_text(encoding="utf-8")
    pieces = re.split(r"^# Helper Agent: (.+)$", text, flags=re.MULTILINE)
    main = re.sub(r"<!--.*?-->", "", pieces[0], flags=re.DOTALL).strip()
    sections = {SHOPPING_ASSISTANT: main}
    for name, body in zip(pieces[1::2], pieces[2::2]):
        sections[name.strip()] = f"# {name.strip()} (helper agent)\n{body}".strip()
    return sections


def _finished(result) -> str:
    return f"final answer returned (finish_reason={result.response.finish_reason or 'unknown'})"


def _stop_reason(exc: BaseException) -> str:
    """A plain-English reason a run stopped early, for the audit trail."""
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
        return f"stopped: hit the {AGENT_TIME_LIMIT_SECONDS}-second time limit"
    if isinstance(exc, asyncio.CancelledError):
        return "stopped: the whole reply hit its time limit"
    if isinstance(exc, UsageLimitExceeded):
        return f"stopped: usage limit reached ({exc})"
    if "content_filter" in str(exc):
        return "stopped: blocked by the content filter"
    return f"error: {type(exc).__name__}"


async def _run_helper(helper: Agent, name: str, question: str, ctx: RunContext[ChatDeps]) -> str:
    """Run a helper agent and add its run to the audit trail, however it ends."""
    ctx.deps.used(name)
    try:
        result = await helper.run(question[:MAX_HELPER_QUESTION], usage=ctx.usage)
    except BaseException as exc:
        record_audit(name, "", _stop_reason(exc))
        raise
    record_audit(name, result.output, _finished(result))
    return result.output


def build_agent() -> Agent[ChatDeps, AgentOutput]:
    """A fresh set of agents per request, so no HTTP client outlives its request."""
    model = _model()
    prompts = _prompts()
    campus_guide = Agent(
        model,
        name=CAMPUS_GUIDE,
        instructions=prompts[CAMPUS_GUIDE],
        capabilities=[NativeTool(WebSearchTool(search_context_size="low"))],
    )
    style_advisor = Agent(model, name=STYLE_ADVISOR, instructions=prompts[STYLE_ADVISOR])

    agent = Agent(
        model,
        name=SHOPPING_ASSISTANT,
        deps_type=ChatDeps,
        output_type=AgentOutput,
        instructions=prompts[SHOPPING_ASSISTANT],
        tools=ALL_TOOLS,
    )

    @agent.instructions
    def shopper_instructions(ctx: RunContext[ChatDeps]) -> str:
        """The logged-in shopper's name and email, added to the instructions each reply."""
        shopper_context = ctx.deps.shopper_context
        if not shopper_context.logged_in:
            return "## Shopper\nThe shopper is not logged in, so you don't know their name or email."
        full_name = " ".join(part for part in (shopper_context.first_name, shopper_context.last_name) if part)
        return (
            "## Shopper\n"
            f"- name: {full_name}\n"
            f"- first name: {shopper_context.first_name}\n"
            f"- email: {shopper_context.email}\n"
            "This comes from their account, so it's accurate. Follow the privacy rules for it."
        )

    @agent.instructions
    def page_context_instructions(ctx: RunContext[ChatDeps]) -> str:
        """The current page and the currently viewed product, added to the instructions each reply."""
        page_context = ctx.deps.page_context
        current_product = page_context.current_product
        lines = ["## Current page"]
        lines.append(
            f"The shopper is on this page of the website: {page_context.page}" if page_context.page else "The page is unknown."
        )
        if current_product:
            lines.append(
                "They are looking at this product (read from the database just now):\n"
                f"- product_id: {current_product.product_id}\n"
                f"- name: {current_product.name}\n"
                f"- type: {current_product.garment_type}\n"
                f"- price: ${current_product.price:.2f}\n"
                f"- colors: {', '.join(current_product.colors)}\n"
                'When they say "this", "it", "this one" or ask about a color or size without naming a '
                f"product (for example \"Do you have this in medium?\"), they mean {current_product.name}. "
                f"For sizes and stock, call size_lookup or stock_lookup with product_id {current_product.product_id}."
            )
        else:
            lines.append("They are not on a product page, so there is no current product.")
        return "\n".join(lines)

    @agent.tool
    async def ask_campus_guide(ctx: RunContext[ChatDeps], question: str) -> str:
        """Ask the Campus Guide agent a general question about Yale or New Haven.

        Use for traditions, history, residential colleges, sports, The Game, or what a
        design refers to. It knows nothing about our products. Send only the question,
        never the shopper's name or personal details.

        Args:
            question: One self-contained question, e.g. "Who is Handsome Dan?"
        """
        return await _run_helper(campus_guide, CAMPUS_GUIDE, question, ctx)

    @agent.tool
    async def ask_style_advisor(ctx: RunContext[ChatDeps], question: str) -> str:
        """Ask the Style Advisor agent for outfit, weather, layering or gift advice.

        It answers with general advice and suggested filters (type, weather, design,
        color) to use with filter_products. It knows nothing about our products. Send only
        the question, never the shopper's name or personal details.

        Args:
            question: One self-contained question, e.g. "What should I wear to a November football game?"
        """
        return await _run_helper(style_advisor, STYLE_ADVISOR, question, ctx)

    return agent


def _history(turns: list[ChatTurn]) -> list[ModelMessage]:
    """Rebuild earlier turns in the format PydanticAI expects."""
    messages: list[ModelMessage] = []
    for turn in turns:
        if turn.role == "user":
            messages.append(ModelRequest(parts=[UserPromptPart(content=turn.content)]))
        else:
            messages.append(ModelResponse(parts=[TextPart(content=turn.content)]))
    return messages


def _tools_used(messages: list[ModelMessage]) -> list[str]:
    names: list[str] = []
    for message in messages:
        for part in message.parts:
            if isinstance(part, (ToolCallPart, NativeToolCallPart)) and part.tool_name != "final_result":
                if part.tool_name not in names:
                    names.append(part.tool_name)
    return names


def _cards(product_ids: list[str]) -> tuple[list[ProductCard], list[str]]:
    """Look up each product the model mentioned. Made-up ids are silently dropped."""
    cards, kept = [], []
    for product_id in dict.fromkeys(product_ids):
        product = get_product(product_id)
        if product:
            cards.append(ProductCard(**{k: product[k] for k in ProductCard.model_fields}))
            kept.append(product_id)
        if len(cards) == MAX_CARDS:
            break
    return cards, kept


def shopper_context_from_user(user: dict | None) -> ShopperContext:
    """The shopper's name and email for the agent, from the logged-in user (empty for guests).

    main.py passes the user it found from the login cookie, so identity can't be faked by
    typing into the chat.
    """
    if not user:
        return ShopperContext()
    return ShopperContext(
        logged_in=True,
        first_name=user.get("first_name"),
        last_name=user.get("last_name"),
        email=user.get("email"),
    )


def build_page_context(current_page: str | None, current_product_id: str | None) -> PageContext:
    """The page the shopper is on, plus the currently viewed product on a product detail page.

    The product is looked up in the catalogue table here, so only its ID is trusted from the
    browser. An ID that isn't in the database is ignored.
    """
    current_product = None
    if current_product_id:
        found = get_product(current_product_id)
        if found:
            current_product = CurrentProduct(**{k: found[k] for k in CurrentProduct.model_fields})
    return PageContext(page=current_page, current_product=current_product)


async def run_chat(
    turns: list[ChatTurn],
    shopper_context: ShopperContext,
    page_context: PageContext | None = None,
) -> ChatOutcome:
    """Answer the shopper's newest message.

    Three kinds of context reach the agent:
    - identity: `shopper_context` (name and email) goes into the instructions
    - conversation: earlier `turns` become the model's message history
    - page: `page_context` (current page and current_product) goes into the instructions
    """
    *earlier, latest = turns
    deps = ChatDeps(
        shopper_context=shopper_context,
        page_context=page_context or PageContext(),
        agents_used=[SHOPPING_ASSISTANT],
    )
    try:
        # Nothing runs longer than 3 minutes: past that, the run is cancelled.
        result = await asyncio.wait_for(
            build_agent().run(
                latest.content,
                deps=deps,
                message_history=_history(earlier),
                usage_limits=USAGE_LIMITS,
            ),
            timeout=AGENT_TIME_LIMIT_SECONDS,
        )
    except Exception as exc:
        # Log details on the server only; shoppers never see internal error text.
        logger.warning("chat failed: %s: %s", type(exc).__name__, exc)
        reason = _stop_reason(exc)
        if "content filter" in reason:
            text = "Sorry, I can only help with Campus Customs products, sizes and stock."
        elif "time limit" in reason:
            text = "Sorry, that took too long. Please try a simpler question."
        elif "usage limit" in reason:
            text = "Sorry, I couldn't finish that one. Please try asking in a simpler way."
        else:
            text = "Sorry, something went wrong on our end. Please try again in a moment."
        record_audit(SHOPPING_ASSISTANT, text, reason)
        return ChatOutcome(ChatReply(reply=text, agents_used=deps.agents_used), [], [], reason)

    record_audit(SHOPPING_ASSISTANT, result.output.reply, _finished(result))
    cards, product_ids = _cards(result.output.product_ids)
    return ChatOutcome(
        reply=ChatReply(reply=result.output.reply, products=cards, agents_used=deps.agents_used),
        product_ids=product_ids,
        tools_used=_tools_used(result.all_messages()),
        outcome="answered",
    )


# ============================================================================
# Audit trail
#
# Append-only audit trail of agent loop activity: output/audit_trail.json.
#
# Every agent run (the Shopping Assistant and each helper it calls) adds one entry:
#     {"time": "...", "name": "...", "result": "...", "stop_reason": "..."}
#
# Rules:
# - Entries are only ever added. The file is never cleared, between runs or restarts.
# - Each write goes to a temporary file first and then replaces the real one, so a crash
#   mid-write can't leave a half-written file.
# - If the file can't be read (for example someone edited it by hand and broke the JSON),
#   it's copied to audit_trail.unreadable-<time>.json and a new list is started. Nothing
#   is deleted.
# - Shoppers' messages are not stored here, only a short piece of each agent's result,
#   with any email address replaced by "[email hidden]".
# ============================================================================

AUDIT_PATH = Path(__file__).resolve().parent.parent / "output" / "audit_trail.json"
RESULT_CHARS = 300

_audit_lock = threading.Lock()


EMAIL_ADDRESS = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")


def _clip_result(text: str) -> str:
    """Shorten a result for the audit trail, blanking out any email address."""
    text = EMAIL_ADDRESS.sub("[email hidden]", " ".join(str(text).split()))
    return text if len(text) <= RESULT_CHARS else text[: RESULT_CHARS - 1].rstrip() + "…"


def _read_existing() -> list:
    if not AUDIT_PATH.exists():
        return []
    raw = AUDIT_PATH.read_text(encoding="utf-8").strip()
    if not raw:
        return []
    try:
        rows = json.loads(raw)
        return rows if isinstance(rows, list) else [rows]
    except json.JSONDecodeError:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        AUDIT_PATH.with_name(f"audit_trail.unreadable-{stamp}.json").write_text(raw, encoding="utf-8")
        return []


def record_audit(name: str, result: str, stop_reason: str) -> None:
    """Add one entry. Never raises: a logging problem must not break the chat."""
    entry = {
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "name": name,
        "result": _clip_result(result),
        "stop_reason": stop_reason,
    }
    try:
        with _audit_lock:
            AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
            rows = _read_existing()
            rows.append(entry)
            tmp = AUDIT_PATH.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, AUDIT_PATH)
    except OSError as exc:
        logger.warning("audit trail write failed: %s", exc)
