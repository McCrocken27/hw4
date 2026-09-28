"""Data shapes and spec limits shared by main.py, agent.py and tools.py.

Pydantic checks every value against these types, so bad input is rejected before
it reaches the agent or the database. The spec limits at the top are the single
place every limit is defined.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import Annotated, Literal, TypeVar

from pydantic import BaseModel, EmailStr, Field, StringConstraints, field_validator, model_validator

# ============================================================================
# Spec limits
#
# Every spec limit for the Campus Customs backend, in one place.
#
# Change a number here and it changes everywhere it's enforced.
# ============================================================================

# Search and product results
MAX_RESULTS_PER_REQUEST = 50  # most products one /api/products request returns
PAGE_SIZE = 20  # products shown per page on the website
MAX_MATCHES = 50  # most matches any search or filter returns, even if more qualify

# Cart
MAX_QTY_PER_ITEM = 10  # most units of one product + size in a cart

# Processing loops
MAX_LOOP_ITERATIONS = 100  # most products or cart items any loop will process

# Agent runs
AGENT_TIME_LIMIT_SECONDS = 180  # a chat reply is stopped after 3 minutes
AGENT_REQUEST_LIMIT = 12  # most model calls for one chat reply (helpers included)

T = TypeVar("T")


class LoopLimitReached(Exception):
    """A loop hit MAX_LOOP_ITERATIONS before finishing."""


def bounded(items: Iterable[T], what: str, limit: int = MAX_LOOP_ITERATIONS, strict: bool = False) -> Iterator[T]:
    """Loop over items, but never more than `limit` of them.

    strict=False: stop quietly after `limit` items (the caller can tell by counting).
    strict=True:  raise LoopLimitReached if there are more than `limit` items.
    """
    for count, item in enumerate(items, start=1):
        if count > limit:
            if strict:
                raise LoopLimitReached(f"Stopped after {limit} {what}")
            return
        yield item


# ---------- chat: what the website sends and gets back ----------


class ChatTurn(BaseModel):
    """One message in the conversation."""

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class ChatRequest(BaseModel):
    """Body of POST /api/chat: the conversation so far, ending with the shopper's newest message.

    The website also says which page the shopper is on, and which product if it's a
    product page. The server looks the product up in the database itself, so only the ID
    is trusted from the browser, and an unknown ID is ignored.
    """

    messages: list[ChatTurn] = Field(min_length=1, max_length=40)
    current_page: str | None = Field(default=None, max_length=200, pattern=r"^/[\w\-./?=&%+]*$")
    current_product_id: str | None = Field(default=None, max_length=100, pattern=r"^[a-z0-9][a-z0-9\-]*$")

    @model_validator(mode="after")
    def ends_with_user(self):
        if self.messages[-1].role != "user":
            raise ValueError("The last message must be from the user")
        return self


class ProductCard(BaseModel):
    """A clickable product shown under a chat reply."""

    product_id: str
    name: str
    price: float
    image_url: str


class ChatReply(BaseModel):
    """Body returned by POST /api/chat."""

    reply: str
    products: list[ProductCard] = Field(default_factory=list)
    agents_used: list[str] = Field(
        default_factory=list, description="Display names of the agents that worked on this reply"
    )


class HistoryMessage(BaseModel):
    """One saved message from GET /api/chat/history (logged-in shoppers only)."""

    role: Literal["user", "assistant"]
    content: str
    products: list[ProductCard] = Field(default_factory=list)
    created_at: str


class AgentOutput(BaseModel):
    """What the model must return. agent.py turns product_ids into ProductCards."""

    reply: str = Field(description="The message shown to the shopper, in plain text")
    product_ids: list[str] = Field(
        default_factory=list,
        description="product_id of every product the reply recommends or mentions, best first",
    )


class ShopperContext(BaseModel):
    """Who the agent is talking to, from the logged-in account (all empty for guests).

    The Shopping Assistant gets the shopper's name and email. Helper agents never do, and
    nothing else from the account (password hash, orders, other customers) is shared.
    """

    logged_in: bool = False
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None


class CurrentProduct(BaseModel):
    """The product the shopper is looking at, read fresh from the catalogue table."""

    product_id: str
    name: str
    garment_type: str
    price: float
    colors: list[str]


class PageContext(BaseModel):
    """Where the shopper is on the website when they send a message."""

    page: str | None = Field(default=None, description="The page's path, e.g. /products/yale-dad-hoodie or /cart")
    current_product: CurrentProduct | None = Field(
        default=None, description="The product being viewed; set only on a product detail page"
    )


@dataclass
class ChatDeps:
    """Passed to every tool during one chat reply.

    shopper_context (name and email) and page_context (current page and product) stay with
    the main agent; helper agents only ever get the question. agents_used collects which
    agents worked on the reply, for the agent log.
    """

    shopper_context: ShopperContext
    page_context: PageContext = field(default_factory=PageContext)
    agents_used: list[str] = field(default_factory=list)

    def used(self, agent_name: str) -> None:
        if agent_name not in self.agents_used:
            self.agents_used.append(agent_name)


# ---------- tool results: what the agent sees ----------


class ProductSummary(BaseModel):
    product_id: str
    name: str
    garment_type: str
    price: float
    short_description: str


class DescriptionLookup(BaseModel):
    """Result of description_lookup: price and full description, straight from the catalogue table."""

    product_id: str
    name: str
    garment_type: str
    price: float
    description: str
    colors: list[str]


class SizeLookup(BaseModel):
    """Result of size_lookup: which sizes the item comes in and which can be bought right now."""

    product_id: str
    name: str
    sizes_offered: list[str]
    sizes_in_stock: list[str]
    sizes_out_of_stock: list[str]


class SizeStock(BaseModel):
    size: str
    quantity: int
    status: Literal["in stock", "OUT OF STOCK"]


class StockLookup(BaseModel):
    """Result of stock_lookup: exact quantities from the inventory table."""

    product_id: str
    name: str
    stock: list[SizeStock]
    total_in_stock: int
    completely_out_of_stock: bool = Field(description="True only if every size is at 0")
    summary: str


class SearchResult(BaseModel):
    total_matches: int
    products: list[ProductSummary]
    note: str = ""


GarmentType = Literal["hoodie", "crewneck", "t-shirt", "quarter-zip", "jacket", "long-sleeve shirt", "mockneck"]
Size = Literal["XS", "S", "M", "L", "XL", "XXL"]
Design = Literal["logo", "script"]
Weather = Literal["warm", "cold"]


class FilteredProduct(BaseModel):
    """One result of filter_products, with the traits it was filtered on."""

    product_id: str
    name: str
    garment_type: str
    price: float
    colors: list[str]
    weather: Weather
    has_logo: bool
    has_script: bool
    sizes_in_stock: list[str]


class FilterResult(BaseModel):
    filters_used: dict[str, str]
    total_matches: int
    products: list[FilteredProduct]
    note: str = ""


class Category(BaseModel):
    garment_type: str
    product_count: int
    lowest_price: float
    highest_price: float


# ---------- product lists ----------


class ProductPage(BaseModel):
    """Body of GET /api/products. Never more than 50 products per request."""

    products: list[dict]
    total_matches: int = Field(description="How many products qualified, before the 50-product cap")
    returned: int
    max_results: int = Field(description="The per-request cap (50)")
    page_size: int = Field(description="How many the website shows per page (20)")
    capped: bool = Field(description="True if more products qualified than were returned")
    partial: bool = Field(description="True if the 100-iteration loop cap stopped the search early")


# ---------- Yale Athletics scores ----------


class GameResult(BaseModel):
    date: str
    sport: str
    opponent: str
    home: bool
    outcome: Literal["W", "L", "T"]
    yale_score: int
    opponent_score: int


class UpcomingGame(BaseModel):
    date: str
    time: str | None
    sport: str
    opponent: str
    home: bool


class Scoreboard(BaseModel):
    """Body of GET /api/scores."""

    results: list[GameResult]
    upcoming: list[UpcomingGame]
    updated_at: str | None
    source: str
    available: bool


# ---------- cart and orders ----------

CartSize = Literal["XS", "S", "M", "L", "XL", "XXL"]


class AddItemRequest(BaseModel):
    """Body of POST /api/cart/items."""

    product_id: str = Field(min_length=1, max_length=100)
    size: CartSize
    quantity: int = Field(default=1, ge=1, le=10)


class SetQuantityRequest(BaseModel):
    """Body of PATCH /api/cart/items/{product_id}/{size}. 0 removes the item."""

    quantity: int = Field(ge=0, le=10)


class CartLine(BaseModel):
    product_id: str
    name: str
    size: str
    quantity: int
    in_stock: int
    unit_price: float
    line_total: float
    image_url: str
    problem: str | None = Field(
        default=None, description="Set if stock dropped below what's in the cart since it was added"
    )


class Cart(BaseModel):
    """The shopper's cart. All prices and totals are worked out on the server."""

    items: list[CartLine]
    item_count: int
    subtotal: float
    subtotal_cents: int
    has_problems: bool


