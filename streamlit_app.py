#!/usr/bin/env python3
"""
ArthikAI — Streamlit Cloud Deployment Entry Point
Embeds the complete ArthikAI frontend with full backend logic.
"""

import os
import sys
import json
import re
import sqlite3
import hashlib
import secrets
import math
import threading
import urllib.request
import urllib.error
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse

import streamlit as st
import streamlit.components.v1 as components

# ─────────────────────────────────────────────
# Streamlit Page Config
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="ArthikAI — Financial Inclusion Assistant",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="collapsed",
    menu_items={
        "Get Help": "https://github.com/aparnamishraa26-lab/arthik-ai",
        "About": "ArthikAI — SDG 1 Financial Inclusion Platform",
    },
)

# ─────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = os.path.join(BASE_DIR, "public")
DB_FILE = os.path.join(BASE_DIR, "arthik_data.db")
KB_FILE = os.path.join(BASE_DIR, "knowledge_base.json")

# ─────────────────────────────────────────────
# Database
# ─────────────────────────────────────────────
def get_db_connection():
    conn = sqlite3.connect(DB_FILE, timeout=10.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    with get_db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                income INTEGER DEFAULT 0,
                dependents INTEGER DEFAULT 1,
                city TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                session_id TEXT NOT NULL,
                sender TEXT NOT NULL,
                message TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_session ON chat_history(session_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_user ON chat_history(user_id)")
        conn.commit()

init_db()

# ─────────────────────────────────────────────
# API Keys from Streamlit Secrets / Env
# ─────────────────────────────────────────────
def _get_secret(key):
    try:
        return st.secrets.get(key, os.environ.get(key, ""))
    except Exception:
        return os.environ.get(key, "")

GEMINI_API_KEY = _get_secret("GEMINI_API_KEY")
GROQ_API_KEY   = _get_secret("GROQ_API_KEY")
OPENAI_API_KEY = _get_secret("OPENAI_API_KEY")

# ─────────────────────────────────────────────
# Auth Helpers
# ─────────────────────────────────────────────
def hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000)
    return key.hex(), salt

def verify_password(stored_hash, salt, input_password):
    key, _ = hash_password(input_password, salt)
    return secrets.compare_digest(stored_hash, key)

def get_user_from_token(token):
    if not token:
        return None
    with get_db_connection() as conn:
        row = conn.execute("""
            SELECT u.id, u.name, u.email, u.income, u.dependents, u.city
            FROM sessions s
            JOIN users u ON s.user_id = u.id
            WHERE s.token = ?
        """, (token,)).fetchone()
        return dict(row) if row else None

# ─────────────────────────────────────────────
# Financial Engine
# ─────────────────────────────────────────────
def compute_budget_70_20_10(income):
    income = int(income)
    needs = int(math.floor(income * 0.70))
    savings_debt = int(math.floor(income * 0.20))
    buffer = income - needs - savings_debt
    daily_savings = int(math.floor(savings_debt / 30))
    return {
        "income": income,
        "needs_70": needs,
        "savings_debt_20": savings_debt,
        "buffer_10": buffer,
        "daily_savings": daily_savings,
        "emergency_3mo": savings_debt * 3,
        "emergency_6mo": savings_debt * 6,
    }

def extract_numbers(text):
    found = []
    for m in re.findall(r"(\d+(?:\.\d+)?)\s*(?:k|thousand)", text, re.IGNORECASE):
        found.append(int(float(m) * 1000))
    for m in re.findall(r"(\d+(?:\.\d+)?)\s*(?:lakh|lac)", text, re.IGNORECASE):
        found.append(int(float(m) * 100000))
    for r in re.findall(r"(?:₹|rs\.?|inr)?\s*(\b\d{2,7}\b)", text, re.IGNORECASE):
        val = int(r)
        if val not in found and val >= 10:
            found.append(val)
    return found

SYSTEM_PROMPT = """You are Arthik Sathi, an empathetic, highly practical and mathematically rigorous Personal Financial Advisor.
Your mission is to help individuals and families build micro-emergency funds, escape high-interest moneylender debt, and access government welfare schemes.

Strict Guidelines:
1. Always maintain an empathetic, practical, and non-judgmental tone.
2. Ensure 100% mathematical precision in all budget breakdowns (70% Needs, 20% Savings/Debt, 10% Buffer).
3. If the user asks for a personalized budget/plan but hasn't provided their monthly income, politely request their income, family dependents, and major expenses before giving generic advice.
4. Recommend realistic micro-goals (e.g. saving ₹20-₹50/day rather than asking them to save 6 months of salary immediately).
5. Recommend official public schemes when relevant (PM Jan Dhan Yojana, PM Suraksha Bima, PM Jeevan Jyoti, APY, Mudra Shishu, PM SVANidhi).
6. Strictly refuse speculative stock trading, cryptocurrency, or get-rich-quick advice.
7. Include the educational financial guidance disclaimer.
"""

def generate_contextual_response(user_msg, user_profile=None, context_history=None):
    msg_lower = user_msg.lower()
    nums = extract_numbers(user_msg)
    user_income = user_profile.get("income", 0) if user_profile else 0
    dependents = user_profile.get("dependents", 1) if user_profile else 1

    if nums:
        possible_income = max(nums)
        if 2000 <= possible_income <= 500000 and any(w in msg_lower for w in ["salary","income","kama","earn","budget","paisa","rupay","mahina","month"]):
            user_income = possible_income

    if any(k in msg_lower for k in ["crypto","bitcoin","stocks","trading","intraday","forex","get rich","double money","lottery","satta"]):
        return (
            "### 🛡️ Financial Safety Advisory: Capital Protection First\n\n"
            "I cannot provide stock market picks, cryptocurrency speculation, or trading advice.\n\n"
            "For individual and household security, high-risk speculative trading carries an alarming probability of **total capital wipeout**.\n\n"
            "**Recommended Wealth Protection Hierarchy:**\n"
            "1. **Starter Emergency Reserve**: Keep ₹2,000 - ₹5,000 in a safe, zero-balance bank account.\n"
            "2. **Micro-Insurance**: Enroll in PMSBY (₹20/year) and PMJJBY (₹436/year) to protect dependents.\n"
            "3. **Debt Freedom**: Eliminate high-interest informal loans before investing anywhere.\n"
            "4. **Guaranteed Social Pension**: Enroll in Atal Pension Yojana (APY) for secure life-long pension."
        )

    asks_for_plan = any(w in msg_lower for w in ["plan","budget","financial plan","kharcha manage","manage my money","bachat kaise"])
    has_income = (user_income > 0) or ("limited" in msg_lower and "income" in msg_lower)
    if asks_for_plan and not has_income and not nums:
        return (
            "### 📋 To Provide an Accurate Financial Plan, I Need a Few Details\n\n"
            "To ensure there are **zero calculation errors** and to give you an actionable, realistic plan tailored specifically for you, please share:\n\n"
            "1. **Monthly Income**: How much do you (or your household) take home each month?\n"
            "2. **Family Dependents**: How many family members depend on this income?\n"
            "3. **Fixed Monthly Outflows**: What is your approximate monthly rent and grocery/ration cost?\n"
            "4. **Existing Loans**: Do you have any active moneylender or credit debt?\n\n"
            "*(You can also update these directly in your Profile at the top right, or simply type them here!)*"
        )

    if user_income > 0 and (nums or any(w in msg_lower for w in ["budget","plan","salary","income","divide","70/20/10","kama","calculate"])):
        calc = compute_budget_70_20_10(user_income)
        return (
            f"### 📊 Verified Personal Budget Allocation for Monthly Income: ₹{calc['income']:,}\n\n"
            f"Here is your mathematically verified **70/20/10 Financial Framework** tailored for household security:\n\n"
            f"1. **70% Essentials (Needs) = ₹{calc['needs_70']:,} / month**\n"
            f"   - Food grains/ration, rent, electricity, cooking gas, essential medicines, and school fees.\n\n"
            f"2. **20% Debt Clearance & Emergency Buffer = ₹{calc['savings_debt_20']:,} / month**\n"
            f"   - That breaks down to saving exactly **₹{calc['daily_savings']:,} per day**.\n"
            f"   - **Step A**: Allocate 10-15% (₹{int(user_income*0.12):,}) towards clearing high-interest debt first.\n"
            f"   - **Step B**: Channel the remaining into a separate bank account.\n"
            f"   - **Target 1 (3 Months Buffer)**: ₹{calc['emergency_3mo']:,}\n"
            f"   - **Target 2 (6 Months Security Cushion)**: ₹{calc['emergency_6mo']:,}\n\n"
            f"3. **10% Flexible Buffer = ₹{calc['buffer_10']:,} / month**\n"
            f"   - Unavoidable personal expenses, minor family needs, or urgent transport.\n\n"
            f"💡 **Next Action Step**: Put aside **₹{calc['daily_savings']:,}** today in a separate zero-balance account."
        )

    if ("limited" in msg_lower and "income" in msg_lower) or ("emergency fund" in msg_lower) or ("build a small emergency fund" in msg_lower):
        return (
            "### 4 Practical Steps to Manage Expenses & Build an Emergency Fund on a Limited Income\n\n"
            "When income is tight, traditional financial advice ('save 6 months of expenses') feels impossible. Here is an actionable 4-step framework:\n\n"
            "1. **Set a Realistic Micro-Target (₹1,000 to ₹3,000 First)**:\n"
            "   - Your first goal is a small 'shock absorber' that prevents borrowing from high-interest lenders.\n\n"
            "2. **The 70 / 20 / 10 Low-Income Budget Rule**:\n"
            "   - **70% Essentials**: Groceries/ration, rent, electricity, medicines, and child schooling.\n"
            "   - **20% Debt Relief & Emergency Savings**: Clear high-interest loans first, then save ₹20 - ₹50 daily.\n"
            "   - **10% Discretionary Buffer**: A small safety cushion for unavoidable expenses.\n\n"
            "3. **Audit & Plug 'Invisible Leaks'**:\n"
            "   - Track every ₹10-₹20 expense for 7 days. Redirecting just **₹30 a day saves ₹900 a month**.\n\n"
            "4. **Separate the Cushion (Zero-Balance Rule)**:\n"
            "   - Open a **Pradhan Mantri Jan Dhan Yojana (PMJDY)** zero-balance bank account for emergency savings.\n\n"
            "**Action Item for Today**: Put aside just ₹30 or ₹50 tonight. Consistency beats amount every single time."
        )

    if any(w in msg_lower for w in ["vendor","thela","hawker","street vendor","patri","svanidhi"]):
        return (
            "### 🛒 PM SVANidhi — Collateral-Free Working Capital for Street Vendors\n\n"
            "- **1st Tranche**: **₹10,000** collateral-free loan with 1-year tenure.\n"
            "- **2nd & 3rd Tranches**: Increases to **₹20,000** and then **₹50,000** upon timely repayment.\n"
            "- **7% Interest Subsidy**: Direct government interest cashback into your bank account.\n"
            "- **Digital Cashback**: Up to ₹1,200/year cashback on UPI QR transactions.\n\n"
            "**How to Apply**: Visit `pmsvanidhi.mohua.gov.in` or any Common Service Center (CSC)."
        )

    if any(w in msg_lower for w in ["debt","karz","karza","loan","moneylender","sahukar","byaaj","interest","chhutkara"]):
        return (
            "### ⛓️ How to Escape High-Interest Moneylenders (Sahukar Debt)\n\n"
            "Local moneylenders charging 5% to 10% per *month* (60% to 120% annually) drain households into poverty.\n\n"
            "1. **The Avalanche Debt Payoff**: List all debts by monthly interest rate. Throw every extra rupee at the highest-interest debt first.\n"
            "2. **Refinance into Formal Micro-Credit**: Apply for a **PM MUDRA Shishu Loan** (collateral-free up to ₹50,000 at 9-12% annual interest).\n"
            "3. **Join a Self-Help Group (SHG)**: Under NRLM/NULM, SHGs provide low-interest emergency credit pools at 7-9% annual interest."
        )

    if "jan dhan" in msg_lower or "pmjdy" in msg_lower or "bank account" in msg_lower or "khata" in msg_lower:
        return (
            "### 🏦 Pradhan Mantri Jan Dhan Yojana (PMJDY) — Complete Guide\n\n"
            "**Key Benefits:**\n"
            "- **Zero Minimum Balance**: Never charged a penalty, even if your balance is ₹0.\n"
            "- **Free RuPay Debit Card**: Includes built-in **₹2 Lakh accidental insurance cover**.\n"
            "- **Overdraft Facility up to ₹10,000**: After 6 months of active account maintenance.\n"
            "- **Direct Subsidies (DBT)**: All government welfare credits flow straight into this account.\n\n"
            "**Required Documents**: Aadhaar Card and 2 passport photos at any nationalized bank branch."
        )

    if any(w in msg_lower for w in ["pmsby","pmjjby","bima","insurance","suraksha","jeevan jyoti"]):
        return (
            "### 🛡️ Government Micro-Insurance: PMSBY & PMJJBY\n\n"
            "Protect your family for less than ₹1.25 per day:\n\n"
            "1. **PM Suraksha Bima Yojana (PMSBY)**:\n"
            "   - **Coverage**: ₹2 Lakh on accidental death or permanent total disability.\n"
            "   - **Premium**: Only **₹20 per YEAR**.\n\n"
            "2. **PM Jeevan Jyoti Bima Yojana (PMJJBY)**:\n"
            "   - **Coverage**: ₹2 Lakh life cover payable to your nominee on death due to any reason.\n"
            "   - **Premium**: **₹436 per YEAR** (approx ₹36/month)."
        )

    if any(w in msg_lower for w in ["leak","kharch","bacha","save money","spend","saving","snack","chai","samosa"]):
        return (
            "### 🔍 Plugging Daily Expense Leaks\n\n"
            "1. **The Daily Snack Calculation**: Saving ₹40/day = **₹1,200/month** = **₹14,400/year**.\n"
            "2. **Bulk vs Daily Purchases**: Buying staple ration items in monthly bulk saves 25-40%.\n"
            "3. **Mobile Recharge Optimization**: Select a single consolidated 84-day or 365-day plan."
        )

    return (
        "Namaste! I am **Arthik Sathi**, your Personal Financial Advisor.\n\n"
        "I am ready to help you with:\n"
        "- **Accurate 70/20/10 Budgeting**: Tell me your monthly income for exact spending allocations.\n"
        "- **Emergency Fund Plan**: Step-by-step guidance to save ₹20 - ₹50 daily.\n"
        "- **Debt Elimination**: Plans to escape informal high-interest moneylender loans.\n"
        "- **Government Social Protection**: PM Jan Dhan, PMSBY, APY, and PM SVANidhi.\n\n"
        "What is your monthly income or financial question today?"
    )

def call_llm_api(user_msg, context_history=None):
    messages_payload = [{"role": "system", "content": SYSTEM_PROMPT}]
    if context_history:
        for item in context_history[-6:]:
            role = "user" if item["sender"] == "user" else "assistant"
            messages_payload.append({"role": role, "content": item["message"]})
    messages_payload.append({"role": "user", "content": user_msg})

    if GEMINI_API_KEY:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
            prompt_text = SYSTEM_PROMPT + "\n\n"
            if context_history:
                for c in context_history[-4:]:
                    prompt_text += f"{c['sender'].capitalize()}: {c['message']}\n"
            prompt_text += f"User: {user_msg}\nAssistant:"
            payload = {"contents": [{"parts": [{"text": prompt_text}]}], "generationConfig": {"temperature": 0.4, "maxOutputTokens": 800}}
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=8) as response:
                result = json.loads(response.read().decode("utf-8"))
                text = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                if text:
                    return text.strip()
        except Exception as e:
            print("Gemini API error:", e)

    if GROQ_API_KEY:
        try:
            url = "https://api.groq.com/openai/v1/chat/completions"
            payload = {"model": "llama-3.1-8b-instant", "messages": messages_payload, "temperature": 0.4, "max_tokens": 800}
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "Authorization": f"Bearer {GROQ_API_KEY}"})
            with urllib.request.urlopen(req, timeout=8) as response:
                result = json.loads(response.read().decode("utf-8"))
                text = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                if text:
                    return text.strip()
        except Exception as e:
            print("Groq API error:", e)

    return None

