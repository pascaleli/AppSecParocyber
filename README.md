# ParoCyberBank

A simple online banking application for teaching application security. Run it on Kali (or any machine with Python 3), explore the app and its API, and discover security issues together in class.

## Run on Kali

Create a virtual environment, install dependencies, then start the app:

```bash
cd ~/Desktop/AppSecParocyber
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:5000** in a browser. If you update the code, restart the server (`Ctrl+C` then `python app.py` again) so new routes and pages are loaded.

## What you get

- **Web UI**: sign in, dashboard, view accounts, view all transactions, make transfers (by searching or selecting a payee—no need to know account numbers), manage saved payees, profile, and help.
- **REST API**: same actions via JSON for use with Postman, curl, or Burp Suite.

Demo logins:

- **alice** / alice123  
- **bob** / bob456  
- **charlie** / charlie789  

## Making a transfer (no account numbers needed)

1. Go to **Transfer**.
2. Search for the recipient by name or username, or click a **saved payee**.
3. Choose **To account** from the dropdown (their account(s) appear with masked numbers, e.g. “Main Checking ****4002”).
4. Select **From account**, enter amount and optional memo, then **Send transfer**.

You can save payees from the **Payees** page or when searching during a transfer.

## Pages

| Page | Description |
|------|-------------|
| Dashboard | Your accounts and balances |
| Transfer | Send money (search payee → select their account → send) |
| Transactions | All transactions across your accounts |
| Payees | View and add saved payees for quick transfer |
| Profile | Your username, full name, email |
| Help | How to use the app |

## API overview

All API routes (except login and health) require a logged-in session (cookie). Log in via the web UI or `POST /api/login` and keep the session cookie.

| Endpoint | Description |
|----------|-------------|
| `POST /api/login` | Log in (JSON: username, password) |
| `POST /api/logout` | Log out |
| `GET /api/users/search?q=...` | Search users by name or username |
| `GET /api/users/<user_id>/accounts` | List accounts for a user (e.g. payee) |
| `GET /api/accounts` | List your accounts |
| `GET /api/accounts/<id>` | Account details |
| `GET /api/transactions?account_id=<id>` | Transactions for an account |
| `GET /api/transactions/all` | All your transactions (any account) |
| `POST /api/transfer` | Transfer (JSON: from_account_id, to_account_id, amount_cents, memo) |
| `GET /api/payees` | List your saved payees |
| `POST /api/payees` | Add payee (JSON: payee_user_id, label) |
| `DELETE /api/payees/<id>` | Remove a saved payee |
| `GET /api/health` | Health check |

Database: SQLite, stored as **parocyberbank.db** in the project folder (created on first run).

## Teaching notes

Use the app as a normal bank during the course. Have students use the UI and the API (with Burp or Postman), then guide them to find and discuss real OWASP-style issues in the implementation—no spoilers in this README so you can discover them together.
