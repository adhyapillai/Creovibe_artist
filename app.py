from flask import Flask, request, jsonify, session, render_template
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import pymysql
import bcrypt
from pymysql.cursors import DictCursor
from jinja2 import TemplateNotFound
import os  # <-- Make sure this is here
import secrets
import json
import uuid
import hmac
import hashlib
import requests
from functools import wraps
import sys
import logging
print("Python executable:", sys.executable)
print("Current working directory:", os.getcwd())
print("Templates folder exists:", os.path.exists('templates'))
print("login.html exists:", os.path.exists(os.path.join('templates', 'login.html')))


app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'creovibe-secret-key-change-in-production-2024')
app.config['SESSION_TYPE'] = 'filesystem'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=1)
app.config['PORTFOLIO_UPLOAD_DIR'] = os.path.join('static', 'uploads', 'portfolio')
app.config['PROFILE_PICTURE_UPLOAD_DIR'] = os.path.join('static', 'uploads', 'profile_pictures')
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.route('/test')
def test():
    return "Flask is working!"

ALLOWED_PORTFOLIO_EXTENSIONS = {'jpg', 'jpeg', 'png', 'mp4'}
ALLOWED_PROFILE_PICTURE_EXTENSIONS = {'jpg', 'jpeg', 'png'}

SUBSCRIPTION_PLANS = {

    "basic": {
        "plan_id": 1,
        "plan_name": "Basic",
        "plan_type": "basic",
        "amount": 199,
        "duration_days": 30,
        "duration_label": "1 Month",
        "features": [
            "Unlimited Bookings",
            "1 Month Validity",
            "Standard Listing"
        ]
    },

    "premium": {
        "plan_id": 2,
        "plan_name": "Premium",
        "plan_type": "premium",
        "amount": 399,
        "duration_days": 90,
        "duration_label": "3 Months",
        "features": [
            "Unlimited Bookings",
            "3 Months Validity",
            "Priority Listing"
        ]
    },

    "pro": {
        "plan_id": 3,
        "plan_name": "Pro",
        "plan_type": "pro",
        "amount": 599,
        "duration_days": 180,
        "duration_label": "6 Months",
        "features": [
            "Unlimited Bookings",
            "6 Months Validity",
            "Featured Artist Listing"
        ]
    }
}


def parse_portfolio_paths(raw_value):
    if not raw_value:
        return []
    if isinstance(raw_value, list):
        return raw_value
    if isinstance(raw_value, str):
        try:
            parsed = json.loads(raw_value)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            if ',' in raw_value:
                return [x.strip() for x in raw_value.split(',') if x.strip()]
            return [raw_value]
    return []


def is_allowed_portfolio_file(filename):
    if not filename or '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in ALLOWED_PORTFOLIO_EXTENSIONS


def is_allowed_profile_picture_file(filename):
    if not filename or '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in ALLOWED_PROFILE_PICTURE_EXTENSIONS


def get_profile_picture_column(cur):
    cur.execute("SHOW COLUMNS FROM artist_table")
    columns = cur.fetchall() or []
    fields = {str(col.get('Field', '')).lower(): col.get('Field') for col in columns}
    for candidate in [
        'profile_picture_path',
        'profile_pic_path',
        'profile_picture',
        'profile_pic',
        'avatar_path',
        'photo_path'
    ]:
        if candidate in fields:
            return fields[candidate]
    return None


def ensure_artist_schema(cur):
    cur.execute("SHOW COLUMNS FROM artist_table")
    existing = {str(col.get('Field', '')).lower() for col in (cur.fetchall() or [])}
    if 'profile_pic' not in existing:
        cur.execute("ALTER TABLE artist_table ADD COLUMN profile_pic VARCHAR(255) NULL")
    if 'portfolio_files' not in existing:
        cur.execute("ALTER TABLE artist_table ADD COLUMN portfolio_files VARCHAR(1000) NULL")
    if 'working_start_time' not in existing:
        cur.execute("ALTER TABLE artist_table ADD COLUMN working_start_time VARCHAR(5) NULL")
    if 'working_end_time' not in existing:
        cur.execute("ALTER TABLE artist_table ADD COLUMN working_end_time VARCHAR(5) NULL")


CATEGORY_NAME_TO_ID = {
    'singer': 1,
    'dancer': 2,
    'photographer': 3
}


def resolve_category_id(cur, category_value):
    if category_value is None:
        return None
    raw_value = str(category_value).strip()
    if not raw_value:
        return None

    if raw_value.isdigit():
        return int(raw_value)

    cur.execute(
        """
        SELECT category_id
        FROM category_table
        WHERE LOWER(category_name) = LOWER(%s)
        LIMIT 1
        """,
        (raw_value,)
    )
    row = cur.fetchone()
    if row and row.get('category_id') is not None:
        return int(row['category_id'])

    return CATEGORY_NAME_TO_ID.get(raw_value.lower())


def ensure_calendar_schema(cur):
    cur.execute("SHOW COLUMNS FROM calendar_table")
    cols = cur.fetchall() or []
    field_map = {}
    type_map = {}
    for col in cols:
        actual = str(col.get('Field', ''))
        lower = actual.lower()
        field_map[lower] = actual
        type_map[lower] = str(col.get('Type', '')).lower()
    if 'slot_type' not in field_map:
        cur.execute("ALTER TABLE calendar_table ADD COLUMN slot_type ENUM('Communication','Performance') DEFAULT 'Performance'")
    elif 'enum' not in type_map.get('slot_type', ''):
        actual_name = field_map['slot_type']
        cur.execute(f"ALTER TABLE calendar_table MODIFY COLUMN `{actual_name}` ENUM('Communication','Performance') DEFAULT 'Performance'")
    else:
        # Ensure the ENUM has the correct values
        current_enum = type_map.get('slot_type', '')
        if 'performance' not in current_enum:
            actual_name = field_map['slot_type']
            cur.execute(f"ALTER TABLE calendar_table MODIFY COLUMN `{actual_name}` ENUM('Communication','Performance') DEFAULT 'Performance'")
    if 'price' not in field_map:
        cur.execute("ALTER TABLE calendar_table ADD COLUMN price DECIMAL(10,2) DEFAULT 0")


def ensure_subscription_schema(cur):
    # Intentionally no schema changes here.
    return


def get_table_columns(cur, table_name):
    cur.execute(f"SHOW COLUMNS FROM {table_name}")
    return [row.get('Field') for row in (cur.fetchall() or []) if row.get('Field')]


def pick_column(columns, candidates):
    lookup = {str(col).lower(): col for col in (columns or [])}
    for name in candidates:
        key = str(name).lower()
        if key in lookup:
            return lookup[key]
    return None


def get_plan_definition(plan_type):
    return SUBSCRIPTION_PLANS.get(str(plan_type or '').lower())


def seed_subscription_plans(cur):
    cur.execute("SELECT COUNT(*) AS total FROM subscription_plan_table")
    row = cur.fetchone() or {}
    if int(row.get('total') or 0) > 0:
        return
    plan_rows = [
        (1, 'Basic',   199, 30,  0, 0),  # 1 Month
        (2, 'Premium', 399, 90,  1, 0),  # 3 Months
        (3, 'Pro',     599, 180, 1, 1)   # 6 Months
    ]
    cur.executemany(
        """
        INSERT INTO subscription_plan_table
            (plan_id, plan_name, amount, duration_days, has_priority, has_featured)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        plan_rows
    )


def get_plan_by_id(cur, plan_id):
    cur.execute(
        """
        SELECT plan_id, plan_name, amount, duration_days, has_priority, has_featured
        FROM subscription_plan_table
        WHERE plan_id = %s
        LIMIT 1
        """,
        (plan_id,)
    )
    row = cur.fetchone()
    if not row:
        return None
    return {
        'plan_id': int(row.get('plan_id')),
        'plan_name': row.get('plan_name') or '',
        'plan_type': str(row.get('plan_name') or '').strip().lower(),
        'amount': float(row.get('amount') or 0),
        'duration_days': int(row.get('duration_days') or 0),
        'has_priority': bool(row.get('has_priority')),
        'has_featured': bool(row.get('has_featured'))
    }


def resolve_plan(cur, payload):
    raw_plan_id = payload.get('plan_id')
    if raw_plan_id is not None and str(raw_plan_id).strip().isdigit():
        return get_plan_by_id(cur, int(raw_plan_id))

    raw_plan_type = str(payload.get('plan_type') or '').strip().lower()
    if raw_plan_type:
        cur.execute(
            """
            SELECT plan_id, plan_name, amount, duration_days, has_priority, has_featured
            FROM subscription_plan_table
            WHERE LOWER(plan_name) = %s
            LIMIT 1
            """,
            (raw_plan_type,)
        )
        row = cur.fetchone()
        if row:
            return {
                'plan_id': int(row.get('plan_id')),
                'plan_name': row.get('plan_name') or '',
                'plan_type': str(row.get('plan_name') or '').strip().lower(),
                'amount': float(row.get('amount') or 0),
                'duration_days': int(row.get('duration_days') or 0),
                'has_priority': bool(row.get('has_priority')),
                'has_featured': bool(row.get('has_featured'))
            }
    return None


def expire_outdated_subscriptions(cur, artist_id):
    cur.execute(
        """
        UPDATE subscription_table
        SET status = 'inactive'
        WHERE artist_id = %s
          AND end_date < CURDATE()
          AND LOWER(status) = 'active'
        """,
        (artist_id,)
    )


def create_free_trial_if_missing(cur, artist_id):
    cur.execute(
        "SELECT subscription_id FROM subscription_table WHERE artist_id = %s ORDER BY subscription_id DESC LIMIT 1",
        (artist_id,)
    )
    existing = cur.fetchone()
    if existing:
        return

    start_date = datetime.now().date()
    end_date = start_date + timedelta(days=30)
    cur.execute("SELECT plan_id FROM subscription_plan_table WHERE LOWER(plan_name) = 'basic' LIMIT 1")
    plan_row = cur.fetchone() or {}
    basic_plan_id = int(plan_row.get('plan_id') or 1)
    cur.execute(
        """
        INSERT INTO subscription_table
        (artist_id, plan_id, start_date, end_date, status)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (artist_id, basic_plan_id, start_date, end_date, 'active')
    )

def get_current_subscription(cur, artist_id):
    cur.execute(
        """
        SELECT
            s.subscription_id,
            s.artist_id,
            s.plan_id,
            p.plan_name,
            p.duration_days,
            p.amount,
            s.start_date,
            s.end_date,
            s.status
        FROM subscription_table s
        LEFT JOIN subscription_plan_table p ON p.plan_id = s.plan_id
        WHERE s.artist_id = %s
        ORDER BY s.subscription_id DESC
        LIMIT 1
        """,
        (artist_id,)
    )
    sub = cur.fetchone()
    if not sub:
        return None
    
    start_date = sub.get('start_date')
    end_date = sub.get('end_date')
    plan_type = str(sub.get('plan_name') or '').strip().lower()
    amount = float(sub.get('amount') or 0)
    trial_expired = bool(end_date and end_date < datetime.now().date())
    normalized_status = str(sub.get('status') or '').lower()
    if normalized_status not in ('active', 'inactive'):
        normalized_status = 'inactive' if trial_expired else 'active'
    if trial_expired:
        normalized_status = 'inactive'

    billing_cycle = 'yearly' if start_date and end_date and (end_date - start_date).days >= 365 else 'monthly'

    display_status = 'expired' if trial_expired else normalized_status
    return {
        'subscription_id': sub.get('subscription_id'),
        'plan_id': sub.get('plan_id'),
        'plan_name': sub.get('plan_name') or '',
        'plan_type': plan_type or 'basic',
        'billing_cycle': billing_cycle,
        'next_billing_date': end_date.isoformat() if (end_date and end_date >= datetime.now().date()) else None,
        'amount': amount,
        'status': display_status,
        'payment_status': 'success' if amount > 0 else 'trial',
        'start_date': start_date.isoformat() if start_date else None,
        'end_date': end_date.isoformat() if end_date else None,
        'trial_expired': trial_expired,
        'requires_paid_plan': trial_expired
    }
    # ... rest of function remains the same

'''def get_current_subscription(cur, artist_id):
    cur.execute(
        """
        SELECT
            s.subscription_id,
            s.artist_id,
            s.plan_id,
            p.plan_name,
            p.duration_days,
            s.amount,
            s.start_date,
            s.end_date,
            s.status
        FROM subscription_table s
        LEFT JOIN subscription_plan_table p ON p.plan_id = s.plan_id
        WHERE artist_id = %s
        ORDER BY s.subscription_id DESC
        LIMIT 1
        """,
        (artist_id,)
    )'''
    


def has_active_subscription(cur, artist_id):
    expire_outdated_subscriptions(cur, artist_id)
    cur.execute(
        """
        SELECT subscription_id
        FROM subscription_table
        WHERE artist_id = %s
          AND LOWER(status) = 'active'
          AND end_date >= CURDATE()
        ORDER BY subscription_id DESC
        LIMIT 1
        """,
        (artist_id,)
    )
    return bool(cur.fetchone())


def get_billing_history(cur, artist_id):
    cur.execute(
        """
        SELECT
            s.start_date,
            s.end_date,
            s.status,
            p.plan_name,
            p.amount
        FROM subscription_table s
        LEFT JOIN subscription_plan_table p ON p.plan_id = s.plan_id
        WHERE s.artist_id = %s
        ORDER BY s.subscription_id DESC
        """,
        (artist_id,)
    )
    rows = cur.fetchall() or []
    history = []
    for row in rows:
        history.append({
            'date': row.get('start_date').isoformat() if row.get('start_date') else None,
            'description': f"{str(row.get('plan_name') or '').strip()} subscription",
            'amount': float(row.get('amount') or 0),
            'payment_method': 'Razorpay' if float(row.get('amount') or 0) > 0 else 'Free Trial',
            'status': str(row.get('status') or '').lower() or 'active',
            'end_date': row.get('end_date').isoformat() if row.get('end_date') else None
        })
    return history


