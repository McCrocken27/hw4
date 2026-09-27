r"""Campus Customs API (FastAPI).

Run from backend/:  uvicorn main:app --reload --port 8000
                    (with the venv active, or .venv\Scripts\python.exe -m uvicorn ...)
Open API docs:      http://127.0.0.1:8000/docs
Frontend (Vite):    http://127.0.0.1:5173

Sections: accounts, carts and orders, chat history, Yale scores, then the API routes.
The AI agent itself lives in agent.py, tools.py, models.py and prompts/prompt.md.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sqlite3
import ssl
import threading
import time
import xml.etree.ElementTree as ET
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import httpx
import truststore
from fastapi import Cookie, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import tools
from agent import run_chat
from models import (
    MAX_LOOP_ITERATIONS,
    MAX_QTY_PER_ITEM,
    MAX_RESULTS_PER_REQUEST,
    PAGE_SIZE,
    AddItemRequest,
    Cart,
    CartLine,
    ChatReply,
    ChatRequest,
    GameResult,
    HistoryMessage,
    LoginRequest,
    LoopLimitReached,
    OrderLine,
    OrderReceipt,
    ProductCard,
    ProductPage,
    PublicUser,
    Scoreboard,
    SetQuantityRequest,
    ShopperContext,
    SignupRequest,
    StockProblem,
    UpcomingGame,
    bounded,
)

logger = logging.getLogger("uvicorn.error")


# ============================================================================
# Accounts: passwords, sessions and login rate limiting
#
# Accounts, password hashing, login sessions and login rate limiting.
#
# Security choices:
# - Passwords are never stored. Only a salted PBKDF2-SHA256 hash is kept.
#   New hashes use 600,000 rounds: "pbkdf2_sha256$600000$<salt>$<hex digest>".
#   Older rows use "pbkdf2_sha256$<salt>$<hex digest>" at 120,000 rounds; they still
#   work and are upgraded to the stronger format the next time that user logs in.
# - Login sessions are random 256-bit tokens kept in an HttpOnly cookie. The database
#   only holds a SHA-256 hash of each token, so a leaked database cannot be used to
#   hijack sessions.
# - Every query uses ? placeholders, so user input is never pasted into SQL.
# - Repeated failed logins are slowed down per email and per IP address.
# ============================================================================

ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 600_000
LEGACY_ITERATIONS = 120_000
SESSION_DAYS = 7

MAX_FAILED_PER_EMAIL = 5
MAX_FAILED_PER_IP = 20
LOCKOUT_SECONDS = 15 * 60


class EmailTaken(Exception):
    pass


# ---------- password hashing ----------


def _pbkdf2(password: str, salt: str, iterations: int) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations).hex()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    return f"{ALGORITHM}${ITERATIONS}${salt}${_pbkdf2(password, salt, ITERATIONS)}"


def _parse_hash(stored: str) -> tuple[int, str, str] | None:
    parts = stored.split("$")
    if len(parts) == 4 and parts[0] == ALGORITHM and parts[1].isdigit():
        return int(parts[1]), parts[2], parts[3]
    if len(parts) == 3 and parts[0] == ALGORITHM:
        return LEGACY_ITERATIONS, parts[1], parts[2]
    return None


def verify_password(password: str, stored: str) -> bool:
    parsed = _parse_hash(stored)
    if parsed is None:
        return False
    iterations, salt, digest = parsed
    # compare_digest takes the same time whether or not the hashes match.
    return hmac.compare_digest(_pbkdf2(password, salt, iterations), digest)


def needs_rehash(stored: str) -> bool:
    parsed = _parse_hash(stored)
    return parsed is None or parsed[0] < ITERATIONS


# Checked when an email is not registered, so a wrong email takes as long as a wrong password.
_DUMMY_HASH = hash_password(secrets.token_hex(16))


# ---------- users ----------


def _public_user(row: sqlite3.Row) -> dict:
    """The only user fields ever sent to the browser. Never includes the password hash."""
    return {
        "id": row["id"],
        "first_name": row["first_name"],
        "last_name": row["last_name"],
        "email": row["email"],
    }


def create_user(first_name: str, last_name: str, email: str, password: str) -> dict:
    email = email.strip().lower()
    with tools.get_db() as conn:
        if conn.execute(
            "SELECT 1 FROM users WHERE lower(email) = ?", (email,)
        ).fetchone():
            raise EmailTaken
        try:
            cur = conn.execute(
                "INSERT INTO users (name, first_name, last_name, email, password_hash)"
                " VALUES (?, ?, ?, ?, ?)",
                (f"{first_name} {last_name}", first_name, last_name, email, hash_password(password)),
            )
        except sqlite3.IntegrityError as exc:
            raise EmailTaken from exc
        row = conn.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _public_user(row)


def authenticate(email: str, password: str) -> dict | None:
    """Return the user if the email and password match, else None."""
    email = email.strip().lower()
    with tools.get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE lower(email) = ?", (email,)).fetchone()
        if row is None:
            verify_password(password, _DUMMY_HASH)
            return None
        if not verify_password(password, row["password_hash"]):
            return None
        if needs_rehash(row["password_hash"]):
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (hash_password(password), row["id"]),
            )
    return _public_user(row)


# ---------- sessions ----------


def init_sessions_table() -> None:
    with tools.get_db() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )"""
        )
        conn.execute("DELETE FROM sessions WHERE expires_at < ?", (_auth_now(),))


