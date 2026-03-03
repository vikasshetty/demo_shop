from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.status import HTTP_303_SEE_OTHER
import os

from .db import db
from .seed import seed
from .security import (
    hash_password,
    verify_password,
    get_or_set_csrf_token,
    require_csrf,
    ENABLE_SECURITY_HEADERS,
)

APP_SECRET = os.environ.get("DEMO_SHOP_SECRET", "dev-secret-change-me")

app = FastAPI(title="Demo Shop")
app.add_middleware(SessionMiddleware, secret_key=APP_SECRET, same_site="lax")

BASE_DIR = os.path.dirname(__file__)
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

@app.on_event("startup")
def startup():
    seed()

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    if ENABLE_SECURITY_HEADERS:
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "img-src 'self' https: data:; "
            "style-src 'self' 'unsafe-inline';"
        )
    return response

def money(cents: int) -> str:
    return f"${cents/100:.2f}"

def current_user(request: Request):
    uid = request.session.get("user_id")
    if not uid:
        return None
    with db() as conn:
        row = conn.execute("SELECT id, email, is_admin FROM users WHERE id=?", (uid,)).fetchone()
        return dict(row) if row else None

def require_login(request: Request):
    user = current_user(request)
    if not user:
        return None, RedirectResponse("/login", status_code=HTTP_303_SEE_OTHER)
    return user, None

def get_cart(request: Request) -> dict:
    # cart = { product_id(str): qty(int) }
    return request.session.get("cart", {})

def set_cart(request: Request, cart: dict):
    request.session["cart"] = cart

def cart_totals(cart: dict):
    # Return keys that won't collide with dict methods in templates:
    #   cart["cart_items"] instead of cart["items"] (dict.items() collision)
    if not cart:
        return {"cart_items": [], "subtotal_cents": 0, "subtotal": money(0)}

    ids = [int(pid) for pid in cart.keys()]
    with db() as conn:
        placeholders = ",".join(["?"] * len(ids))
        rows = conn.execute(
            f"SELECT id, sku, name, price_cents, image_url, inventory, is_active FROM products WHERE id IN ({placeholders})",
            ids,
        ).fetchall()

    by_id = {r["id"]: r for r in rows}
    cart_items = []
    subtotal = 0

    for pid_str, qty in cart.items():
        pid = int(pid_str)
        p = by_id.get(pid)
        if not p or not p["is_active"]:
            continue

        qty = max(1, int(qty))
        line = p["price_cents"] * qty
        subtotal += line

        cart_items.append(
            {
                "id": pid,
                "sku": p["sku"],
                "name": p["name"],
                "price_cents": p["price_cents"],
                "price": money(p["price_cents"]),
                "qty": qty,
                "line_total": money(line),
                "image_url": p["image_url"],
            }
        )

    return {"cart_items": cart_items, "subtotal_cents": subtotal, "subtotal": money(subtotal)}

def cart_count(request: Request) -> int:
    c = get_cart(request)
    try:
        return sum(int(v) for v in c.values())
    except Exception:
        return 0

