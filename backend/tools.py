"""The shopping agent's tools, and the read-only catalogue access they use.

Part 1 reads products and inventory from data/campus_customs.db. main.py also uses
it for the website's product pages and search.
Part 2 is the tools the agent can call (listed in ALL_TOOLS). They are all read-only
and only see products. Their docstrings are sent to the model as instructions.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from models import (
    MAX_LOOP_ITERATIONS,
    MAX_MATCHES,
    MAX_RESULTS_PER_REQUEST,
    Category,
    DescriptionLookup,
    Design,
    FilteredProduct,
    FilterResult,
    GarmentType,
    ProductSummary,
    SearchResult,
    Size,
    SizeLookup,
    SizeStock,
    StockLookup,
    Weather,
    bounded,
)

# ============================================================================
# Part 1: catalogue access (read products and inventory)
#
# Read products and inventory from data/campus_customs.db.
#
# Spec limits (see limits.py):
# - Searches and product lists return at most 50 products, even if more qualify.
# - No loop processes more than 100 products. Searches narrow the catalogue in SQL first,
#   so Python only scores the rows that could match; if more than 100 rows could still
#   match, scoring stops at 100 and the result is marked partial.
# ============================================================================

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "campus_customs.db"

SIZE_ORDER = ["XS", "S", "M", "L", "XL", "XXL"]

SORTS = {
    "relevance": "name COLLATE NOCASE",
    "price-asc": "price, name COLLATE NOCASE",
    "price-desc": "price DESC, name COLLATE NOCASE",
    "name-asc": "name COLLATE NOCASE",
    "name-desc": "name COLLATE NOCASE DESC",
}


def get_db() -> sqlite3.Connection:
    """Read-write connection. Only accounts, chat history, carts and orders use this."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_readonly_db() -> sqlite3.Connection:
    """Read-only connection for product lookups (including the chat agent's tools)."""
    conn = sqlite3.connect(f"{DB_PATH.as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def short_description(text: str, limit: int = 90) -> str:
    """First sentence, trimmed to fit on a product card."""
    first = re.split(r"(?<=[.!?])\s", text.strip(), maxsplit=1)[0]
    if len(first) <= limit:
        return first
    return first[: limit - 1].rsplit(" ", 1)[0].rstrip(",;") + "…"


def _product(row: sqlite3.Row) -> dict:
    return {
        "product_id": row["product_id"],
        "name": row["name"],
        "garment_type": row["garment_type"],
        "description": row["description"],
        "short_description": short_description(row["description"]),
        "colors": json.loads(row["colors"]),
        "search_tags": json.loads(row["search_tags"]),
        "image_url": f"/media/{row['image_file_path']}",
        "price": row["price"],
    }


def _sorted_sizes(sizes: list[dict]) -> list[dict]:
    rank = {s: i for i, s in enumerate(SIZE_ORDER)}
    return sorted(sizes, key=lambda s: rank.get(s["size"], len(SIZE_ORDER)))


def _with_inventory(conn: sqlite3.Connection, rows: list[sqlite3.Row]) -> list[dict]:
    """Turn catalogue rows into product dicts with stock per size (at most 100 rows)."""
    products = [_product(r) for r in bounded(rows, "products")]
    if not products:
        return []
    ids = [p["product_id"] for p in products]
    stock: dict[str, list[dict]] = {}
    for r in conn.execute(
        f"SELECT product_id, size, quantity FROM inventory WHERE product_id IN ({','.join('?' * len(ids))})",
        ids,
    ):
        stock.setdefault(r["product_id"], []).append({"size": r["size"], "quantity": r["quantity"]})
    for p in products:
        p["inventory"] = _sorted_sizes(stock.get(p["product_id"], []))
    return products


def count_products() -> int:
    with get_readonly_db() as conn:
        return conn.execute("SELECT COUNT(*) FROM catalogue").fetchone()[0]


def get_products_by_ids(product_ids: list[str]) -> list[dict]:
    """Specific products, in the order asked for (at most 50)."""
    ids = list(dict.fromkeys(product_ids))[:MAX_RESULTS_PER_REQUEST]
    if not ids:
        return []
    with get_readonly_db() as conn:
        rows = conn.execute(
            f"SELECT * FROM catalogue WHERE product_id IN ({','.join('?' * len(ids))})", ids
        ).fetchall()
        found = {p["product_id"]: p for p in _with_inventory(conn, rows)}
    return [found[i] for i in ids if i in found]


def get_product(product_id: str) -> dict | None:
    """One product with its per-size stock, or None if the id is unknown."""
    products = get_products_by_ids([product_id])
    if not products:
        return None
    product = products[0]
    product["total_stock"] = sum(s["quantity"] for s in product["inventory"])
    return product


# ---------- search ----------

# Words shoppers type that the catalogue spells differently.
SYNONYMS = {
    "tee": ["tee", "t-shirt", "t shirt"],
    "tshirt": ["t-shirt", "t shirt"],
    "hoody": ["hoodie", "hooded"],
    "hoodie": ["hoodie", "hooded"],
    "1/4": ["1/4", "1 4", "quarter"],
    "quarterzip": ["quarter-zip", "1 4 zip"],
    "sweater": ["sweater", "sweatshirt"],
    "grey": ["grey", "gray"],
    "gray": ["gray", "grey"],
}

# How much a match counts, by where it was found.
FIELD_WEIGHTS = {"name": 5, "garment_type": 3, "search_tags": 2, "colors": 2, "description": 1}

# All the text a search word can match, as one lowercase SQL expression.
HAYSTACK = "lower(name || ' ' || garment_type || ' ' || search_tags || ' ' || colors || ' ' || description)"


def _variants(word: str) -> list[str]:
    """The word, its synonyms, and its singular form ("hoodies" -> "hoodie")."""
    forms = [word]
    if len(word) > 3 and word.endswith("s"):
        forms.append(word[:-1])
    return list(dict.fromkeys(v for f in forms for v in SYNONYMS.get(f, [f])))


def _patterns(word: str) -> list[re.Pattern]:
    """Match the start of a word, so "hoo" finds "hoodie" but "na" doesn't find "Diana"."""
    return [re.compile(r"(?<![a-z0-9])" + re.escape(v)) for v in _variants(word)]


def _like(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


@dataclass
class SqlFilter:
    """A condition the database checks before any Python loop runs."""

    sql: str
    params: tuple = ()


@dataclass
class SearchPage:
    products: list[dict]
    total_matches: int  # how many products qualified (before the 50 cap)
    partial: bool  # True if the 100-iteration loop cap stopped scoring early


def search_catalogue(
    query: str = "",
    sort: str = "relevance",
    sql_filters: list[SqlFilter] | None = None,
    keep: Callable[[dict], bool] | None = None,
    limit: int = MAX_MATCHES,
) -> SearchPage:
    """Products matching every word of the query, best matches first, at most 50.

    Words can be partial ("hoo" finds hoodies) so results update as the shopper types.
    sql_filters narrow the rows in the database; keep() is an extra check in Python.
    """
    limit = min(limit, MAX_MATCHES)
    order = SORTS.get(sort, SORTS["relevance"])
    words = query.lower().split()[:10]
    where, params = [], []
    for word in words:
        variants = _variants(word)
        where.append("(" + " OR ".join(f"{HAYSTACK} LIKE ? ESCAPE '\\'" for _ in variants) + ")")
        params.extend(_like(v) for v in variants)
    for f in sql_filters or []:
        where.append(f"({f.sql})")
        params.extend(f.params)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    with get_readonly_db() as conn:
        # Nothing to score or check in Python: let the database sort and cap it.
        if not words and keep is None:
            total = conn.execute(f"SELECT COUNT(*) FROM catalogue {where_sql}", params).fetchone()[0]
            rows = conn.execute(
                f"SELECT * FROM catalogue {where_sql} ORDER BY {order} LIMIT ?", [*params, limit]
            ).fetchall()
            return SearchPage(_with_inventory(conn, rows), total, partial=False)

        # Otherwise fetch the rows that could match (one extra, to tell if there are more
        # than the loop cap), then score them in Python.
        rows = conn.execute(
            f"SELECT * FROM catalogue {where_sql} ORDER BY name COLLATE NOCASE LIMIT ?",
            [*params, MAX_LOOP_ITERATIONS + 1],
        ).fetchall()
        partial = len(rows) > MAX_LOOP_ITERATIONS
        candidates = _with_inventory(conn, rows)  # stops at 100

    patterns = [_patterns(w) for w in words]
    scored = []
    for p in bounded(candidates, "products"):
        if keep and not keep(p):
            continue
        fields = {
            "name": p["name"].lower(),
            "garment_type": p["garment_type"].lower(),
            "search_tags": " ".join(p["search_tags"]).lower(),
            "colors": " ".join(p["colors"]).lower(),
            "description": p["description"].lower(),
        }
        score = 0
        for word_patterns in patterns:
            best = max(
                (weight for field, weight in FIELD_WEIGHTS.items()
                 if any(pat.search(fields[field]) for pat in word_patterns)),
                default=0,
            )
            if best == 0:
                break  # every word has to match somewhere
            score += best
        else:
            if words and fields["name"].startswith(words[0]):
                score += 3
            scored.append((score, p))

    if sort == "price-asc":
        scored.sort(key=lambda r: (r[1]["price"], r[1]["name"].lower()))
    elif sort == "price-desc":
        scored.sort(key=lambda r: (-r[1]["price"], r[1]["name"].lower()))
    elif sort == "name-asc":
        scored.sort(key=lambda r: r[1]["name"].lower())
    elif sort == "name-desc":
        scored.sort(key=lambda r: r[1]["name"].lower(), reverse=True)
    else:
        scored.sort(key=lambda r: (-r[0], r[1]["name"].lower()))
    return SearchPage([p for _, p in scored[:limit]], len(scored), partial)


# ============================================================================
# Part 2: tools the agent can call
#
# Tools the shopping agent can call. All of them are read-only and only see products.
#
# The three lookup tools read campus_customs.db fresh on every call:
# - description_lookup: price and product description (catalogue table)
# - size_lookup: sizes offered, and which are in or out of stock (inventory table)
# - stock_lookup: exact quantity in stock for each size (inventory table)
#
# search_products and list_categories help the agent find the right product_id first.
# The docstrings are sent to the model as each tool's instructions.
# ============================================================================

MAX_RESULTS = 8
MAX_FILTER_RESULTS = 12
STOPWORDS = {"a", "an", "the", "and", "or", "of", "in", "for", "with", "any", "some", "me", "show", "yale"}

# The catalogue uses many labels for the same kind of item ("hoodie", "hooded
# sweatshirt", "pullover hoodie"...). Each family has a whole-word pattern, checked in
# order, so "sweatshirt" is never mistaken for "t-shirt".
FAMILIES = [
    ("quarter-zip", r"\b(quarter|1/4|half)[ -]?zip"),
    ("hoodie", r"\bhood"),
    ("jacket", r"\b(jacket|full[ -]?zip|bomber|fleece)"),
    ("t-shirt", r"\b(t[ -]?shirts?|tees?)\b"),
    ("long-sleeve shirt", r"\b(long[ -]?sleeve|performance)"),
    ("mockneck", r"\bmock[ -]?neck"),
    ("crewneck", r"\b(crew[ -]?neck|sweatshirt|sweater)"),
]


def garment_family(text: str) -> str | None:
    text = text.lower()
    for family, pattern in FAMILIES:
        if re.search(pattern, text):
            return family
    return None


def _summary(p: dict) -> ProductSummary:
    return ProductSummary(
        product_id=p["product_id"],
        name=p["name"],
        garment_type=p["garment_type"],
        price=p["price"],
        short_description=p["short_description"],
    )


# ---------- database pre-filters (they narrow rows before any Python loop runs) ----------

# Words that can appear in each family's garment_type. Deliberately broad; the exact
# family is re-checked in Python with garment_family().
FAMILY_LIKE = {
    "quarter-zip": ["quarter%zip", "1/4%zip", "half%zip"],
    "hoodie": ["hood"],
    "jacket": ["jacket", "full-zip", "full zip", "bomber", "fleece"],
    "t-shirt": ["t-shirt", "t shirt", "tee"],  # never "tshirt": it's inside "sweatshirt"
    "long-sleeve shirt": ["long-sleeve", "long sleeve", "performance"],
    "mockneck": ["mockneck", "mock neck"],
    "crewneck": ["crew", "sweatshirt", "sweater"],
}
LOGO_LIKE = ["logo", "crest", "shield", "emblem", "seal", "graphic", "mascot", "bulldog",
             "helmet", "illustration", "icon", "coat of arms", "heraldic"]
SCRIPT_LIKE = ["wordmark", "letter", "text", "script", "word", "reads", "spelled"]
ITEM_TEXT = "lower(name || ' ' || garment_type || ' ' || description)"


def _any_like(column: str, words: list[str]) -> SqlFilter:
    return SqlFilter(" OR ".join(f"{column} LIKE ?" for _ in words), tuple(f"%{w}%" for w in words))


def _family_filter(family: str) -> SqlFilter:
    return _any_like("lower(garment_type)", FAMILY_LIKE[family])


def _size_filter(size: str) -> SqlFilter:
    return SqlFilter(
        "EXISTS (SELECT 1 FROM inventory i WHERE i.product_id = catalogue.product_id"
        " AND i.size = ? AND i.quantity > 0)",
        (size,),
    )


def _weather_filter(weather: str) -> SqlFilter:
    if weather == "warm":
        return _family_filter("t-shirt")
    # Cold must let through everything that could be cold: anything that isn't clearly a
    # T-shirt, plus any item that mentions a hood or long sleeves.
    return SqlFilter(
        "NOT (lower(garment_type) LIKE '%t-shirt%' OR lower(garment_type) LIKE '%t shirt%')"
        f" OR {ITEM_TEXT} LIKE '%hood%' OR {ITEM_TEXT} LIKE '%long%sleeve%'"
    )


def _design_filter(design: str) -> SqlFilter:
    if design == "logo":
        return _any_like(ITEM_TEXT, LOGO_LIKE)
    words = _any_like(ITEM_TEXT, SCRIPT_LIKE)
    # GLOB is case-sensitive: three capitals in a row means printed text like "YALE".
    return SqlFilter(f"{words.sql} OR description GLOB '*[A-Z][A-Z][A-Z]*'", words.params)


def search_products(
    query: str = "",
    garment_type: str | None = None,
    color: str | None = None,
    max_price: float | None = None,
    size: str | None = None,
) -> SearchResult:
    """Search the Campus Customs catalogue and return up to 8 matching products.

    Keywords are matched against product name, garment type, colors, description and
    search tags. Every keyword has to match; if nothing matches all of them, products
    matching the most keywords are returned instead. Every filter is optional.

    Args:
        query: Keywords, e.g. "bulldog", "Saybrook", "hockey", "mom". Leave empty to browse.
        garment_type: Only this kind of item: hoodie, crewneck, t-shirt, quarter-zip,
            jacket, long-sleeve shirt or mockneck.
        color: Only items in this color, e.g. "navy", "gray", "white".
        max_price: Only items at or below this price in dollars.
        size: Only items with this size in stock: XS, S, M, L, XL or XXL.
    """
    words = [w for w in query.lower().split() if len(w) > 1 and w not in STOPWORDS][:10]
    filters: list[SqlFilter] = []
    family = garment_family(garment_type) if garment_type else None
    if family:
        filters.append(_family_filter(family))
    elif garment_type:
        filters.append(SqlFilter("lower(garment_type) LIKE ?", (f"%{garment_type.lower().rstrip('s')}%",)))
    if color:
        filters.append(SqlFilter("lower(colors) LIKE ?", (f"%{color.lower()}%",)))
    if max_price is not None:
        filters.append(SqlFilter("price <= ?", (max_price,)))
    if size:
        filters.append(_size_filter(size.strip().upper()))
    keep = (lambda p: garment_family(p["garment_type"]) == family) if family else None

    page = search_catalogue(" ".join(words), sql_filters=filters, keep=keep)
    products, total, partial = page.products, page.total_matches, page.partial
    if not products and len(words) > 1:
        # Nothing matched every keyword: rank by how many keywords each product matches.
        hits: dict[str, list] = {}
        for word in bounded(words, "keywords"):
            one = search_catalogue(word, sql_filters=filters, keep=keep)
            partial = partial or one.partial
            for p in bounded(one.products, "products"):
                hits.setdefault(p["product_id"], [0, p])[0] += 1
        ranked = sorted(hits.values(), key=lambda h: -h[0])
        products, total = [p for _, p in ranked][:MAX_MATCHES], len(ranked)

    note = ""
    if total > MAX_RESULTS:
        note = f"Showing the top {MAX_RESULTS} of {total}. Add keywords or filters to narrow it down."
    elif not products:
        note = "No matches. Try fewer keywords or drop a filter."
    if partial:
        note += f" The search stopped after checking {MAX_LOOP_ITERATIONS} products, so some may be missing."
    return SearchResult(
        total_matches=total,
        products=[_summary(p) for p in products[:MAX_RESULTS]],
        note=note.strip(),
    )


def _not_found(product_id: str) -> str:
    return f"No product with id {product_id!r} in the database. Use search_products to find the right id."


def _catalogue_row(conn, product_id: str):
    return conn.execute(
        "SELECT product_id, name, garment_type, price, description, colors"
        " FROM catalogue WHERE product_id = ?",
        (product_id,),
    ).fetchone()


def _inventory_rows(conn, product_id: str) -> list[tuple[str, int]]:
    rows = conn.execute(
        "SELECT size, quantity FROM inventory WHERE product_id = ?", (product_id,)
    ).fetchall()
    rank = {s: i for i, s in enumerate(SIZE_ORDER)}
    return sorted(((r["size"], r["quantity"]) for r in rows), key=lambda r: rank.get(r[0], 99))


def description_lookup(product_id: str) -> DescriptionLookup | str:
    """Look up a product's price and full description in the database.

    Returns the name, garment type, price in dollars, full description and colors.
    Use this before stating a price or describing an item.

    Args:
        product_id: The product_id from search_products, e.g. "yale-dad-hoodie".
    """
    with get_readonly_db() as conn:
        row = _catalogue_row(conn, product_id)
    if row is None:
        return _not_found(product_id)
    return DescriptionLookup(
        product_id=row["product_id"],
        name=row["name"],
        garment_type=row["garment_type"],
        price=row["price"],
        description=row["description"],
        colors=json.loads(row["colors"]),
    )


def size_lookup(product_id: str) -> SizeLookup | str:
    """Look up which sizes a product comes in, and which sizes are in or out of stock.

    Use this when a shopper asks what sizes are available.

    Args:
        product_id: The product_id from search_products, e.g. "yale-dad-hoodie".
    """
    with get_readonly_db() as conn:
        row = _catalogue_row(conn, product_id)
        inventory = _inventory_rows(conn, product_id) if row else []
    if row is None:
        return _not_found(product_id)
    return SizeLookup(
        product_id=product_id,
        name=row["name"],
        sizes_offered=[size for size, _ in inventory],
        sizes_in_stock=[size for size, qty in inventory if qty > 0],
        sizes_out_of_stock=[size for size, qty in inventory if qty <= 0],
    )


def stock_lookup(product_id: str, size: str | None = None) -> StockLookup | str:
    """Look up exactly how many of a product are in stock, for every size or one size.

    A quantity of 0 is marked "OUT OF STOCK". Use this before saying whether something
    is available or how many are left.

    Args:
        product_id: The product_id from search_products, e.g. "yale-dad-hoodie".
        size: Optional single size to check: XS, S, M, L, XL or XXL. Leave empty for all sizes.
    """
    with get_readonly_db() as conn:
        row = _catalogue_row(conn, product_id)
        inventory = _inventory_rows(conn, product_id) if row else []
    if row is None:
        return _not_found(product_id)
    product_total = sum(q for _, q in inventory)

    if size:
        size = size.strip().upper()
        offered = [s for s, _ in inventory]
        if size not in offered:
            return f"{row['name']} does not come in size {size}. Sizes offered: {', '.join(offered)}."
        inventory = [(s, q) for s, q in inventory if s == size]

    stock = [
        SizeStock(size=s, quantity=q, status="in stock" if q > 0 else "OUT OF STOCK")
        for s, q in inventory
    ]
    total = sum(item.quantity for item in stock)
    sold_out = [item.size for item in stock if item.quantity <= 0]
    if product_total == 0:
        summary = f"{row['name']} is OUT OF STOCK in every size."
    elif total == 0:
        summary = f"{row['name']} is OUT OF STOCK in size {size}."
    elif sold_out:
        summary = f"{total} in stock. OUT OF STOCK in: {', '.join(sold_out)}."
    else:
        summary = f"{total} in stock. Every size checked is available."
    return StockLookup(
        product_id=product_id,
        name=row["name"],
        stock=stock,
        total_in_stock=total,
        completely_out_of_stock=product_total == 0,
        summary=summary,
    )


# ---------- filtering ----------

# Kinds of items that always have long sleeves, even when the description doesn't say so.
LONG_SLEEVE_FAMILIES = {"crewneck", "quarter-zip", "jacket", "long-sleeve shirt", "mockneck"}
LOGO_WORDS = re.compile(
    r"\b(logos?|crests?|shields?|emblems?|seals?|graphics?|mascot|bulldogs?|helmets?|"
    r"illustrations?|icons?|coat of arms|heraldic)\b"
)
SCRIPT_WORDS = re.compile(
    r"\b(wordmarks?|lettering|letters?|block-letter|text|script|words?|reads|spelled)\b"
)
# Two or more capital words in a row (like "YALE HOCKEY") mean text is printed on it.
PRINTED_CAPS = re.compile(r"\b[A-Z]{3,}\b")


def product_traits(p: dict) -> dict:
    """Work out weather, logo and script traits from the catalogue text.

    Cold weather: the item has a hood or long sleeves. Everything else is warm weather.
    """
    text = " ".join([p["name"], p["garment_type"], p["description"]]).lower()
    family = garment_family(p["garment_type"])
    has_hood = bool(re.search(r"\bhood", text))
    has_long_sleeves = bool(re.search(r"\blong[ -]?sleeve", text)) or family in LONG_SLEEVE_FAMILIES
    return {
        "family": family,
        "weather": "cold" if has_hood or has_long_sleeves else "warm",
        "has_logo": bool(LOGO_WORDS.search(text)),
        "has_script": bool(SCRIPT_WORDS.search(text) or PRINTED_CAPS.search(p["description"])),
    }


def filter_products(
    garment_type: GarmentType | None = None,
    size: Size | None = None,
    color: str | None = None,
    design: Design | None = None,
    weather: Weather | None = None,
    keyword: str | None = None,
) -> FilterResult:
    """Filter the catalogue by any mix of these traits. Every filter is optional.

    Args:
        garment_type: Type of clothing: hoodie, crewneck, t-shirt, quarter-zip, jacket,
            long-sleeve shirt or mockneck.
        size: Only items with this size in stock right now: XS, S, M, L, XL or XXL.
        color: Only items that come in this color, e.g. "navy", "gray", "white", "cream".
        design: "logo" for items with a logo, crest, shield, mascot or other graphic.
            "script" for items with printed words or lettering (like a YALE wordmark).
            Many items have both.
        weather: "cold" for cold-weather clothing (has a hood or long sleeves).
            "warm" for warm-weather clothing (no hood and short sleeves).
        keyword: Optional word that must appear in the name or description, e.g. "bulldog", "Saybrook".
    """
    filters = {
        k: v
        for k, v in {
            "garment_type": garment_type,
            "size": size,
            "color": color,
            "design": design,
            "weather": weather,
            "keyword": keyword,
        }.items()
        if v
    }
    sql: list[SqlFilter] = []
    if garment_type:
        sql.append(_family_filter(garment_type))
    if size:
        sql.append(_size_filter(size))
    if color:
        sql.append(SqlFilter("lower(colors) LIKE ?", (f"%{color.lower()}%",)))
    if weather:
        sql.append(_weather_filter(weather))
    if design:
        sql.append(_design_filter(design))

    def keep(p: dict) -> bool:
        """Exact checks on the rows the database let through."""
        traits = product_traits(p)
        return (
            (not garment_type or traits["family"] == garment_type)
            and (not weather or traits["weather"] == weather)
            and (design != "logo" or traits["has_logo"])
            and (design != "script" or traits["has_script"])
        )

    page = search_catalogue(keyword or "", sql_filters=sql, keep=keep)
    matches = []
    for p in bounded(page.products, "products"):
        traits = product_traits(p)
        matches.append(
            FilteredProduct(
                product_id=p["product_id"],
                name=p["name"],
                garment_type=p["garment_type"],
                price=p["price"],
                colors=p["colors"],
                weather=traits["weather"],
                has_logo=traits["has_logo"],
                has_script=traits["has_script"],
                sizes_in_stock=[s["size"] for s in p["inventory"] if s["quantity"] > 0],
            )
        )

    note = ""
    if not matches:
        note = "Nothing matches every filter. Try dropping one filter and searching again."
    elif page.total_matches > MAX_FILTER_RESULTS:
        note = f"Showing {MAX_FILTER_RESULTS} of {page.total_matches}. Add a filter to narrow it down."
    if page.partial:
        note += f" The filter stopped after checking {MAX_LOOP_ITERATIONS} products, so some may be missing."
    return FilterResult(
        filters_used=filters,
        total_matches=page.total_matches,
        products=matches[:MAX_FILTER_RESULTS],
        note=note.strip(),
    )


def list_categories() -> list[Category]:
    """List every kind of item the store sells, with how many products and the price range.

    Use this when a shopper wants to browse or asks what the store carries.
    """
    # The database groups the products, so Python only loops over the ~20 garment labels.
    with get_readonly_db() as conn:
        rows = conn.execute(
            "SELECT garment_type, COUNT(*) AS n, MIN(price) AS lo, MAX(price) AS hi"
            " FROM catalogue GROUP BY garment_type"
        ).fetchall()
    groups: dict[str, list[float]] = {}
    for r in bounded(rows, "garment types"):
        family = garment_family(r["garment_type"]) or r["garment_type"]
        g = groups.setdefault(family, [0, r["lo"], r["hi"]])
        g[0] += r["n"]
        g[1], g[2] = min(g[1], r["lo"]), max(g[2], r["hi"])
    return [
        Category(garment_type=kind, product_count=n, lowest_price=lo, highest_price=hi)
        for kind, (n, lo, hi) in sorted(groups.items(), key=lambda kv: -kv[1][0])
    ]


ALL_TOOLS = [
    search_products,
    filter_products,
    description_lookup,
    size_lookup,
    stock_lookup,
    list_categories,
]
