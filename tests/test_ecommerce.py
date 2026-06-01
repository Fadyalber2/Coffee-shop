from datetime import UTC, datetime, timedelta
from pathlib import Path
import shutil
import tempfile

import pytest

import app as ecommerce_app
from app import app, basedir, db, User, Product, CartItem, Order, cancel_expired_pending_orders, seed_sample_data


@pytest.fixture()
def client():
    real_db_path = Path(basedir) / "instance" / "coffee_shop.db"
    backup_path = None
    if real_db_path.exists():
        backup_file = tempfile.NamedTemporaryFile(delete=False)
        backup_file.close()
        backup_path = Path(backup_file.name)
        shutil.copy2(real_db_path, backup_path)

    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        WTF_CSRF_ENABLED=False,
    )
    with app.app_context():
        db.drop_all()
        db.create_all()
        drink = Product(
            name="Latte",
            price=4.5,
            description="Smooth espresso with milk",
            image_url="/static/images/latte.jpg",
            category="drink",
        )
        food = Product(
            name="Croissant",
            price=3.0,
            description="Buttery pastry",
            image_url="/static/images/croissants-table_144627-21539.jpg",
            category="food",
        )
        db.session.add_all([drink, food])
        db.session.commit()
        yield app.test_client()
        db.session.remove()
        db.drop_all()

    if backup_path and backup_path.exists():
        real_db_path.parent.mkdir(exist_ok=True)
        shutil.copy2(backup_path, real_db_path)
        backup_path.unlink()


def register(client, username="buyer", email="buyer@example.com", password="secret123"):
    return client.post(
        "/register",
        data={"username": username, "email": email, "password": password},
        follow_redirects=True,
    )


def login(client, username="buyer", password="secret123"):
    return client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=True,
    )


def test_registration_hashes_password_and_login_still_works(client):
    register(client)

    with app.app_context():
        user = User.query.filter_by(username="buyer").one()
        assert user.password != "secret123"
        assert user.check_password("secret123")
        assert not user.check_password("wrong-password")

    response = login(client)
    assert b"buyer" in response.data


def test_login_prevents_open_redirect(client):
    register(client)
    # Attempt to redirect to a malicious external site
    response = client.post(
        "/login?next=http://malicious.com",
        data={"username": "buyer", "password": "secret123"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"] == "/" or response.headers["Location"] == "http://localhost/"


def test_security_headers_are_present(client):
    response = client.get("/")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert "Content-Security-Policy" in response.headers


def test_menu_supports_search_category_and_price_filters(client):
    response = client.get("/menu?q=latte&category=drink&min_price=4&max_price=5")

    assert response.status_code == 200
    assert b"Latte" in response.data
    assert b"Croissant" not in response.data


def test_checkout_creates_order_records_and_clears_cart(client):
    register(client)
    login(client)
    with app.app_context():
        product = Product.query.filter_by(name="Latte").one()
        user = User.query.filter_by(username="buyer").one()
        db.session.add(CartItem(user_id=user.id, product_id=product.id, quantity=2))
        db.session.commit()

    response = client.post(
        "/process_payment",
        data={
            "payment_method": "cash",
            "shipping_name": "Buyer Name",
            "shipping_address": "123 Main Street",
            "shipping_phone": "01000000000",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Order placed successfully" in response.data
    with app.app_context():
        order = ecommerce_app.Order.query.filter_by(user_id=User.query.filter_by(username="buyer").one().id).one()
        assert order.status == "paid"
        assert order.payment_method == "cash"
        assert order.items[0].product_name == "Latte"
        assert CartItem.query.count() == 0


def test_stripe_checkout_requires_server_key_and_keeps_cart(client, monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    register(client)
    login(client)
    with app.app_context():
        product = Product.query.filter_by(name="Latte").one()
        user = User.query.filter_by(username="buyer").one()
        db.session.add(CartItem(user_id=user.id, product_id=product.id, quantity=1))
        db.session.commit()

    response = client.post(
        "/process_payment",
        data={
            "payment_method": "stripe",
            "shipping_name": "Buyer Name",
            "shipping_address": "123 Main Street",
            "shipping_phone": "01000000000",
        },
        follow_redirects=True,
    )

    assert b"Stripe is not configured" in response.data
    with app.app_context():
        assert CartItem.query.count() == 1


def test_expired_pending_orders_are_cancelled_after_one_minute(client):
    register(client)
    with app.app_context():
        user = User.query.filter_by(username="buyer").one()
        old_order = Order(
            user_id=user.id,
            subtotal=4.5,
            discount=0.9,
            total=3.6,
            payment_method="stripe",
            status="pending",
            shipping_name="Buyer Name",
            shipping_address="123 Main Street",
            shipping_phone="01000000000",
            created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=61),
        )
        recent_order = Order(
            user_id=user.id,
            subtotal=4.5,
            discount=0.9,
            total=3.6,
            payment_method="stripe",
            status="pending",
            shipping_name="Buyer Name",
            shipping_address="123 Main Street",
            shipping_phone="01000000000",
            created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=30),
        )
        db.session.add_all([old_order, recent_order])
        db.session.commit()

        cancelled_count = cancel_expired_pending_orders()

        assert cancelled_count == 1
        assert old_order.status == "cancelled"
        assert recent_order.status == "pending"


def test_cart_update_rejects_non_integer_quantity(client):
    register(client)
    login(client)
    with app.app_context():
        product = Product.query.filter_by(name="Latte").one()
        user = User.query.filter_by(username="buyer").one()
        cart_item = CartItem(user_id=user.id, product_id=product.id, quantity=1)
        db.session.add(cart_item)
        db.session.commit()
        item_id = cart_item.id

    response = client.post(f"/update_cart/{item_id}", json={"quantity": "abc"})

    assert response.status_code == 400
    assert response.get_json()["error"] == "Quantity must be a whole number"


def test_seed_sample_data_creates_admin_and_catalog(client):
    with app.app_context():
        db.drop_all()
        db.create_all()

        seed_sample_data()

        admin = User.query.filter_by(username="admin").one()
        assert admin.is_admin
        assert admin.check_password("admin123")
        assert Product.query.filter_by(category="drink").count() >= 1
        assert Product.query.filter_by(category="food").count() >= 1


def test_seed_sample_data_resets_legacy_plaintext_admin_password(client):
    with app.app_context():
        db.drop_all()
        db.create_all()
        db.session.add(User(
            username="admin",
            email="old-admin@example.com",
            password="admin",
            is_admin=False,
        ))
        db.session.commit()

        seed_sample_data()

        admin = User.query.filter_by(username="admin").one()
        assert admin.is_admin
        assert admin.check_password("admin123")
        assert not admin.check_password("admin")