def _auth_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    with tools.get_db() as conn:
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (_token_hash(token), user_id, _auth_now(), expires.isoformat(timespec="seconds")),
        )
    return token


def user_for_session(token: str | None) -> dict | None:
    if not token:
        return None
    with tools.get_db() as conn:
        row = conn.execute(
            "SELECT users.* FROM sessions JOIN users ON users.id = sessions.user_id"
            " WHERE sessions.token_hash = ? AND sessions.expires_at > ?",
            (_token_hash(token), _auth_now()),
        ).fetchone()
    return _public_user(row) if row else None


def delete_session(token: str | None) -> None:
    if token:
        with tools.get_db() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))


# ---------- login rate limiting ----------

_failures: dict[str, list[float]] = {}
_failures_lock = threading.Lock()


def _recent_failures(key: str, now: float) -> list[float]:
    stamps = [t for t in _failures.get(key, []) if now - t < LOCKOUT_SECONDS]
    _failures[key] = stamps
    return stamps


def login_blocked(key: str, limit: int) -> bool:
    now = time.monotonic()
    with _failures_lock:
        return len(_recent_failures(key, now)) >= limit


def record_failed_login(*keys: str) -> None:
    now = time.monotonic()
    with _failures_lock:
        for k in keys:
            _recent_failures(k, now).append(now)


def clear_failed_logins(*keys: str) -> None:
    with _failures_lock:
        for k in keys:
            _failures.pop(k, None)


# ============================================================================
# Carts and orders
#
# Shopping carts and orders, stored in campus_customs.db.
#
# Tables (created at startup if missing):
# - carts:       one per shopper. Logged-in shoppers' carts are tied to user_id; guests'
#                carts are found by a random cookie token (only its SHA-256 hash is stored).
# - cart_items:  product_id + size + quantity. One row per product and size.
# - orders / order_items: placed orders, with the price paid for each item.
#
# Rules:
# - Prices and totals always come from the database, never from the browser.
# - Money is added up in whole cents so totals never drift (no 0.1 + 0.2 problems).
# - A cart can never hold more of a size than is in stock.
# - Placing an order re-checks stock inside one database transaction. If any item asks
#   for more than is available, the whole order is rejected and nothing changes.
# ============================================================================

MAX_PER_ITEM = MAX_QTY_PER_ITEM  # 10 units of one product + size
MAX_CART_LINES = MAX_LOOP_ITERATIONS  # loops over cart items never pass 100


class CartError(Exception):
    """A request the cart can't do. status is the HTTP code to send back."""

    def __init__(self, status: int, message: str, problems: list[StockProblem] | None = None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.problems = problems or []


def init_cart_tables() -> None:
    with tools.get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS carts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE,
                token_hash TEXT UNIQUE,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS cart_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cart_id INTEGER NOT NULL,
                product_id TEXT NOT NULL,
                size TEXT NOT NULL,
                quantity INTEGER NOT NULL CHECK (quantity > 0),
                added_at TEXT NOT NULL,
                FOREIGN KEY (cart_id) REFERENCES carts(id),
                FOREIGN KEY (product_id) REFERENCES catalogue(product_id),
                UNIQUE (cart_id, product_id, size)
            );
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                item_count INTEGER NOT NULL,
                subtotal_cents INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                product_id TEXT NOT NULL,
                size TEXT NOT NULL,
                quantity INTEGER NOT NULL CHECK (quantity > 0),
                unit_price_cents INTEGER NOT NULL,
                line_total_cents INTEGER NOT NULL,
                FOREIGN KEY (order_id) REFERENCES orders(id),
                FOREIGN KEY (product_id) REFERENCES catalogue(product_id)
            );
            """
        )


def _cart_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _cents(price: float) -> int:
    return round(price * 100)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_guest_token() -> str:
    return secrets.token_urlsafe(32)


def _capped(rows):
    """Loop over cart items, refusing to go past 100 (the processing-loop cap)."""
    try:
        yield from bounded(rows, "cart items", strict=True)
    except LoopLimitReached as exc:
        raise CartError(413, f"{exc}. Please remove some items and try again.") from exc


# ---------- finding the shopper's cart ----------


def _find_cart(conn: sqlite3.Connection, user_id: int | None, token: str | None) -> int | None:
    if user_id is not None:
        row = conn.execute("SELECT id FROM carts WHERE user_id = ?", (user_id,)).fetchone()
    elif token:
        row = conn.execute(
            "SELECT id FROM carts WHERE token_hash = ? AND user_id IS NULL", (_hash_token(token),)
        ).fetchone()
    else:
        row = None
    return row["id"] if row else None


def _get_or_create_cart(conn: sqlite3.Connection, user_id: int | None, token: str | None) -> int:
    cart_id = _find_cart(conn, user_id, token)
    if cart_id is not None:
        return cart_id
    if user_id is None and not token:
        raise CartError(400, "Missing cart")
    now = _cart_now()
    cur = conn.execute(
        "INSERT INTO carts (user_id, token_hash, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (user_id, None if user_id is not None else _hash_token(token), now, now),
    )
    return cur.lastrowid


def _touch_cart(conn: sqlite3.Connection, cart_id: int) -> None:
    conn.execute("UPDATE carts SET updated_at = ? WHERE id = ?", (_cart_now(), cart_id))


# ---------- stock ----------


def _stock(conn: sqlite3.Connection, product_id: str, size: str) -> int:
    """How many of this product and size are in stock. Raises 404 if it doesn't exist."""
    if not conn.execute("SELECT 1 FROM catalogue WHERE product_id = ?", (product_id,)).fetchone():
        raise CartError(404, "That product doesn't exist")
    row = conn.execute(
        "SELECT quantity FROM inventory WHERE product_id = ? AND size = ?", (product_id, size)
    ).fetchone()
    if row is None:
        raise CartError(404, f"That product doesn't come in size {size}")
    return row["quantity"]


