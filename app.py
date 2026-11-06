import os
from datetime import date
from decimal import Decimal
from functools import wraps
from flask import (Flask, flash, redirect, render_template, request,
                   url_for, abort, session, jsonify)
from mysql.connector import connect, Error
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'change-this-development-secret')

DB = dict(
    host=os.getenv('DB_HOST', 'localhost'),
    port=int(os.getenv('DB_PORT', '3306')),
    user=os.getenv('DB_USER', 'root'),
    password=os.getenv('DB_PASSWORD', ''),
    database=os.getenv('DB_NAME', 'e_waste')
)

# ---------------------------------------------------------------------------
# Metadata allowlist (admin CRUD – preserved exactly as before, now with
# Password column added to COLLECTION_AGENTS)
# ---------------------------------------------------------------------------
TABLES = {
    'USERS': {
        'title': 'Users', 'pk': 'User_ID',
        'cols': [
            ('User_ID',   'User ID',     'number',   False, True,  None),
            ('Name',      'Full name',   'text',     True,  False, None),
            ('Email',     'Email',       'email',    True,  False, None),
            ('Phone',     'Phone',       'text',     True,  False, None),
            ('Address',   'Address',     'textarea', False, False, None),
            ('Password',  'Password',    'password', True,  False, None),
            ('User_Role', 'Role',        'select',   True,  False,
             [('USER', 'User'), ('ADMIN', 'Admin')]),
        ],
        'list':   ['User_ID', 'Name', 'Email', 'Phone', 'User_Role'],
        'search': ['Name', 'Email', 'Phone'],
    },
    'E_WASTE_CATEGORIES': {
        'title': 'E-Waste Categories', 'pk': 'Category_ID',
        'cols': [
            ('Category_ID',    'Category ID',    'number',  False, True,  None),
            ('Category_Name',  'Category name',  'text',    True,  False, None),
            ('Description',    'Description',    'textarea',False, False, None),
            ('Recycling_Value','Recycling value','decimal', False, False, None),
        ],
        'list':   ['Category_ID', 'Category_Name', 'Description', 'Recycling_Value'],
        'search': ['Category_Name', 'Description'],
    },
    'PICKUP_REQUESTS': {
        'title': 'Pickup Requests', 'pk': 'Request_ID',
        'cols': [
            ('Request_ID',     'Request ID',     'number',   False, True,  None),
            ('User_ID',        'User',           'fk',       True,  False,
             ('USERS', 'User_ID', 'Name')),
            ('Request_Date',   'Request date',   'date',     True,  False, None),
            ('Pickup_Address', 'Pickup address', 'textarea', True,  False, None),
            ('Status',         'Status',         'select',   True,  False,
             [('Pending','Pending'),('Assigned','Assigned'),
              ('In Progress','In Progress'),('Completed','Completed'),
              ('Cancelled','Cancelled')]),
        ],
        'list':   ['Request_ID', 'User_ID', 'Request_Date', 'Pickup_Address', 'Status'],
        'search': ['Pickup_Address', 'Status'],
    },
    'PICKUP_REQUEST_ITEMS': {
        'title': 'Pickup Request Items', 'pk': 'Request_Item_ID',
        'cols': [
            ('Request_Item_ID','Request item ID','number',False,True, None),
            ('Request_ID',     'Pickup request', 'fk',    True, False,
             ('PICKUP_REQUESTS','Request_ID','Request_ID')),
            ('Category_ID',    'Category',       'fk',    True, False,
             ('E_WASTE_CATEGORIES','Category_ID','Category_Name')),
            ('Quantity',       'Quantity',       'number',True, False, None),
        ],
        'list':   ['Request_Item_ID', 'Request_ID', 'Category_ID', 'Quantity'],
        'search': [],
    },
    'COLLECTION_AGENTS': {
        'title': 'Collection Agents', 'pk': 'Agent_ID',
        'cols': [
            ('Agent_ID',  'Agent ID',    'number',   False, True,  None),
            ('Agent_Name','Agent name',  'text',     True,  False, None),
            ('Phone',     'Phone',       'text',     True,  False, None),
            ('Email',     'Email',       'email',    False, False, None),
            ('Password',  'Password',    'password', False, False, None),
            ('Status',    'Status',      'select',   True,  False,
             [('Available','Available'),('Busy','Busy'),('Inactive','Inactive')]),
        ],
        'list':   ['Agent_ID', 'Agent_Name', 'Phone', 'Email', 'Status'],
        'search': ['Agent_Name', 'Phone', 'Email'],
    },
    'PICKUP_ASSIGNMENTS': {
        'title': 'Pickup Assignments', 'pk': 'Assignment_ID',
        'cols': [
            ('Assignment_ID', 'Assignment ID', 'number', False, True,  None),
            ('Request_ID',    'Pickup request','fk',     True,  False,
             ('PICKUP_REQUESTS','Request_ID','Request_ID')),
            ('Agent_ID',      'Collection agent','fk',  True,  False,
             ('COLLECTION_AGENTS','Agent_ID','Agent_Name')),
            ('Center_ID',     'Recycling center','fk',  True,  False,
             ('RECYCLING_CENTERS','Center_ID','Center_Name')),
            ('Assignment_Date','Assignment date','date', True,  False, None),
            ('Status',        'Status',         'select',True,  False,
             [('Assigned','Assigned'),('In Progress','In Progress'),
              ('Completed','Completed'),('Cancelled','Cancelled')]),
        ],
        'list':   ['Assignment_ID','Request_ID','Agent_ID','Center_ID','Assignment_Date','Status'],
        'search': ['Status'],
    },
    'RECYCLING_CENTERS': {
        'title': 'Recycling Centers', 'pk': 'Center_ID',
        'cols': [
            ('Center_ID',  'Center ID',  'number',   False, True,  None),
            ('Center_Name','Center name','text',     True,  False, None),
            ('Address',    'Address',    'textarea', True,  False, None),
            ('Phone',      'Phone',      'text',     False, False, None),
            ('Capacity',   'Capacity',   'number',   False, False, None),
        ],
        'list':   ['Center_ID','Center_Name','Address','Phone','Capacity'],
        'search': ['Center_Name','Address','Phone'],
    },
    'PAYMENTS': {
        'title': 'Payments', 'pk': 'Payment_ID',
        'cols': [
            ('Payment_ID',     'Payment ID',    'number',  False, True,  None),
            ('Request_ID',     'Pickup request','fk',      True,  False,
             ('PICKUP_REQUESTS','Request_ID','Request_ID')),
            ('Amount',         'Amount',        'decimal', True,  False, None),
            ('Payment_Date',   'Payment date',  'date',    False, False, None),
            ('Payment_Method', 'Payment method','select',  False, False,
             [('UPI','UPI'),('Cash','Cash'),('Bank Transfer','Bank Transfer'),
              ('Card','Card'),('Other','Other')]),
            ('Payment_Status', 'Payment status','select',  True,  False,
             [('Pending','Pending'),('Completed','Completed'),
              ('Failed','Failed'),('Refunded','Refunded')]),
        ],
        'list':   ['Payment_ID','Request_ID','Amount','Payment_Date','Payment_Method','Payment_Status'],
        'search': ['Payment_Method','Payment_Status'],
    },
}

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
def db():
    return connect(**DB)

