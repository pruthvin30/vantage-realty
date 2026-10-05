from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
import sqlite3
import hashlib
import re
import os

app = Flask(__name__)
CORS(app)

# Groq API
client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=os.environ.get("GROQ_API_KEY")
)

# Database path
DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "users.db"
)


# ---------------- DATABASE ----------------

def init_db():
    conn = sqlite3.connect(DB_PATH)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


init_db()


# ---------------- PASSWORD ----------------

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def validate_password(password):

    if len(password) < 12 or len(password) > 16:
        return "Password must be 12-16 characters long"

    if not re.search(r"[A-Z]", password):
        return "Password must contain at least one uppercase letter"

    if not re.search(r"[a-z]", password):
        return "Password must contain at least one lowercase letter"

    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return "Password must contain at least one special character"

    return None


# ---------------- EMAIL ----------------

def validate_email(email):
    return re.match(
        r"^[\w\.-]+@[\w\.-]+\.\w+$",
        email
    ) is not None


# ---------------- SIGNUP ----------------

@app.route("/signup", methods=["POST"])
def signup():

    data = request.json

    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not name:
        return jsonify({
            "success": False,
            "message": "Please enter your name"
        }), 400

    if not validate_email(email):
        return jsonify({
            "success": False,
            "message": "Please enter a valid email"
        }), 400

    pw_error = validate_password(password)

    if pw_error:
        return jsonify({
            "success": False,
            "message": pw_error
        }), 400

    conn = sqlite3.connect(DB_PATH)

    try:

        conn.execute(
            """
            INSERT INTO users
            (name, email, password_hash)
            VALUES (?, ?, ?)
            """,
            (name, email, hash_password(password))
        )

        conn.commit()

        return jsonify({
            "success": True,
            "name": name
        })

    except sqlite3.IntegrityError:

        return jsonify({
            "success": False,
            "message": "An account with this email already exists"
        }), 400

    finally:
        conn.close()


# ---------------- LOGIN ----------------

@app.route("/login", methods=["POST"])
def login():

    data = request.json

    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    conn = sqlite3.connect(DB_PATH)

    cursor = conn.execute(
        "SELECT name, password_hash FROM users WHERE email = ?",
        (email,)
    )

    row = cursor.fetchone()

    conn.close()

    if row and row[1] == hash_password(password):

        return jsonify({
            "success": True,
            "name": row[0]
        })

    return jsonify({
        "success": False,
        "message": "Invalid email or password"
    }), 401


# ---------------- CHATBOT ----------------

@app.route("/chat", methods=["POST"])
def chat():

    data = request.json

    user_message = data.get("message", "")
    history = data.get("history", [])
    user_name = data.get("name", "")

    name_instruction = ""

    if user_name:
        name_instruction = (
            f" The person you're talking to is named {user_name}. "
            "Address them by their first name naturally in your replies, "
            "especially in greetings."
        )

    system_prompt = (
        "You are the AI assistant for Vantage Realty, a real estate "
        "platform covering Bangalore and Chennai. You help visitors "
        "with questions about buying apartments or land, understanding "
        "locality prices, and general real estate guidance for these "
        "two cities. Keep answers concise and helpful. If asked about "
        "a specific listing's exact price or availability, direct them "
        "to browse the Listings page or use the Enquire button."
        + name_instruction
    )

    messages = (
        [{"role": "system", "content": system_prompt}]
        + history
        + [{"role": "user", "content": user_message}]
    )

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        max_tokens=500,
        messages=messages
    )

    return jsonify({
        "reply": response.choices[0].message.content
    })


# ---------------- RUN SERVER ----------------

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False
    )