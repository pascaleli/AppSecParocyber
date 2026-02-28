#
# This code was developed for the *Practical Web Application
# Penetration Test (WAPT)* course created by Leonardo Tamiano
# (Hexdump).  Unauthorized reproduction, distribution, or use of this
# material outside the scope of the course is strictly prohibited.

# All rights reserved.
#
# Copyright (c) 2025 Leonardo Tamiano (Hexdump)
#

from flask import Flask, request, redirect, render_template_string, session, g
import sqlite3
import os
import secrets

# ------------------------------------

app = Flask(__name__)
app.secret_key = os.urandom(24)

DATABASE = 'users.db'

# HTML Templates
login_page = '''
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>Login Form</title>
  <style>
    body {
      margin: 0;
      padding: 0;
      font-family: Arial, sans-serif;
      background-color: grey;
      height: 100vh;
      display: flex;
      justify-content: center;
      align-items: center;
    }

    .login-container {
      background-color: #fff;
      padding: 2rem;
      border-radius: 10px;
      box-shadow: 0 0 10px rgba(0,0,0,0.1);
      width: 300px;
    }

    .login-container h2 {
      text-align: center;
      margin-bottom: 1.5rem;
    }

    .login-container input[type="text"],
    .login-container input[type="password"] {
      width: 100%;
      padding: 0.75rem;
      margin-bottom: 1rem;
      border: 1px solid #ccc;
      border-radius: 5px;
    }

    .login-container button {
      width: 100%;
      padding: 0.75rem;
      background-color: #007BFF;
      border: none;
      color: white;
      border-radius: 5px;
      font-size: 1rem;
      cursor: pointer;
    }

    .login-container button:hover {
      background-color: #0056b3;
    }
  </style>
</head>
<body>
<div class="login-container">
    <form method="POST">
        <h2>Login</h2>
        <input type="text" name="username" placeholder="Username"><br><br>
        <input type="password" name="password" placeholder="Password" type="password"><br><br>
        <button type="submit">Login</button>
        {% if error %}<p style="color:red;">{{ error }}</p>{% endif %}
    </form>
</div>
</body>
</html>
'''

profile_page = '''
<!DOCTYPE html>
<html>
<head><title>Profile</title></head>
<body>
    <h1>Welcome, {{ username }}</h1>
    {% if apikey %}
    <p>Your API Key: <b>{{ apikey }}</b></p>
    {% else %}
    <p>You are a normal user.</p>
    {% endif %}
</body>
</html>
'''

# ------------------------------------

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
    return g.db

def db_init():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("CREATE TABLE users (username TEXT, password TEXT, apikey TEXT)")
    
    # create administrator credential
    admin_password = secrets.token_urlsafe(12)
    admin_apikey = 'API-' + secrets.token_urlsafe(24)
    c.execute("INSERT INTO users (username, password, apikey) VALUES (?, ?, ?)",
              ('admin', admin_password, admin_apikey))

    # create basic user credential
    c.execute("INSERT INTO users VALUES ('user', 'password', NULL)")    

    conn.commit()
    conn.close()

# -------    
    
@app.teardown_appcontext
def close_connection(exception):
    db = g.pop('db', None)
    if db:
        db.close()

@app.route('/', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db = get_db()
        query = f"SELECT username, apikey FROM users WHERE username='{username}' AND password='{password}'"
        cur = db.execute(query)
        user = cur.fetchone()
        if user:
            session['username'] = user[0]
            session['apikey'] = user[1]
            return redirect('/profile')
        else:
            error = 'Invalid credentials'
    return render_template_string(login_page, error=error)

@app.route('/profile')
def profile():
    if 'username' not in session:
        return redirect('/')
    return render_template_string(profile_page, username=session['username'], apikey=session.get('apikey'))

# -------

if __name__ == '__main__':
    if not os.path.exists(DATABASE):
        db_init()
    
    app.run(debug=True)