def _check_stock(requested: int, available: int, name_size: str) -> None:
    if available <= 0:
        raise CartError(409, f"{name_size} is out of stock")
    if requested > available:
        raise CartError(409, f"Only {available} of {name_size} in stock")


def _item_label(conn: sqlite3.Connection, product_id: str, size: str) -> str:
    row = conn.execute("SELECT name FROM catalogue WHERE product_id = ?", (product_id,)).fetchone()
    return f"{row['name'] if row else product_id} (size {size})"


# ---------- reading the cart ----------


def _read_cart(conn: sqlite3.Connection, cart_id: int | None) -> Cart:
    if cart_id is None:
        return Cart(items=[], item_count=0, subtotal=0.0, subtotal_cents=0, has_problems=False)
    rows = conn.execute(
        """SELECT ci.product_id, ci.size, ci.quantity, c.name, c.price, c.image_file_path,
                  COALESCE(i.quantity, 0) AS in_stock
           FROM cart_items ci
           JOIN catalogue c ON c.product_id = ci.product_id
           LEFT JOIN inventory i ON i.product_id = ci.product_id AND i.size = ci.size
           WHERE ci.cart_id = ?
           ORDER BY ci.id""",
        (cart_id,),
    ).fetchall()
    lines = []
    for r in _capped(rows):
        unit = _cents(r["price"])
        lines.append(
            CartLine(
                product_id=r["product_id"],
                name=r["name"],
                size=r["size"],
                quantity=r["quantity"],
                in_stock=r["in_stock"],
                unit_price=unit / 100,
                line_total=unit * r["quantity"] / 100,
                image_url=f"/media/{r['image_file_path']}",
                problem=(
                    "Out of stock" if r["in_stock"] <= 0
                    else f"Only {r['in_stock']} left" if r["quantity"] > r["in_stock"]
                    else None
                ),
            )
        )
    subtotal_cents = sum(round(line.line_total * 100) for line in lines)
    return Cart(
        items=lines,
        item_count=sum(line.quantity for line in lines),
        subtotal=subtotal_cents / 100,
        subtotal_cents=subtotal_cents,
        has_problems=any(line.problem for line in lines),
    )


def read_cart(user_id: int | None, token: str | None) -> Cart:
    with tools.get_readonly_db() as conn:
        return _read_cart(conn, _find_cart(conn, user_id, token))


# ---------- changing the cart ----------


def add_item(user_id: int | None, token: str | None, product_id: str, size: str, quantity: int) -> Cart:
    """Add quantity more of a product and size. Rejected if the cart would exceed stock."""
    with tools.get_db() as conn:
        available = _stock(conn, product_id, size)
        cart_id = _get_or_create_cart(conn, user_id, token)
        row = conn.execute(
            "SELECT quantity FROM cart_items WHERE cart_id = ? AND product_id = ? AND size = ?",
            (cart_id, product_id, size),
        ).fetchone()
        new_quantity = (row["quantity"] if row else 0) + quantity
        if new_quantity > MAX_PER_ITEM:
            raise CartError(409, f"You can have up to {MAX_PER_ITEM} of one item and size in your cart")
        _check_stock(new_quantity, available, _item_label(conn, product_id, size))
        if row is None:
            lines = conn.execute("SELECT COUNT(*) FROM cart_items WHERE cart_id = ?", (cart_id,)).fetchone()[0]
            if lines >= MAX_CART_LINES:
                raise CartError(409, f"Your cart can hold up to {MAX_CART_LINES} different items")
        conn.execute(
            """INSERT INTO cart_items (cart_id, product_id, size, quantity, added_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT (cart_id, product_id, size) DO UPDATE SET quantity = excluded.quantity""",
            (cart_id, product_id, size, new_quantity, _cart_now()),
        )
        _touch_cart(conn, cart_id)
        return _read_cart(conn, cart_id)