def config(name):
    if name not in TABLES:
        abort(404)
    return TABLES[name]

def fields_for(conn, table):
    fields = []
    for name, label, kind, required, readonly, extra in table['cols']:
        options = []
        if kind == 'fk':
            t, k, l = extra
            cur = conn.cursor()
            cur.execute(f'SELECT `{k}`, `{l}` FROM `{t}` ORDER BY `{k}`')
            options = [(str(r[0]), f'{r[0]} — {r[1]}') for r in cur.fetchall()]
            cur.close()
        elif kind == 'select':
            options = extra or []
        fields.append(dict(name=name, label=label, kind=kind,
                           required=required, readonly=readonly, options=options))
    return fields

def parse(field, raw, editing=False):
    if field['kind'] == 'password':
        if raw == '':
            if editing:
                return None
            raise ValueError('Password is required.')
        return generate_password_hash(raw)
    if raw == '':
        if field['required']:
            raise ValueError(f"{field['label']} is required.")
        return None
    kind = field['kind']
    if kind == 'number':
        return int(raw)
    if kind == 'decimal':
        return Decimal(raw)
    if kind == 'date':
        date.fromisoformat(raw)
        return raw
    if kind == 'fk':
        return int(raw)
    if kind == 'select' and raw not in {str(v) for v, _ in field['options']}:
        raise ValueError(f"Invalid {field['label']}.")
    return raw

def get_record(conn, name, rid):
    cur = conn.cursor(dictionary=True)
    cur.execute(
        f"SELECT * FROM `{name}` WHERE `{TABLES[name]['pk']}`=%s", (rid,))
    row = cur.fetchone()
    cur.close()
    return row

# ---------------------------------------------------------------------------
# Template filter
# ---------------------------------------------------------------------------
@app.template_filter('pretty')
def pretty(value):
    return str(value).replace('_', ' ')

# ---------------------------------------------------------------------------
# Auth decorators
# ---------------------------------------------------------------------------
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to continue.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please log in to continue.', 'warning')
                return redirect(url_for('login'))
            if session.get('role') not in roles:
                flash('Access denied. You do not have permission to view that page.', 'danger')
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated
    return decorator

# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------
@app.route('/')
def index():
    if 'user_id' in session:
        role = session.get('role')
        if role == 'ADMIN':
            return redirect(url_for('admin_dashboard'))
        elif role == 'COLLECTION_AGENT':
            return redirect(url_for('agent_dashboard'))
        else:
            return redirect(url_for('user_dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        if not email or not password:
            flash('Email and password are required.', 'danger')
            return render_template('auth/login.html')

        conn = None
        try:
            conn = db()
            cur = conn.cursor(dictionary=True)

            # Check USERS table first
            cur.execute(
                'SELECT User_ID, Name, Email, Password, User_Role FROM USERS WHERE Email=%s',
                (email,))
            user = cur.fetchone()

            if user and user['Password'] and check_password_hash(user['Password'], password):
                session.clear()
                session['user_id'] = user['User_ID']
                session['name'] = user['Name']
                session['email'] = user['Email']
                session['role'] = user['User_Role']  # 'USER' or 'ADMIN'
                cur.close()

                if user['User_Role'] == 'ADMIN':
                    flash(f"Welcome back, {user['Name']}! You are logged in as Admin.", 'success')
                    return redirect(url_for('admin_dashboard'))
                else:
                    flash(f"Welcome back, {user['Name']}!", 'success')
                    return redirect(url_for('user_dashboard'))

            # Check COLLECTION_AGENTS table
            cur.execute(
                'SELECT Agent_ID, Agent_Name, Email, Password FROM COLLECTION_AGENTS WHERE Email=%s',
                (email,))
            agent = cur.fetchone()
            cur.close()

            if agent and agent['Password'] and check_password_hash(agent['Password'], password):
                session.clear()
                session['user_id'] = agent['Agent_ID']
                session['name'] = agent['Agent_Name']
                session['email'] = agent['Email']
                session['role'] = 'COLLECTION_AGENT'
                flash(f"Welcome back, {agent['Agent_Name']}!", 'success')
                return redirect(url_for('agent_dashboard'))

            flash('Invalid email or password. Please try again.', 'danger')

        except Error as e:
            flash(f'Database error: {e}', 'danger')
        finally:
            if conn and conn.is_connected():
                conn.close()

    return render_template('auth/login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        name      = request.form.get('name', '').strip()
        email     = request.form.get('email', '').strip()
        phone     = request.form.get('phone', '').strip()
        address   = request.form.get('address', '').strip()
        password  = request.form.get('password', '')
        confirm   = request.form.get('confirm_password', '')
        role      = request.form.get('account_type', '')  # 'USER' or 'COLLECTION_AGENT'

        errors = []
        if not name:        errors.append('Full name is required.')
        if not email:       errors.append('Email is required.')
        if not phone:       errors.append('Phone number is required.')
        if not password:    errors.append('Password is required.')
        if len(password) < 6: errors.append('Password must be at least 6 characters.')
        if password != confirm: errors.append('Passwords do not match.')
        if role not in ('USER', 'COLLECTION_AGENT'):
            errors.append('Please select a valid account type.')

        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('auth/register.html',
                                   form_data=request.form)

        conn = None
        try:
            conn = db()
            cur = conn.cursor(dictionary=True)

            if role == 'USER':
                # Check email uniqueness in USERS
                cur.execute('SELECT User_ID FROM USERS WHERE Email=%s', (email,))
                if cur.fetchone():
                    flash('An account with this email already exists.', 'danger')
                    cur.close()
                    return render_template('auth/register.html', form_data=request.form)
                # Check phone uniqueness in USERS
                cur.execute('SELECT User_ID FROM USERS WHERE Phone=%s', (phone,))
                if cur.fetchone():
                    flash('An account with this phone number already exists.', 'danger')
                    cur.close()
                    return render_template('auth/register.html', form_data=request.form)

                hashed = generate_password_hash(password)
                cur.execute(
                    'INSERT INTO USERS (Name, Email, Phone, Address, Password, User_Role) '
                    'VALUES (%s, %s, %s, %s, %s, %s)',
                    (name, email, phone, address or None, hashed, 'USER'))
                conn.commit()
                cur.close()
                flash('Registration successful! Please log in.', 'success')
                return redirect(url_for('login'))

            else:  # COLLECTION_AGENT
                # Check email uniqueness in COLLECTION_AGENTS
                cur.execute('SELECT Agent_ID FROM COLLECTION_AGENTS WHERE Email=%s', (email,))
                if cur.fetchone():
                    flash('A collection agent account with this email already exists.', 'danger')
                    cur.close()
                    return render_template('auth/register.html', form_data=request.form)
                # Check phone uniqueness in COLLECTION_AGENTS
                cur.execute('SELECT Agent_ID FROM COLLECTION_AGENTS WHERE Phone=%s', (phone,))
                if cur.fetchone():
                    flash('A collection agent account with this phone number already exists.', 'danger')
                    cur.close()
                    return render_template('auth/register.html', form_data=request.form)

                hashed = generate_password_hash(password)
                cur.execute(
                    'INSERT INTO COLLECTION_AGENTS (Agent_Name, Phone, Email, Password, Status) '
                    'VALUES (%s, %s, %s, %s, %s)',
                    (name, phone, email, hashed, 'Available'))
                conn.commit()
                cur.close()
                flash('Collection agent account created! Please log in.', 'success')
                return redirect(url_for('login'))

        except Error as e:
            if conn and conn.is_connected():
                conn.rollback()
            flash(f'Registration failed: {e}', 'danger')
        finally:
            if conn and conn.is_connected():
                conn.close()

    return render_template('auth/register.html', form_data={})

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('login'))

# ---------------------------------------------------------------------------
# Admin routes (preserved + protected)
# ---------------------------------------------------------------------------
@app.route('/admin')
@role_required('ADMIN')
def admin_dashboard():
    conn = None
    try:
        conn = db()
        cur = conn.cursor()
        counts = {}
        for name in TABLES:
            cur.execute(f'SELECT COUNT(*) FROM `{name}`')
            counts[name] = cur.fetchone()[0]
        cur.execute('''
            SELECT P.Request_ID, U.Name, P.Request_Date, P.Pickup_Address, P.Status
            FROM PICKUP_REQUESTS P
            JOIN USERS U ON P.User_ID = U.User_ID
            ORDER BY P.Request_ID DESC
            LIMIT 6
        ''')
        recent = cur.fetchall()
        cur.close()
        return render_template('admin/dashboard.html', tables=TABLES,
                               counts=counts, recent=recent)
    except Error as e:
        flash(f'MySQL error: {e}', 'danger')
        return render_template('admin/dashboard.html', tables=TABLES,
                               counts={}, recent=[])
    finally:
        if conn and conn.is_connected():
            conn.close()

@app.route('/admin/tables/<name>')
@role_required('ADMIN')
def listing(name):
    t = config(name)
    conn = None
    try:
        conn = db()
        cur = conn.cursor(dictionary=True)
        cols = t['list']
        sql = f"SELECT {', '.join(f'`{c}`' for c in cols)} FROM `{name}`"
        q = request.args.get('q', '').strip()
        params = []
        if q and t['search']:
            sql += ' WHERE ' + ' OR '.join(
                f"CAST(`{c}` AS CHAR) LIKE %s" for c in t['search'])
            params = [f'%{q}%' for _ in t['search']]
        sql += f" ORDER BY `{t['pk']}` DESC LIMIT 500"
        cur.execute(sql, tuple(params))
        records = cur.fetchall()
        cur.close()
        return render_template('admin/listing.html', name=name, table=t,
                               records=records, q=q)
    except Error as e:
        flash(f'Could not load records: {e}', 'danger')
        return render_template('admin/listing.html', name=name, table=t,
                               records=[], q='')
    finally:
        if conn and conn.is_connected():
            conn.close()

@app.route('/admin/tables/<name>/new', methods=['GET', 'POST'])
@role_required('ADMIN')
def create(name):
    t = config(name)
    conn = None
    try:
        conn = db()
        fields = fields_for(conn, t)
        if request.method == 'POST':
            values = {}
            for f in fields:
                if not f['readonly']:
                    values[f['name']] = parse(f, request.form.get(f['name'], ''))
            cols = list(values)
            sql = (f"INSERT INTO `{name}` "
                   f"({', '.join(f'`{c}`' for c in cols)}) "
                   f"VALUES ({', '.join(['%s'] * len(cols))})")
            cur = conn.cursor()
            cur.execute(sql, tuple(values[c] for c in cols))
            conn.commit()
            cur.close()
            flash(f"{t['title']} record added successfully.", 'success')
            return redirect(url_for('listing', name=name))
        return render_template('admin/form.html', name=name, table=t,
                               fields=fields, record=None, mode='Add')
    except ValueError as e:
        flash(str(e), 'warning')
        return redirect(url_for('create', name=name))
    except Error as e:
        if conn and conn.is_connected():
            conn.rollback()
        flash(f'Could not add record: {e}', 'danger')
        return redirect(url_for('create', name=name))
    finally:
        if conn and conn.is_connected():
            conn.close()

@app.route('/admin/tables/<name>/<int:rid>/edit', methods=['GET', 'POST'])
@role_required('ADMIN')
def edit(name, rid):
    t = config(name)
    conn = None
    try:
        conn = db()
        record = get_record(conn, name, rid)
        if not record:
            abort(404)
        fields = fields_for(conn, t)
        if request.method == 'POST':
            values = {}
            for f in fields:
                if f['readonly']:
                    continue
                raw = request.form.get(f['name'], '')
                if f['kind'] == 'password' and raw == '':
                    continue
                values[f['name']] = parse(f, raw, editing=True)
            if values:
                cols = list(values)
                sql = (f"UPDATE `{name}` SET "
                       f"{', '.join(f'`{c}`=%s' for c in cols)} "
                       f"WHERE `{t['pk']}`=%s")
                cur = conn.cursor()
                cur.execute(sql, tuple(values[c] for c in cols) + (rid,))
                conn.commit()
                cur.close()
            flash(f"{t['title']} record updated successfully.", 'success')
            return redirect(url_for('listing', name=name))
        return render_template('admin/form.html', name=name, table=t,
                               fields=fields, record=record, mode='Edit')
    except ValueError as e:
        flash(str(e), 'warning')
        return redirect(url_for('edit', name=name, rid=rid))
    except Error as e:
        if conn and conn.is_connected():
            conn.rollback()
        flash(f'Could not update record: {e}', 'danger')
        return redirect(url_for('edit', name=name, rid=rid))
    finally:
        if conn and conn.is_connected():
            conn.close()

@app.route('/admin/tables/<name>/<int:rid>/delete', methods=['POST'])
@role_required('ADMIN')
def delete(name, rid):
    t = config(name)
    conn = None
    try:
        conn = db()
        cur = conn.cursor()
        cur.execute(
            f"DELETE FROM `{name}` WHERE `{t['pk']}`=%s", (rid,))
        conn.commit()
        affected = cur.rowcount
        cur.close()
        flash('Record deleted.' if affected else 'No matching record found.',
              'success' if affected else 'warning')
    except Error as e:
        if conn and conn.is_connected():
            conn.rollback()
        flash(f'Could not delete record. It may be referenced by another table. Details: {e}', 'danger')
    finally:
        if conn and conn.is_connected():
            conn.close()
    return redirect(url_for('listing', name=name))

# ---------------------------------------------------------------------------
# User routes
# ---------------------------------------------------------------------------
@app.route('/user/dashboard')
@role_required('USER')
def user_dashboard():
    uid = session['user_id']
    conn = None
    try:
        conn = db()
        cur = conn.cursor()

        cur.execute('SELECT COUNT(*) FROM PICKUP_REQUESTS WHERE User_ID=%s', (uid,))
        total = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM PICKUP_REQUESTS WHERE User_ID=%s AND Status='Pending'", (uid,))
        pending = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM PICKUP_REQUESTS WHERE User_ID=%s AND Status='Completed'", (uid,))
        completed = cur.fetchone()[0]

        cur.execute('''
            SELECT Request_ID, Request_Date, Pickup_Address, Status
            FROM PICKUP_REQUESTS WHERE User_ID=%s
            ORDER BY Request_ID DESC LIMIT 5
        ''', (uid,))
        recent = cur.fetchall()
        cur.close()

        return render_template('user/dashboard.html',
                               total=total, pending=pending,
                               completed=completed, recent=recent)
    except Error as e:
        flash(f'Database error: {e}', 'danger')
        return render_template('user/dashboard.html',
                               total=0, pending=0, completed=0, recent=[])
    finally:
        if conn and conn.is_connected():
            conn.close()

@app.route('/user/profile', methods=['GET', 'POST'])
@role_required('USER')
def user_profile():
    uid = session['user_id']
    conn = None
    try:
        conn = db()
        cur = conn.cursor(dictionary=True)
        if request.method == 'POST':
            name    = request.form.get('name', '').strip()
            phone   = request.form.get('phone', '').strip()
            address = request.form.get('address', '').strip()
            password= request.form.get('password', '')
            confirm = request.form.get('confirm_password', '')

            if not name:
                flash('Full name is required.', 'danger')
                cur.execute('SELECT * FROM USERS WHERE User_ID=%s', (uid,))
                user = cur.fetchone()
                return render_template('user/profile.html', user=user)

            if password:
                if len(password) < 6:
                    flash('Password must be at least 6 characters.', 'danger')
                    cur.execute('SELECT * FROM USERS WHERE User_ID=%s', (uid,))
                    user = cur.fetchone()
                    return render_template('user/profile.html', user=user)
                if password != confirm:
                    flash('Passwords do not match.', 'danger')
                    cur.execute('SELECT * FROM USERS WHERE User_ID=%s', (uid,))
                    user = cur.fetchone()
                    return render_template('user/profile.html', user=user)
                hashed = generate_password_hash(password)
                cur.execute(
                    'UPDATE USERS SET Name=%s, Phone=%s, Address=%s, Password=%s WHERE User_ID=%s',
                    (name, phone, address or None, hashed, uid))
            else:
                cur.execute(
                    'UPDATE USERS SET Name=%s, Phone=%s, Address=%s WHERE User_ID=%s',
                    (name, phone, address or None, uid))

            conn.commit()
            session['name'] = name
            flash('Profile updated successfully.', 'success')
            return redirect(url_for('user_profile'))

        cur.execute('SELECT * FROM USERS WHERE User_ID=%s', (uid,))
        user = cur.fetchone()
        cur.close()
        return render_template('user/profile.html', user=user)
    except Error as e:
        flash(f'Database error: {e}', 'danger')
        return render_template('user/profile.html', user={})
    finally:
        if conn and conn.is_connected():
            conn.close()

@app.route('/user/categories')
@role_required('USER')
def user_categories():
    conn = None
    try:
        conn = db()
        cur = conn.cursor(dictionary=True)
        cur.execute('SELECT * FROM E_WASTE_CATEGORIES ORDER BY Category_ID')
        categories = cur.fetchall()
        cur.close()
        return render_template('user/categories.html', categories=categories)
    except Error as e:
        flash(f'Database error: {e}', 'danger')
        return render_template('user/categories.html', categories=[])
    finally:
        if conn and conn.is_connected():
            conn.close()

@app.route('/user/request-pickup', methods=['GET', 'POST'])
@role_required('USER')
def user_request_pickup():
    uid = session['user_id']
    conn = None
    try:
        conn = db()
        cur = conn.cursor(dictionary=True)
        cur.execute('SELECT * FROM E_WASTE_CATEGORIES ORDER BY Category_Name')
        categories = cur.fetchall()

        if request.method == 'POST':
            pickup_address = request.form.get('pickup_address', '').strip()
            if not pickup_address:
                flash('Pickup address is required.', 'danger')
                return render_template('user/request_pickup.html', categories=categories)

            selected_cats = request.form.getlist('category_ids')
            if not selected_cats:
                flash('Please select at least one e-waste category.', 'danger')
                return render_template('user/request_pickup.html', categories=categories)

            items = []
            for cat_id in selected_cats:
                qty_raw = request.form.get(f'quantity_{cat_id}', '').strip()
                if not qty_raw or not qty_raw.isdigit() or int(qty_raw) <= 0:
                    flash(f'Please enter a valid quantity for all selected categories.', 'danger')
                    return render_template('user/request_pickup.html', categories=categories)
                items.append((int(cat_id), int(qty_raw)))

            today = date.today().isoformat()
            cur2 = conn.cursor()
            cur2.execute(
                'INSERT INTO PICKUP_REQUESTS (User_ID, Request_Date, Pickup_Address, Status) '
                'VALUES (%s, %s, %s, %s)',
                (uid, today, pickup_address, 'Pending'))
            request_id = cur2.lastrowid

            for cat_id, qty in items:
                cur2.execute(
                    'INSERT INTO PICKUP_REQUEST_ITEMS (Request_ID, Category_ID, Quantity) '
                    'VALUES (%s, %s, %s)',
                    (request_id, cat_id, qty))

            conn.commit()
            cur2.close()
            flash('Pickup request submitted successfully!', 'success')
            return redirect(url_for('user_my_requests'))

        cur.close()
        return render_template('user/request_pickup.html', categories=categories)
    except Error as e:
        if conn and conn.is_connected():
            conn.rollback()
        flash(f'Database error: {e}', 'danger')
        return render_template('user/request_pickup.html', categories=[])
    finally:
        if conn and conn.is_connected():
            conn.close()

@app.route('/user/my-requests')
@role_required('USER')
def user_my_requests():
    uid = session['user_id']
    conn = None
    try:
        conn = db()
        cur = conn.cursor(dictionary=True)
        cur.execute('''
            SELECT PR.Request_ID, PR.Request_Date, PR.Pickup_Address, PR.Status,
                   PA.Assignment_Date,
                   CA.Agent_Name, CA.Phone AS Agent_Phone,
                   RC.Center_Name
            FROM PICKUP_REQUESTS PR
            LEFT JOIN PICKUP_ASSIGNMENTS PA ON PR.Request_ID = PA.Request_ID
            LEFT JOIN COLLECTION_AGENTS CA ON PA.Agent_ID = CA.Agent_ID
            LEFT JOIN RECYCLING_CENTERS RC ON PA.Center_ID = RC.Center_ID
            WHERE PR.User_ID = %s
            ORDER BY PR.Request_ID DESC
        ''', (uid,))
        requests_data = cur.fetchall()
        cur.close()
        return render_template('user/my_requests.html', requests=requests_data)
    except Error as e:
        flash(f'Database error: {e}', 'danger')
        return render_template('user/my_requests.html', requests=[])
    finally:
        if conn and conn.is_connected():
            conn.close()

@app.route('/user/payments')
@role_required('USER')
def user_payments():
    uid = session['user_id']
    conn = None
    try:
        conn = db()
        cur = conn.cursor(dictionary=True)
        cur.execute('''
            SELECT PAY.Payment_ID, PAY.Request_ID, PR.Pickup_Address,
                   PAY.Amount, PAY.Payment_Date, PAY.Payment_Method, PAY.Payment_Status
            FROM PAYMENTS PAY
            JOIN PICKUP_REQUESTS PR ON PAY.Request_ID = PR.Request_ID
            WHERE PR.User_ID = %s
            ORDER BY PAY.Payment_ID DESC
        ''', (uid,))
        payments = cur.fetchall()
        cur.close()
        return render_template('user/payments.html', payments=payments)
    except Error as e:
        flash(f'Database error: {e}', 'danger')
        return render_template('user/payments.html', payments=[])
    finally:
        if conn and conn.is_connected():
            conn.close()

# ---------------------------------------------------------------------------
# Collection Agent routes
# ---------------------------------------------------------------------------
@app.route('/agent/dashboard')
@role_required('COLLECTION_AGENT')
def agent_dashboard():
    agent_id = session['user_id']
    conn = None
    try:
        conn = db()
        cur = conn.cursor()

        cur.execute('SELECT COUNT(*) FROM PICKUP_ASSIGNMENTS WHERE Agent_ID=%s', (agent_id,))
        total = cur.fetchone()[0]

        cur.execute(
            "SELECT COUNT(*) FROM PICKUP_ASSIGNMENTS WHERE Agent_ID=%s AND Status='Assigned'",
            (agent_id,))
        pending = cur.fetchone()[0]

        cur.execute(
            "SELECT COUNT(*) FROM PICKUP_ASSIGNMENTS WHERE Agent_ID=%s AND Status='Completed'",
            (agent_id,))
        completed = cur.fetchone()[0]

        cur.execute('''
            SELECT PA.Assignment_ID, PR.Request_ID, U.Name AS User_Name,
                   PR.Pickup_Address, PA.Status, PA.Assignment_Date
            FROM PICKUP_ASSIGNMENTS PA
            JOIN PICKUP_REQUESTS PR ON PA.Request_ID = PR.Request_ID
            JOIN USERS U ON PR.User_ID = U.User_ID
            WHERE PA.Agent_ID = %s
            ORDER BY PA.Assignment_ID DESC
            LIMIT 5
        ''', (agent_id,))
        recent = cur.fetchall()
        cur.close()

        return render_template('agent/dashboard.html',
                               total=total, pending=pending,
                               completed=completed, recent=recent)
    except Error as e:
        flash(f'Database error: {e}', 'danger')
        return render_template('agent/dashboard.html',
                               total=0, pending=0, completed=0, recent=[])
    finally:
        if conn and conn.is_connected():
            conn.close()

@app.route('/agent/profile', methods=['GET', 'POST'])
@role_required('COLLECTION_AGENT')
def agent_profile():
    agent_id = session['user_id']
    conn = None
    try:
        conn = db()
        cur = conn.cursor(dictionary=True)
        if request.method == 'POST':
            name     = request.form.get('name', '').strip()
            phone    = request.form.get('phone', '').strip()
            password = request.form.get('password', '')
            confirm  = request.form.get('confirm_password', '')

            if not name:
                flash('Agent name is required.', 'danger')
                cur.execute('SELECT * FROM COLLECTION_AGENTS WHERE Agent_ID=%s', (agent_id,))
                agent = cur.fetchone()
                return render_template('agent/profile.html', agent=agent)

            if password:
                if len(password) < 6:
                    flash('Password must be at least 6 characters.', 'danger')
                    cur.execute('SELECT * FROM COLLECTION_AGENTS WHERE Agent_ID=%s', (agent_id,))
                    agent = cur.fetchone()
                    return render_template('agent/profile.html', agent=agent)
                if password != confirm:
                    flash('Passwords do not match.', 'danger')
                    cur.execute('SELECT * FROM COLLECTION_AGENTS WHERE Agent_ID=%s', (agent_id,))
                    agent = cur.fetchone()
                    return render_template('agent/profile.html', agent=agent)
                hashed = generate_password_hash(password)
                cur.execute(
                    'UPDATE COLLECTION_AGENTS SET Agent_Name=%s, Phone=%s, Password=%s WHERE Agent_ID=%s',
                    (name, phone, hashed, agent_id))
            else:
                cur.execute(
                    'UPDATE COLLECTION_AGENTS SET Agent_Name=%s, Phone=%s WHERE Agent_ID=%s',
                    (name, phone, agent_id))

            conn.commit()
            session['name'] = name
            flash('Profile updated successfully.', 'success')
            return redirect(url_for('agent_profile'))

        cur.execute('SELECT * FROM COLLECTION_AGENTS WHERE Agent_ID=%s', (agent_id,))
        agent = cur.fetchone()
        cur.close()
        return render_template('agent/profile.html', agent=agent)
    except Error as e:
        flash(f'Database error: {e}', 'danger')
        return render_template('agent/profile.html', agent={})
    finally:
        if conn and conn.is_connected():
            conn.close()

@app.route('/agent/pickups')
@role_required('COLLECTION_AGENT')
def agent_pickups():
    agent_id = session['user_id']
    conn = None
    try:
        conn = db()
        cur = conn.cursor(dictionary=True)
        cur.execute('''
            SELECT PA.Assignment_ID, PA.Assignment_Date, PA.Status AS Assignment_Status,
                   PR.Request_ID, PR.Request_Date, PR.Pickup_Address, PR.Status AS Request_Status,
                   U.Name AS User_Name, U.Phone AS User_Phone, U.Email AS User_Email
            FROM PICKUP_ASSIGNMENTS PA
            JOIN PICKUP_REQUESTS PR ON PA.Request_ID = PR.Request_ID
            JOIN USERS U ON PR.User_ID = U.User_ID
            WHERE PA.Agent_ID = %s
            ORDER BY PA.Assignment_ID DESC
        ''', (agent_id,))
        assignments = cur.fetchall()

        # For each assignment, fetch the items
        for a in assignments:
            cur.execute('''
                SELECT EC.Category_Name, PRI.Quantity
                FROM PICKUP_REQUEST_ITEMS PRI
                JOIN E_WASTE_CATEGORIES EC ON PRI.Category_ID = EC.Category_ID
                WHERE PRI.Request_ID = %s
            ''', (a['Request_ID'],))
            a['items'] = cur.fetchall()

        cur.close()
        return render_template('agent/pickups.html', assignments=assignments)
    except Error as e:
        flash(f'Database error: {e}', 'danger')
        return render_template('agent/pickups.html', assignments=[])
    finally:
        if conn and conn.is_connected():
            conn.close()

@app.route('/agent/update-status/<int:assignment_id>', methods=['POST'])
@role_required('COLLECTION_AGENT')
def agent_update_status(assignment_id):
    agent_id = session['user_id']
    new_status = request.form.get('status', '').strip()

    valid_statuses = {'Assigned', 'Processing', 'Completed', 'Cancelled'}
    if new_status not in valid_statuses:
        flash('Invalid status value.', 'danger')
        return redirect(url_for('agent_pickups'))

    conn = None
    try:
        conn = db()
        cur = conn.cursor(dictionary=True)

        # Verify this assignment belongs to this agent
        cur.execute(
            'SELECT Assignment_ID FROM PICKUP_ASSIGNMENTS WHERE Assignment_ID=%s AND Agent_ID=%s',
            (assignment_id, agent_id))
        if not cur.fetchone():
            flash('Assignment not found or access denied.', 'danger')
            cur.close()
            return redirect(url_for('agent_pickups'))

        # Update assignment status
        cur.execute(
            'UPDATE PICKUP_ASSIGNMENTS SET Status=%s WHERE Assignment_ID=%s AND Agent_ID=%s',
            (new_status, assignment_id, agent_id))

        # Also mirror status to PICKUP_REQUESTS
        status_map = {
            'Assigned': 'Assigned',
            'Processing': 'In Progress',
            'Completed': 'Completed',
            'Cancelled': 'Cancelled',
        }
        cur.execute('''
            UPDATE PICKUP_REQUESTS SET Status=%s
            WHERE Request_ID = (
                SELECT Request_ID FROM PICKUP_ASSIGNMENTS WHERE Assignment_ID=%s
            )
        ''', (status_map[new_status], assignment_id))

        conn.commit()
        cur.close()
        flash(f'Status updated to "{new_status}" successfully.', 'success')
    except Error as e:
        if conn and conn.is_connected():
            conn.rollback()
        flash(f'Could not update status: {e}', 'danger')
    finally:
        if conn and conn.is_connected():
            conn.close()

    return redirect(url_for('agent_pickups'))

# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------
@app.errorhandler(404)
def missing(_):
    return render_template('404.html'), 404

if __name__ == '__main__':
    app.run(debug=True)