@app.get("/", response_class=HTMLResponse)
def home(request: Request, q: str = ""):
    user = current_user(request)
    csrf = get_or_set_csrf_token(request)
    with db() as conn:
        if q:
            rows = conn.execute(
                """
                SELECT id, sku, name, description, price_cents, image_url
                FROM products
                WHERE is_active=1 AND (name LIKE ? OR description LIKE ? OR sku LIKE ?)
                ORDER BY created_at DESC
                """,
                (f"%{q}%", f"%{q}%", f"%{q}%"),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, sku, name, description, price_cents, image_url
                FROM products
                WHERE is_active=1
                ORDER BY created_at DESC
                LIMIT 24
                """
            ).fetchall()

    products = [{**dict(r), "price": money(r["price_cents"])} for r in rows]
    return templates.TemplateResponse(
        "home.html",
        {
            "request": request,
            "user": user,
            "products": products,
            "q": q,
            "csrf": csrf,
            "cart_count": cart_count(request),
        },
    )

@app.get("/product/{product_id}", response_class=HTMLResponse)
def product_page(request: Request, product_id: int):
    user = current_user(request)
    csrf = get_or_set_csrf_token(request)
    with db() as conn:
        p = conn.execute("SELECT * FROM products WHERE id=? AND is_active=1", (product_id,)).fetchone()
    if not p:
        return HTMLResponse("Product not found", status_code=404)

    pd = dict(p)
    pd["price"] = money(pd["price_cents"])
    return templates.TemplateResponse(
        "product.html",
        {"request": request, "user": user, "p": pd, "csrf": csrf, "cart_count": cart_count(request)},
    )

@app.post("/cart/add")
def cart_add(
    request: Request,
    product_id: int = Form(...),
    qty: int = Form(1),
    csrf_token: str | None = Form(None),
):
    require_csrf(request, csrf_token)
    cart = get_cart(request)
    pid = str(int(product_id))
    cart[pid] = int(cart.get(pid, 0)) + max(1, int(qty))
    set_cart(request, cart)
    return RedirectResponse("/cart", status_code=HTTP_303_SEE_OTHER)

@app.get("/cart", response_class=HTMLResponse)
def cart_view(request: Request):
    user = current_user(request)
    csrf = get_or_set_csrf_token(request)
    totals = cart_totals(get_cart(request))
    return templates.TemplateResponse(
        "cart.html",
        {"request": request, "user": user, "cart": totals, "csrf": csrf, "cart_count": cart_count(request)},
    )

@app.post("/cart/update")
def cart_update(
    request: Request,
    product_id: int = Form(...),
    qty: int = Form(...),
    csrf_token: str | None = Form(None),
):
    require_csrf(request, csrf_token)
    cart = get_cart(request)
    pid = str(int(product_id))
    qty = int(qty)
    if qty <= 0:
        cart.pop(pid, None)
    else:
        cart[pid] = qty
    set_cart(request, cart)
    return RedirectResponse("/cart", status_code=HTTP_303_SEE_OTHER)

@app.get("/checkout", response_class=HTMLResponse)
def checkout_page(request: Request):
    user, redirect = require_login(request)
    if redirect:
        return redirect

    csrf = get_or_set_csrf_token(request)
    totals = cart_totals(get_cart(request))
    if not totals["cart_items"]:
        return RedirectResponse("/cart", status_code=HTTP_303_SEE_OTHER)

    shipping = 599
    tax = int(totals["subtotal_cents"] * 0.0625)
    total = totals["subtotal_cents"] + shipping + tax

    return templates.TemplateResponse(
        "checkout.html",
        {
            "request": request,
            "user": user,
            "cart": totals,
            "shipping": money(shipping),
            "tax": money(tax),
            "total": money(total),
            "csrf": csrf,
            "cart_count": cart_count(request),
        },
    )

@app.post("/checkout")
def checkout_submit(
    request: Request,
    ship_name: str = Form(...),
    ship_address1: str = Form(...),
    ship_address2: str = Form(""),
    ship_city: str = Form(...),
    ship_state: str = Form(...),
    ship_zip: str = Form(...),
    card_number: str = Form(...),
    csrf_token: str | None = Form(None),
):
    require_csrf(request, csrf_token)
    user, redirect = require_login(request)
    if redirect:
        return redirect

    totals = cart_totals(get_cart(request))
    if not totals["cart_items"]:
        return RedirectResponse("/cart", status_code=HTTP_303_SEE_OTHER)

    shipping = 599
    tax = int(totals["subtotal_cents"] * 0.0625)
    total = totals["subtotal_cents"] + shipping + tax
    cleaned = card_number.strip().replace(" ", "")
    last4 = cleaned[-4:] if len(cleaned) >= 4 else None

    with db() as conn:
        cur = conn.execute(
            """
            INSERT INTO orders(
              user_id, status, subtotal_cents, shipping_cents, tax_cents, total_cents,
              email, ship_name, ship_address1, ship_address2, ship_city, ship_state, ship_zip, payment_last4
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                user["id"], "placed", totals["subtotal_cents"], shipping, tax, total,
                user["email"], ship_name, ship_address1, ship_address2, ship_city, ship_state, ship_zip, last4
            ),
        )
        order_id = cur.lastrowid

        for it in totals["cart_items"]:
            conn.execute(
                """
                INSERT INTO order_items(order_id, product_id, sku, name, unit_price_cents, qty, line_total_cents)
                VALUES(?,?,?,?,?,?,?)
                """,
                (
                    order_id, it["id"], it["sku"], it["name"], it["price_cents"], it["qty"], it["price_cents"] * it["qty"]
                ),
            )

    set_cart(request, {})
    return RedirectResponse(f"/orders?placed={order_id}", status_code=HTTP_303_SEE_OTHER)

@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    user = current_user(request)
    csrf = get_or_set_csrf_token(request)
    return templates.TemplateResponse(
        "register.html",
        {"request": request, "user": user, "csrf": csrf, "cart_count": cart_count(request)},
    )