def set_quantity(user_id: int | None, token: str | None, product_id: str, size: str, quantity: int) -> Cart:
    """Change how many of an item are in the cart. 0 removes it."""
    if quantity == 0:
        return remove_item(user_id, token, product_id, size)
    if quantity > MAX_PER_ITEM:
        raise CartError(409, f"You can have up to {MAX_PER_ITEM} of one item and size in your cart")
    with tools.get_db() as conn:
        cart_id = _find_cart(conn, user_id, token)
        if cart_id is None or not conn.execute(
            "SELECT 1 FROM cart_items WHERE cart_id = ? AND product_id = ? AND size = ?",
            (cart_id, product_id, size),
        ).fetchone():
            raise CartError(404, "That item isn't in your cart")
        _check_stock(quantity, _stock(conn, product_id, size), _item_label(conn, product_id, size))
        conn.execute(
            "UPDATE cart_items SET quantity = ? WHERE cart_id = ? AND product_id = ? AND size = ?",
            (quantity, cart_id, product_id, size),
        )
        _touch_cart(conn, cart_id)
        return _read_cart(conn, cart_id)


def remove_item(user_id: int | None, token: str | None, product_id: str, size: str) -> Cart:
    with tools.get_db() as conn:
        cart_id = _find_cart(conn, user_id, token)
        deleted = 0
        if cart_id is not None:
            deleted = conn.execute(
                "DELETE FROM cart_items WHERE cart_id = ? AND product_id = ? AND size = ?",
                (cart_id, product_id, size),
            ).rowcount
        if not deleted:
            raise CartError(404, "That item isn't in your cart")
        _touch_cart(conn, cart_id)
        return _read_cart(conn, cart_id)


def clear_cart(user_id: int | None, token: str | None) -> Cart:
    with tools.get_db() as conn:
        cart_id = _find_cart(conn, user_id, token)
        if cart_id is not None:
            conn.execute("DELETE FROM cart_items WHERE cart_id = ?", (cart_id,))
            _touch_cart(conn, cart_id)
        return _read_cart(conn, cart_id)


def merge_guest_cart(token: str | None, user_id: int) -> None:
    """When a guest logs in, move their cart into their account (never beyond stock)."""
    if not token:
        return
    with tools.get_db() as conn:
        guest_id = _find_cart(conn, None, token)
        if guest_id is None:
            return
        user_cart = _get_or_create_cart(conn, user_id, None)
        for item in _capped(conn.execute(
            "SELECT product_id, size, quantity FROM cart_items WHERE cart_id = ?", (guest_id,)
        ).fetchall()):
            existing = conn.execute(
                "SELECT quantity FROM cart_items WHERE cart_id = ? AND product_id = ? AND size = ?",
                (user_cart, item["product_id"], item["size"]),
            ).fetchone()
            available = conn.execute(
                "SELECT quantity FROM inventory WHERE product_id = ? AND size = ?",
                (item["product_id"], item["size"]),
            ).fetchone()
            wanted = min(
                (existing["quantity"] if existing else 0) + item["quantity"],
                available["quantity"] if available else 0,
                MAX_PER_ITEM,
            )
            if wanted > 0:
                conn.execute(
                    """INSERT INTO cart_items (cart_id, product_id, size, quantity, added_at)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT (cart_id, product_id, size) DO UPDATE SET quantity = excluded.quantity""",
                    (user_cart, item["product_id"], item["size"], wanted, _cart_now()),
                )
        conn.execute("DELETE FROM cart_items WHERE cart_id = ?", (guest_id,))
        conn.execute("DELETE FROM carts WHERE id = ?", (guest_id,))
        _touch_cart(conn, user_cart)


# ---------- placing an order ----------


