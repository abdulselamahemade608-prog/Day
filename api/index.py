
import os
import secrets
import psycopg2
import requests

from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

ADMIN_ID = 8845432223

REQUIRED_CHANNELS = [
    "@ABDU_CRYPTO",
    "@proof_chnallel",
    "@m_r_work1"
]


# =========================================================
# DATABASE
# =========================================================

def get_db():
    return psycopg2.connect(DATABASE_URL)


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id BIGSERIAL PRIMARY KEY,
            telegram_id BIGINT UNIQUE NOT NULL,
            username TEXT,
            first_name TEXT,
            balance NUMERIC(18,2) NOT NULL DEFAULT 0,
            referral_code TEXT UNIQUE NOT NULL,
            referred_by BIGINT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id BIGSERIAL PRIMARY KEY,
            telegram_id BIGINT NOT NULL,
            type TEXT NOT NULL,
            amount NUMERIC(18,2) NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ad_sessions (
            id BIGSERIAL PRIMARY KEY,
            telegram_id BIGINT NOT NULL,
            nonce TEXT UNIQUE NOT NULL,
            completed BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS withdrawals (
            id BIGSERIAL PRIMARY KEY,
            telegram_id BIGINT NOT NULL,
            amount NUMERIC(18,2) NOT NULL,
            method TEXT NOT NULL,
            account TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    conn.commit()
    cur.close()
    conn.close()


# =========================================================
# TELEGRAM API
# =========================================================

def telegram(method, data):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"

    try:
        response = requests.post(
            url,
            json=data,
            timeout=15
        )

        return response.json()

    except Exception:
        return {
            "ok": False,
            "description": "Telegram API error"
        }


def check_channel_member(user_id, channel):
    result = telegram(
        "getChatMember",
        {
            "chat_id": channel,
            "user_id": user_id
        }
    )

    if not result.get("ok"):
        return False

    status = result["result"]["status"]

    return status in [
        "creator",
        "administrator",
        "member"
    ]


def check_all_channels(user_id):
    results = []

    for channel in REQUIRED_CHANNELS:

        joined = check_channel_member(
            user_id,
            channel
        )

        results.append({
            "channel": channel,
            "joined": joined
        })

    all_joined = all(
        item["joined"]
        for item in results
    )

    return {
        "all_joined": all_joined,
        "channels": results
    }


# =========================================================
# USER
# =========================================================

def create_or_get_user(
    telegram_id,
    username=None,
    first_name=None
):

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT telegram_id,
               username,
               first_name,
               balance,
               referral_code
        FROM users
        WHERE telegram_id = %s
        """,
        (telegram_id,)
    )

    user = cur.fetchone()

    if user:

        cur.close()
        conn.close()

        return {
            "telegram_id": user[0],
            "username": user[1],
            "first_name": user[2],
            "balance": float(user[3]),
            "referral_code": user[4]
        }

    referral_code = secrets.token_urlsafe(6)

    cur.execute(
        """
        INSERT INTO users (
            telegram_id,
            username,
            first_name,
            referral_code
        )
        VALUES (%s,%s,%s,%s)
        RETURNING telegram_id,
                  username,
                  first_name,
                  balance,
                  referral_code
        """,
        (
            telegram_id,
            username,
            first_name,
            referral_code
        )
    )

    user = cur.fetchone()

    conn.commit()

    cur.close()
    conn.close()

    return {
        "telegram_id": user[0],
        "username": user[1],
        "first_name": user[2],
        "balance": float(user[3]),
        "referral_code": user[4]
    }


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():
    return send_from_directory(
        os.path.dirname(__file__),
        "index.html"
    )


# =========================================================
# INITIALIZE
# =========================================================

@app.route("/api/init", methods=["POST"])
def initialize():

    data = request.get_json() or {}

    telegram_id = data.get("telegram_id")
    username = data.get("username")
    first_name = data.get("first_name")

    if not telegram_id:
        return jsonify({
            "ok": False,
            "error": "telegram_id required"
        }), 400

    user = create_or_get_user(
        telegram_id,
        username,
        first_name
    )

    membership = check_all_channels(
        telegram_id
    )

    return jsonify({
        "ok": True,
        "user": user,
        "membership": membership
    })


# =========================================================
# CHECK CHANNELS
# =========================================================

@app.route("/api/check-membership", methods=["POST"])
def membership():

    data = request.get_json() or {}

    telegram_id = data.get("telegram_id")

    if not telegram_id:
        return jsonify({
            "ok": False,
            "error": "telegram_id required"
        }), 400

    result = check_all_channels(
        telegram_id
    )

    return jsonify({
        "ok": True,
        **result
    })


# =========================================================
# BALANCE
# =========================================================

@app.route("/api/balance", methods=["POST"])
def balance():

    data = request.get_json() or {}

    telegram_id = data.get("telegram_id")

    if not telegram_id:
        return jsonify({
            "ok": False,
            "error": "telegram_id required"
        }), 400

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT balance
        FROM users
        WHERE telegram_id = %s
        """,
        (telegram_id,)
    )

    row = cur.fetchone()

    cur.close()
    conn.close()

    if not row:
        return jsonify({
            "ok": False,
            "error": "User not found"
        }), 404

    return jsonify({
        "ok": True,
        "balance": float(row[0])
    })


# =========================================================
# START AD SESSION
# =========================================================

@app.route("/api/ad/start", methods=["POST"])
def start_ad():

    data = request.get_json() or {}

    telegram_id = data.get("telegram_id")

    if not telegram_id:
        return jsonify({
            "ok": False,
            "error": "telegram_id required"
        }), 400

    membership = check_all_channels(
        telegram_id
    )

    if not membership["all_joined"]:
        return jsonify({
            "ok": False,
            "error": "Join all required channels first",
            "membership": membership
        }), 403

    nonce = secrets.token_urlsafe(32)

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO ad_sessions (
            telegram_id,
            nonce
        )
        VALUES (%s,%s)
        """,
        (
            telegram_id,
            nonce
        )
    )

    conn.commit()

    cur.close()
    conn.close()

    return jsonify({
        "ok": True,
        "nonce": nonce,
        "reward": 0.10
    })


# =========================================================
# COMPLETE AD
# =========================================================

@app.route("/api/ad/complete", methods=["POST"])
def complete_ad():

    data = request.get_json() or {}

    telegram_id = data.get("telegram_id")
    nonce = data.get("nonce")

    if not telegram_id or not nonce:
        return jsonify({
            "ok": False,
            "error": "Invalid request"
        }), 400

    membership = check_all_channels(
        telegram_id
    )

    if not membership["all_joined"]:
        return jsonify({
            "ok": False,
            "error": "Join all required channels"
        }), 403

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id, completed
        FROM ad_sessions
        WHERE telegram_id = %s
          AND nonce = %s
        FOR UPDATE
        """,
        (
            telegram_id,
            nonce
        )
    )

    session = cur.fetchone()

    if not session:
        conn.rollback()
        cur.close()
        conn.close()

        return jsonify({
            "ok": False,
            "error": "Invalid ad session"
        }), 400

    if session[1]:
        conn.rollback()
        cur.close()
        conn.close()

        return jsonify({
            "ok": False,
            "error": "Ad already rewarded"
        }), 400

    reward = 0.10

    cur.execute(
        """
        UPDATE ad_sessions
        SET completed = TRUE
        WHERE id = %s
        """,
        (session[0],)
    )

    cur.execute(
        """
        UPDATE users
        SET balance = balance + %s
        WHERE telegram_id = %s
        """,
        (
            reward,
            telegram_id
        )
    )

    cur.execute(
        """
        INSERT INTO transactions (
            telegram_id,
            type,
            amount,
            description
        )
        VALUES (%s,%s,%s,%s)
        """,
        (
            telegram_id,
            "ad_reward",
            reward,
            "Watch ad reward"
        )
    )

    conn.commit()

    cur.close()
    conn.close()

    return jsonify({
        "ok": True,
        "reward": reward
    })


