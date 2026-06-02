from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, abort, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import UTC, datetime, timedelta
import os
from sqlalchemy import text
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

# Set the absolute path for the database
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

app = Flask(__name__)
# Secret key used for:
# 1. Session Security: Protects user session data from tampering
# 2. Flash Messages: Enables temporary message encryption between page loads
# 3. CSRF Protection: Prevents cross-site request forgery attacks on forms
# 4. Cookie Security: Signs cookies to prevent client-side manipulation
app.config['SECRET_KEY'] = 'dev-key-12345'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'instance', 'coffee_shop.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False #ay 7aga btzed bt2l f db mby3osh y3ml reload 3shan tt8ir hya auto btt8ir
app.config['SESSION_PERMANENT'] = False  # Never use permanent sessions
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=1)  # Short session lifetime

# Configure upload settings
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'images')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Clear sessions on each request
@app.before_request
def clear_session():
    if not request.endpoint:
        return
    # Clear any existing session
    if not current_user.is_authenticated:
        session.clear()
    # Ensure sessions are never permanent
    session.permanent = False

# Database Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    cart_items = db.relationship('CartItem', backref='user', lazy=True)
    orders = db.relationship('Order', backref='user', lazy=True)

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        if self.password and self.password.startswith(('pbkdf2:', 'scrypt:')):
            return check_password_hash(self.password, password)
        return self.password == password

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(200))
    image_url = db.Column(db.String(200))
    category = db.Column(db.String(50), nullable=False, default='drink')  # 'drink' or 'food'

class CartItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    product = db.relationship('Product')

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    subtotal = db.Column(db.Float, nullable=False)
    discount = db.Column(db.Float, nullable=False, default=0)
    total = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='paid')
    shipping_name = db.Column(db.String(120), nullable=False)
    shipping_address = db.Column(db.String(250), nullable=False)
    shipping_phone = db.Column(db.String(30), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(UTC).replace(tzinfo=None))
    items = db.relationship('OrderItem', backref='order', lazy=True, cascade='all, delete-orphan')

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    product_name = db.Column(db.String(100), nullable=False)
    unit_price = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)

def parse_price_filter(value):
    if value in (None, ''):
        return None
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    return price if price >= 0 else None

def cancel_expired_pending_orders(now=None):
    cutoff = (now or datetime.now(UTC).replace(tzinfo=None)) - timedelta(minutes=1)
    expired_orders = Order.query.filter(
        Order.status == 'pending',
        Order.created_at <= cutoff
    ).all()

    for order in expired_orders:
        order.status = 'cancelled'

    if expired_orders:
        db.session.commit()

    return len(expired_orders)

def ensure_schema_updates():
    order_columns = db.session.execute(text('PRAGMA table_info("order")')).fetchall()
    order_column_names = {column[1] for column in order_columns}
    if order_columns and 'created_at' not in order_column_names:
        db.session.execute(text('ALTER TABLE "order" ADD COLUMN created_at DATETIME'))
        db.session.execute(text(
            'UPDATE "order" SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL'
        ))
        db.session.commit()

def seed_sample_data():
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(username='admin', email='admin@cozycoffee.com', is_admin=True)
        admin.set_password('admin123')
        db.session.add(admin)
    else:
        admin.is_admin = True
        if admin.password and not admin.password.startswith(('pbkdf2:', 'scrypt:')):
            admin.set_password('admin123')

    sample_products = [
        {
            'name': 'Latte',
            'price': 4.50,
            'description': 'Smooth espresso with steamed milk and a light foam finish.',
            'image_url': '/static/images/latte.jpg',
            'category': 'drink'
        },
        {
            'name': 'Mocha',
            'price': 5.25,
            'description': 'Chocolate, espresso, and milk blended into a rich cafe favorite.',
            'image_url': '/static/images/mocha.jpg',
            'category': 'drink'
        },
        {
            'name': 'Chocolate Muffin',
            'price': 3.75,
            'description': 'Soft chocolate muffin baked fresh for a sweet coffee pairing.',
            'image_url': '/static/images/choco_muffin.jpg',
            'category': 'food'
        },
        {
            'name': 'Croissant',
            'price': 3.00,
            'description': 'Buttery layered pastry with a crisp golden crust.',
            'image_url': '/static/images/croissants-table_144627-21539.jpg',
            'category': 'food'
        },
    ]

    for product_data in sample_products:
        if not Product.query.filter_by(name=product_data['name']).first():
            db.session.add(Product(**product_data))

    db.session.commit()

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def flash_message(message, category='info'):
    flash(message, category)