def activate_paid_subscription(cur, artist_id, plan, payment_id, order_id):
    start_date = datetime.now().date()
    end_date = start_date + timedelta(days=int(plan['duration_days']))
    cur.execute("UPDATE subscription_table SET status = 'inactive' WHERE artist_id = %s AND LOWER(status) = 'active'", (artist_id,))
    cur.execute(
        """
        INSERT INTO subscription_table
        (artist_id, plan_id, start_date, end_date, status)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            artist_id,
            int(plan['plan_id']),
            start_date,
            end_date,
            'active'
        )
    )

# ========== DATABASE ==========
def get_db():
    return pymysql.connect(
        host='localhost',
        user='root',
        password='root123',
        database='creovibe_db',
        cursorclass=DictCursor,
        charset='utf8mb4',
        autocommit=False
    )


# ========== MIDDLEWARE ==========
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'artist_id' not in session:
            return jsonify({'error': 'Login required'}), 401
        return f(*args, **kwargs)
    return decorated

# ========== STATIC PAGES ==========
# ========== STATIC PAGES ==========

# ========== STATIC PAGES ==========
@app.route('/')
def index():
    return render_template('login.html')

@app.route('/<path:page>')  # Changed <page> to <path:page> to catch ALL urls, even with slashes
def static_page(page):
    # 1. Clean up the URL if the browser accidentally includes 'templates/'
    if page.startswith('templates/'):
        page = page.replace('templates/', '', 1)
        
    # 2. Add .html if the URL doesn't have an extension
    if not page.endswith('.html') and '.' not in page:
        page += '.html'
        
    # 3. Print exactly what the server is trying to find to your terminal
    print(f"\n---> BROWSER IS LOOKING FOR: {page} <---")
        
    try:
        # Safely render the template
        return render_template(page)
    except TemplateNotFound:
        # If the file isn't in the folder, print a massive error to the terminal
        print(f"---> CRITICAL ERROR: '{page}' IS MISSING FROM THE 'templates' FOLDER! <---\n")
        
        # Show a helpful error directly on the browser screen instead of a generic 404
        error_html = f"""
            <div style="font-family: Arial; padding: 40px; text-align: center;">
                <h2 style="color: #ff4757;">File Not Found</h2>
                <p>Flask is looking for the file <b>{page}</b>, but it is missing from your <b>templates</b> folder.</p>
                <p>Please ensure {page} is saved exactly at: <i>D:\\ADHYA\\SDP\\CODE\\creovibe_artist\\templates\\{page}</i></p>
            </div>
        """
        return error_html, 404


# ========== API ROUTES ==========

# 1. STATES API ENDPOINT
@app.route('/api/states')
@login_required
def api_states():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT state_id, state_name FROM state_table ORDER BY state_name")
        states = cur.fetchall()
        cur.close()
        conn.close()
        
        return jsonify({'success': True, 'states': states})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# 2. CITIES API ENDPOINT
@app.route('/api/cities/<int:state_id>')
@login_required
def api_cities(state_id):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT city_id, city_name FROM city_table WHERE state_id = %s ORDER BY city_name", (state_id,))
        cities = cur.fetchall()
        cur.close()
        conn.close()
        
        return jsonify({'success': True, 'cities': cities})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# 3. CATEGORIES
@app.route('/api/categories')
def api_categories():
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT category_id, category_name
            FROM category_table
            ORDER BY category_name
            """
        )
        categories = cur.fetchall() or []
        return jsonify({'success': True, 'categories': categories})
    except Exception as e:
        logger.exception("Categories fetch failed")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@app.route('/api/register', methods=['POST'])
def api_register():
    conn = None
    cur = None
    try:
        payload = request.form if request.form else (request.get_json(silent=True) or {})

        first_name = str(payload.get('first_name') or '').strip()
        last_name = str(payload.get('last_name') or '').strip()
        username = str(payload.get('username') or '').strip()
        email = str(payload.get('email') or '').strip()
        raw_password = str(payload.get('password') or '').strip()
        gender = str(payload.get('gender') or '').strip()
        dob = str(payload.get('dob') or '').strip()
        phone_number = str(payload.get('phone_number') or payload.get('phone') or '').strip()
        pincode = str(payload.get('pincode') or '').strip()
        state_id = payload.get('state_id')
        city_id = payload.get('city_id')
        category_id = payload.get('category_id')
        category_name = str(payload.get('category') or '').strip()

        if not all([first_name, last_name, username, raw_password, gender, dob, phone_number, pincode]):
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400
        if not category_id and not category_name:
            return jsonify({'success': False, 'error': 'Category is required'}), 400
        if not state_id or not city_id:
            return jsonify({'success': False, 'error': 'State and city are required'}), 400

        conn = get_db()
        cur = conn.cursor()

        if category_id is None or str(category_id).strip() == '':
            category_id = resolve_category_id(cur, category_name)
        try:
            category_id = int(category_id)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'Invalid category_id'}), 400

        cur.execute("SELECT category_name FROM category_table WHERE category_id = %s LIMIT 1", (category_id,))
        category_row = cur.fetchone()
        if not category_row:
            return jsonify({'success': False, 'error': 'Invalid category selected'}), 400
        category_text = category_row.get('category_name') or ''

        cur.execute("SELECT COUNT(*) AS total FROM state_table WHERE state_id = %s", (state_id,))
        if int((cur.fetchone() or {}).get('total') or 0) == 0:
            return jsonify({'success': False, 'error': 'Invalid state selected'}), 400

        cur.execute("SELECT COUNT(*) AS total FROM city_table WHERE city_id = %s AND state_id = %s", (city_id, state_id))
        if int((cur.fetchone() or {}).get('total') or 0) == 0:
            return jsonify({'success': False, 'error': 'Invalid city selected'}), 400
        
        cur.execute(
            "SELECT artist_id FROM artist_table WHERE username = %s OR phone_number = %s LIMIT 1",
            (username, phone_number)
        )
        if cur.fetchone():
            return jsonify({'success': False, 'error': 'Username or phone number already exists'}), 400

        portfolio_files = request.files.getlist('portfolio_files')
        portfolio_paths = []
        if portfolio_files:
            os.makedirs(app.config['PORTFOLIO_UPLOAD_DIR'], exist_ok=True)
            for file_obj in portfolio_files:
                if not file_obj or not file_obj.filename:
                    continue
                if not is_allowed_portfolio_file(file_obj.filename):
                    return jsonify({'success': False, 'error': 'Only jpg, jpeg, png, mp4 portfolio files are allowed'}), 400
                safe_name = secure_filename(file_obj.filename)
                ext = safe_name.rsplit('.', 1)[1].lower()
                stored_name = f"new_{uuid.uuid4().hex}.{ext}"
                abs_path = os.path.join(app.config['PORTFOLIO_UPLOAD_DIR'], stored_name)
                file_obj.save(abs_path)
                portfolio_paths.append('/static/uploads/portfolio/' + stored_name)

        hashed_password = bcrypt.hashpw(raw_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        primary_portfolio_path = portfolio_paths[0] if portfolio_paths else '/static/uploads/portfolio/default_portfolio.jpg'

        cur.execute(
            """
            INSERT INTO artist_table
            (first_name, last_name, username, password, email, gender, dob, phone_number,
             state_id, city_id, category_id, portfolio_path, verification_status, is_enabled,
             profile_pic, portfolio_files, rating)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', 1,
                    %s, %s, %s)
            """,
            (
                first_name, last_name, username, hashed_password, email or None,
                gender, dob, phone_number,
                state_id, city_id, category_id, primary_portfolio_path,
                '', json.dumps(portfolio_paths), 0.0
            )
        )
        new_artist_id = cur.lastrowid
        conn.commit()

        return jsonify({
            'success': True,
            'message': 'Registration submitted. Account is pending approval.',
            'artist_id': new_artist_id
        })
        
    except Exception as e:
        if conn:
            conn.rollback()
        logger.exception("Registration failed")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@app.route('/api/forgot_password', methods=['POST'])
def api_forgot_password():
    conn = None
    cur = None
    try:
        data = request.get_json() or {}
        username = str(data.get('username') or '').strip()
        email = str(data.get('email') or '').strip()
        if not username and not email:
            return jsonify({'success': False, 'error': 'username or email is required'}), 400

        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT artist_id, username, email
            FROM artist_table
            WHERE LOWER(username) = LOWER(%s) OR LOWER(email) = LOWER(%s)
            LIMIT 1
            """,
            (username or email, email or username)
        )
        row = cur.fetchone()
        if not row:
            return jsonify({'success': True, 'message': 'If account exists, reset instructions have been sent'})

        reset_token = uuid.uuid4().hex
        logger.info("Password reset token for artist_id=%s: %s", row.get('artist_id'), reset_token)

        return jsonify({
            'success': True,
            'message': 'Password reset email queued'
        })
    except Exception as e:
        logger.exception("Forgot password failed")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

# 3. LOGIN - FIXED VERSION

# 3. LOGIN - WORKING VERSION

@app.route('/api/login', methods=['POST'])
def api_login():
    try:
        if not request.is_json:
            return jsonify({'success': False, 'error': 'Invalid request'}), 400

        data = request.get_json() or {}
        username = str(data.get('username') or '').strip()
        password = str(data.get('password') or '').strip()

        if not username or not password:
            return jsonify({'success': False, 'error': 'Username and password required'}), 400

        conn = get_db()
        cur = conn.cursor()

        # Use correct schema column names for artist_table
        cur.execute("""
            SELECT 
                artist_id,
                first_name,
                last_name,
                username,
                email,
                password,
                verification_status,
                is_enabled,
                category_id
            FROM artist_table
            WHERE LOWER(username) = LOWER(%s) OR LOWER(email) = LOWER(%s)
            LIMIT 1
        """, (username, username))

        artist = cur.fetchone()

        if not artist:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'User not found'})

        # Check verification status
        status = str(artist.get('verification_status') or '').strip().lower()
        if status != 'approved':
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Your account is pending approval'})

        # Check if enabled
        try:
            enabled = int(artist.get('is_enabled') or 0)
        except (TypeError, ValueError):
            enabled = 0
        if enabled != 1:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Account disabled'})

        # Check password
        stored_hash = str(artist.get('password') or '')
        if not stored_hash or not bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8')):
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Invalid password'})

        # Set session
        session['artist_id'] = artist['artist_id']
        session['username'] = artist['username']
        session.permanent = True

        # Create free trial if needed
        sub_conn = get_db()
        try:
            sub_cur = sub_conn.cursor()
            create_free_trial_if_missing(sub_cur, artist['artist_id'])
            sub_conn.commit()
            sub_cur.close()
        finally:
            sub_conn.close()

        cur.close()
        conn.close()

        return jsonify({
            'success': True,
            'artist_id': artist['artist_id'],
            'name': f"{artist.get('first_name', '')} {artist.get('last_name', '')}".strip(),
            'email': artist.get('email', '')
        })

    except Exception as e:
        logger.exception("Login error")
        return jsonify({'success': False, 'error': str(e)})

'''@app.route('/api/login', methods=['POST'])
def api_login():
    try:
        if not request.is_json:
            return jsonify({'success': False, 'error': 'Invalid request'}), 400

        data = request.get_json() or {}
        username = str(data.get('username') or '').strip()
        password = str(data.get('password') or '').strip()

        if not username or not password:
            return jsonify({'success': False, 'error': 'Username and password required'}), 400

        conn = get_db()
        cur = conn.cursor()

        # Use CORRECT lowercase column names
        cur.execute("""
            SELECT 
                artist_id,
                first_name,
                last_name,
                username,
                password,
                verification_status,
                is_enabled,
                category_id
            FROM artist_table
            WHERE LOWER(username) = LOWER(%s) OR LOWER(email) = LOWER(%s)
            LIMIT 1
        """, (username, username))

        artist = cur.fetchone()

        if not artist:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'User not found'})

        # Check verification status - use lowercase column name
        status = str(artist.get('verification_status') or '').strip().lower()
        if status != 'approved':
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Your account is pending approval'})

        # Check if enabled - use lowercase column name
        try:
            enabled = int(artist.get('is_enabled') or 0)
        except (TypeError, ValueError):
            enabled = 0
        if enabled != 1:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Account disabled'})

        # Check password
        stored_hash = str(artist.get('password') or '')
        if not stored_hash or not bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8')):
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Invalid password'})

        # Set session
        session['artist_id'] = artist['artist_id']
        session['username'] = artist['username']
        session.permanent = True

        cur.close()
        conn.close()

        return jsonify({
            'success': True,
            'artist_id': artist['artist_id'],
            'name': f"{artist.get('first_name', '')} {artist.get('last_name', '')}".strip(),
            'category_id': artist.get('category_id')
        })

    except Exception as e:
        logger.exception("Login error")
        return jsonify({'success': False, 'error': str(e)})'''

'''@app.route('/api/login', methods=['POST'])
def api_login():
    try:
        if not request.is_json:
            return jsonify({'success': False, 'error': 'Invalid request'}), 400

        data = request.get_json() or {}
        username = str(data.get('username') or '').strip()
        password = str(data.get('password') or '').strip()

        if not username or not password:
            return jsonify({'success': False, 'error': 'Username and password required'}), 400

        conn = get_db()
        cur = conn.cursor()

        cur.execute("""
            SELECT 
                a.artist_id,
                a.first_name,
                a.last_name,
                a.username,
                a.password,
                a.verification_status,
                a.is_enabled,
                a.category_id,
                ct.category_name
            FROM artist_table a
            LEFT JOIN category_table ct 
                ON a.category_id = ct.category_id
            WHERE LOWER(a.username) = LOWER(%s)
            LIMIT 1
        """, (username,))


        artist = cur.fetchone()

        if not artist:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'User not found'})

        status = str(artist.get('Verification_status') or '').strip().lower()
        if status != 'approved':
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Your account is pending approval'})

        try:
            enabled = int(artist.get('Is_enabled') or 0)
        except (TypeError, ValueError):
            enabled = 0
        if enabled != 1:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Account disabled'})

        stored_hash = str(artist.get('Password') or '')
        if not stored_hash or not bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8')):
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Invalid password'})

        session['artist_id'] = artist['artist_id']
        session['username'] = artist['username']
        session.permanent = True

        cur.close()
        conn.close()

        return jsonify({
            'success': True,
            'artist_id': artist['artist_id'],
            'name': f"{artist['first_name']} {artist['last_name']}",
            'category': artist.get('category_name') or artist.get('Category') or '',
            'category_id': artist.get('category_id')
        })

    except Exception as e:
        logger.exception("Login error")
        return jsonify({'success': False, 'error': str(e)})'''


@app.route('/api/debug_passwords', methods=['GET'])
def debug_passwords():
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT artist_ID, username, password, verification_status, is_enabled
            FROM artist_table
            ORDER BY artist_ID ASC
            """
        )
        artists = cur.fetchall()

        result = []
        for artist in artists:
            pwd = str(artist.get('password') or '')
            pwd_preview = pwd[:20] + "..." if len(pwd) > 20 else pwd
            is_bcrypt_prefix = pwd.startswith('$2b$') or pwd.startswith('$2a$') or pwd.startswith('$2y$')
            bcrypt_usable = False
            if is_bcrypt_prefix:
                try:
                    bcrypt.checkpw('Test@1234'.encode('utf-8'), pwd.encode('utf-8'))
                    bcrypt_usable = True
                except Exception:
                    bcrypt_usable = False
            result.append({
                'artist_ID': artist['artist_ID'],
                'username': artist['username'],
                'password_preview': pwd_preview,
                'password_length': len(pwd),
                'starts_with_bcrypt': is_bcrypt_prefix,
                'bcrypt_hash_readable': bcrypt_usable,
                'verification_status': artist.get('verification_status'),
                'is_enabled': artist.get('is_enabled')
            })

        return jsonify({'success': True, 'artists': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
    

# 4. LOGOUT

@app.route('/api/deactivate', methods=['POST'])
@login_required
def api_deactivate():
    """Deactivate the logged-in artist account (is_enabled = 0) then log out."""
    try:
        artist_id = session['artist_id']
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "UPDATE artist_table SET is_enabled = 0 WHERE artist_id = %s",
            (artist_id,)
        )
        conn.commit()
        cur.close()
        conn.close()
        session.clear()
        return jsonify({'success': True, 'message': 'Account deactivated'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'success': True})

# 5. CHECK SESSION
# 5. CHECK SESSION - FIXED
@app.route('/api/check_session')
def api_check_session():
    if 'artist_id' in session:
        conn = get_db()
        cur = conn.cursor()
        ensure_artist_schema(cur)
        cur.execute("SELECT first_name, last_name, profile_pic FROM artist_table WHERE artist_id = %s", (session['artist_id'],))
        artist = cur.fetchone()
        cur.close()
        conn.close()
        first_name = (artist or {}).get('first_name') or ''
        last_name = (artist or {}).get('last_name') or ''
        initials = ((first_name[:1] + last_name[:1]).upper() or (first_name[:2].upper() if first_name else 'CV'))
        return jsonify({
            'logged_in': True,
            'artist_id': session['artist_id'],
            'name': first_name,
            'user_initials': initials,
            'profile_pic': (artist or {}).get('profile_pic') or ''
        })
    return jsonify({'logged_in': False})

# 6. PROFILE
# 6. PROFILE - FIXED COLUMN NAMES
@app.route('/api/profile')
@login_required
def api_profile():
    try:
        conn = get_db()
        cur = conn.cursor()
        artist_id = session['artist_id']

        # Try with c.pincode first; fall back without it if column doesn't exist
        profile_query_with_pincode = """
            SELECT
                a.artist_id,
                a.first_name,
                a.last_name,
                a.username,
                a.password,
                a.gender,
                a.dob,
                a.phone_number,
                a.state_id,
                a.city_id,
                a.portfolio_path,
                a.verification_status,
                a.is_enabled,
                a.created_at,
                a.profile_pic,
                a.portfolio_files,
                a.working_start_time,
                a.working_end_time,
                a.email,
                a.experience_years,
                a.price_per_hour,
                a.rating,
                a.category_id,
                ct.category_name,
                s.state_name,
                c.city_name,
                c.pincode,
                abd.bank_name,
                abd.account_number AS bank_account_number,
                abd.account_holder_name,
                abd.ifsc_code,
                abd.upi_id
            FROM artist_table a
            LEFT JOIN category_table ct ON a.category_id = ct.category_id
            LEFT JOIN state_table s ON a.state_id = s.state_id
            LEFT JOIN city_table c ON a.city_id = c.city_id
            LEFT JOIN artist_bank_details abd ON a.artist_id = abd.artist_id
            WHERE a.artist_id = %s
            LIMIT 1
        """
        profile_query_without_pincode = """
            SELECT
                a.artist_id,
                a.first_name,
                a.last_name,
                a.username,
                a.password,
                a.gender,
                a.dob,
                a.phone_number,
                a.state_id,
                a.city_id,
                a.portfolio_path,
                a.verification_status,
                a.is_enabled,
                a.created_at,
                a.profile_pic,
                a.portfolio_files,
                a.working_start_time,
                a.working_end_time,
                a.email,
                a.experience_years,
                a.price_per_hour,
                a.rating,
                a.category_id,
                ct.category_name,
                s.state_name,
                c.city_name,
                NULL AS pincode,
                abd.bank_name,
                abd.account_number AS bank_account_number,
                abd.account_holder_name,
                abd.ifsc_code,
                abd.upi_id
            FROM artist_table a
            LEFT JOIN category_table ct ON a.category_id = ct.category_id
            LEFT JOIN state_table s ON a.state_id = s.state_id
            LEFT JOIN city_table c ON a.city_id = c.city_id
            LEFT JOIN artist_bank_details abd ON a.artist_id = abd.artist_id
            WHERE a.artist_id = %s
            LIMIT 1
        """
        try:
            cur.execute(profile_query_with_pincode, (artist_id,))
        except Exception:
            cur.execute(profile_query_without_pincode, (artist_id,))

        '''cur.execute(
            """
            SELECT
                a.Artist_ID, a.First_Name, a.Last_Name, a.Username, a.Email,
                a.Gender, a.dob, a.Phone_Number, a.State_ID, a.City_ID,
                a.Portfolio_Path, a.verification_status, a.is_enabled, a.created_at,
                a.profile_pic, a.portfolio_files,
                a.working_start_time, a.working_end_time,
                a.experience_years, a.price_per_hour, a.rating, a.category_id,
                ct.category_name,
                s.state_name,
                c.city_name,
                c.pincode,
                abd.bank_name,
                abd.account_number  AS bank_account_number,
                abd.account_holder_name,
                abd.ifsc_code,
                abd.upi_id
            FROM artist_table a
            LEFT JOIN category_table ct  ON a.category_id = ct.category_id
            LEFT JOIN state_table s      ON a.State_ID    = s.state_id
            LEFT JOIN city_table c       ON a.City_ID     = c.city_id
            LEFT JOIN artist_bank_details abd ON a.Artist_ID = abd.artist_id
            WHERE a.Artist_ID = %s
            LIMIT 1
            """,
            (artist_id,)
        )'''



        artist = cur.fetchone()
        
        if not artist:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Artist not found'})

        portfolio_files = parse_portfolio_paths(artist.get('portfolio_files'))
        if not portfolio_files and artist.get('portfolio_path'):
            portfolio_files = [artist.get('portfolio_path')]

        artist_payload = {
            'artist_id': artist.get('artist_id'),
            'first_name': artist.get('first_name') or '',
            'last_name': artist.get('last_name') or '',
            'username': artist.get('username') or '',
            'email': artist.get('email') or '',
            'gender': artist.get('gender') or '',
            'dob': str(artist.get('dob') or ''),
            'phone_number': artist.get('phone_number') or '',
            'pincode': artist.get('pincode') or '',
            'state_id': artist.get('state_id'),
            'city_id': artist.get('city_id'),
            'state_name': artist.get('state_name') or '',
            'city_name': artist.get('city_name') or '',
            'category': artist.get('category_name') or '',
            'category_id': artist.get('category_id'),
            'category_name': artist.get('category_name') or '',
            'portfolio_path': artist.get('portfolio_path') or '',
            'portfolio_files': portfolio_files,
            'profile_pic': artist.get('profile_pic') or '',
            'verification_status': artist.get('verification_status') or '',
            'is_enabled': artist.get('is_enabled'),
            'created_at': artist.get('created_at').isoformat() if artist.get('created_at') else None,
            'working_start_time': artist.get('working_start_time') or '',
            'working_end_time': artist.get('working_end_time') or '',
            'bank_name': artist.get('bank_name') or '',
            'bank_account_number': artist.get('bank_account_number') or '',
            'account_holder_name': artist.get('account_holder_name') or '',
            'ifsc_code': artist.get('ifsc_code') or '',
            'upi_id': artist.get('upi_id') or '',
            'experience_years': artist.get('experience_years'),
            'price_per_hour': float(artist.get('price_per_hour') or 0),
            'rating': float(artist.get('rating') or 0.0)
        }
        
        cur.execute("SHOW TABLES")
        table_rows = cur.fetchall() or []
        table_names = {str(list(r.values())[0]).lower() for r in table_rows if r}

        stats = {
            'total_bookings': 0,
            'avg_rating': 0.0,
            'earnings': 0.0,
            'days_on_platform': 0
        }

        if 'booking_table' in table_names:
            booking_cols = get_table_columns(cur, 'booking_table')
            booking_artist_col = pick_column(booking_cols, ['artist_id'])
            if booking_artist_col:
                cur.execute(
                    f"SELECT COUNT(*) AS total FROM booking_table WHERE `{booking_artist_col}` = %s",
                    (artist_id,)
                )
                stats['total_bookings'] = int((cur.fetchone() or {}).get('total') or 0)

        if 'feedback_table' in table_names:
            feedback_cols = get_table_columns(cur, 'feedback_table')
            feedback_artist_col = pick_column(feedback_cols, ['artist_id'])
            feedback_rating_col = pick_column(feedback_cols, ['rating'])
            if feedback_artist_col and feedback_rating_col:
                cur.execute(
                    f"""
                    SELECT AVG(`{feedback_rating_col}`) AS avg_rating
                    FROM feedback_table
                    WHERE `{feedback_artist_col}` = %s
                    """,
                    (artist_id,)
                )
                stats['avg_rating'] = float((cur.fetchone() or {}).get('avg_rating') or 0.0)

        earnings_table = None
        for candidate in ('payment_table', 'earnings_table', 'booking_table'):
            if candidate in table_names:
                earnings_table = candidate
                break
        if earnings_table:
            earnings_cols = get_table_columns(cur, earnings_table)
            earnings_artist_col = pick_column(earnings_cols, ['artist_id'])
            earnings_amount_col = pick_column(earnings_cols, ['amount', 'payment_amount'])
            if earnings_artist_col and earnings_amount_col:
                cur.execute(
                    f"""
                    SELECT SUM(`{earnings_amount_col}`) AS total_earnings
                    FROM {earnings_table}
                    WHERE `{earnings_artist_col}` = %s
                    """,
                    (artist_id,)
                )
                stats['earnings'] = float((cur.fetchone() or {}).get('total_earnings') or 0.0)

        if artist.get('created_at'):
            cur.execute(
                "SELECT DATEDIFF(CURDATE(), DATE(created_at)) AS days_on_platform FROM artist_table WHERE artist_id = %s",
                (artist_id,)
            )
            stats['days_on_platform'] = int((cur.fetchone() or {}).get('days_on_platform') or 0)
        
        cur.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'artist': artist_payload,
            'stats': stats
        })
    except Exception as e:
        logger.exception("Profile fetch failed")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/profile/portfolio', methods=['POST'])