def place_order_from_cart(user_id: int) -> OrderReceipt:
    """Turn the shopper's cart into an order.

    Everything happens in one locked transaction: stock is re-checked for every item,
    and if any item asks for more than is in stock the whole order is rejected with a
    list of the problems. Otherwise inventory goes down, the order is saved, and the
    cart is emptied.
    """
    conn = tools.get_db()
    conn.isolation_level = None  # manage the transaction by hand
    try:
        # IMMEDIATE takes the write lock now, so two orders can't both claim the last item.
        conn.execute("BEGIN IMMEDIATE")
        cart_id = _find_cart(conn, user_id, None)
        rows = conn.execute(
            """SELECT ci.product_id, ci.size, ci.quantity, c.name, c.price,
                      COALESCE(i.quantity, 0) AS in_stock
               FROM cart_items ci
               JOIN catalogue c ON c.product_id = ci.product_id
               LEFT JOIN inventory i ON i.product_id = ci.product_id AND i.size = ci.size
               WHERE ci.cart_id = ?
               ORDER BY ci.id""",
            (cart_id,),
        ).fetchall() if cart_id else []
        if not rows:
            raise CartError(400, "Your cart is empty")
        rows = list(_capped(rows))

        problems = [
            StockProblem(
                product_id=r["product_id"],
                name=r["name"],
                size=r["size"],
                requested=r["quantity"],
                available=max(r["in_stock"], 0),
            )
            for r in rows
            if r["quantity"] > r["in_stock"]
        ]
        if problems:
            raise CartError(
                409, "Some items don't have enough stock. Nothing was ordered.", problems
            )

        lines = [
            OrderLine(
                product_id=r["product_id"],
                name=r["name"],
                size=r["size"],
                quantity=r["quantity"],
                unit_price=_cents(r["price"]) / 100,
                line_total=_cents(r["price"]) * r["quantity"] / 100,
            )
            for r in rows
        ]
        subtotal_cents = sum(_cents(r["price"]) * r["quantity"] for r in rows)
        item_count = sum(r["quantity"] for r in rows)
        now = _cart_now()
        order_id = conn.execute(
            "INSERT INTO orders (user_id, status, item_count, subtotal_cents, created_at)"
            " VALUES (?, 'placed', ?, ?, ?)",
            (user_id, item_count, subtotal_cents, now),
        ).lastrowid
        for r in rows:
            unit = _cents(r["price"])
            conn.execute(
                "INSERT INTO order_items (order_id, product_id, size, quantity, unit_price_cents, line_total_cents)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (order_id, r["product_id"], r["size"], r["quantity"], unit, unit * r["quantity"]),
            )
            # The "quantity >= ?" guard means stock can never go below zero.
            updated = conn.execute(
                "UPDATE inventory SET quantity = quantity - ?"
                " WHERE product_id = ? AND size = ? AND quantity >= ?",
                (r["quantity"], r["product_id"], r["size"], r["quantity"]),
            ).rowcount
            if updated != 1:
                raise CartError(409, "Stock changed while ordering. Nothing was ordered.")
        conn.execute("DELETE FROM cart_items WHERE cart_id = ?", (cart_id,))
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()

    return OrderReceipt(
        order_id=order_id,
        status="placed",
        items=lines,
        item_count=item_count,
        subtotal=subtotal_cents / 100,
        created_at=now,
    )


# ============================================================================
# Chat history and the agent log table
#
# Chat history (chat_messages table) and the agent log (agent_log table).
#
# chat_messages follows the format of the rows already in the database:
# - one row per message; role is "user" or "assistant"
# - products_json is NULL for the shopper's message; for the assistant's message it is a
#   JSON list of the products shown with the reply ([] if none)
# - both rows of one exchange share the same created_at timestamp (UTC, "YYYY-MM-DD HH:MM:SS")
#
# Only logged-in shoppers get chat history. The agent log records every reply (guests too)
# but stores only which agents and tools were used, never the message text.
# ============================================================================

HISTORY_LIMIT = 50

# Same keys as the products already saved in chat_messages.products_json.
SAVED_PRODUCT_KEYS = (
    "product_id", "name", "garment_type", "description", "colors", "search_tags",
    "image_file_path", "image_url", "price", "inventory", "total_stock",
)