# Routes
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/menu')
def menu():
    search = request.args.get('q', '').strip()
    category = request.args.get('category', 'all')
    min_price = parse_price_filter(request.args.get('min_price'))
    max_price = parse_price_filter(request.args.get('max_price'))

    query = Product.query
    if search:
        query = query.filter(
            db.or_(
                Product.name.ilike(f'%{search}%'),
                Product.description.ilike(f'%{search}%')
            )
        )
    if category in ['drink', 'food']:
        query = query.filter_by(category=category)
    if min_price is not None:
        query = query.filter(Product.price >= min_price)
    if max_price is not None:
        query = query.filter(Product.price <= max_price)

    products = query.order_by(Product.category, Product.name).all()
    drinks = [product for product in products if product.category == 'drink']
    foods = [product for product in products if product.category == 'food']
    return render_template('menu.html', drinks=drinks, foods=foods,
                         search=search, selected_category=category,
                         min_price=min_price, max_price=max_price)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if User.query.filter_by(username=username).first():
            flash_message('Username already exists')
            return redirect(url_for('register'))
        
        if not username or not email or not password:
            flash_message('Please fill in all fields')
            return redirect(url_for('register'))
        if User.query.filter_by(email=email).first():
            flash_message('Email already exists')
            return redirect(url_for('register'))

        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit() # save aldata fe aldatabase
        flash_message('Registration successful! Please log in.')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    # Clear session when accessing login page
    if request.method == 'GET':
        logout_user()
        session.clear()
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            flash_message('Please fill in all fields')
            return redirect(url_for('login'))
        
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            if not user.password.startswith(('pbkdf2:', 'scrypt:')):
                user.set_password(password)
                db.session.commit()
            login_user(user, remember=False)  # Never remember sessions
            next_page = request.args.get('next')
            return redirect(next_page or url_for('home'))
        else:
            flash_message('Invalid username or password')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.clear()
    flash_message('You have been logged out.')
    return redirect(url_for('home'))

@app.route('/add_to_cart/<int:product_id>', methods=['POST'])
@login_required
def add_to_cart(product_id):
    db.get_or_404(Product, product_id)
    cart_item = CartItem.query.filter_by(user_id=current_user.id, product_id=product_id).first()
    if cart_item:
        cart_item.quantity += 1
    else:
        cart_item = CartItem(user_id=current_user.id, product_id=product_id)
        db.session.add(cart_item)
    db.session.commit()
    return jsonify({'status': 'success'}) #bt3rf aluser en aldenia tmm w et3mlo add to cart

@app.route('/cart')
@login_required
def cart():
    cart_items = CartItem.query.filter_by(user_id=current_user.id).all()
    total = sum(item.product.price * item.quantity for item in cart_items)
    return render_template('cart.html', cart_items=cart_items, total=total)

@app.route('/update_cart/<int:item_id>', methods=['POST'])
@login_required
def update_cart(item_id):
    cart_item = db.get_or_404(CartItem, item_id)
    if cart_item.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        quantity = int((request.get_json(silent=True) or {}).get('quantity', 0))
    except (TypeError, ValueError):
        return jsonify({'error': 'Quantity must be a whole number'}), 400
    if quantity > 0:
        cart_item.quantity = quantity
    else:
        db.session.delete(cart_item)
    db.session.commit()
    return jsonify({'status': 'success'})