@login_required
def api_profile_portfolio_upload():
    try:
        files = request.files.getlist('portfolio_files')
        if not files:
            return jsonify({'success': False, 'error': 'No files selected'})

        conn = get_db()
        cur = conn.cursor()
        artist_id = session['artist_id']

        ensure_artist_schema(cur)
        cur.execute("SELECT portfolio_files FROM artist_table WHERE artist_id = %s", (artist_id,))
        row = cur.fetchone()
        existing_files = parse_portfolio_paths((row or {}).get('portfolio_files'))

        if len(existing_files) + len(files) > 10:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Maximum 10 media files allowed'})

        os.makedirs(app.config['PORTFOLIO_UPLOAD_DIR'], exist_ok=True)
        uploaded_paths = []

        for file_obj in files:
            filename = file_obj.filename or ''
            if not is_allowed_portfolio_file(filename):
                cur.close()
                conn.close()
                return jsonify({'success': False, 'error': 'Only jpg, jpeg, png, mp4 files are allowed'})

            safe_name = secure_filename(filename)
            ext = safe_name.rsplit('.', 1)[1].lower()
            stored_name = f"{artist_id}_{uuid.uuid4().hex}.{ext}"
            abs_path = os.path.join(app.config['PORTFOLIO_UPLOAD_DIR'], stored_name)
            file_obj.save(abs_path)
            uploaded_paths.append('/static/uploads/portfolio/' + stored_name)

        final_files = existing_files + uploaded_paths

        if len(final_files) < 3:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Minimum 3 media files required'})

        cur.execute(
            "UPDATE artist_table SET portfolio_files = %s WHERE artist_id = %s",
            (json.dumps(final_files), artist_id)
        )

        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True, 'portfolio_files': final_files})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/artist/<int:artist_id>/portfolio')
