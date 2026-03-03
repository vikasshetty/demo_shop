from .db import db, init_db
from .security import hash_password

def seed():
    init_db()
    with db() as conn:
        # Admin user
        conn.execute(
            "INSERT OR IGNORE INTO users(email, password_hash, is_admin) VALUES(?,?,1)",
            ("admin@demo.local", hash_password("Admin123!")),
        )
        # Regular user
        conn.execute(
            "INSERT OR IGNORE INTO users(email, password_hash, is_admin) VALUES(?,?,0)",
            ("user@demo.local", hash_password("User123!")),
        )

        products = [
            ("SKU-1001", "Blue Hoodie", "Cozy fleece hoodie in blue.", 4999, "https://picsum.photos/seed/hoodie/640/480", 25),
            ("SKU-1002", "Running Shoes", "Lightweight trainers for everyday runs.", 7999, "https://picsum.photos/seed/shoes/640/480", 18),
            ("SKU-1003", "Coffee Mug", "Ceramic mug with matte finish.", 1299, "https://picsum.photos/seed/mug/640/480", 40),
            ("SKU-1004", "Backpack", "Minimal daypack with laptop sleeve.", 6599, "https://picsum.photos/seed/backpack/640/480", 12),
        ]
        for sku, name, desc, price, img, inv in products:
            conn.execute(
                """
                INSERT OR IGNORE INTO products(sku, name, description, price_cents, image_url, inventory, is_active)
                VALUES(?,?,?,?,?,?,1)
                """,
                (sku, name, desc, price, img, inv),
            )