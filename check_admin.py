import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash

conn = mysql.connector.connect(
    host='localhost', port=3306, user='root', password='root', database='e_waste'
)
cur = conn.cursor()

# Check admin password
cur.execute('SELECT User_ID, Name, Email, Password FROM USERS WHERE User_Role=%s', ('ADMIN',))
row = cur.fetchone()
if row:
    pwd = row[3] or ''
    is_hashed = pwd.startswith('pbkdf2') or pwd.startswith('scrypt')
    print(f'Admin: {row[1]} ({row[2]})')
    print(f'Password preview: {pwd[:40]}...' if len(pwd) > 40 else f'Password: {pwd}')
    print(f'Already hashed: {is_hashed}')

    if not is_hashed and pwd:
        print('Re-hashing plain text password...')
        new_hash = generate_password_hash(pwd)
        cur.execute('UPDATE USERS SET Password=%s WHERE User_ID=%s', (new_hash, row[0]))
        conn.commit()
        print(f'Password re-hashed. You can now login with: {row[2]} / {pwd}')
    elif not pwd:
        # Set a default
        new_hash = generate_password_hash('admin123')
        cur.execute('UPDATE USERS SET Password=%s WHERE User_ID=%s', (new_hash, row[0]))
        conn.commit()
        print(f'Password was NULL. Set to: admin@ewaste.com / admin123')
    else:
        print('Password is already hashed. Admin can log in normally.')

# Set demo passwords for collection agents so they can be tested
print('\nSetting demo passwords for collection agents (agent123)...')
cur.execute('SELECT Agent_ID, Agent_Name FROM COLLECTION_AGENTS WHERE Password IS NULL')
agents = cur.fetchall()
for a in agents:
    hashed = generate_password_hash('agent123')
    cur.execute('UPDATE COLLECTION_AGENTS SET Password=%s WHERE Agent_ID=%s', (hashed, a[0]))
    print(f'  Set password for agent {a[1]}')
conn.commit()
print('Done!')

cur.close()
conn.close()