def get_chatbot_response(user_msg, user_profile=None, context_history=None):
    llm_resp = call_llm_api(user_msg, context_history)
    if llm_resp:
        return llm_resp
    return generate_contextual_response(user_msg, user_profile, context_history)

# ─────────────────────────────────────────────
# Embedded HTTP Server (for arena /chat endpoint)
# ─────────────────────────────────────────────
_server_started = False
_SERVER_PORT = 5000

class _ArthikHandler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def _json(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self._cors()
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _body(self):
        n = int(self.headers.get("Content-Length", 0))
        if n <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode())
        except Exception:
            return {}

    def _auth_user(self):
        ah = self.headers.get("Authorization", "")
        if ah.startswith("Bearer "):
            return get_user_from_token(ah[7:].strip())
        return None

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path == "/health":
            self._json(200, {"status": "ok", "service": "ArthikAI"})
            return
        if self.path == "/api/auth/me":
            u = self._auth_user()
            if not u:
                self._json(401, {"error": "Unauthorized"})
                return
            self._json(200, {"user": u})
            return
        if self.path.startswith("/api/chat/history"):
            session_id = ""
            if "?" in self.path:
                params = urllib.parse.parse_qs(self.path.split("?")[1])
                session_id = params.get("session_id", [""])[0]
            u = self._auth_user()
            user_id = u["id"] if u else None
            with get_db_connection() as conn:
                if user_id and session_id:
                    rows = conn.execute("SELECT sender, message, timestamp FROM chat_history WHERE session_id=? OR user_id=? ORDER BY id ASC LIMIT 100", (session_id, user_id)).fetchall()
                elif session_id:
                    rows = conn.execute("SELECT sender, message, timestamp FROM chat_history WHERE session_id=? ORDER BY id ASC LIMIT 100", (session_id,)).fetchall()
                else:
                    rows = []
            self._json(200, {"history": [dict(r) for r in rows]})
            return
        # Serve static files
        req_path = self.path.split("?")[0]
        if req_path in ("/", ""):
            req_path = "/index.html"
        import mimetypes
        file_path = os.path.join(PUBLIC_DIR, os.path.normpath(req_path.lstrip("/")))
        if os.path.isfile(file_path):
            mime, _ = mimetypes.guess_type(file_path)
            with open(file_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", mime or "text/plain")
            self.send_header("Content-Length", str(len(content)))
            self._cors()
            self.end_headers()
            self.wfile.write(content)
            return
        self.send_response(404)
        self.end_headers()
        self.wfile.write(b"404")

    def do_POST(self):
        if self.path == "/api/auth/signup":
            d = self._body()
            name, email, password = d.get("name","").strip(), d.get("email","").strip().lower(), d.get("password","").strip()
            income, dependents, city = int(d.get("income",0)), int(d.get("dependents",1)), d.get("city","").strip()
            if not name or not email or not password:
                self._json(400, {"error": "Name, email and password are required"})
                return
            pwd_hash, salt = hash_password(password)
            user_id = "usr_" + secrets.token_hex(8)
            try:
                with get_db_connection() as conn:
                    conn.execute("INSERT INTO users (id,name,email,password_hash,salt,income,dependents,city) VALUES (?,?,?,?,?,?,?,?)", (user_id,name,email,pwd_hash,salt,income,dependents,city))
                    token = "tok_" + secrets.token_hex(20)
                    conn.execute("INSERT INTO sessions (token,user_id) VALUES (?,?)", (token,user_id))
                    conn.commit()
                self._json(200, {"token": token, "user": {"id":user_id,"name":name,"email":email,"income":income,"dependents":dependents,"city":city}})
            except sqlite3.IntegrityError:
                self._json(400, {"error": "An account with this email already exists."})
            return

        if self.path == "/api/auth/login":
            d = self._body()
            email, password = d.get("email","").strip().lower(), d.get("password","").strip()
            if not email or not password:
                self._json(400, {"error": "Email and password are required."})
                return
            with get_db_connection() as conn:
                row = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
                if not row or not verify_password(row["password_hash"], row["salt"], password):
                    self._json(401, {"error": "Invalid email or password."})
                    return
                token = "tok_" + secrets.token_hex(20)
                conn.execute("INSERT INTO sessions (token,user_id) VALUES (?,?)", (token, row["id"]))
                conn.commit()
            self._json(200, {"token": token, "user": {"id":row["id"],"name":row["name"],"email":row["email"],"income":row["income"],"dependents":row["dependents"],"city":row["city"]}})
            return

        if self.path == "/api/auth/update_profile":
            u = self._auth_user()
            if not u:
                self._json(401, {"error": "Unauthorized"})
                return
            d = self._body()
            income = int(d.get("income", u["income"]))
            dependents = int(d.get("dependents", u["dependents"]))
            city = d.get("city", u["city"]).strip()
            with get_db_connection() as conn:
                conn.execute("UPDATE users SET income=?,dependents=?,city=? WHERE id=?", (income,dependents,city,u["id"]))
                conn.commit()
            u.update({"income":income,"dependents":dependents,"city":city})
            self._json(200, {"user": u})
            return

        if self.path in ["/chat", "/chat/"]:
            d = self._body()
            message = d.get("message","").strip()
            session_id = d.get("session_id","arena_default_session")
            if not message:
                self._json(400, {"error": "'message' field is required."})
                return
            u = self._auth_user()
            user_id = u["id"] if u else None
            context_history = []
            with get_db_connection() as conn:
                rows = conn.execute("SELECT sender,message FROM chat_history WHERE session_id=? ORDER BY id DESC LIMIT 6", (session_id,)).fetchall()
                context_history = [dict(r) for r in reversed(rows)]
            reply = get_chatbot_response(message, user_profile=u, context_history=context_history)
            try:
                with get_db_connection() as conn:
                    conn.execute("INSERT INTO chat_history (user_id,session_id,sender,message) VALUES (?,?,'user',?)", (user_id,session_id,message))
                    conn.execute("INSERT INTO chat_history (user_id,session_id,sender,message) VALUES (?,?,'assistant',?)", (user_id,session_id,reply))
                    conn.commit()
            except Exception as e:
                print("Error saving chat history:", e)
            self._json(200, {"response": reply})
            return

        self.send_response(404)
        self.end_headers()

    def do_DELETE(self):
        if self.path.startswith("/api/chat/history"):
            session_id = ""
            if "?" in self.path:
                params = urllib.parse.parse_qs(self.path.split("?")[1])
                session_id = params.get("session_id",[""])[0]
            u = self._auth_user()
            user_id = u["id"] if u else None
            with get_db_connection() as conn:
                if user_id:
                    conn.execute("DELETE FROM chat_history WHERE user_id=?", (user_id,))
                if session_id:
                    conn.execute("DELETE FROM chat_history WHERE session_id=?", (session_id,))
                conn.commit()
            self._json(200, {"success": True, "message": "Chat history cleared successfully."})
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress server logs in Streamlit output

def _start_backend_server():
    global _server_started
    if not _server_started:
        try:
            httpd = HTTPServer(("0.0.0.0", _SERVER_PORT), _ArthikHandler)
            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            _server_started = True
            print(f"[ArthikAI] Backend server started on port {_SERVER_PORT}")
        except Exception as e:
            print(f"[ArthikAI] Backend server error: {e}")

_start_backend_server()

# ─────────────────────────────────────────────
# Load Frontend Files
# ─────────────────────────────────────────────
def load_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""

html_content = load_file(os.path.join(PUBLIC_DIR, "index.html"))
css_content  = load_file(os.path.join(PUBLIC_DIR, "style.css"))
js_content   = load_file(os.path.join(PUBLIC_DIR, "app.js"))

# Inject CSS and JS directly into the HTML so it works in the iframe
# Replace link/script tags with inline versions for Streamlit iframe
inline_html = html_content
# Inject CSS inline
if '<link rel="stylesheet" href="style.css">' in inline_html:
    inline_html = inline_html.replace(
        '<link rel="stylesheet" href="style.css">',
        f"<style>\n{css_content}\n</style>"
    )
elif "</head>" in inline_html:
    inline_html = inline_html.replace("</head>", f"<style>\n{css_content}\n</style>\n</head>")

# Inject JS inline (replace script src with inline)
if '<script src="app.js"></script>' in inline_html:
    inline_html = inline_html.replace(
        '<script src="app.js"></script>',
        f"<script>\n{js_content}\n</script>"
    )
elif "</body>" in inline_html:
    inline_html = inline_html.replace("</body>", f"<script>\n{js_content}\n</script>\n</body>")

# ─────────────────────────────────────────────
# Streamlit UI — Full-page iframe embed
# ─────────────────────────────────────────────

# Hide Streamlit default header/footer for clean full-page look
st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
    .block-container {
        padding: 0 !important;
        max-width: 100% !important;
    }
    .stApp {
        margin: 0;
        padding: 0;
    }
</style>
""", unsafe_allow_html=True)

# Embed the full ArthikAI app
components.html(inline_html, height=900, scrolling=True)