@app.post("/register")
def register_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    csrf_token: str | None = Form(None),
):
    require_csrf(request, csrf_token)
    email = email.strip().lower()
    if len(password) < 8:
        return HTMLResponse("Password must be at least 8 characters", status_code=400)

    with db() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO users(email, password_hash, is_admin) VALUES(?,?,0)",
                (email, hash_password(password)),
            )
        except Exception:
            return HTMLResponse("That email is already registered.", status_code=400)
        request.session["user_id"] = cur.lastrowid

    return RedirectResponse("/", status_code=HTTP_303_SEE_OTHER)

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    user = current_user(request)
    csrf = get_or_set_csrf_token(request)
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "user": user, "csrf": csrf, "cart_count": cart_count(request)},
    )

@app.post("/login")
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    csrf_token: str | None = Form(None),
):
    require_csrf(request, csrf_token)
    email = email.strip().lower()
    with db() as conn:
        row = conn.execute(
            "SELECT id, email, password_hash, is_admin FROM users WHERE email=?",
            (email,),
        ).fetchone()

    if not row or not verify_password(password, row["password_hash"]):
        return HTMLResponse("Invalid credentials", status_code=401)

    request.session["user_id"] = row["id"]
    return RedirectResponse("/", status_code=HTTP_303_SEE_OTHER)

@app.post("/logout")
def logout(request: Request, csrf_token: str | None = Form(None)):
    require_csrf(request, csrf_token)
    request.session.clear()
    return RedirectResponse("/", status_code=HTTP_303_SEE_OTHER)

@app.get("/orders", response_class=HTMLResponse)
def orders_page(request: Request, placed: str = ""):
    user, redirect = require_login(request)
    if redirect:
        return redirect

    csrf = get_or_set_csrf_token(request)
    with db() as conn:
        orders = conn.execute(
            "SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC",
            (user["id"],),
        ).fetchall()

        out = []
        for o in orders:
            items = conn.execute("SELECT * FROM order_items WHERE order_id=?", (o["id"],)).fetchall()
            out.append({"order": dict(o), "items": [dict(i) for i in items]})

    return templates.TemplateResponse(
        "orders.html",
        {
            "request": request,
            "user": user,
            "orders": out,
            "placed": placed,
            "csrf": csrf,
            "money": money,
            "cart_count": cart_count(request),
        },
    )

@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    user, redirect = require_login(request)
    if redirect:
        return redirect
    if not user["is_admin"]:
        return HTMLResponse("Forbidden", status_code=403)

    csrf = get_or_set_csrf_token(request)
    with db() as conn:
        products = conn.execute("SELECT * FROM products ORDER BY created_at DESC").fetchall()

    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "user": user,
            "products": [dict(p) for p in products],
            "csrf": csrf,
            "money": money,
            "cart_count": cart_count(request),
        },
    )

@app.post("/admin/product/create")
def admin_create_product(
    request: Request,
    sku: str = Form(...),
    name: str = Form(...),
    description: str = Form(...),
    price_cents: int = Form(...),
    image_url: str = Form(""),
    inventory: int = Form(0),
    is_active: int = Form(1),
    csrf_token: str | None = Form(None),
):
    require_csrf(request, csrf_token)
    user = current_user(request)
    if not user or not user["is_admin"]:
        return HTMLResponse("Forbidden", status_code=403)

    with db() as conn:
        conn.execute(
            """
            INSERT INTO products(sku, name, description, price_cents, image_url, inventory, is_active)
            VALUES(?,?,?,?,?,?,?)
            """,
            (
                sku.strip(),
                name.strip(),
                description.strip(),
                int(price_cents),
                image_url.strip(),
                int(inventory),
                1 if int(is_active) else 0,
            ),
        )
    return RedirectResponse("/admin", status_code=HTTP_303_SEE_OTHER)

@app.post("/admin/product/toggle")
def admin_toggle_product(
    request: Request,
    product_id: int = Form(...),
    csrf_token: str | None = Form(None),
):
    require_csrf(request, csrf_token)
    user = current_user(request)
    if not user or not user["is_admin"]:
        return HTMLResponse("Forbidden", status_code=403)

    with db() as conn:
        p = conn.execute("SELECT is_active FROM products WHERE id=?", (product_id,)).fetchone()
        if p:
            conn.execute("UPDATE products SET is_active=? WHERE id=?", (0 if p["is_active"] else 1, product_id))

    return RedirectResponse("/admin", status_code=HTTP_303_SEE_OTHER)