def init_agent_log_table() -> None:
    with tools.get_db() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS agent_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                chat_message_id INTEGER,
                agents_used TEXT NOT NULL,
                tools_used TEXT NOT NULL,
                outcome TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (chat_message_id) REFERENCES chat_messages(id)
            )"""
        )


def _history_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _saved_product(product_id: str) -> dict | None:
    p = tools.get_product(product_id)
    if p is None:
        return None
    p["image_file_path"] = p["image_url"].removeprefix("/media/")
    return {k: p[k] for k in SAVED_PRODUCT_KEYS}


def save_exchange(user_id: int, user_text: str, reply: str, product_ids: list[str]) -> int:
    """Save the shopper's message and the reply. Returns the assistant row's id."""
    products = [p for p in (_saved_product(pid) for pid in product_ids) if p]
    stamp = _history_now()
    with tools.get_db() as conn:
        conn.execute(
            "INSERT INTO chat_messages (user_id, role, content, products_json, created_at)"
            " VALUES (?, 'user', ?, NULL, ?)",
            (user_id, user_text, stamp),
        )
        cur = conn.execute(
            "INSERT INTO chat_messages (user_id, role, content, products_json, created_at)"
            " VALUES (?, 'assistant', ?, ?, ?)",
            (user_id, reply, json.dumps(products, ensure_ascii=False), stamp),
        )
        return cur.lastrowid


def get_history(user_id: int, limit: int = HISTORY_LIMIT) -> list[HistoryMessage]:
    """The shopper's most recent messages, oldest first. Only ever their own rows."""
    with tools.get_readonly_db() as conn:
        rows = conn.execute(
            "SELECT role, content, products_json, created_at FROM chat_messages"
            " WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    messages = []
    for row in reversed(rows):
        products = json.loads(row["products_json"]) if row["products_json"] else []
        cards = [
            ProductCard(
                product_id=p["product_id"],
                name=p["name"],
                price=p["price"],
                image_url=p.get("image_url") or f"/media/{p['image_file_path']}",
            )
            for p in products
        ]
        messages.append(
            HistoryMessage(role=row["role"], content=row["content"], products=cards, created_at=row["created_at"])
        )
    return messages


def log_agents(
    user_id: int | None,
    chat_message_id: int | None,
    agents_used: list[str],
    tools_used: list[str],
    outcome: str,
) -> None:
    with tools.get_db() as conn:
        conn.execute(
            "INSERT INTO agent_log (user_id, chat_message_id, agents_used, tools_used, outcome, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, chat_message_id, json.dumps(agents_used), json.dumps(tools_used), outcome, _history_now()),
        )


# ============================================================================
# Yale Athletics scores
#
# Yale Athletics scores for the home page ticker.
#
# Source: the public calendar RSS feed on yalebulldogs.com (Yale's official athletics site).
# Each finished game's description has a result line like "W 3-1", "L 25-38" or "T 1-1".
# The feed is fetched at most every 15 minutes and cached in memory; if it can't be
# reached, the last good copy is served, or an empty list if there isn't one yet.
# ============================================================================

FEED_URL = "https://yalebulldogs.com/calendar.ashx/calendar.rss?sport_id=0"
SOURCE_URL = "https://yalebulldogs.com"
CACHE_SECONDS = 15 * 60
MAX_RESULTS = 15
MAX_UPCOMING = 6

SIDEARM = "{http://sidearmsports.com/schemas/cal_rss/1.0/}"
RESULT_LINE = re.compile(r"^\s*([WLT])\s+(\d+)\s*-\s*(\d+)", re.MULTILINE)
SPORT = re.compile(r"Yale University (.+?) (?:vs\.?|at) ", re.IGNORECASE)
OPPONENT_CLEANUP = re.compile(r"^(University of |The )", re.IGNORECASE)

_scores_cache: dict = {"at": 0.0, "board": None}

# Check HTTPS certificates with the operating system's trust tools. yalebulldogs.com
# doesn't send its full certificate chain, which Windows can complete but Python's
# bundled list can't. Certificates are still fully verified.
_TLS = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
_scores_lock = threading.Lock()


def _parse_feed(xml_text: str) -> Scoreboard:
    root = ET.fromstring(xml_text)
    results: list[GameResult] = []
    upcoming: list[UpcomingGame] = []
    now = datetime.now().isoformat()

    for item in root.findall("channel/item"):
        title = item.findtext("title") or ""
        # The feed separates lines with a literal "\n" (backslash + n), not real newlines.
        description = (item.findtext("description") or "").replace("\\n", "\n")
        start = (item.findtext(f"{SIDEARM}localstartdate") or "")[:19]
        sport_match = SPORT.search(title)
        opponent = OPPONENT_CLEANUP.sub("", (item.findtext(f"{SIDEARM}opponent") or "").strip())
        if not sport_match or not opponent or not start:
            continue
        sport = sport_match.group(1).strip()
        home = " vs" in title.split(sport, 1)[-1][:5]
        if opponent.lower().startswith("yale"):
            # Events Yale hosts list Yale itself as the "opponent".
            opponent, home = "Yale-hosted event", True
        result = RESULT_LINE.search(description)
        if result:
            outcome, yale, them = result.groups()
            results.append(
                GameResult(
                    date=start[:10],
                    sport=sport,
                    opponent=opponent,
                    home=home,
                    outcome=outcome,
                    yale_score=int(yale),
                    opponent_score=int(them),
                )
            )
        elif start >= now[: len(start)]:
            upcoming.append(
                UpcomingGame(date=start[:10], time=start[11:16] or None, sport=sport, opponent=opponent, home=home)
            )

    results.sort(key=lambda g: g.date, reverse=True)
    upcoming.sort(key=lambda g: (g.date, g.time or ""))
    return Scoreboard(
        results=results[:MAX_RESULTS],
        upcoming=upcoming[:MAX_UPCOMING],
        updated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        source=SOURCE_URL,
        available=True,
    )


def get_scoreboard() -> Scoreboard:
    with _scores_lock:
        board = _scores_cache["board"]
        if board is not None and time.monotonic() - _scores_cache["at"] < CACHE_SECONDS:
            return board
        try:
            response = httpx.get(
                FEED_URL,
                timeout=10,
                headers={"User-Agent": "CampusCustoms/1.0"},
                follow_redirects=True,
                verify=_TLS,
            )
            response.raise_for_status()
            board = _parse_feed(response.text)
            _scores_cache.update(at=time.monotonic(), board=board)
        except Exception as exc:
            logger.warning("scores feed failed: %s: %s", type(exc).__name__, exc)
            # Try again in a minute rather than on every page load.
            _scores_cache["at"] = time.monotonic() - CACHE_SECONDS + 60
            if board is None:
                return Scoreboard(results=[], upcoming=[], updated_at=None, source=SOURCE_URL, available=False)
        return board


# ============================================================================
# The API
#
# FastAPI app and routes.
# ============================================================================

SESSION_COOKIE = "cc_session"
CART_COOKIE = "cc_cart"  # guests only; logged-in shoppers' carts are tied to their account
CART_DAYS = 30
# Set COOKIE_SECURE=1 when the site is served over HTTPS so the cookie is never sent over plain HTTP.
COOKIE_SECURE = os.getenv("COOKIE_SECURE") == "1"

CHAT_LIMIT = 15  # messages per visitor per minute; each one costs a model call


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_sessions_table()
    init_agent_log_table()
    init_cart_tables()
    yield


app = FastAPI(title="Campus Customs", version="0.3.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)


@app.exception_handler(CartError)
async def cart_error(_: Request, exc: CartError):
    """Cart and order problems come back as {"detail": "...", "problems": [...]}."""
    return JSONResponse(
        status_code=exc.status,
        content={"detail": exc.message, "problems": [p.model_dump() for p in exc.problems]},
    )


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    if request.url.path.startswith(("/api/auth", "/api/cart", "/api/orders")):
        response.headers["Cache-Control"] = "no-store"
    return response


# Product images, e.g. /media/products/yale-dad-hoodie.jpg. Only the products folder is
# served, so the database file next to it can never be downloaded.
app.mount("/media/products", StaticFiles(directory=tools.DATA_DIR / "products"), name="media")


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_DAYS * 24 * 3600,
        httponly=True,  # page scripts (and anything injected into them) cannot read it
        samesite="strict",  # other websites cannot make requests with it
        secure=COOKIE_SECURE,
        path="/",
    )


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


_chat_times: dict[str, list[float]] = {}
_chat_lock = threading.Lock()


def _chat_allowed(key: str) -> bool:
    now = time.monotonic()
    with _chat_lock:
        recent = [t for t in _chat_times.get(key, []) if now - t < 60]
        allowed = len(recent) < CHAT_LIMIT
        if allowed:
            recent.append(now)
        _chat_times[key] = recent
    return allowed


# ---------- products ----------


@app.get("/api/health")
def health():
    return {"ok": True, "products": tools.count_products()}


@app.get("/api/products", response_model=ProductPage)
def products(
    q: str = Query(default="", max_length=100),
    sort: str = Query(default="relevance", pattern="^(relevance|price-asc|price-desc|name-asc|name-desc)$"),
    ids: str = Query(default="", max_length=3000, description="Comma-separated product_ids"),
):
    """Products for the website: a search (?q=), a sort (?sort=), or specific ?ids=.

    Returns at most 50 products per request, even if more qualify. Sorting happens
    before the cap, so "price high to low" really starts with the most expensive items.
    """
    if ids:
        wanted = [i for i in ids.split(",") if i][: MAX_RESULTS_PER_REQUEST]
        found = tools.get_products_by_ids(wanted)
        page = tools.SearchPage(found, len(found), partial=False)
    else:
        page = tools.search_catalogue(q, sort=sort, limit=MAX_RESULTS_PER_REQUEST)
    return ProductPage(
        products=page.products,
        total_matches=page.total_matches,
        returned=len(page.products),
        max_results=MAX_RESULTS_PER_REQUEST,
        page_size=PAGE_SIZE,
        capped=page.total_matches > len(page.products),
        partial=page.partial,
    )


@app.get("/api/products/{product_id}")
def product(product_id: str):
    item = tools.get_product(product_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return item


# ---------- chat ----------


@app.post("/api/chat", response_model=ChatReply)
async def chat(body: ChatRequest, request: Request, cc_session: str | None = Cookie(default=None)):
    """Send the conversation to the shopping agent and return its reply plus product cards.

    Logged-in shoppers get both messages saved to chat_messages. Every reply is written
    to agent_log with the agents and tools that worked on it.
    """
    if not _chat_allowed(_client_ip(request)):
        raise HTTPException(
            status_code=429, detail="You're sending messages quickly. Please wait a minute."
        )
    user = user_for_session(cc_session)
    shopper = ShopperContext(first_name=user["first_name"] if user else None)
    result = await run_chat(body.messages, shopper)

    message_id = None
    if user and result.outcome == "answered":
        message_id = save_exchange(
            user["id"], body.messages[-1].content, result.reply.reply, result.product_ids
        )
    log_agents(
        user["id"] if user else None,
        message_id,
        result.reply.agents_used,
        result.tools_used,
        result.outcome,
    )
    return result.reply


@app.get("/api/chat/history", response_model=list[HistoryMessage])
def chat_history(cc_session: str | None = Cookie(default=None)):
    """The logged-in shopper's saved chat. Guests have no saved """
    user = user_for_session(cc_session)
    if user is None:
        return []
    return get_history(user["id"])


# ---------- Yale Athletics scores ----------


@app.get("/api/scores", response_model=Scoreboard)
def yale_scores():
    """Latest Yale Athletics results and upcoming games, from yalebulldogs.com (cached 15 min)."""
    return get_scoreboard()


# ---------- cart ----------


def _cart_owner(
    response: Response | None, cc_session: str | None, cc_cart: str | None, create: bool = False
) -> tuple[int | None, str | None]:
    """Whose cart this is: the logged-in user, or a guest identified by the cart cookie.

    Guests get a random cart cookie the first time they add something.
    """
    user = user_for_session(cc_session)
    if user:
        return user["id"], None
    if not cc_cart and create and response is not None:
        cc_cart = new_guest_token()
        response.set_cookie(
            CART_COOKIE,
            cc_cart,
            max_age=CART_DAYS * 24 * 3600,
            httponly=True,
            samesite="strict",
            secure=COOKIE_SECURE,
            path="/",
        )
    return None, cc_cart


@app.get("/api/cart", response_model=Cart)
def get_cart(cc_session: str | None = Cookie(default=None), cc_cart: str | None = Cookie(default=None)):
    """The shopper's cart, with prices and totals worked out from the database."""
    return read_cart(*_cart_owner(None, cc_session, cc_cart))


@app.post("/api/cart/items", response_model=Cart)
def add_to_cart(
    body: AddItemRequest,
    response: Response,
    cc_session: str | None = Cookie(default=None),
    cc_cart: str | None = Cookie(default=None),
):
    """Add an item. Rejected with 409 if the cart would hold more than is in stock."""
    user_id, token = _cart_owner(response, cc_session, cc_cart, create=True)
    return add_item(user_id, token, body.product_id, body.size, body.quantity)


@app.patch("/api/cart/items/{product_id}/{size}", response_model=Cart)
def update_cart_item(
    product_id: str,
    size: str,
    body: SetQuantityRequest,
    cc_session: str | None = Cookie(default=None),
    cc_cart: str | None = Cookie(default=None),
):
    """Set an item's quantity (0 removes it). Rejected with 409 if it's more than is in stock."""
    return set_quantity(*_cart_owner(None, cc_session, cc_cart), product_id, size, body.quantity)


@app.delete("/api/cart/items/{product_id}/{size}", response_model=Cart)
def remove_from_cart(
    product_id: str,
    size: str,
    cc_session: str | None = Cookie(default=None),
    cc_cart: str | None = Cookie(default=None),
):
    return remove_item(*_cart_owner(None, cc_session, cc_cart), product_id, size)


@app.delete("/api/cart", response_model=Cart)
def empty_cart(cc_session: str | None = Cookie(default=None), cc_cart: str | None = Cookie(default=None)):
    return clear_cart(*_cart_owner(None, cc_session, cc_cart))


# ---------- orders ----------


@app.post("/api/orders", status_code=201, response_model=OrderReceipt)
def place_order(cc_session: str | None = Cookie(default=None)):
    """Place an order from the cart (logged-in shoppers only, no payment yet).

    Stock is checked again at this moment. If any item asks for more than is available,
    the whole order is rejected with 409 and a list of the problems, and nothing changes.
    """
    user = user_for_session(cc_session)
    if user is None:
        raise HTTPException(status_code=401, detail="Please log in to place an order")
    return place_order_from_cart(user["id"])


# ---------- accounts ----------


def _move_guest_cart(response: Response, cc_cart: str | None, user_id: int) -> None:
    """After logging in or signing up, the guest cart joins the account's """
    if cc_cart:
        merge_guest_cart(cc_cart, user_id)
        response.delete_cookie(CART_COOKIE, path="/")


@app.post("/api/auth/signup", status_code=201, response_model=PublicUser)
def signup(body: SignupRequest, response: Response, cc_cart: str | None = Cookie(default=None)):
    try:
        user = create_user(body.first_name, body.last_name, body.email, body.password)
    except EmailTaken:
        raise HTTPException(status_code=409, detail="An account with that email already exists")
    _set_session_cookie(response, create_session(user["id"]))
    _move_guest_cart(response, cc_cart, user["id"])
    return user


@app.post("/api/auth/login", response_model=PublicUser)
def login(
    body: LoginRequest, request: Request, response: Response, cc_cart: str | None = Cookie(default=None)
):
    email_key = f"email:{body.email.strip().lower()}"
    ip_key = f"ip:{_client_ip(request)}"
    if login_blocked(email_key, MAX_FAILED_PER_EMAIL) or login_blocked(
        ip_key, MAX_FAILED_PER_IP
    ):
        raise HTTPException(
            status_code=429, detail="Too many failed attempts. Please wait 15 minutes and try again."
        )
    user = authenticate(body.email, body.password)
    if user is None:
        record_failed_login(email_key, ip_key)
        # Same message for a wrong email or a wrong password, so attackers can't find accounts.
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    clear_failed_logins(email_key)
    _set_session_cookie(response, create_session(user["id"]))
    _move_guest_cart(response, cc_cart, user["id"])
    return user


@app.post("/api/auth/logout")
def logout(response: Response, cc_session: str | None = Cookie(default=None)):
    delete_session(cc_session)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@app.get("/api/auth/me")
def me(cc_session: str | None = Cookie(default=None)) -> dict[str, PublicUser | None]:
    user = user_for_session(cc_session)
    return {"user": PublicUser(**user) if user else None}