class StockProblem(BaseModel):
    """One item that can't be ordered because there isn't enough stock."""

    product_id: str
    name: str
    size: str
    requested: int
    available: int


class OrderLine(BaseModel):
    product_id: str
    name: str
    size: str
    quantity: int
    unit_price: float
    line_total: float


class OrderReceipt(BaseModel):
    order_id: int
    status: str
    items: list[OrderLine]
    item_count: int
    subtotal: float
    created_at: str


# ---------- accounts ----------

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
Password = Annotated[str, StringConstraints(max_length=128)]


class PublicUser(BaseModel):
    """The only user fields ever sent to the browser. Never includes the password hash."""

    id: int
    first_name: str | None
    last_name: str | None
    email: str


class SignupRequest(BaseModel):
    first_name: Name
    last_name: Name
    email: EmailStr = Field(max_length=254)
    password: Password
    confirm_password: Password

    @field_validator("first_name", "last_name")
    @classmethod
    def plain_name(cls, value: str) -> str:
        if not re.fullmatch(r"[^\W\d_]+(?:[ '\-.][^\W\d_]+)*\.?", value):
            raise ValueError("Names can only use letters, spaces, hyphens and apostrophes")
        return value

    @field_validator("password")
    @classmethod
    def strong_password(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
            raise ValueError("Password must include at least one letter and one number")
        return value

    @model_validator(mode="after")
    def passwords_match(self):
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")
        if self.email.split("@")[0].lower() in self.password.lower():
            raise ValueError("Password cannot contain your email name")
        return self


class LoginRequest(BaseModel):
    email: str = Field(max_length=254)
    password: Password