@app.route('/checkout', methods=['GET'])
@login_required
def checkout():
    cancel_expired_pending_orders()
    cart_items = CartItem.query.filter_by(user_id=current_user.id).all()
    if not cart_items:
        flash_message('Your cart is empty', 'warning')
        return redirect(url_for('menu'))
    
    original_total = sum(item.product.price * item.quantity for item in cart_items)
    discount = original_total * 0.20  # 20% discount
    final_total = original_total - discount
    
    return render_template('checkout.html', cart_items=cart_items, 
                         original_total=original_total, 
                         discount=discount, 
                         final_total=final_total)

@app.route('/process_payment', methods=['POST'])
@login_required
def process_payment():
    payment_method = request.form.get('payment_method')
    shipping_name = request.form.get('shipping_name', '').strip()
    shipping_address = request.form.get('shipping_address', '').strip()
    shipping_phone = request.form.get('shipping_phone', '').strip()
    
    if payment_method not in ['cash', 'card', 'stripe']:
        flash_message('Invalid payment method', 'danger')
        return redirect(url_for('checkout'))
    if not all([shipping_name, shipping_address, shipping_phone]):
        flash_message('Please enter your shipping details', 'danger')
        return redirect(url_for('checkout'))
    if payment_method == 'card':
        card_number = request.form.get('card_number', '').replace(' ', '')
        expiry = request.form.get('expiry', '').strip()
        cvv = request.form.get('cvv', '').strip()
        if not (card_number.isdigit() and len(card_number) in [15, 16] and expiry and cvv.isdigit() and len(cvv) in [3, 4]):
            flash_message('Please enter valid card details', 'danger')
            return redirect(url_for('checkout'))
    
    cart_items = CartItem.query.filter_by(user_id=current_user.id).all()
    if not cart_items:
        flash_message('Your cart is empty', 'danger')
        return redirect(url_for('menu'))

    original_total = sum(item.product.price * item.quantity for item in cart_items)
    discount = original_total * 0.20  # 20% discount
    final_total = original_total - discount

    order_status = 'pending' if payment_method == 'stripe' else 'paid'
    order = Order(
        user_id=current_user.id,
        subtotal=original_total,
        discount=discount,
        total=final_total,
        payment_method=payment_method,
        shipping_name=shipping_name,
        shipping_address=shipping_address,
        shipping_phone=shipping_phone,
        status=order_status
    )
    for item in cart_items:
        order.items.append(OrderItem(
            product_id=item.product_id,
            product_name=item.product.name,
            unit_price=item.product.price,
            quantity=item.quantity
        ))
    db.session.add(order)
    db.session.flush()

    if payment_method == 'stripe':
        stripe_secret_key = os.getenv('STRIPE_SECRET_KEY')
        if not stripe_secret_key:
            db.session.rollback()
            flash_message('Stripe is not configured. Add STRIPE_SECRET_KEY to enable hosted card payments.', 'danger')
            return redirect(url_for('checkout'))

        try:
            import stripe
            stripe.api_key = stripe_secret_key
            checkout_session = stripe.checkout.Session.create(
                mode='payment',
                line_items=[
                    {
                        'price_data': {
                            'currency': os.getenv('STRIPE_CURRENCY', 'usd'),
                            'product_data': {'name': item.product.name},
                            'unit_amount': int(round(item.product.price * 100)),
                        },
                        'quantity': item.quantity,
                    }
                    for item in cart_items
                ],
                metadata={'order_id': order.id, 'user_id': current_user.id},
                success_url=url_for('stripe_success', order_id=order.id, _external=True),
                cancel_url=url_for('checkout', _external=True),
            )
            db.session.commit()
            return redirect(checkout_session.url)
        except Exception as e:
            db.session.rollback()
            flash_message(f'Stripe checkout could not be started: {str(e)}', 'danger')
            return redirect(url_for('checkout'))
    
    # Clear the cart after successful payment
    for item in cart_items:
        db.session.delete(item)
    db.session.commit()
    
    flash_message(f'Order placed successfully! Payment of ${final_total:.2f} processed successfully. Saved ${discount:.2f} with discount.', 'success')
    return redirect(url_for('menu'))