def api_artist_portfolio(artist_id):
    try:
        conn = get_db()
        cur = conn.cursor()
        ensure_artist_schema(cur)
        cur.execute("SELECT portfolio_files FROM artist_table WHERE artist_id = %s", (artist_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()

        if not row:
            return jsonify({'success': False, 'error': 'Artist not found'}), 404

        return jsonify({'success': True, 'portfolio_files': parse_portfolio_paths(row.get('portfolio_files'))})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# 7. UPDATE PROFILE
# 7. UPDATE PROFILE - FIXED COLUMN NAMES
@app.route('/api/profile/update', methods=['POST'])
@login_required
def api_update_profile():
    try:
        data = request.json
        artist_id = session['artist_id']
        
        # Validate required fields
        required_fields = ['first_name', 'last_name', 'phone', 'gender', 'dob', 
                          'category', 'state_id', 'city_id']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({'success': False, 'error': f'{field.replace("_", " ").title()} is required'})
        
        conn = get_db()
        cur = conn.cursor()
        
        # Check if state and city exist (lowercase per schema)
        cur.execute("SELECT COUNT(*) as count FROM state_table WHERE state_id = %s", (data['state_id'],))
        state_exists = cur.fetchone()['count'] > 0
        
        cur.execute("SELECT COUNT(*) as count FROM city_table WHERE city_id = %s AND state_id = %s", 
                   (data['city_id'], data['state_id']))
        city_exists = cur.fetchone()['count'] > 0
        
        if not state_exists:
            return jsonify({'success': False, 'error': 'Invalid state selected'})
        
        if not city_exists:
            return jsonify({'success': False, 'error': 'Invalid city selected'})

        category_id = resolve_category_id(cur, data.get('category'))
        if not category_id:
            return jsonify({'success': False, 'error': 'Invalid category selected'})

        # Update query with correct column names
        cur.execute("""
            UPDATE artist_table 
            SET first_name = %s, 
                last_name = %s, 
                phone_number = %s,
                gender = %s, 
                dob = %s, 
                state_id = %s, 
                city_id = %s, 
                category_id = %s
            WHERE artist_id = %s
        """, (
            data['first_name'],
            data['last_name'],
            data['phone'],
            data['gender'],
            data['dob'],
            data['state_id'],
            data['city_id'],
            category_id,
            artist_id
        ))
        
        # Update artist_table using correct PascalCase column names per schema
        '''cur.execute("""
            UPDATE artist_table 
            SET First_Name = %s, 
                Last_Name = %s, 
                Phone_Number = %s,
                Gender = %s, 
                dob = %s, 
                State_ID = %s, 
                City_ID = %s, 
                category_id = %s
            WHERE Artist_ID = %s
        """, (
            data['first_name'],
            data['last_name'],
            data['phone'],
            data['gender'],
            data['dob'],
            data['state_id'],
            data['city_id'],
            category_id,
            artist_id
        ))'''
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Profile updated successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/profile/update_with_media', methods=['POST'])
@login_required
def api_update_profile_with_media():
    try:
        data = request.form
        artist_id = session['artist_id']

        required_fields = ['first_name', 'last_name', 'phone', 'gender', 'dob',
                           'category', 'state_id', 'city_id']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({'success': False, 'error': f'{field.replace("_", " ").title()} is required'})

        conn = get_db()
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) as count FROM state_table WHERE state_id = %s", (data['state_id'],))
        state_exists = cur.fetchone()['count'] > 0

        cur.execute("SELECT COUNT(*) as count FROM city_table WHERE city_id = %s AND state_id = %s",
                    (data['city_id'], data['state_id']))
        city_exists = cur.fetchone()['count'] > 0

        if not state_exists:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Invalid state selected'})
        if not city_exists:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Invalid city selected'})

        category_id = resolve_category_id(cur, data.get('category'))
        if not category_id:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Invalid category selected'})

        ensure_artist_schema(cur)
        cur.execute("SELECT portfolio_files, profile_pic FROM artist_table WHERE artist_id = %s", (artist_id,))
        artist_row = cur.fetchone() or {}
        existing_portfolio = parse_portfolio_paths(artist_row.get('portfolio_files'))

        removed_portfolio_indexes = set()
        removed_raw = data.get('removed_portfolio_indexes', '[]')
        try:
            removed_portfolio_indexes = {int(idx) for idx in json.loads(removed_raw)}
        except Exception:
            removed_portfolio_indexes = set()

        replacement_indices = [int(x) for x in request.form.getlist('replacement_indices') if str(x).strip().isdigit()]
        replacement_files = request.files.getlist('replacement_files')
        if len(replacement_indices) != len(replacement_files):
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Invalid replacement portfolio payload'})

        replacement_map = {}
        for idx, file_obj in zip(replacement_indices, replacement_files):
            filename = file_obj.filename or ''
            if not is_allowed_portfolio_file(filename):
                cur.close()
                conn.close()
                return jsonify({'success': False, 'error': 'Only jpg, jpeg, png, mp4 files are allowed'})
            replacement_map[idx] = file_obj

        new_portfolio_files = request.files.getlist('portfolio_new_files')
        for file_obj in new_portfolio_files:
            filename = file_obj.filename or ''
            if not is_allowed_portfolio_file(filename):
                cur.close()
                conn.close()
                return jsonify({'success': False, 'error': 'Only jpg, jpeg, png, mp4 files are allowed'})

        os.makedirs(app.config['PORTFOLIO_UPLOAD_DIR'], exist_ok=True)

        updated_portfolio = []
        for idx, existing_path in enumerate(existing_portfolio):
            if idx in removed_portfolio_indexes:
                continue
            if idx in replacement_map:
                file_obj = replacement_map[idx]
                safe_name = secure_filename(file_obj.filename or 'portfolio_file')
                ext = safe_name.rsplit('.', 1)[1].lower()
                stored_name = f"{artist_id}_{uuid.uuid4().hex}.{ext}"
                abs_path = os.path.join(app.config['PORTFOLIO_UPLOAD_DIR'], stored_name)
                file_obj.save(abs_path)
                updated_portfolio.append('/static/uploads/portfolio/' + stored_name)
            else:
                updated_portfolio.append(existing_path)

        for file_obj in new_portfolio_files:
            if not file_obj or not file_obj.filename:
                continue
            safe_name = secure_filename(file_obj.filename)
            ext = safe_name.rsplit('.', 1)[1].lower()
            stored_name = f"{artist_id}_{uuid.uuid4().hex}.{ext}"
            abs_path = os.path.join(app.config['PORTFOLIO_UPLOAD_DIR'], stored_name)
            file_obj.save(abs_path)
            updated_portfolio.append('/static/uploads/portfolio/' + stored_name)

        if len(updated_portfolio) < 3:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Minimum 3 media files required'})
        if len(updated_portfolio) > 10:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Maximum 10 media files allowed'})

        profile_picture_path = artist_row.get('profile_pic')
        profile_picture_file = request.files.get('profile_picture')
        if profile_picture_file and profile_picture_file.filename:
            if not is_allowed_profile_picture_file(profile_picture_file.filename):
                cur.close()
                conn.close()
                return jsonify({'success': False, 'error': 'Profile picture must be jpg, jpeg, or png'})

            os.makedirs(app.config['PROFILE_PICTURE_UPLOAD_DIR'], exist_ok=True)
            safe_name = secure_filename(profile_picture_file.filename)
            ext = safe_name.rsplit('.', 1)[1].lower()
            stored_name = f"{artist_id}_{uuid.uuid4().hex}.{ext}"
            abs_path = os.path.join(app.config['PROFILE_PICTURE_UPLOAD_DIR'], stored_name)
            profile_picture_file.save(abs_path)
            profile_picture_path = '/static/uploads/profile_pictures/' + stored_name

        query = """
            UPDATE artist_table 
            SET first_name = %s,
                last_name = %s,
                phone_number = %s,
                gender = %s,
                dob = %s,
                state_id = %s,
                city_id = %s,
                category_id = %s,
                portfolio_files = %s
        """

        '''query = """
            UPDATE artist_table 
            SET First_Name = %s,
                Last_Name = %s,
                Phone_Number = %s,
                Gender = %s,
                dob = %s,
                State_ID = %s,
                City_ID = %s,
                category_id = %s,
                portfolio_files = %s
        """'''
        params = [
            data['first_name'],
            data['last_name'],
            data['phone'],
            data['gender'],
            data['dob'],
            data['state_id'],
            data['city_id'],
            category_id,
            json.dumps(updated_portfolio)
        ]

        if profile_picture_path:
            query += ", profile_pic = %s"
            params.append(profile_picture_path)

        query += " WHERE artist_id = %s"
        params.append(artist_id)

        cur.execute(query, tuple(params))
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({
            'success': True,
            'message': 'Profile updated successfully',
            'portfolio_files': updated_portfolio,
            'profile_picture_path': profile_picture_path
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# 8. DASHBOARD
@app.route('/api/dashboard')
@login_required
def api_dashboard():
    try:
        conn = get_db()
        cur = conn.cursor()
        artist_id = session['artist_id']
        auto_complete_bookings(artist_id)

        ensure_artist_schema(cur)
        cur.execute("SHOW TABLES")
        table_rows = cur.fetchall() or []
        table_names = {str(list(r.values())[0]).lower() for r in table_rows if r}

        # Use known schema column names for artist_table directly
        cur.execute(
            """
            SELECT artist_id, first_name, last_name, username, profile_pic
            FROM artist_table
            WHERE artist_id = %s
            """,
            (artist_id,)
        )
        artist = cur.fetchone() or {}

        total_bookings = 0
        earnings = 0.0
        upcoming = []
        feedback = []

        if 'booking_table' in table_names:
            booking_cols = get_table_columns(cur, 'booking_table')
            booking_id_col = pick_column(booking_cols, ['booking_id'])
            booking_artist_col = pick_column(booking_cols, ['artist_id'])
            booking_date_col = pick_column(booking_cols, ['booking_date', 'slot_date', 'booked_at', 'created_at'])
            booking_time_col = pick_column(booking_cols, ['slot_time', 'start_time'])
            booking_status_col = pick_column(booking_cols, ['status', 'booking_status'])
            booking_type_col = pick_column(booking_cols, ['booking_type', 'slot_type', 'type', 'service_type'])
            booking_client_name_col = pick_column(booking_cols, ['client_name'])
            booking_client_id_col = pick_column(booking_cols, ['client_id'])
            booking_amount_col = pick_column(booking_cols, ['amount', 'payment_amount'])

            if booking_artist_col:
                cur.execute(
                    f"SELECT COUNT(*) AS total FROM booking_table WHERE `{booking_artist_col}` = %s",
                    (artist_id,)
                )
                total_bookings = int((cur.fetchone() or {}).get('total') or 0)

            if booking_artist_col and booking_amount_col:
                cur.execute(
                    f"""
                    SELECT SUM(`{booking_amount_col}`) AS total_earnings
                    FROM booking_table
                    WHERE `{booking_artist_col}` = %s
                    """,
                    (artist_id,)
                )
                earnings = float((cur.fetchone() or {}).get('total_earnings') or 0.0)

            # Fetch upcoming bookings using calendar_table join for precise datetime filtering
            cur.execute(
                """
                SELECT
                    b.Booking_ID AS booking_id,
                    cal.Slot_Date AS slot_date,
                    cal.Start_Time AS start_time,
                    cal.End_Time AS end_time,
                    cal.Slot_type AS slot_type,
                    b.Booking_Status AS booking_status,
                    b.Client_ID AS client_id,
                    c.first_name AS client_first_name,
                    c.last_name AS client_last_name
                FROM booking_table b
                LEFT JOIN calendar_table cal ON cal.Slot_ID = b.Slot_ID
                LEFT JOIN client_table c ON c.client_id = b.Client_ID
                WHERE b.Artist_ID = %s
                  AND b.booking_status != 'cancelled'
                  AND CONCAT(cal.Slot_Date, ' ', cal.Start_Time) > NOW()
                ORDER BY cal.Slot_Date ASC, cal.Start_Time ASC
                LIMIT 5
                """,
                (artist_id,)
            )
            booking_rows = cur.fetchall() or []

            if booking_artist_col and booking_date_col:
                pass  # query already done above

                for row in booking_rows:
                    booking_date = row.get('slot_date')
                    if isinstance(booking_date, datetime):
                        booking_date = booking_date.date()
                    slot_date_str = booking_date.strftime('%Y-%m-%d') if booking_date else ''

                    raw_time = row.get('start_time')
                    if hasattr(raw_time, 'total_seconds'):
                        total = int(raw_time.total_seconds())
                        start_time = f"{total // 3600:02d}:{(total % 3600) // 60:02d}"
                    else:
                        start_time = str(raw_time or '09:00')[:5]

                    raw_type = str(row.get('slot_type') or '').strip()
                    slot_type = raw_type if raw_type in ('Communication', 'Performance') else 'Performance'

                    status = str(row.get('booking_status') or 'confirmed').lower()

                    upcoming.append({
                        'Slot_Date': slot_date_str,
                        'first_name': row.get('client_first_name') or 'Client',
                        'last_name': row.get('client_last_name') or '',
                        'Start_Time': start_time,
                        'Slot_Type': slot_type,
                        'Booking_Status': status
                    })

        if earnings == 0.0:
            for candidate in ('payment_table', 'earnings_table'):
                if candidate not in table_names:
                    continue
                pay_cols = get_table_columns(cur, candidate)
                pay_artist_col = pick_column(pay_cols, ['artist_id'])
                pay_amount_col = pick_column(pay_cols, ['amount', 'payment_amount'])
                if pay_artist_col and pay_amount_col:
                    cur.execute(
                        f"""
                        SELECT SUM(`{pay_amount_col}`) AS total_earnings
                        FROM {candidate}
                        WHERE `{pay_artist_col}` = %s
                        """,
                        (artist_id,)
                    )
                    earnings = float((cur.fetchone() or {}).get('total_earnings') or 0.0)
                    break

        if 'feedback_table' in table_names:
            feedback_cols = get_table_columns(cur, 'feedback_table')
            feedback_artist_col = pick_column(feedback_cols, ['artist_id'])
            feedback_rating_col = pick_column(feedback_cols, ['rating'])
            feedback_comment_col = pick_column(feedback_cols, ['comment', 'comments', 'message'])
            feedback_created_col = pick_column(feedback_cols, ['created_at', 'timestamp', 'date'])
            feedback_client_name_col = pick_column(feedback_cols, ['client_name'])

            if feedback_artist_col and feedback_rating_col:
                select_parts = [
                    f"`{feedback_rating_col}` AS rating",
                    f"`{feedback_comment_col}` AS comments" if feedback_comment_col else "NULL AS comments",
                    f"`{feedback_created_col}` AS created_at" if feedback_created_col else "CURRENT_TIMESTAMP AS created_at",
                    f"`{feedback_client_name_col}` AS client_name" if feedback_client_name_col else "'Client' AS client_name"
                ]
                order_by = f"ORDER BY `{feedback_created_col}` DESC" if feedback_created_col else ""
                cur.execute(
                    f"""
                    SELECT {", ".join(select_parts)}
                    FROM feedback_table
                    WHERE `{feedback_artist_col}` = %s
                    {order_by}
                    LIMIT 3
                    """,
                    (artist_id,)
                )
                rows = cur.fetchall() or []
                for row in rows:
                    client_name = str(row.get('client_name') or 'Client').strip()
                    name_parts = client_name.split()
                    first_name = name_parts[0] if name_parts else 'Client'
                    last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''
                    created_at = row.get('created_at')
                    if isinstance(created_at, datetime):
                        created_value = created_at.isoformat()
                    else:
                        created_value = f"{created_at}T00:00:00" if created_at else datetime.now().isoformat()
                    feedback.append({
                        'first_name': first_name,
                        'last_name': last_name,
                        'Rating': int(float(row.get('rating') or 0)),
                        'Comments': row.get('comments') or '',
                        'Created_At': created_value
                    })

        cur.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'artist': artist,
            'stats': {
                'total_bookings': total_bookings,
                'earnings': earnings
            },
            'upcoming_bookings': upcoming,
            'recent_feedback': feedback
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# 9. CHANGE PASSWORD

@app.route('/api/change_password', methods=['POST'])
@login_required
def api_change_password():
    try:
        data = request.get_json()

        artist_id = session['artist_id']
        current_password = data.get('current_password')
        new_password = data.get('new_password')

        conn = get_db()
        cur = conn.cursor()

        cur.execute(
            "SELECT password FROM artist_table WHERE artist_id=%s",
            (artist_id,)
        )

        artist = cur.fetchone()

        if not artist:
            return jsonify({'success': False, 'error': 'Artist not found'})

        stored_hash = artist.get('password') or ''

        # CHECK PASSWORD WITH BCRYPT
        if not bcrypt.checkpw(current_password.encode('utf-8'), stored_hash.encode('utf-8')):
            return jsonify({'success': False, 'error': 'Current password incorrect'})

        # HASH NEW PASSWORD
        new_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        cur.execute(
            "UPDATE artist_table SET password=%s WHERE artist_id=%s",
            (new_hash, artist_id)
        )

        conn.commit()

        cur.close()
        conn.close()

        return jsonify({'success': True, 'message': 'Password updated successfully'})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# 10. SUBSCRIPTION
@app.route('/api/subscription')
@login_required
def api_subscription():
    try:
        conn = get_db()
        cur = conn.cursor()
        artist_id = session['artist_id']

        seed_subscription_plans(cur)
        expire_outdated_subscriptions(cur, artist_id)
        create_free_trial_if_missing(cur, artist_id)
        conn.commit()

        current_subscription = get_current_subscription(cur, artist_id)
        billing_history = get_billing_history(cur, artist_id)

        cur.execute(
            """
            SELECT plan_id, plan_name, amount, duration_days, has_priority, has_featured
            FROM subscription_plan_table
            ORDER BY plan_id
            """
        )
        rows = cur.fetchall() or []
        plans = []
        # Duration label map
        _duration_labels = {30: '1 Month', 90: '3 Months', 180: '6 Months'}
        for row in rows:
            duration_days = int(row.get('duration_days') or 0)
            duration_label = _duration_labels.get(duration_days, f'{duration_days} Days')
            features = ['Unlimited Bookings']
            features.append(f'{duration_label} Validity')
            if int(row.get('has_priority') or 0) == 1:
                features.append('Priority Listing')
            if int(row.get('has_featured') or 0) == 1:
                features.append('Featured Artist Listing')
            plans.append({
                'Plan_ID': row.get('plan_id'),
                'plan_id': row.get('plan_id'),
                'Plan_Name': row.get('plan_name'),
                'plan_name': row.get('plan_name'),
                'Plan_Type': str(row.get('plan_name') or '').lower(),
                'plan_type': str(row.get('plan_name') or '').lower(),
                'Amount': float(row.get('amount') or 0),
                'amount': float(row.get('amount') or 0),
                'Duration_Days': duration_days,
                'duration_days': duration_days,
                'duration_label': duration_label,
                'Features': features,
                'features': features
            })

        cur.close()
        conn.close()

        return jsonify({
            'success': True,
            'plans': plans,
            'subscription': current_subscription,
            'billing_history': billing_history
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/create_order', methods=['POST'])
@app.route('/api/subscription/create_order', methods=['POST'])
@login_required
def api_subscription_create_order():
    try:
        data = request.get_json() or {}
        conn = get_db()
        cur = conn.cursor()
        seed_subscription_plans(cur)
        plan = resolve_plan(cur, data)
        cur.close()
        conn.close()
        if not plan:
            return jsonify({'success': False, 'error': 'Invalid plan selected'}), 400

        key_id = os.getenv('RAZORPAY_KEY_ID', '').strip()
        key_secret = os.getenv('RAZORPAY_SECRET', '').strip() or os.getenv('RAZORPAY_KEY_SECRET', '').strip()
        if not key_id or not key_secret:
            return jsonify({'success': False, 'error': 'Payment gateway is not configured'}), 500

        amount_paise = int(float(plan['amount']) * 100)
        receipt = f"sub_{session['artist_id']}_{int(datetime.now().timestamp())}"
        payload = {
            'amount': amount_paise,
            'currency': 'INR',
            'receipt': receipt,
            'notes': {
                'artist_id': str(session['artist_id']),
                'plan_id': str(plan['plan_id'])
            }
        }

        resp = requests.post(
            'https://api.razorpay.com/v1/orders',
            auth=(key_id, key_secret),
            json=payload,
            timeout=20
        )
        if resp.status_code >= 400:
            return jsonify({'success': False, 'error': 'Failed to initialize payment'}), 500

        order = resp.json()
        return jsonify({
            'success': True,
            'order_id': order.get('id'),
            'amount': amount_paise,
            'currency': 'INR',
            'key_id': key_id,
            'plan_name': plan['plan_name'],
            'plan_type': plan['plan_type'],
            'plan_id': plan['plan_id']
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/subscription/verify_payment', methods=['POST'])
@login_required
def api_subscription_verify_payment():
    try:
        data = request.get_json() or {}
        conn = get_db()
        cur = conn.cursor()
        seed_subscription_plans(cur)
        plan = resolve_plan(cur, data)
        cur.close()
        conn.close()
        if not plan:
            return jsonify({'success': False, 'error': 'Invalid plan selected'}), 400

        order_id = data.get('razorpay_order_id')
        payment_id = data.get('razorpay_payment_id')
        signature = data.get('razorpay_signature')

        if not order_id or not payment_id or not signature:
            return jsonify({'success': False, 'error': 'Missing payment verification fields'}), 400

        key_secret = os.getenv('RAZORPAY_SECRET', '').strip() or os.getenv('RAZORPAY_KEY_SECRET', '').strip()
        key_id = os.getenv('RAZORPAY_KEY_ID', '').strip()
        if not key_id or not key_secret:
            return jsonify({'success': False, 'error': 'Payment gateway is not configured'}), 500

        signed_payload = f"{order_id}|{payment_id}"
        expected_signature = hmac.new(
            key_secret.encode('utf-8'),
            signed_payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()  # hmac.new() is valid in Python's hmac module

        if not hmac.compare_digest(expected_signature, signature):
            return jsonify({'success': False, 'error': 'Payment verification failed'}), 400

        # Verify payment status with Razorpay before activation.
        payment_resp = requests.get(
            f'https://api.razorpay.com/v1/payments/{payment_id}',
            auth=(key_id, key_secret),
            timeout=20
        )
        if payment_resp.status_code >= 400:
            return jsonify({'success': False, 'error': 'Unable to verify payment with gateway'}), 500

        payment_data = payment_resp.json()
        if payment_data.get('status') not in ('captured', 'authorized'):
            return jsonify({'success': False, 'error': 'Payment not captured'}), 400

        conn = get_db()
        cur = conn.cursor()
        seed_subscription_plans(cur)
        activate_paid_subscription(cur, session['artist_id'], plan, payment_id, order_id)
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({'success': True, 'message': 'Payment Successful'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# 11. CALENDAR
@app.route('/api/calendar')
@login_required
def api_calendar():
    try:
        conn = get_db()
        cur = conn.cursor()
        artist_id = session['artist_id']

        ensure_artist_schema(cur)
        ensure_calendar_schema(cur)

        booking_cols = get_table_columns(cur, 'booking_table')
        artist_cols = get_table_columns(cur, 'artist_table')

        booking_id_col = pick_column(booking_cols, ['booking_id'])
        booking_artist_col = pick_column(booking_cols, ['artist_id'])
        booking_date_col = pick_column(booking_cols, ['booking_date', 'slot_date', 'booked_at'])
        booking_time_col = pick_column(booking_cols, ['slot_time', 'start_time'])
        booking_status_col = pick_column(booking_cols, ['status', 'booking_status'])
        booking_client_col = pick_column(booking_cols, ['client_name'])
        booking_type_col = pick_column(booking_cols, ['booking_type', 'slot_type', 'type'])
        booking_title_col = pick_column(booking_cols, ['description', 'title', 'event_name'])
        artist_id_col = pick_column(artist_cols, ['Artist_ID', 'artist_id'])
        start_time_col = pick_column(artist_cols, ['working_start_time'])
        end_time_col = pick_column(artist_cols, ['working_end_time'])

        if not booking_artist_col or not booking_date_col:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Booking table is missing required columns'}), 500

        select_parts = [
            f"`{booking_id_col}` AS booking_id" if booking_id_col else "NULL AS booking_id",
            f"`{booking_date_col}` AS booking_date",
            f"`{booking_time_col}` AS slot_time" if booking_time_col else "NULL AS slot_time",
            f"`{booking_status_col}` AS booking_status" if booking_status_col else "'confirmed' AS booking_status",
            f"`{booking_client_col}` AS client_name" if booking_client_col else "NULL AS client_name",
            f"`{booking_type_col}` AS booking_type" if booking_type_col else "'Event' AS booking_type",
            f"`{booking_title_col}` AS booking_title" if booking_title_col else "NULL AS booking_title"
        ]

        order_by = f"ORDER BY DATE(`{booking_date_col}`) ASC"
        if booking_time_col:
            order_by += f", `{booking_time_col}` ASC"

        cur.execute(
            f"""
            SELECT {", ".join(select_parts)}
            FROM booking_table
            WHERE `{booking_artist_col}` = %s
              AND DATE(`{booking_date_col}`) >= CURDATE()
            {order_by}
            """,
            (artist_id,)
        )
        rows = cur.fetchall() or []

        def normalize_booking_type(raw_type):
            text = str(raw_type or '').strip().lower()
            if 'comm' in text:
                return 'Communication'
            return 'Performance'

        def normalize_status(raw_status):
            status = str(raw_status or 'confirmed').strip().lower()
            if status in ('confirmed', 'completed', 'cancelled', 'reschedule'):
                return status
            if status in ('canceled',):
                return 'cancelled'
            if status in ('rescheduled', 'reschedule requested', 'reschedule_request'):
                return 'reschedule'
            return 'confirmed'

        def parse_slot_time(slot_time_value):
            raw = str(slot_time_value or '').strip()
            if not raw:
                return ('09:00', '10:00')
            normalized = raw.replace('.', ':').replace(' to ', '-').replace(' TO ', '-')
            parts = [p.strip() for p in normalized.split('-') if p.strip()]

            def to_hhmm(value):
                for fmt in ('%H:%M:%S', '%H:%M', '%I:%M %p'):
                    try:
                        return datetime.strptime(value, fmt).strftime('%H:%M')
                    except Exception:
                        continue
                if len(value) == 5 and value[2] == ':':
                    return value
                return None

            start = to_hhmm(parts[0]) if parts else None
            end = to_hhmm(parts[1]) if len(parts) > 1 else None
            if not start:
                start = '09:00'
            if not end:
                try:
                    end_dt = datetime.strptime(start, '%H:%M') + timedelta(hours=1)
                    end = end_dt.strftime('%H:%M')
                except Exception:
                    end = '10:00'
            return (start, end)

        events = []
        today = datetime.now().date()

        for row in rows:
            date_value = row.get('booking_date')
            if isinstance(date_value, datetime):
                booking_date = date_value.date()
            else:
                booking_date = date_value

            if not booking_date:
                continue
            if isinstance(booking_date, str):
                try:
                    booking_date = datetime.strptime(booking_date[:10], '%Y-%m-%d').date()
                except Exception:
                    continue

            start_hhmm, end_hhmm = parse_slot_time(row.get('slot_time'))
            booking_type = normalize_booking_type(row.get('booking_type'))
            client_name = row.get('client_name')
            base_title = row.get('booking_title') or 'Booking'
            title = f"{booking_type}: {base_title}"
            if client_name:
                title = f"{title} - {client_name}"

            status = normalize_status(row.get('booking_status'))
            booking_id = row.get('booking_id')
            event_id = str(booking_id) if booking_id is not None else f"{booking_date}_{start_hhmm}_{booking_type}"

            events.append({
                'id': event_id,
                'title': title,
                'start': f"{booking_date}T{start_hhmm}:00",
                'end': f"{booking_date}T{end_hhmm}:00",
                'type': 'booking',
                'booking_type': booking_type,
                'status': status,
                'client_name': client_name
            })

        # ---- Fetch calendar_table slots (Available / Blocked) ----
        cal_cols = get_table_columns(cur, 'calendar_table')
        cal_slot_id = pick_column(cal_cols, ['Slot_ID', 'slot_id'])
        cal_artist_id = pick_column(cal_cols, ['Artist_ID', 'artist_id'])
        cal_slot_date = pick_column(cal_cols, ['Slot_Date', 'slot_date'])
        cal_start = pick_column(cal_cols, ['Start_Time', 'start_time'])
        cal_end = pick_column(cal_cols, ['End_Time', 'end_time'])
        cal_status = pick_column(cal_cols, ['Status', 'status'])
        cal_slot_type = pick_column(cal_cols, ['Slot_type', 'slot_type'])
        cal_price = pick_column(cal_cols, ['price'])

        if cal_artist_id and cal_slot_date and cal_start and cal_end and cal_status:
            slot_select = [
                f"`{cal_slot_id}` AS slot_id" if cal_slot_id else "NULL AS slot_id",
                f"`{cal_slot_date}` AS slot_date",
                f"`{cal_start}` AS start_time",
                f"`{cal_end}` AS end_time",
                f"`{cal_status}` AS status",
                f"`{cal_slot_type}` AS slot_type" if cal_slot_type else "'Performance' AS slot_type",
                f"`{cal_price}` AS price" if cal_price else "0 AS price"
            ]
            cur.execute(
                f"""
                SELECT {", ".join(slot_select)}
                FROM calendar_table
                WHERE `{cal_artist_id}` = %s
                  AND `{cal_slot_date}` >= CURDATE()
                ORDER BY `{cal_slot_date}` ASC, `{cal_start}` ASC
                """,
                (artist_id,)
            )
            slot_rows = cur.fetchall() or []

            for sr in slot_rows:
                slot_date = sr.get('slot_date')
                if isinstance(slot_date, datetime):
                    slot_date = slot_date.date()
                if isinstance(slot_date, str):
                    try:
                        slot_date = datetime.strptime(slot_date[:10], '%Y-%m-%d').date()
                    except Exception:
                        continue
                if not slot_date:
                    continue

                st_raw = sr.get('start_time') or '09:00'
                et_raw = sr.get('end_time') or '10:00'
                # Handle timedelta from MySQL TIME columns
                if hasattr(st_raw, 'total_seconds'):
                    total = int(st_raw.total_seconds())
                    st = f"{total // 3600:02d}:{(total % 3600) // 60:02d}"
                else:
                    st = str(st_raw).strip()
                    if len(st) > 5:
                        st = st[:5]
                if hasattr(et_raw, 'total_seconds'):
                    total = int(et_raw.total_seconds())
                    et = f"{total // 3600:02d}:{(total % 3600) // 60:02d}"
                else:
                    et = str(et_raw).strip()
                    if len(et) > 5:
                        et = et[:5]

                slot_status = str(sr.get('status') or 'Available').strip()
                slot_type_val = str(sr.get('slot_type') or 'Performance').strip()
                slot_price = float(sr.get('price') or 0)
                sid = sr.get('slot_id')
                eid = f"slot_{sid}" if sid else f"slot_{slot_date}_{st}"

                # Title: clean AM/PM time range only
                try:
                    st_ampm = datetime.strptime(st, '%H:%M').strftime('%I:%M %p')
                    et_ampm = datetime.strptime(et, '%H:%M').strftime('%I:%M %p')
                except Exception:
                    st_ampm, et_ampm = st, et
                title = f"{st_ampm} - {et_ampm}"

                events.append({
                    'id': eid,
                    'title': title,
                    'start': f"{slot_date}T{st}:00",
                    'end': f"{slot_date}T{et}:00",
                    'type': 'slot',
                    'slot_type': slot_type_val,
                    'status': slot_status,
                    'price': slot_price,
                    'slot_id': sid
                })

        # ---- Availability (working hours) ----
        availability = {'start_time': '09:00', 'end_time': '18:00'}
        if artist_id_col and start_time_col and end_time_col:
            cur.execute(
                f"SELECT `{start_time_col}` AS start_time, `{end_time_col}` AS end_time FROM artist_table WHERE `{artist_id_col}` = %s",
                (artist_id,)
            )
            wh_row = cur.fetchone() or {}
            if wh_row.get('start_time'):
                availability['start_time'] = wh_row.get('start_time')
            if wh_row.get('end_time'):
                availability['end_time'] = wh_row.get('end_time')

        cur.close()
        conn.close()

        return jsonify({
            'success': True,
            'events': events,
            'availability': availability
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/availability', methods=['POST'])
@login_required
def api_availability():
    try:
        data = request.get_json() or {}
        start_time = str(data.get('start_time') or '').strip()
        end_time = str(data.get('end_time') or '').strip()
        slot_type = str(data.get('slot_type') or 'Performance').strip()
        price = data.get('price')
        apply_to = str(data.get('apply_to') or 'selected_date').strip()
        selected_date = str(data.get('selected_date') or '').strip()

        if not start_time or not end_time:
            return jsonify({'success': False, 'error': 'Start and end time are required'}), 400

        datetime.strptime(start_time, '%H:%M')
        datetime.strptime(end_time, '%H:%M')

        if start_time >= end_time:
            return jsonify({'success': False, 'error': 'Start time must be before end time'}), 400

        if slot_type not in ('Communication', 'Performance'):
            slot_type = 'Performance'

        if price is None:
            return jsonify({'success': False, 'error': 'Price is required'}), 400
        price = float(price)
        if price < 100:
            return jsonify({'success': False, 'error': 'Minimum slot price is ₹100'}), 400
        if slot_type == 'Communication' and price > 500:
            return jsonify({'success': False, 'error': 'Communication price cannot exceed ₹500'}), 400

        # Determine dates to generate slots for
        target_dates = []
        if apply_to == 'this_week':
            today = datetime.now().date()
            weekday = today.weekday()  # Monday=0
            monday = today - timedelta(days=weekday)
            for i in range(7):
                d = monday + timedelta(days=i)
                if d >= today:
                    target_dates.append(d)
        else:
            # selected_date
            if not selected_date:
                return jsonify({'success': False, 'error': 'Please select a date on the calendar'}), 400
            try:
                target_dates.append(datetime.strptime(selected_date, '%Y-%m-%d').date())
            except ValueError:
                return jsonify({'success': False, 'error': 'Invalid date format'}), 400

        conn = get_db()
        cur = conn.cursor()
        ensure_artist_schema(cur)
        ensure_calendar_schema(cur)

        artist_id = session['artist_id']

        # Save working hours to artist_table
        artist_cols = get_table_columns(cur, 'artist_table')
        artist_id_col = pick_column(artist_cols, ['Artist_ID', 'artist_id'])
        wh_start_col = pick_column(artist_cols, ['working_start_time'])
        wh_end_col = pick_column(artist_cols, ['working_end_time'])

        if artist_id_col and wh_start_col and wh_end_col:
            cur.execute(
                f"UPDATE artist_table SET `{wh_start_col}` = %s, `{wh_end_col}` = %s WHERE `{artist_id_col}` = %s",
                (start_time, end_time, artist_id)
            )

        # Detect calendar_table columns
        cal_cols = get_table_columns(cur, 'calendar_table')
        cal_artist_col = pick_column(cal_cols, ['Artist_ID', 'artist_id'])
        cal_date_col = pick_column(cal_cols, ['Slot_Date', 'slot_date'])
        cal_start_col = pick_column(cal_cols, ['Start_Time', 'start_time'])
        cal_end_col = pick_column(cal_cols, ['End_Time', 'end_time'])
        cal_status_col = pick_column(cal_cols, ['Status', 'status'])
        cal_slot_type_col = pick_column(cal_cols, ['Slot_type', 'slot_type'])
        cal_price_col = pick_column(cal_cols, ['price'])

        if not cal_artist_col or not cal_date_col or not cal_start_col or not cal_end_col or not cal_status_col:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Calendar table is missing required columns'}), 500

        # Generate 1-hour slots between start_time and end_time for each target_date
        slots_created = 0
        for target_date in target_dates:
            current_time = datetime.strptime(start_time, '%H:%M')
            end_time_dt = datetime.strptime(end_time, '%H:%M')

            while current_time + timedelta(hours=1) <= end_time_dt:
                slot_start = current_time.strftime('%H:%M')
                slot_end = (current_time + timedelta(hours=1)).strftime('%H:%M')

                # Check if slot already exists (use HOUR comparison to avoid timedelta mismatch)
                cur.execute(
                    f"""
                    SELECT COUNT(*) AS cnt FROM calendar_table
                    WHERE `{cal_artist_col}` = %s
                      AND `{cal_date_col}` = %s
                      AND HOUR(`{cal_start_col}`) = %s
                      AND MINUTE(`{cal_start_col}`) = %s
                    """,
                    (artist_id, target_date, current_time.hour, current_time.minute)
                )
                exists = (cur.fetchone() or {}).get('cnt', 0)

                if exists == 0:
                    insert_cols = [f"`{cal_artist_col}`", f"`{cal_date_col}`", f"`{cal_start_col}`", f"`{cal_end_col}`", f"`{cal_status_col}`"]
                    insert_vals = [artist_id, target_date, slot_start, slot_end, 'Available']
                    placeholders = ['%s'] * 5

                    if cal_slot_type_col:
                        insert_cols.append(f"`{cal_slot_type_col}`")
                        insert_vals.append(slot_type)
                        placeholders.append('%s')
                    if cal_price_col:
                        insert_cols.append(f"`{cal_price_col}`")
                        insert_vals.append(price)
                        placeholders.append('%s')

                    cur.execute(
                        f"INSERT INTO calendar_table ({', '.join(insert_cols)}) VALUES ({', '.join(placeholders)})",
                        tuple(insert_vals)
                    )
                    slots_created += 1

                current_time += timedelta(hours=1)

        conn.commit()
        cur.close()
        conn.close()

        date_label = ', '.join(str(d) for d in target_dates)
        return jsonify({
            'success': True,
            'message': f'{slots_created} slot(s) created for {date_label}'
        })
    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid time format'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/delete_slot/<int:slot_id>', methods=['DELETE'])
@login_required
def api_delete_slot(slot_id):
    try:
        conn = get_db()
        cur = conn.cursor()
        ensure_calendar_schema(cur)

        cal_cols = get_table_columns(cur, 'calendar_table')
        cal_slot_id = pick_column(cal_cols, ['Slot_ID', 'slot_id'])
        cal_artist_id = pick_column(cal_cols, ['Artist_ID', 'artist_id'])
        cal_status = pick_column(cal_cols, ['Status', 'status'])

        if not cal_slot_id or not cal_artist_id:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Calendar table missing required columns'}), 500

        cur.execute(
            f"SELECT `{cal_status}` AS status FROM calendar_table WHERE `{cal_slot_id}` = %s AND `{cal_artist_id}` = %s",
            (slot_id, session['artist_id'])
        )
        slot = cur.fetchone()

        if not slot:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Slot not found'}), 404

        if str(slot.get('status', '')).strip() != 'Available':
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Only Available slots can be deleted'}), 400

        cur.execute(
            f"DELETE FROM calendar_table WHERE `{cal_slot_id}` = %s AND `{cal_artist_id}` = %s",
            (slot_id, session['artist_id'])
        )
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({'success': True, 'message': 'Slot deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ===== AUTO COMPLETE BOOKINGS =====
def auto_complete_bookings(artist_id):
    try:
        conn = get_db()
        cur = conn.cursor()

        # Mark confirmed bookings as completed if slot_date + end_time < NOW()
        # Uses calendar_table join for precise datetime comparison
        cur.execute("""
            UPDATE booking_table b
            JOIN calendar_table cal ON cal.Slot_ID = b.Slot_ID
            SET b.booking_status = 'completed'
            WHERE b.artist_id = %s
              AND b.booking_status = 'confirmed'
              AND CONCAT(cal.Slot_Date, ' ', cal.End_Time) < NOW()
        """, (artist_id,))

        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print("Auto completion error:", e)

# 12. BOOKINGS
@app.route('/api/bookings')
@login_required
def api_bookings():
    try:
        conn = get_db()
        cur = conn.cursor()
        artist_id = session['artist_id']
        auto_complete_bookings(artist_id)
        booking_cols = get_table_columns(cur, 'booking_table')
        has_cancelled_by = 'cancelled_by' in {str(c).lower() for c in booking_cols}
        has_cancelled_at = 'cancelled_at' in {str(c).lower() for c in booking_cols}

        cancelled_by_select = "b.cancelled_by AS cancelled_by," if has_cancelled_by else "NULL AS cancelled_by,"
        cancelled_at_select = "b.cancelled_at AS cancelled_at," if has_cancelled_at else "NULL AS cancelled_at,"
        
        cur.execute(
    f"""
    SELECT
        b.Booking_ID,
        b.Client_ID,
        b.Artist_ID,  -- booking_table uses PascalCase
        b.Slot_ID,
        b.Booking_Status,
        b.reschedule_status,
        {cancelled_by_select}
        {cancelled_at_select}
        c.first_name AS client_first_name,
        c.last_name  AS client_last_name,
        c.phone_number AS client_phone,
        c.username AS client_username,
        cal.Slot_Date,
        cal.Start_Time,
        cal.End_Time,
        cal.Slot_type,
        cal.price
    FROM booking_table b
    LEFT JOIN client_table c ON c.client_id = b.Client_ID
    LEFT JOIN calendar_table cal ON cal.Slot_ID = b.Slot_ID
    WHERE b.Artist_ID = %s
    ORDER BY cal.Slot_Date DESC, cal.Start_Time DESC, b.Booking_ID DESC
    """,
    (artist_id,)
)


        rows = cur.fetchall() or []

        bookings = []
        for row in rows:
            booking_date = row.get('Slot_Date')
            start_time = str(row.get('Start_Time') or '09:00')[:5]
            end_time = str(row.get('End_Time') or '10:00')[:5]
            client_first = str(row.get('client_first_name') or '').strip()
            client_last = str(row.get('client_last_name') or '').strip()
            client_name = f"{client_first} {client_last}".strip() or 'Client'
            booking_id = row.get('Booking_ID')
            booking_type = str(row.get('Slot_type') or 'Performance')
            if booking_type not in ('Communication', 'Performance'):
                booking_type = 'Performance'
            bookings.append({
                'id': str(booking_id) if booking_id is not None else f"{booking_date}_{start_time}",
                'booking_reference': f"BK{int(booking_id):04d}" if booking_id is not None and str(booking_id).isdigit() else f"BK-{booking_date}",
                'client_name': client_name,
                'client_id': row.get('Client_ID'),
                'client_first_name': client_first or 'Client',
                'client_last_name': client_last,
                'client_phone': row.get('client_phone') or '',
                'client_username': row.get('client_username') or '',
                'slot_type': booking_type,
                'service_type': booking_type,
                'booking_type': booking_type,
                'date_time': f"{booking_date}T{start_time}:00" if booking_date else None,
                'end_datetime': f"{booking_date}T{end_time}:00" if booking_date else None,
                'slot_date': str(booking_date) if booking_date else None,
                'start_time': start_time,
                'end_time': end_time,
                'status': str(row.get('Booking_Status') or '').lower() or 'confirmed',
                'reschedule_status': row.get('reschedule_status'),
                'cancelled_by': row.get('cancelled_by'),
                'cancelled_at': row.get('cancelled_at').isoformat() if row.get('cancelled_at') else None
            })

        cur.close()
        conn.close()
        return jsonify({'success': True, 'bookings': bookings})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/bookings/<int:booking_id>/emergency_cancel', methods=['POST'])
@login_required
def api_emergency_cancel_booking(booking_id):
    try:
        data = request.get_json() or {}
        action = str(data.get('action') or 'cancel').strip().lower()
        cancelled_by = str(data.get('cancelled_by') or 'artist').strip().lower()
        if cancelled_by not in ('artist', 'client'):
            cancelled_by = 'artist'
        new_slot_id = data.get('new_slot_id')

        conn = get_db()
        cur = conn.cursor()
        artist_id = session['artist_id']

        booking_cols = get_table_columns(cur, 'booking_table')
        booking_id_col = pick_column(booking_cols, ['booking_id'])
        booking_artist_col = pick_column(booking_cols, ['artist_id'])
        booking_status_col = pick_column(booking_cols, ['Booking_Status', 'booking_status', 'status'])
        booking_slot_col = pick_column(booking_cols, ['Slot_ID', 'slot_id'])
        booking_new_slot_col = pick_column(booking_cols, ['new_slot_id'])
        cancelled_by_col = pick_column(booking_cols, ['cancelled_by'])

        if not booking_id_col or not booking_artist_col or not booking_status_col:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Booking table is missing required columns'}), 500

        select_parts = [
            f"`{booking_id_col}` AS booking_id",
            f"`{booking_status_col}` AS booking_status"
        ]
        if booking_slot_col:
            select_parts.append(f"`{booking_slot_col}` AS slot_id")
        if booking_new_slot_col:
            select_parts.append(f"`{booking_new_slot_col}` AS new_slot_id")

        cur.execute(
            f"""
            SELECT {', '.join(select_parts)}
            FROM booking_table
            WHERE `{booking_id_col}` = %s AND `{booking_artist_col}` = %s
            """,
            (booking_id, artist_id)
        )
        row = cur.fetchone()
        if not row:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Booking not found'}), 404

        # ---------- Client initiated reschedule flow ----------
        # Client selects an Available slot. Booking_Status -> 'reschedule',
        # new_slot_id -> selected slot. Do NOT change Slot_ID. Do NOT modify calendar_table.
        if action == 'reschedule':
            if not new_slot_id:
                cur.close()
                conn.close()
                return jsonify({'success': False, 'error': 'new_slot_id is required for reschedule'}), 400

            # Verify the selected slot is Available
            calendar_cols = get_table_columns(cur, 'calendar_table')
            calendar_slot_col = pick_column(calendar_cols, ['Slot_ID', 'slot_id'])
            calendar_status_col = pick_column(calendar_cols, ['Status', 'status'])
            if calendar_slot_col and calendar_status_col:
                cur.execute(
                    f"SELECT `{calendar_status_col}` AS slot_status FROM calendar_table WHERE `{calendar_slot_col}` = %s",
                    (new_slot_id,)
                )
                slot_row = cur.fetchone()
                if not slot_row or str(slot_row.get('slot_status', '')).strip() != 'Available':
                    cur.close()
                    conn.close()
                    return jsonify({'success': False, 'error': 'Selected slot is not Available'}), 400

            update_parts = [f"`{booking_status_col}` = %s"]
            update_vals = ['reschedule']
            if booking_new_slot_col:
                update_parts.append(f"`{booking_new_slot_col}` = %s")
                update_vals.append(new_slot_id)
            if cancelled_by_col:
                update_parts.append(f"`{cancelled_by_col}` = %s")
                update_vals.append('client')
            update_vals.extend([booking_id, artist_id])

            cur.execute(
                f"""
                UPDATE booking_table
                SET {', '.join(update_parts)}
                WHERE `{booking_id_col}` = %s AND `{booking_artist_col}` = %s
                """,
                tuple(update_vals)
            )
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({'success': True, 'message': 'Booking marked for reschedule'})

        # ---------- Artist accepts reschedule ----------
        # Retrieve old_slot_id (current Slot_ID) and new_slot_id from booking.
        # Update: Slot_ID = new_slot_id, new_slot_id = NULL, Booking_Status = 'confirmed'
        # Calendar: old_slot_id -> 'Available', new_slot_id -> 'Blocked'
        if action == 'accept_reschedule':
            old_slot_id = row.get('slot_id')
            resolved_new_slot_id = row.get('new_slot_id') or new_slot_id

            calendar_cols = get_table_columns(cur, 'calendar_table')
            calendar_slot_col = pick_column(calendar_cols, ['Slot_ID', 'slot_id'])
            calendar_status_col = pick_column(calendar_cols, ['Status', 'status'])

            update_parts = [f"`{booking_status_col}` = %s"]
            update_vals = ['confirmed']
            if booking_slot_col and resolved_new_slot_id:
                update_parts.append(f"`{booking_slot_col}` = %s")
                update_vals.append(resolved_new_slot_id)
            if booking_new_slot_col:
                update_parts.append(f"`{booking_new_slot_col}` = NULL")
            update_vals.extend([booking_id, artist_id])

            cur.execute(
                f"""
                UPDATE booking_table
                SET {', '.join(update_parts)}
                WHERE `{booking_id_col}` = %s AND `{booking_artist_col}` = %s
                """,
                tuple(update_vals)
            )

            # Update calendar_table: old slot -> Available, new slot -> Blocked
            if calendar_slot_col and calendar_status_col:
                if old_slot_id is not None:
                    cur.execute(
                        f"UPDATE calendar_table SET `{calendar_status_col}` = 'Available' WHERE `{calendar_slot_col}` = %s",
                        (old_slot_id,)
                    )
                if resolved_new_slot_id:
                    cur.execute(
                        f"UPDATE calendar_table SET `{calendar_status_col}` = 'Blocked' WHERE `{calendar_slot_col}` = %s",
                        (resolved_new_slot_id,)
                    )

            conn.commit()
            cur.close()
            conn.close()
            return jsonify({'success': True, 'message': 'Reschedule accepted and booking confirmed'})

        # ---------- Artist rejects reschedule ----------
        # new_slot_id = NULL, Booking_Status = 'confirmed'
        # Do NOT modify Slot_ID. Do NOT modify calendar_table.
        if action == 'reject_reschedule':
            update_parts = [f"`{booking_status_col}` = %s"]
            update_vals = ['confirmed']
            if booking_new_slot_col:
                update_parts.append(f"`{booking_new_slot_col}` = NULL")
            update_vals.extend([booking_id, artist_id])

            cur.execute(
                f"""
                UPDATE booking_table
                SET {', '.join(update_parts)}
                WHERE `{booking_id_col}` = %s AND `{booking_artist_col}` = %s
                """,
                tuple(update_vals)
            )
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({'success': True, 'message': 'Reschedule rejected, booking remains confirmed'})

        # ---------- Default: Emergency cancel ----------
        if cancelled_by_col:
            cur.execute(
                f"""
                UPDATE booking_table
                SET `{booking_status_col}` = %s, `{cancelled_by_col}` = %s
                WHERE `{booking_id_col}` = %s AND `{booking_artist_col}` = %s
                """,
                ('cancelled', cancelled_by, booking_id, artist_id)
            )
        else:
            cur.execute(
                f"""
                UPDATE booking_table
                SET `{booking_status_col}` = %s
                WHERE `{booking_id_col}` = %s AND `{booking_artist_col}` = %s
                """,
                ('cancelled', booking_id, artist_id)
            )

        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True, 'message': 'Booking cancelled in emergency flow'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# 13. EARNINGS
@app.route('/api/earnings')
@login_required
def api_earnings():
    try:
        conn = get_db()
        cur = conn.cursor()
        artist_id = session['artist_id']

        # Bank details come from artist_bank_details (separate table)
        cur.execute(
            """
            SELECT
                abd.bank_name,
                abd.account_number,
                abd.account_holder_name,
                abd.ifsc_code,
                abd.upi_id
            FROM artist_table a
            LEFT JOIN artist_bank_details abd ON a.artist_id = abd.artist_id
            WHERE a.artist_id = %s
            LIMIT 1
            """,
            (artist_id,)
        )
        bank_row = cur.fetchone() or {}
        bank_details = {
            'bank_name': bank_row.get('bank_name') or '',
            'account_number': bank_row.get('account_number') or '',
            'account_holder': bank_row.get('account_holder_name') or '',
            'ifsc_code': bank_row.get('ifsc_code') or '',
            'upi_id': bank_row.get('upi_id') or ''
        }

        transactions = []
        total = 0.0

        cur.execute(
            """
            SELECT
                p.payment_id,
                p.amount,
                p.payment_status,
                p.payment_method,
                p.booking_id,
                p.subscription_id,
                b.booking_id AS Booking_ID,
                b.booking_status AS Booking_Status,
                b.client_id AS Client_ID,
                b.reschedule_status,
                c.first_name AS client_first_name,
                c.last_name AS client_last_name,
                cal.slot_type AS Slot_type,
                cal.slot_date AS Slot_Date
            FROM payment_table p
            LEFT JOIN booking_table b ON b.booking_id = p.booking_id
            LEFT JOIN client_table c ON c.client_id = b.client_id
            LEFT JOIN calendar_table cal ON cal.slot_id = b.slot_id
            WHERE (b.Artist_ID = %s OR p.subscription_id IN (
                SELECT subscription_id FROM subscription_table WHERE artist_id = %s
            ))
            ORDER BY p.payment_id DESC
            """,
            (artist_id, artist_id)
        )
        rows = cur.fetchall() or []
        for row in rows:
            amount = float(row.get('amount') or 0)
            total += amount
            client_name = f"{row.get('client_first_name') or ''} {row.get('client_last_name') or ''}".strip() or 'Client'
            slot_type = str(row.get('Slot_type') or 'Performance')
            if slot_type not in ('Communication', 'Performance'):
                slot_type = 'Performance'
            slot_date = row.get('Slot_Date')
            date_iso = f"{slot_date}T00:00:00" if slot_date else datetime.now().isoformat()
            transactions.append({
                'date': date_iso,
                'client_name': client_name,
                'booking_type': slot_type,
                'booking_reference': f"BK{int(row.get('Booking_ID')):04d}" if row.get('Booking_ID') else '-',
                'amount': amount,
                'status': str(row.get('payment_status') or 'pending'),
                'payment_id': str(row.get('payment_id') or '-'),
                'payment_method': row.get('payment_method') or '-',
                'reschedule_status': row.get('reschedule_status')
            })

        cur.close()
        conn.close()

        return jsonify({
            'success': True,
            'stats': {
                'total': total,
                'available': total
            },
            'transactions': transactions,
            'bank_details': bank_details
        })
    except Exception as e:
        logger.exception("Earnings fetch failed")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/artist/bank-details', methods=['GET', 'POST'])
@login_required
def api_artist_bank_details():
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        artist_id = session['artist_id']

        if request.method == 'GET':
            cur.execute(
                """
                SELECT bank_name, account_number, account_holder_name, ifsc_code, upi_id
                FROM artist_bank_details
                WHERE artist_id = %s
                LIMIT 1
                """,
                (artist_id,)
            )
            row = cur.fetchone() or {}
            return jsonify({
                'success': True,
                'bank_details': {
                    'bank_name': row.get('bank_name', ''),
                    'account_number': row.get('account_number', ''),
                    'account_holder': row.get('account_holder_name', ''),
                    'ifsc_code': row.get('ifsc_code', ''),
                    'upi_id': row.get('upi_id', '')
                }
            })

        # POST — upsert bank details in artist_bank_details
        data = request.get_json() or {}
        cur.execute(
            """
            INSERT INTO artist_bank_details
                (artist_id, bank_name, account_holder_name, account_number, ifsc_code, upi_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                bank_name           = VALUES(bank_name),
                account_holder_name = VALUES(account_holder_name),
                account_number      = VALUES(account_number),
                ifsc_code           = VALUES(ifsc_code),
                upi_id              = VALUES(upi_id)
            """,
            (
                artist_id,
                str(data.get('bank_name', '')).strip(),
                str(data.get('account_holder', '')).strip(),
                str(data.get('account_number', '')).strip(),
                str(data.get('ifsc_code', '')).strip(),
                str(data.get('upi_id', '')).strip()
            )
        )
        conn.commit()
        return jsonify({'success': True, 'message': 'Bank details saved'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    finally:
        if cur: cur.close()
        if conn: conn.close()


@app.route('/api/earnings/bank_details', methods=['POST'])
@login_required
def api_earnings_bank_details():
    return api_artist_bank_details()


@app.route('/api/artist/favorites/count')
@login_required
def api_artist_favorites_count():
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COUNT(*) AS total
            FROM favorite_table
            WHERE artist_id = %s
            """,
            (session['artist_id'],)
        )
        row = cur.fetchone() or {}
        return jsonify({'success': True, 'count': int(row.get('total') or 0)})
    except Exception as e:
        logger.exception("Favorites count failed")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

# 14. NOTIFICATIONS

@app.route('/api/notifications/count')
@login_required
def api_notifications_count():
    """Returns the number of unread notifications for the logged-in artist."""
    try:
        conn = get_db()
        cur = conn.cursor()
        artist_id = session['artist_id']
        cur.execute(
            """
            SELECT COUNT(*) AS unread
            FROM notification_table
            WHERE recipient_type = 'artist'
              AND artist_id = %s
              AND is_read = 0
            """,
            (artist_id,)
        )
        row = cur.fetchone() or {}
        unread = int(row.get('unread') or 0)
        cur.close()
        conn.close()
        return jsonify({'success': True, 'unread': unread})
    except Exception as e:
        return jsonify({'success': False, 'unread': 0, 'error': str(e)})


@app.route('/api/notifications')
@login_required
def api_notifications():
    try:
        conn = get_db()
        cur = conn.cursor()
        artist_id = session['artist_id']

        notifications = []

        cur.execute(
            """
            SELECT
                notification_id,
                title,
                message,
                is_read
            FROM notification_table
            WHERE recipient_type = 'artist'
              AND artist_id = %s
            ORDER BY notification_id DESC
            LIMIT 100
            """,
            (artist_id,)
        )
        rows = cur.fetchall() or []
        for row in rows:
            notifications.append({
                'id': str(row.get('notification_id')),
                'type': 'system',
                'title': row.get('title') or 'Notification',
                'message': row.get('message') or 'You have a new update.',
                'timestamp': datetime.now().isoformat(),
                'read': bool(row.get('is_read')),
                'client_name': ''
            })

        if not notifications:
            cur.execute(
                """
                SELECT
                    b.booking_id AS booking_id,
                    b.booking_status AS booking_status,
                    c.first_name AS first_name,
                    c.last_name AS last_name,
                    cal.slot_type AS slot_type,
                    cal.slot_date AS slot_date
                FROM booking_table b
                LEFT JOIN client_table c ON c.client_id = b.client_id
                LEFT JOIN calendar_table cal ON cal.slot_id = b.slot_id
                WHERE b.artist_id = %s
                ORDER BY b.booking_id DESC
                LIMIT 50
                """,
                (artist_id,)
            )
            fallback_rows = cur.fetchall() or []
            for row in fallback_rows:
                client_name = f"{row.get('first_name') or ''} {row.get('last_name') or ''}".strip() or 'Client'
                status = str(row.get('booking_status') or 'confirmed').lower()
                slot_type = str(row.get('slot_type') or 'Performance')
                title = f"{slot_type} Booking"
                if status == 'reschedule':
                    title = 'Reschedule Requested'
                elif status in ('cancelled', 'canceled'):
                    title = f"{slot_type} Cancelled"
                notifications.append({
                    'id': f"booking_{row.get('booking_id')}",
                    'type': 'booking',
                    'title': title,
                    'message': f"{slot_type} booking update from {client_name}",
                    'timestamp': f"{row.get('slot_date')}T00:00:00" if row.get('slot_date') else datetime.now().isoformat(),
                    'read': False,
                    'booking_id': str(row.get('booking_id')),
                    'status': status,
                    'client_name': client_name
                })

        cur.close()
        conn.close()

        return jsonify({'success': True, 'notifications': notifications})
    except Exception as e:
        logger.exception("Notifications fetch failed")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/notifications/mark_all_read', methods=['POST'])
@login_required
def api_notifications_mark_all_read():
    try:
        conn = get_db()
        cur = conn.cursor()
        artist_id = session['artist_id']

        cur.execute("""
            UPDATE notification_table
            SET is_read = 1
            WHERE recipient_type = 'artist'
            AND artist_id = %s
            AND is_read = 0
        """, (artist_id,))

        affected = cur.rowcount
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({'success': True, 'message': f'{affected} notification(s) marked as read'})
    except Exception as e:
        logger.exception("Mark all read failed")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/client_profile')
@login_required
def api_client_profile():
    try:
        client_id = request.args.get('client_id')
        if not client_id:
            return jsonify({'success': False, 'error': 'client_id is required'}), 400

        conn = get_db()
        cur = conn.cursor()

        cur.execute("""
            SELECT
                c.first_name,
                c.last_name,
                c.username AS email,
                c.phone_number,
                city.city_name,
                state.state_name
            FROM client_table c
            LEFT JOIN city_table city ON c.city_id = city.city_id
            LEFT JOIN state_table state ON c.state_id = state.state_id
            WHERE c.client_id = %s
        """, (client_id,))

        client = cur.fetchone()
        cur.close()
        conn.close()

        if not client:
            return jsonify({'success': False, 'error': 'Client not found'}), 404

        city = client.get('city_name') or ''
        state = client.get('state_name') or ''
        location = f"{city}, {state}" if city and state else (city or state or '')

        return jsonify({
            'success': True,
            'client': {
                'first_name': client.get('first_name') or '',
                'last_name': client.get('last_name') or '',
                'email': client.get('email') or '',
                'phone_number': client.get('phone_number') or '',
                'city_name': city,
                'state_name': state,
                'location': location
            }
        })
    except Exception as e:
        logger.exception("Client profile fetch failed")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/bookings/<int:booking_id>/cancel', methods=['POST'])
@login_required
def api_cancel_booking(booking_id):
    try:
        data = request.get_json() or {}
        reason = str(data.get('cancellation_reason') or '').strip()
        if not reason:
            return jsonify({'success': False, 'error': 'Cancellation reason is required'}), 400

        conn = get_db()
        cur = conn.cursor()
        artist_id = session['artist_id']

        # Verify booking belongs to this artist
        cur.execute("""
            SELECT Booking_ID, Booking_Status
            FROM booking_table
            WHERE Booking_ID = %s AND Artist_ID = %s
        """, (booking_id, artist_id))
        row = cur.fetchone()
        if not row:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Booking not found'}), 404

        if str(row.get('Booking_Status') or '').lower() == 'cancelled':
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Booking is already cancelled'}), 400

        cur.execute("""
            UPDATE booking_table
            SET booking_status = 'cancelled',
                cancelled_by = 'artist',
                cancelled_at = NOW(),
                cancellation_reason = %s
            WHERE Booking_ID = %s AND Artist_ID = %s
        """, (reason, booking_id, artist_id))

        # Release the calendar slot back to Available
        cur.execute("""
            UPDATE calendar_table cal
            JOIN booking_table b ON b.Slot_ID = cal.Slot_ID
            SET cal.Status = 'Available'
            WHERE b.Booking_ID = %s
        """, (booking_id,))

        conn.commit()
        cur.close()
        conn.close()

        return jsonify({'success': True, 'message': 'Booking cancelled successfully'})
    except Exception as e:
        logger.exception("Booking cancellation failed")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/bookings/<int:booking_id>/reschedule_request', methods=['POST'])
@login_required
def api_reschedule_request(booking_id):
    try:
        data = request.get_json() or {}
        reason = str(data.get('reschedule_reason') or '').strip()
        new_slot_id = data.get('new_slot_id')

        if not reason:
            return jsonify({'success': False, 'error': 'Reschedule reason is required'}), 400
        if not new_slot_id:
            return jsonify({'success': False, 'error': 'New slot selection is required'}), 400

        conn = get_db()
        cur = conn.cursor()
        artist_id = session['artist_id']

        # Verify booking belongs to this artist
        cur.execute("""
            SELECT Booking_ID, Booking_Status
            FROM booking_table
            WHERE Booking_ID = %s AND Artist_ID = %s
        """, (booking_id, artist_id))
        row = cur.fetchone()
        if not row:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Booking not found'}), 404

        if str(row.get('Booking_Status') or '').lower() in ('cancelled', 'completed'):
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Cannot reschedule a cancelled or completed booking'}), 400

        # Verify the selected slot is Available
        cur.execute("""
            SELECT Slot_ID, Status
            FROM calendar_table
            WHERE Slot_ID = %s AND Artist_ID = %s AND Status = 'Available'
        """, (new_slot_id, artist_id))
        slot = cur.fetchone()
        if not slot:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Selected slot is not available'}), 400

        cur.execute("""
            UPDATE booking_table
            SET reschedule_status = 'requested',
                reschedule_reason = %s,
                reschedule_requested_at = NOW(),
                rescheduled_to_slot_id = %s
            WHERE Booking_ID = %s AND Artist_ID = %s
        """, (reason, new_slot_id, booking_id, artist_id))

        conn.commit()
        cur.close()
        conn.close()

        return jsonify({'success': True, 'message': 'Reschedule request submitted'})
    except Exception as e:
        logger.exception("Reschedule request failed")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/available_slots')
@login_required
def api_available_slots():
    """Get available slots for the logged-in artist (for reschedule modal)"""
    try:
        conn = get_db()
        cur = conn.cursor()
        artist_id = session['artist_id']

        cur.execute("""
            SELECT
                Slot_ID,
                Slot_Date,
                Start_Time,
                End_Time,
                Slot_type,
                price
            FROM calendar_table
            WHERE Artist_ID = %s
              AND Status = 'Available'
              AND CONCAT(Slot_Date, ' ', Start_Time) > NOW()
            ORDER BY Slot_Date ASC, Start_Time ASC
        """, (artist_id,))
        rows = cur.fetchall() or []

        slots = []
        for row in rows:
            slot_date = row.get('Slot_Date')
            if isinstance(slot_date, datetime):
                slot_date = slot_date.date()
            start_raw = row.get('Start_Time')
            end_raw = row.get('End_Time')
            if hasattr(start_raw, 'total_seconds'):
                total = int(start_raw.total_seconds())
                start_str = f"{total // 3600:02d}:{(total % 3600) // 60:02d}"
            else:
                start_str = str(start_raw or '')[:5]
            if hasattr(end_raw, 'total_seconds'):
                total = int(end_raw.total_seconds())
                end_str = f"{total // 3600:02d}:{(total % 3600) // 60:02d}"
            else:
                end_str = str(end_raw or '')[:5]

            slots.append({
                'slot_id': row.get('Slot_ID'),
                'slot_date': str(slot_date) if slot_date else '',
                'start_time': start_str,
                'end_time': end_str,
                'slot_type': str(row.get('Slot_type') or 'Performance'),
                'price': float(row.get('price') or 0)
            })

        cur.close()
        conn.close()
        return jsonify({'success': True, 'slots': slots})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# 15. FEEDBACK
@app.route('/api/feedback')
@login_required
def api_feedback():
    try:
        conn = get_db()
        cur = conn.cursor()
        artist_id = session['artist_id']

        cur.execute(
            """
            SELECT
                f.feedback_id,
                f.client_id,
                f.rating,
                f.comments,
                c.first_name AS first_name,
                c.last_name AS last_name
            FROM feedback_table f
            LEFT JOIN client_table c ON c.client_id = f.client_id
            WHERE f.artist_id = %s
            ORDER BY f.feedback_id DESC
            """,
            (artist_id,)
        )
        rows = cur.fetchall() or []

        feedback = []
        total_rating = 0.0

        for row in rows:
            rating = float(row.get('rating') or 0)
            total_rating += rating
            client_name = f"{row.get('first_name') or ''} {row.get('last_name') or ''}".strip() or 'Client'
            initials = ''.join([part[0] for part in client_name.split()[:2]]).upper() or 'C'

            feedback.append({
                'id': str(row.get('feedback_id')) if row.get('feedback_id') is not None else '',
                'client_id': row.get('client_id'),
                'client_name': client_name,
                'client_initials': initials,
                'rating': rating,
                'message': row.get('comments') or '',
                'timestamp': datetime.now().isoformat()
            })

        total_reviews = len(feedback)
        avg_rating = round((total_rating / total_reviews), 1) if total_reviews > 0 else 0.0

        cur.close()
        conn.close()

        return jsonify({
            'success': True,
            'feedback': feedback,
            'stats': {'rating': avg_rating, 'total_reviews': total_reviews}
        })
    except Exception as e:
        logger.exception("Feedback fetch failed")
        return jsonify({'success': False, 'error': str(e)})

# ========== DEMO DATA INSERTION ==========
def ensure_demo_artists():
    """Ensure demo artists exist in the database"""
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        
        # Ensure category table has data
        cur.execute("SELECT COUNT(*) AS total FROM category_table")
        if int((cur.fetchone() or {}).get('total') or 0) == 0:
            cur.executemany(
                """
                INSERT INTO category_table (category_id, category_name)
                VALUES (%s, %s)
                """,
                [(1, 'Singer'), (2, 'Dancer'), (3, 'Photographer')]
            )

        demo_artists = [
            {
                'first_name': 'Rohan',
                'last_name': 'Sharma',
                'username': 'rohan@gmail.com',
                'email': 'rohan@gmail.com',
                'password': bcrypt.hashpw('Test@1234'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8'),
                'gender': 'Male',
                'dob': '1995-05-15',
                'phone_number': '9876543210',
                'state_id': 11,  # Karnataka
                'city_id': 38,   # Bengaluru (auto-increment id from schema)
                'category_id': 1,
                'portfolio_path': 'portfolio1.pdf',
                'verification_status': 'approved',
                'is_enabled': 1,
                'experience_years': 6,
                'price_per_hour': 1200,
                'rating': 4.6
            },
            {
                'first_name': 'Priya',
                'last_name': 'Patel',
                'username': 'priya@gmail.com',
                'email': 'priya@gmail.com',
                'password': bcrypt.hashpw('Test@1234'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8'),
                'gender': 'Female',
                'dob': '1998-08-22',
                'phone_number': '9876543211',
                'state_id': 7,   # Gujarat
                'city_id': 26,   # Ahmedabad (auto-increment id from schema)
                'category_id': 2,
                'portfolio_path': 'portfolio2.pdf',
                'verification_status': 'approved',
                'is_enabled': 1,
                'experience_years': 4,
                'price_per_hour': 1500,
                'rating': 4.8
            },
            {
                'first_name': 'Amit',
                'last_name': 'Verma',
                'username': 'amit@gmail.com',
                'email': 'amit@gmail.com',
                'password': bcrypt.hashpw('Test@1234'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8'),
                'gender': 'Male',
                'dob': '1993-12-10',
                'phone_number': '9876543212',
                'state_id': 14,  # Maharashtra
                'city_id': 48,   # Pune (auto-increment id from schema)
                'category_id': 3,
                'portfolio_path': 'portfolio3.pdf',
                'verification_status': 'approved',
                'is_enabled': 1,
                'experience_years': 8,
                'price_per_hour': 1800,
                'rating': 4.7
            }
        ]

        for artist in demo_artists:
            # Check if artist exists using correct PascalCase column names
            cur.execute(
                """
                SELECT artist_id, password, verification_status, is_enabled
                FROM artist_table
                WHERE Username = %s
                LIMIT 1
                """,
                (artist['username'],)
            )
            existing = cur.fetchone()

            if not existing:
                # Insert new artist using correct PascalCase column names per schema
                cur.execute("""
                    INSERT INTO artist_table 
                    (first_name, last_name, username, email, password, gender, dob, phone_number,
                     state_id, city_id, category_id, portfolio_path, verification_status, is_enabled,
                     experience_years, price_per_hour, rating)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    artist['first_name'], artist['last_name'], artist['username'],
                    artist['email'], artist['password'], artist['gender'], artist['dob'], artist['phone_number'],
                    artist['state_id'], artist['city_id'], artist['category_id'],
                    artist['portfolio_path'], artist['verification_status'], artist['is_enabled'],
                    artist['experience_years'], artist['price_per_hour'], artist['rating']
                ))
            else:
                # Update existing artist if needed
                current_password = str(existing.get('Password') or '')
                should_reset_password = False
                
                if current_password.startswith('$2b$') or current_password.startswith('$2a$') or current_password.startswith('$2y$'):
                    try:
                        if not bcrypt.checkpw('Test@1234'.encode('utf-8'), current_password.encode('utf-8')):
                            should_reset_password = True
                    except Exception:
                        should_reset_password = True
                else:
                    should_reset_password = True

                if should_reset_password:
                    cur.execute(
                        "UPDATE artist_table SET password = %s WHERE artist_id = %s",
                        (artist['password'], existing['artist_id'])
                    )

                # Update verification status and other fields using correct PascalCase columns
                cur.execute(
                    """
                    UPDATE artist_table
                    SET verification_status = %s,
                        is_enabled = %s,
                        Email = %s,
                        category_id = %s,
                        experience_years = %s,
                        price_per_hour = %s,
                        rating = %s
                    WHERE artist_id = %s
                    """,
                    ('approved', 1, artist['email'], artist['category_id'],
                     artist['experience_years'], artist['price_per_hour'],
                     artist['rating'], existing['artist_id'])
                )

        conn.commit()
        print("Demo artists setup complete")
        
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"Error setting up demo artists: {e}")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

'''def ensure_demo_artists():
    """Ensure demo artists exist in the database"""
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS total FROM category_table")
        if int((cur.fetchone() or {}).get('total') or 0) == 0:
            cur.executemany(
                """
                INSERT INTO category_table (category_id, category_name)
                VALUES (%s, %s)
                """,
                [(1, 'Singer'), (2, 'Dancer'), (3, 'Photographer')]
            )

        demo_artists = [
            {
                'first_name': 'Rohan',
                'last_name': 'Sharma',
                'Username': 'rohan@gmail.com',
                'Email': 'rohan@gmail.com',
                'Password': bcrypt.hashpw('Test@1234'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8'),
                'Gender': 'Male',
                'Dob': '1995-05-15',
                'phone_number': '9876543210',
                'state_id': 11,  # Karnataka
                'city_id': 149,  # Bengaluru
                'category_id': 1,
                'Category': 'Singer',
                'portfolio_path': 'portfolio1.pdf',
                'Verification_status': 'approved',
                'Is_enabled': 1,
                'Pincode': '560001',
                'profile_pic': '',
                'portfolio_files': json.dumps(['/static/uploads/portfolio/rohan_demo.jpg']),
                'working_start_time': '09:00',
                'working_end_time': '18:00',
                'bank_name': 'HDFC Bank',
                'bank_account_number': '123456789012',
                'account_holder_name': 'Rohan Sharma',
                'ifsc_code': 'HDFC0001234',
                'upi_id': 'rohan@upi',
                'experience_years': 6,
                'price_per_hour': 1200,
                'rating': 4.6
            },
            {
                'first_name': 'Priya',
                'last_name': 'Patel',
                'Username': 'priya@gmail.com',
                'Email': 'priya@gmail.com',
                'Password': bcrypt.hashpw('Test@1234'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8'),
                'Gender': 'Female',
                'Dob': '1998-08-22',
                'phone_number': '9876543211',
                'state_id': 7,   # Gujarat
                'city_id': 132,  # Ahmedabad
                'category_id': 2,
                'Category': 'Dancer',
                'portfolio_path': 'portfolio2.pdf',
                'Verification_status': 'approved',
                'Is_enabled': 1,
                'Pincode': '380001',
                'profile_pic': '',
                'portfolio_files': json.dumps(['/static/uploads/portfolio/priya_demo.jpg']),
                'working_start_time': '10:00',
                'working_end_time': '19:00',
                'bank_name': 'ICICI Bank',
                'bank_account_number': '987654321000',
                'account_holder_name': 'Priya Patel',
                'ifsc_code': 'ICIC0009876',
                'upi_id': 'priya@upi',
                'experience_years': 4,
                'price_per_hour': 1500,
                'rating': 4.8
            },
            {
                'first_name': 'Amit',
                'last_name': 'Verma',
                'Username': 'amit@gmail.com',
                'Email': 'amit@gmail.com',
                'Password': bcrypt.hashpw('Test@1234'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8'),
                'Gender': 'Male',
                'Dob': '1993-12-10',
                'phone_number': '9876543212',
                'state_id': 14,  # Maharashtra
                'city_id': 216,  # Pune
                'category_id': 3,
                'Category': 'Photographer',
                'portfolio_path': 'portfolio3.pdf',
                'Verification_status': 'approved',
                'Is_enabled': 1,
                'Pincode': '411001',
                'profile_pic': '',
                'portfolio_files': json.dumps(['/static/uploads/portfolio/amit_demo.jpg']),
                'working_start_time': '08:00',
                'working_end_time': '17:00',
                'bank_name': 'SBI',
                'bank_account_number': '456789123456',
                'account_holder_name': 'Amit Verma',
                'ifsc_code': 'SBIN0001111',
                'upi_id': 'amit@upi',
                'experience_years': 8,
                'price_per_hour': 1800,
                'rating': 4.7
            }
        ]

        for artist in demo_artists:
            cur.execute(
                """
                SELECT artist_id, password, verification_status, is_enabled
                FROM artist_table
                WHERE Username = %s
                LIMIT 1
                """,
                (artist['username'],)
            )
            existing = cur.fetchone()

            if not existing:
                cur.execute("""
                    INSERT INTO artist_table 
                    (first_name, last_name, username, email, password, gender, dob, phone_number,
                     state_id, city_id, category_id, portfolio_path, verification_status, is_enabled,
                     profile_pic, portfolio_files, working_start_time, working_end_time,
                     experience_years, price_per_hour, rating)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    artist['first_name'], artist['last_name'], artist['username'],
                    artist['email'], artist['password'], artist['gender'], artist['dob'], artist['phone_number'],
                    artist['state_id'], artist['city_id'], artist['category_id'],
                    artist['portfolio_path'], artist['verification_status'], artist['is_enabled'],
                    artist['profile_pic'], artist['portfolio_files'], artist['working_start_time'], artist['working_end_time'],
                    artist['experience_years'], artist['price_per_hour'], artist['rating']
                ))

            current_password = str(existing.get('Password') or '')
            should_reset_password = False
            if current_password.startswith('$2b$') or current_password.startswith('$2a$') or current_password.startswith('$2y$'):
                try:
                    # Ensure known demo password works for seeded accounts.
                    if not bcrypt.checkpw('Test@1234'.encode('utf-8'), current_password.encode('utf-8')):
                        should_reset_password = True
                except Exception:
                    should_reset_password = True
            else:
                should_reset_password = True

            if should_reset_password:
                repaired_hash = bcrypt.hashpw('artist123'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                cur.execute(
                    "UPDATE artist_table SET password = %s WHERE artist_id = %s",
                    (repaired_hash, existing['artist_id'])
                )

            verification_status = str(existing.get('Verification_status') or '').strip().lower()
            try:
                is_enabled = int(existing.get('Is_enabled') or 0)
            except (TypeError, ValueError):
                is_enabled = 0
            if verification_status != 'approved' or is_enabled != 1:
                cur.execute(
                    """
                    UPDATE artist_table
                    SET Verification_status = %s,
                        Is_enabled = %s,
                        email = %s,
                        category_id = %s,
                        Category = %s,
                        Pincode = %s,
                        portfolio_files = %s,
                        working_start_time = %s,
                        working_end_time = %s,
                        bank_name = %s,
                        bank_account_number = %s,
                        account_holder_name = %s,
                        ifsc_code = %s,
                        upi_id = %s,
                        experience_years = %s,
                        price_per_hour = %s,
                        rating = %s
                    WHERE artist_id = %s
                    """,
                    ('approved', 1, artist['email'], artist['category_id'], artist['Category'], artist['Pincode'],
                     artist['portfolio_files'], artist['working_start_time'], artist['working_end_time'],
                     artist['bank_name'], artist['bank_account_number'], artist['account_holder_name'],
                     artist['ifsc_code'], artist['upi_id'], artist['experience_years'], artist['price_per_hour'],
                     artist['rating'], existing['artist_id'])
                )
            else:
                cur.execute(
                    """
                    UPDATE artist_table
                    SET email = %s,
                        category_id = %s,
                        Category = %s,
                        Pincode = %s,
                        portfolio_files = %s,
                        working_start_time = %s,
                        working_end_time = %s,
                        bank_name = %s,
                        bank_account_number = %s,
                        account_holder_name = %s,
                        ifsc_code = %s,
                        upi_id = %s,
                        experience_years = %s,
                        price_per_hour = %s,
                        rating = %s
                    WHERE artist_id = %s
                    """,
                    (artist['email'], artist['category_id'], artist['Category'], artist['Pincode'],
                     artist['portfolio_files'], artist['working_start_time'], artist['working_end_time'],
                     artist['bank_name'], artist['bank_account_number'], artist['account_holder_name'],
                     artist['ifsc_code'], artist['upi_id'], artist['experience_years'], artist['price_per_hour'],
                     artist['rating'], existing['artist_id'])
                )

        conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"Error setting up demo artists: {e}")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()'''


# ========== RUN APP ==========
if __name__ == '__main__':
    try:
        print("CREOVIBE STARTING...")

        os.makedirs('templates', exist_ok=True)
        os.makedirs('static', exist_ok=True)

        print("Calling ensure_demo_artists()...")
        ensure_demo_artists()
        print("Demo artists done.")

        print("Starting Flask server...")
        app.run(debug=True, port=5000)

    except Exception as e:
        print("FATAL ERROR:")
        print(e)