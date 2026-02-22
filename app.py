"""
ParoCyberBank – Demo bank application (Python + SQLite).
Run: pip install -r requirements.txt && python app.py
"""
import os
import sqlite3
from datetime import datetime
from functools import wraps
from flask import Flask, request, jsonify, session, render_template, redirect, url_for

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-prod")
DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "parocyberbank.db")


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                full_name TEXT NOT NULL,
                email TEXT
            );
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                account_number TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                balance_cents INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_account_id INTEGER NOT NULL,
                to_account_id INTEGER NOT NULL,
                amount_cents INTEGER NOT NULL,
                memo TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (from_account_id) REFERENCES accounts(id),
                FOREIGN KEY (to_account_id) REFERENCES accounts(id)
            );
            CREATE TABLE IF NOT EXISTS saved_payees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                payee_user_id INTEGER NOT NULL,
                label TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (payee_user_id) REFERENCES users(id),
                UNIQUE(user_id, payee_user_id)
            );
        """)
        cur = conn.execute("SELECT COUNT(*) FROM users")
        if cur.fetchone()[0] == 0:
            conn.execute(
                "INSERT INTO users (username, password, full_name, email) VALUES (?, ?, ?, ?)",
                ("alice", "alice123", "Alice Smith", "alice@example.com"),
            )
            conn.execute(
                "INSERT INTO users (username, password, full_name, email) VALUES (?, ?, ?, ?)",
                ("bob", "bob456", "Bob Jones", "bob@example.com"),
            )
            conn.execute(
                "INSERT INTO users (username, password, full_name, email) VALUES (?, ?, ?, ?)",
                ("charlie", "charlie789", "Charlie Admin", "charlie@bank.local"),
            )
            conn.execute(
                "INSERT INTO accounts (user_id, account_number, name, balance_cents) VALUES (1, '400012340001', 'Main Checking', 150000)",
            )
            conn.execute(
                "INSERT INTO accounts (user_id, account_number, name, balance_cents) VALUES (2, '400012340002', 'Main Checking', 75000)",
            )
            conn.execute(
                "INSERT INTO accounts (user_id, account_number, name, balance_cents) VALUES (3, '400012340003', 'Main Checking', 500000)",
            )
            conn.execute(
                "INSERT INTO accounts (user_id, account_number, name, balance_cents) VALUES (3, '400012340004', 'Savings', 1000000)",
            )
            now = datetime.utcnow().isoformat() + "Z"
            conn.execute(
                "INSERT INTO transactions (from_account_id, to_account_id, amount_cents, memo, created_at) VALUES (1, 2, 2500, 'Coffee', ?)",
                (now,),
            )
            conn.execute(
                "INSERT INTO transactions (from_account_id, to_account_id, amount_cents, memo, created_at) VALUES (2, 1, 10000, 'Rent share', ?)",
                (now,),
            )


def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"error": "Login required"}), 401
            return redirect(url_for("login_page", next=request.url))
        return f(*args, **kwargs)
    return wrapped


def row_to_account(r):
    return {
        "id": r["id"],
        "account_number": r["account_number"],
        "name": r["name"],
        "balance_cents": r["balance_cents"],
        "balance": f"{r['balance_cents'] / 100:.2f}",
    }


def row_to_transaction(r, from_number=None, to_number=None):
    d = {
        "id": r["id"],
        "from_account_id": r["from_account_id"],
        "to_account_id": r["to_account_id"],
        "amount_cents": r["amount_cents"],
        "amount": f"{r['amount_cents'] / 100:.2f}",
        "memo": r["memo"] or "",
        "created_at": r["created_at"],
    }
    if from_number:
        d["from_account_number"] = from_number
    if to_number:
        d["to_account_number"] = to_number
    return d


# ---------- Auth ----------

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(force=True, silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    if not username:
        return jsonify({"error": "Username required"}), 400
    conn = get_db()
    row = conn.execute(
        "SELECT id, username, password, full_name FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    conn.close()
    if row and row["password"] == password:
        session["user_id"] = row["id"]
        session["username"] = row["username"]
        session["full_name"] = row["full_name"]
        return jsonify({"ok": True, "user": row["username"], "full_name": row["full_name"]})
    return jsonify({"error": "Invalid credentials"}), 401


@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/logout", methods=["POST"])
def web_logout():
    session.clear()
    return redirect(url_for("login_page"))


# ---------- Search payees – SQL injection in q ----------

@app.route("/api/users/search", methods=["GET"])
@login_required
def api_users_search():
    q = request.args.get("q", "")
    try:
        conn = get_db()
        query = f"SELECT id, username, full_name FROM users WHERE full_name LIKE '%{q}%' OR username LIKE '%{q}%'"
        rows = conn.execute(query).fetchall()
        conn.close()
        return jsonify([dict(r) for r in rows])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- Payee's accounts (for transfer: select destination account by payee) ----------

@app.route("/api/users/<int:user_id>/accounts", methods=["GET"])
@login_required
def api_user_accounts(user_id):
    """Return accounts for a user (e.g. payee) so the sender can choose which account to send to."""
    conn = get_db()
    rows = conn.execute(
        "SELECT id, account_number, name, balance_cents FROM accounts WHERE user_id = ?",
        (user_id,),
    ).fetchall()
    conn.close()
    return jsonify([row_to_account(r) for r in rows])


# ---------- Accounts – IDOR: no ownership check on GET /api/accounts/<id> ----------

@app.route("/api/accounts", methods=["GET"])
@login_required
def api_accounts_list():
    conn = get_db()
    rows = conn.execute(
        "SELECT id, account_number, name, balance_cents FROM accounts WHERE user_id = ?",
        (session["user_id"],),
    ).fetchall()
    conn.close()
    return jsonify([row_to_account(r) for r in rows])


@app.route("/api/accounts/<int:account_id>", methods=["GET"])
@login_required
def api_account_detail(account_id):
    conn = get_db()
    row = conn.execute(
        "SELECT id, user_id, account_number, name, balance_cents FROM accounts WHERE id = ?",
        (account_id,),
    ).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "Account not found"}), 404
    return jsonify(row_to_account(row))


# ---------- Transactions – IDOR: account_id not checked ----------

@app.route("/api/transactions", methods=["GET"])
@login_required
def api_transactions_list():
    account_id = request.args.get("account_id", type=int)
    if not account_id:
        return jsonify({"error": "account_id required"}), 400
    conn = get_db()
    rows = conn.execute(
        """SELECT t.id, t.from_account_id, t.to_account_id, t.amount_cents, t.memo, t.created_at,
                  a_from.account_number AS from_num, a_to.account_number AS to_num
           FROM transactions t
           JOIN accounts a_from ON a_from.id = t.from_account_id
           JOIN accounts a_to ON a_to.id = t.to_account_id
           WHERE t.from_account_id = ? OR t.to_account_id = ?
           ORDER BY t.created_at DESC LIMIT 50""",
        (account_id, account_id),
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        out.append(row_to_transaction(r, from_number=r["from_num"], to_number=r["to_num"]))
    return jsonify(out)


# ---------- All my transactions (across all my accounts) ----------

@app.route("/api/transactions/all", methods=["GET"])
@login_required
def api_transactions_all():
    conn = get_db()
    rows = conn.execute(
        """SELECT t.id, t.from_account_id, t.to_account_id, t.amount_cents, t.memo, t.created_at,
                  a_from.account_number AS from_num, a_to.account_number AS to_num
           FROM transactions t
           JOIN accounts a_from ON a_from.id = t.from_account_id
           JOIN accounts a_to ON a_to.id = t.to_account_id
           JOIN accounts my_acc ON (my_acc.id = t.from_account_id OR my_acc.id = t.to_account_id) AND my_acc.user_id = ?
           ORDER BY t.created_at DESC LIMIT 100""",
        (session["user_id"],),
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        out.append(row_to_transaction(r, from_number=r["from_num"], to_number=r["to_num"]))
    return jsonify(out)


# ---------- Transfer – IDOR: from_account_id not validated ----------

@app.route("/api/transfer", methods=["POST"])
@login_required
def api_transfer():
    data = request.get_json(force=True, silent=True) or {}
    from_id = data.get("from_account_id", type=int)
    to_id = data.get("to_account_id", type=int)
    amount_cents = data.get("amount_cents", type=int)
    memo = (data.get("memo") or "")[:500]

    if not from_id or not to_id or not amount_cents or amount_cents <= 0:
        return jsonify({"error": "Invalid from_account_id, to_account_id, or amount_cents"}), 400
    if from_id == to_id:
        return jsonify({"error": "Same account"}), 400

    conn = get_db()
    from_row = conn.execute("SELECT id, user_id, balance_cents FROM accounts WHERE id = ?", (from_id,)).fetchone()
    to_row = conn.execute("SELECT id FROM accounts WHERE id = ?", (to_id,)).fetchone()
    if not from_row or not to_row:
        conn.close()
        return jsonify({"error": "Account not found"}), 404
    if from_row["balance_cents"] < amount_cents:
        conn.close()
        return jsonify({"error": "Insufficient balance"}), 400

    now = datetime.utcnow().isoformat() + "Z"
    conn.execute(
        "UPDATE accounts SET balance_cents = balance_cents - ? WHERE id = ?",
        (amount_cents, from_id),
    )
    conn.execute(
        "UPDATE accounts SET balance_cents = balance_cents + ? WHERE id = ?",
        (amount_cents, to_id),
    )
    conn.execute(
        "INSERT INTO transactions (from_account_id, to_account_id, amount_cents, memo, created_at) VALUES (?, ?, ?, ?, ?)",
        (from_id, to_id, amount_cents, memo, now),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "message": "Transfer completed"})


# ---------- Saved payees ----------

@app.route("/api/payees", methods=["GET"])
@login_required
def api_payees_list():
    conn = get_db()
    rows = conn.execute(
        """SELECT sp.id, sp.payee_user_id, sp.label, u.username, u.full_name
           FROM saved_payees sp
           JOIN users u ON u.id = sp.payee_user_id
           WHERE sp.user_id = ?
           ORDER BY sp.label""",
        (session["user_id"],),
    ).fetchall()
    conn.close()
    return jsonify([{"id": r["id"], "payee_user_id": r["payee_user_id"], "label": r["label"], "username": r["username"], "full_name": r["full_name"]} for r in rows])


@app.route("/api/payees", methods=["POST"])
@login_required
def api_payees_add():
    data = request.get_json(force=True, silent=True) or {}
    payee_user_id = data.get("payee_user_id", type=int)
    label = (data.get("label") or "").strip()[:200]
    if not payee_user_id or not label:
        return jsonify({"error": "payee_user_id and label required"}), 400
    if payee_user_id == session["user_id"]:
        return jsonify({"error": "Cannot add yourself"}), 400
    conn = get_db()
    exists = conn.execute("SELECT id FROM users WHERE id = ?", (payee_user_id,)).fetchone()
    if not exists:
        conn.close()
        return jsonify({"error": "User not found"}), 404
    try:
        conn.execute(
            "INSERT INTO saved_payees (user_id, payee_user_id, label) VALUES (?, ?, ?)",
            (session["user_id"], payee_user_id, label),
        )
        conn.commit()
        rid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()
        return jsonify({"ok": True, "id": rid})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "Payee already saved"}), 400


@app.route("/api/payees/<int:payee_id>", methods=["DELETE"])
@login_required
def api_payees_delete(payee_id):
    conn = get_db()
    conn.execute("DELETE FROM saved_payees WHERE id = ? AND user_id = ?", (payee_id, session["user_id"]))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# ---------- Web UI ----------

@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "GET":
        return render_template("login.html")
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    if not username:
        return render_template("login.html", error="Username required")
    conn = get_db()
    row = conn.execute(
        "SELECT id, username, password, full_name, email FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    conn.close()
    if row and row["password"] == password:
        session["user_id"] = row["id"]
        session["username"] = row["username"]
        session["full_name"] = row["full_name"]
        session["email"] = row["email"] or ""
        return redirect("/dashboard")
    return render_template("login.html", error="Invalid credentials")


@app.route("/dashboard")
@login_required
def dashboard():
    conn = get_db()
    accounts = conn.execute(
        "SELECT id, account_number, name, balance_cents FROM accounts WHERE user_id = ?",
        (session["user_id"],),
    ).fetchall()
    conn.close()
    return render_template(
        "dashboard.html",
        full_name=session.get("full_name"),
        accounts=[row_to_account(r) for r in accounts],
    )


@app.route("/profile")
@login_required
def profile_page():
    conn = get_db()
    row = conn.execute(
        "SELECT username, full_name, email FROM users WHERE id = ?",
        (session["user_id"],),
    ).fetchone()
    conn.close()
    if not row:
        return redirect("/dashboard")
    return render_template(
        "profile.html",
        username=row["username"],
        full_name=row["full_name"],
        email=row["email"] or "",
    )


@app.route("/transactions")
@login_required
def transactions_page():
    conn = get_db()
    rows = conn.execute(
        """SELECT t.id, t.from_account_id, t.to_account_id, t.amount_cents, t.memo, t.created_at,
                  a_from.account_number AS from_num, a_to.account_number AS to_num
           FROM transactions t
           JOIN accounts a_from ON a_from.id = t.from_account_id
           JOIN accounts a_to ON a_to.id = t.to_account_id
           JOIN accounts my_acc ON (my_acc.id = t.from_account_id OR my_acc.id = t.to_account_id) AND my_acc.user_id = ?
           ORDER BY t.created_at DESC LIMIT 100""",
        (session["user_id"],),
    ).fetchall()
    conn.close()
    transactions = [row_to_transaction(r, from_number=r["from_num"], to_number=r["to_num"]) for r in rows]
    return render_template("transactions.html", transactions=transactions)


@app.route("/payees")
@login_required
def payees_page():
    conn = get_db()
    rows = conn.execute(
        """SELECT sp.id, sp.payee_user_id, sp.label, u.username, u.full_name
           FROM saved_payees sp
           JOIN users u ON u.id = sp.payee_user_id
           WHERE sp.user_id = ?
           ORDER BY sp.label""",
        (session["user_id"],),
    ).fetchall()
    conn.close()
    payees = [{"id": r["id"], "payee_user_id": r["payee_user_id"], "label": r["label"], "username": r["username"], "full_name": r["full_name"]} for r in rows]
    return render_template("payees.html", payees=payees)


@app.route("/accounts/<int:account_id>")
@login_required
def account_page(account_id):
    conn = get_db()
    row = conn.execute(
        "SELECT id, user_id, account_number, name, balance_cents FROM accounts WHERE id = ?",
        (account_id,),
    ).fetchone()
    if not row:
        conn.close()
        return "Account not found", 404
    tx_rows = conn.execute(
        """SELECT t.id, t.from_account_id, t.to_account_id, t.amount_cents, t.memo, t.created_at,
                  a_from.account_number AS from_num, a_to.account_number AS to_num
           FROM transactions t
           JOIN accounts a_from ON a_from.id = t.from_account_id
           JOIN accounts a_to ON a_to.id = t.to_account_id
           WHERE t.from_account_id = ? OR t.to_account_id = ?
           ORDER BY t.created_at DESC LIMIT 50""",
        (account_id, account_id),
    ).fetchall()
    conn.close()
    transactions = [row_to_transaction(r, from_number=r["from_num"], to_number=r["to_num"]) for r in tx_rows]
    return render_template(
        "account.html",
        account=row_to_account(row),
        transactions=transactions,
    )


@app.route("/transfer", methods=["GET", "POST"])
@login_required
def transfer_page():
    if request.method == "GET":
        conn = get_db()
        accounts = conn.execute(
            "SELECT id, account_number, name, balance_cents FROM accounts WHERE user_id = ?",
            (session["user_id"],),
        ).fetchall()
        payees = conn.execute(
            """SELECT sp.payee_user_id, sp.label, u.username, u.full_name
               FROM saved_payees sp JOIN users u ON u.id = sp.payee_user_id
               WHERE sp.user_id = ? ORDER BY sp.label""",
            (session["user_id"],),
        ).fetchall()
        conn.close()
        return render_template(
            "transfer.html",
            accounts=[row_to_account(r) for r in accounts],
            saved_payees=[dict(r) for r in payees],
        )
    from_id = request.form.get("from_account_id", type=int)
    to_id = request.form.get("to_account_id", type=int)
    amount = request.form.get("amount", type=float)
    memo = (request.form.get("memo") or "")[:500]
    if not from_id or not to_id or amount is None or amount <= 0:
        conn = get_db()
        accounts = conn.execute("SELECT id, account_number, name, balance_cents FROM accounts WHERE user_id = ?", (session["user_id"],)).fetchall()
        payees = conn.execute("""SELECT sp.payee_user_id, sp.label, u.username, u.full_name FROM saved_payees sp JOIN users u ON u.id = sp.payee_user_id WHERE sp.user_id = ? ORDER BY sp.label""", (session["user_id"],)).fetchall()
        conn.close()
        return render_template("transfer.html", accounts=[row_to_account(r) for r in accounts], saved_payees=[dict(r) for r in payees], error="Invalid form data")
    amount_cents = int(round(amount * 100))
    conn = get_db()
    from_row = conn.execute("SELECT id, user_id, balance_cents FROM accounts WHERE id = ?", (from_id,)).fetchone()
    to_row = conn.execute("SELECT id FROM accounts WHERE id = ?", (to_id,)).fetchone()
    if not from_row or not to_row:
        acc = conn.execute("SELECT id, account_number, name, balance_cents FROM accounts WHERE user_id = ?", (session["user_id"],)).fetchall()
        pay = conn.execute("""SELECT sp.payee_user_id, sp.label, u.username, u.full_name FROM saved_payees sp JOIN users u ON u.id = sp.payee_user_id WHERE sp.user_id = ? ORDER BY sp.label""", (session["user_id"],)).fetchall()
        conn.close()
        return render_template("transfer.html", accounts=[row_to_account(r) for r in acc], saved_payees=[dict(r) for r in pay], error="Account not found")
    if from_row["balance_cents"] < amount_cents:
        acc = conn.execute("SELECT id, account_number, name, balance_cents FROM accounts WHERE user_id = ?", (session["user_id"],)).fetchall()
        pay = conn.execute("""SELECT sp.payee_user_id, sp.label, u.username, u.full_name FROM saved_payees sp JOIN users u ON u.id = sp.payee_user_id WHERE sp.user_id = ? ORDER BY sp.label""", (session["user_id"],)).fetchall()
        conn.close()
        return render_template("transfer.html", accounts=[row_to_account(r) for r in acc], saved_payees=[dict(r) for r in pay], error="Insufficient balance")
    now = datetime.utcnow().isoformat() + "Z"
    conn.execute("UPDATE accounts SET balance_cents = balance_cents - ? WHERE id = ?", (amount_cents, from_id))
    conn.execute("UPDATE accounts SET balance_cents = balance_cents + ? WHERE id = ?", (amount_cents, to_id))
    conn.execute(
        "INSERT INTO transactions (from_account_id, to_account_id, amount_cents, memo, created_at) VALUES (?, ?, ?, ?, ?)",
        (from_id, to_id, amount_cents, memo, now),
    )
    conn.commit()
    conn.close()
    return redirect("/dashboard")


@app.route("/help")
def help_page():
    return render_template("help.html")


@app.route("/")
def index():
    if "user_id" in session:
        return redirect("/dashboard")
    return render_template("login.html")


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
