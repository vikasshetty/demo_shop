import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.environ.get("DEMO_SHOP_DB", os.path.join(os.path.dirname(__file__), "demo_shop.sqlite3"))

def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn

@contextmanager
def db():
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              email TEXT NOT NULL UNIQUE,
              password_hash TEXT NOT NULL,
              is_admin INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS products (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              sku TEXT NOT NULL UNIQUE,
              name TEXT NOT NULL,
              description TEXT NOT NULL,
              price_cents INTEGER NOT NULL,
              image_url TEXT,
              inventory INTEGER NOT NULL DEFAULT 0,
              is_active INTEGER NOT NULL DEFAULT 1,
              created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS orders (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER NOT NULL,
              status TEXT NOT NULL,
              subtotal_cents INTEGER NOT NULL,
              shipping_cents INTEGER NOT NULL,
              tax_cents INTEGER NOT NULL,
              total_cents INTEGER NOT NULL,
              email TEXT NOT NULL,
              ship_name TEXT NOT NULL,
              ship_address1 TEXT NOT NULL,
              ship_address2 TEXT,
              ship_city TEXT NOT NULL,
              ship_state TEXT NOT NULL,
              ship_zip TEXT NOT NULL,
              payment_last4 TEXT,
              created_at TEXT NOT NULL DEFAULT (datetime('now')),
              FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS order_items (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              order_id INTEGER NOT NULL,
              product_id INTEGER NOT NULL,
              sku TEXT NOT NULL,
              name TEXT NOT NULL,
              unit_price_cents INTEGER NOT NULL,
              qty INTEGER NOT NULL,
              line_total_cents INTEGER NOT NULL,
              FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE,
              FOREIGN KEY(product_id) REFERENCES products(id)
            );

            CREATE INDEX IF NOT EXISTS idx_products_active ON products(is_active);
            CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);
            """
        )