@app.route('/stripe_success/<int:order_id>')
@login_required
def stripe_success(order_id):
    order = db.get_or_404(Order, order_id)
    if order.user_id != current_user.id:
        abort(403)
    if order.status == 'cancelled':
        flash_message('This Stripe order expired. Please start checkout again.', 'warning')
        return redirect(url_for('checkout'))

    order.status = 'paid'
    CartItem.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    flash_message(f'Order #{order.id} paid successfully through Stripe.', 'success')
    return redirect(url_for('menu'))

@app.route('/checkout', methods=['POST']) #b3d ma eshtra aluser bytsfr f sf7t aladmin
@login_required
def checkout_post():
    cart_items = CartItem.query.filter_by(user_id=current_user.id).all()
    for item in cart_items:
        db.session.delete(item)
    db.session.commit()
    # flash_message('Order placed successfully!')
    # return redirect(url_for('home'))

@app.route('/admin')
@login_required
def admin():
    if not current_user.is_authenticated or not current_user.is_admin:
        abort(403)  # Forbidden
    cancel_expired_pending_orders()
    users = User.query.all()
    products = Product.query.all()
    cart_items = CartItem.query.all()
    orders = Order.query.order_by(Order.id.desc()).all()
    return render_template('admin.html', 
                         users=users, 
                         products=products, 
                         cart_items=cart_items,
                         orders=orders)

@app.route('/add_product', methods=['POST'])
@login_required
def add_product():
    if not current_user.is_authenticated or not current_user.is_admin:
        abort(403)  # Forbidden
    try:
        name = request.form.get('name')
        category = request.form.get('category')
        price = float(request.form.get('price'))
        description = request.form.get('description')
        
        # Handle file upload
        if 'image' not in request.files:
            flash_message('No image file provided', 'danger')
            return redirect(url_for('admin'))
            
        file = request.files['image']
        if file.filename == '':
            flash_message('No selected file', 'danger')
            return redirect(url_for('admin'))
            
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            # Create upload folder if it doesn't exist
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            # Save the file
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            image_url = f'/static/images/{filename}'
        else:
            flash_message('Invalid file type. Allowed types are: png, jpg, jpeg, gif', 'danger')
            return redirect(url_for('admin'))

        # Validate inputs
        if not all([name, category, price >= 0, description]):
            flash_message('Please fill in all fields correctly', 'danger')
            return redirect(url_for('admin'))

        # Create new product
        new_product = Product(
            name=name,
            category=category,
            price=price,
            description=description,
            image_url=image_url
        )

        db.session.add(new_product)
        db.session.commit() # save aldata fe aldatabase
        flash_message(f'Product "{name}" added successfully!', 'success')

    except Exception as e:
        db.session.rollback() # delete alchanges
        flash_message(f'Error adding product: {str(e)}', 'danger')

    return redirect(url_for('admin'))

@app.route('/api/products')
def api_products():
    products = Product.query.order_by(Product.category, Product.name).all()
    return jsonify([
        {
            'id': product.id,
            'name': product.name,
            'price': product.price,
            'description': product.description,
            'image_url': product.image_url,
            'category': product.category
        }
        for product in products
    ])

@app.route('/api/orders')
@login_required
def api_orders():
    if not current_user.is_admin:
        abort(403)
    cancel_expired_pending_orders()
    orders = Order.query.order_by(Order.id.desc()).all()
    return jsonify([
        {
            'id': order.id,
            'user': order.user.username,
            'total': order.total,
            'payment_method': order.payment_method,
            'status': order.status,
            'items': [
                {
                    'product_name': item.product_name,
                    'quantity': item.quantity,
                    'unit_price': item.unit_price
                }
                for item in order.items
            ]
        }
        for order in orders
    ])