# =========================================================
# WITHDRAW
# =========================================================

@app.route("/api/withdraw", methods=["POST"])
def withdraw():

    data = request.get_json() or {}

    telegram_id = data.get("telegram_id")
    amount = data.get("amount")
    method = data.get("method")
    account = data.get("account")

    if not all([
        telegram_id,
        amount,
        method,
        account
    ]):
        return jsonify({
            "ok": False,
            "error": "Missing fields"
        }), 400

    try:
        amount = float(amount)
    except Exception:
        return jsonify({
            "ok": False,
            "error": "Invalid amount"
        }), 400

    # LIVE CHANNEL CHECK
    membership = check_all_channels(
        telegram_id
    )

    if not membership["all_joined"]:
        return jsonify({
            "ok": False,
            "error": "You must join all required channels",
            "membership": membership
        }), 403

    minimum = 10.00

    if amount < minimum:
        return jsonify({
            "ok": False,
            "error": f"Minimum withdrawal is {minimum:.2f} ETB"
        }), 400

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT balance
        FROM users
        WHERE telegram_id = %s
        FOR UPDATE
        """,
        (telegram_id,)
    )

    row = cur.fetchone()

    if not row:
        conn.rollback()
        cur.close()
        conn.close()

        return jsonify({
            "ok": False,
            "error": "User not found"
        }), 404

    balance_value = float(row[0])

    if balance_value < amount:

        conn.rollback()
        cur.close()
        conn.close()

        return jsonify({
            "ok": False,
            "error": "Insufficient balance"
        }), 400

    cur.execute(
        """
        SELECT id
        FROM withdrawals
        WHERE telegram_id = %s
          AND status = 'pending'
        LIMIT 1
        """,
        (telegram_id,)
    )

    pending = cur.fetchone()

    if pending:

        conn.rollback()
        cur.close()
        conn.close()

        return jsonify({
            "ok": False,
            "error": "You already have a pending withdrawal"
        }), 400

    cur.execute(
        """
        UPDATE users
        SET balance = balance - %s
        WHERE telegram_id = %s
        """,
        (
            amount,
            telegram_id
        )
    )

    cur.execute(
        """
        INSERT INTO withdrawals (
            telegram_id,
            amount,
            method,
            account
        )
        VALUES (%s,%s,%s,%s)
        RETURNING id
        """,
        (
            telegram_id,
            amount,
            method,
            account
        )
    )

    withdrawal_id = cur.fetchone()[0]

    cur.execute(
        """
        INSERT INTO transactions (
            telegram_id,
            type,
            amount,
            description
        )
        VALUES (%s,%s,%s,%s)
        """,
        (
            telegram_id,
            "withdrawal",
            -amount,
            f"Withdrawal #{withdrawal_id}"
        )
    )

    conn.commit()

    cur.close()
    conn.close()

    # ADMIN NOTIFICATION
    telegram(
        "sendMessage",
        {
            "chat_id": ADMIN_ID,
            "text": (
                "💰 NEW WITHDRAWAL\n\n"
                f"User ID: {telegram_id}\n"
                f"Amount: {amount:.2f} ETB\n"
                f"Method: {method}\n"
                f"Account: {account}\n"
                f"Withdrawal ID: #{withdrawal_id}"
            )
        }
    )

    return jsonify({
        "ok": True,
        "withdrawal_id": withdrawal_id,
        "status": "pending"
    })


# =========================================================
# TELEGRAM WEBHOOK
# =========================================================

@app.route("/api/webhook", methods=["POST"])
def webhook():

    update = request.get_json(
        silent=True
    ) or {}

    message = update.get("message")

    if not message:
        return jsonify({
            "ok": True
        })

    text = message.get("text", "")
    chat = message.get("chat", {})
    user = message.get("from", {})

    chat_id = chat.get("id")
    user_id = user.get("id")

    if text.startswith("/start"):

        create_or_get_user(
            user_id,
            user.get("username"),
            user.get("first_name")
        )

        webapp_url = os.getenv(
            "WEBAPP_URL",
            ""
        )

        telegram(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": (
                    "Welcome to Adewa! 💰\n\n"
                    "Join all required channels "
                    "then open the Mini App."
                ),
                "reply_markup": {
                    "inline_keyboard": [
                        [
                            {
                                "text": "🚀 Open Mini App",
                                "web_app": {
                                    "url": webapp_url
                                }
                            }
                        ]
                    ]
                }
            }
        )

    return jsonify({
        "ok": True
    })


# =========================================================
# HEALTH
# =========================================================

@app.route("/api/health")
def health():

    return jsonify({
        "ok": True,
        "service": "Adewa",
        "channels": REQUIRED_CHANNELS
    })


# =========================================================
# STARTUP
# =========================================================

try:
    init_db()
except Exception as e:
    print("Database initialization error:", e)


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(
            os.getenv("PORT", 5000)
        )
  )