@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not all([username, email, new_password, confirm_password]):
            flash_message('Please fill in all fields')
            return redirect(url_for('reset_password'))
        if new_password != confirm_password:
            flash_message('Passwords do not match')
            return redirect(url_for('reset_password'))
        if len(new_password) < 6:
            flash_message('Password must be at least 6 characters')
            return redirect(url_for('reset_password'))

        user = User.query.filter_by(username=username, email=email).first()
        if not user:
            flash_message('No account found with that username and email')
            return redirect(url_for('reset_password'))

        user.set_password(new_password)
        db.session.commit()
        flash_message('Password reset successful! Please log in.')
        return redirect(url_for('login'))
    return render_template('reset_password.html')

@app.route('/edit_product/<int:product_id>', methods=['POST'])
@login_required
def edit_product(product_id):
    if not current_user.is_admin:
        abort(403)
    product = db.get_or_404(Product, product_id)
    try:
        name = request.form.get('name', '').strip()
        category = request.form.get('category', '').strip()
        price = float(request.form.get('price', 0))
        description = request.form.get('description', '').strip()

        if not all([name, category, description]) or price < 0:
            flash_message('Please fill in all fields correctly', 'danger')
            return redirect(url_for('admin'))

        product.name = name
        product.category = category
        product.price = price
        product.description = description

        file = request.files.get('image')
        if file and file.filename != '':
            if allowed_file(file.filename):
                filename = secure_filename(file.filename)
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                product.image_url = f'/static/images/{filename}'
            else:
                flash_message('Invalid file type. Allowed: png, jpg, jpeg, gif', 'danger')
                return redirect(url_for('admin'))

        db.session.commit()
        flash_message(f'Product "{name}" updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash_message(f'Error updating product: {str(e)}', 'danger')
    return redirect(url_for('admin'))

@app.route('/delete_user/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if not current_user.is_admin:
        abort(403)
    if user_id == current_user.id:
        flash_message('Cannot delete your own account', 'danger')
        return redirect(url_for('admin'))
    user = db.get_or_404(User, user_id)
    if user.is_admin:
        flash_message('Cannot delete another admin account', 'danger')
        return redirect(url_for('admin'))
    try:
        CartItem.query.filter_by(user_id=user_id).delete()
        db.session.delete(user)
        db.session.commit()
        flash_message(f'User "{user.username}" deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash_message(f'Error deleting user: {str(e)}', 'danger')
    return redirect(url_for('admin'))

@app.route('/delete_product/<int:product_id>', methods=['POST'])
@login_required
def delete_product(product_id):
    if not current_user.is_authenticated or not current_user.is_admin:
        abort(403)  # Forbidden
    try:
        # Find the product
        product = db.get_or_404(Product, product_id)
        product_name = product.name

        # Delete related cart items first
        CartItem.query.filter_by(product_id=product_id).delete()
        
        # Delete the product
        db.session.delete(product)
        db.session.commit()
        
        flash_message(f'Product "{product_name}" deleted successfully!', 'success')

    except Exception as e:
        db.session.rollback()
        flash_message(f'Error deleting product: {str(e)}', 'danger')

    return redirect(url_for('admin'))

if __name__ == '__main__':
    with app.app_context():
        # Create instance directory if it doesn't exist
        instance_path = os.path.join(basedir, 'instance')
        if not os.path.exists(instance_path):
            os.makedirs(instance_path)
            
        # Create tables if they don't exist (don't drop existing tables)
        db.create_all()
        ensure_schema_updates()
        
        # Add missing demo data without overwriting existing records
        if not User.query.filter_by(username='admin').first() or not Product.query.first():
            print("Initializing database with sample data...")
            seed_sample_data()
            print("Initial data loaded successfully!")
        
    app.run(debug=True)
