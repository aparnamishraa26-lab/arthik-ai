#!/usr/bin/env python3
"""
ArthikAI — Streamlit Cloud Native App
SDG 1: Financial Inclusion Assistant
Full auth, persistent chat history, PDF export — pure Streamlit, no localhost calls.
"""

import os, re, json, math, sqlite3, hashlib, secrets, time, io
from datetime import datetime

import streamlit as st

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ArthikAI — Financial Inclusion Assistant",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE  = os.path.join(BASE_DIR, "arthik_data.db")

# ── Secrets ───────────────────────────────────────────────────────────────────
def _secret(k):
    try:    return st.secrets.get(k, os.environ.get(k, ""))
    except: return os.environ.get(k, "")

GROQ_API_KEY   = _secret("GROQ_API_KEY")
GEMINI_API_KEY = _secret("GEMINI_API_KEY")

# ── Database ──────────────────────────────────────────────────────────────────
@st.cache_resource
def _get_conn():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("""CREATE TABLE IF NOT EXISTS users(
        id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL, salt TEXT NOT NULL,
        income INTEGER DEFAULT 0, dependents INTEGER DEFAULT 1, city TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sessions(
        token TEXT PRIMARY KEY, user_id TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS chat_history(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, session_id TEXT NOT NULL,
        sender TEXT NOT NULL, message TEXT NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_session ON chat_history(session_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_user   ON chat_history(user_id)")
    conn.commit()
    return conn

db = _get_conn()

# ── Auth helpers ──────────────────────────────────────────────────────────────
def _hash(pwd, salt=None):
    if salt is None: salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pwd.encode(), salt.encode(), 100_000)
    return h.hex(), salt

def _verify(stored, salt, pwd):
    return secrets.compare_digest(stored, _hash(pwd, salt)[0])

def signup(name, email, password, income=0, dependents=1, city=""):
    pwd_hash, salt = _hash(password)
    uid   = "usr_" + secrets.token_hex(8)
    token = "tok_" + secrets.token_hex(20)
    try:
        db.execute("INSERT INTO users(id,name,email,password_hash,salt,income,dependents,city) VALUES(?,?,?,?,?,?,?,?)",
                   (uid, name, email.lower(), pwd_hash, salt, income, dependents, city))
        db.execute("INSERT INTO sessions(token,user_id) VALUES(?,?)", (token, uid))
        db.commit()
        return {"ok": True, "token": token,
                "user": {"id":uid,"name":name,"email":email,"income":income,"dependents":dependents,"city":city}}
    except sqlite3.IntegrityError:
        return {"ok": False, "error": "Email already registered."}

def login(email, password):
    row = db.execute("SELECT * FROM users WHERE email=?", (email.lower(),)).fetchone()
    if not row or not _verify(row["password_hash"], row["salt"], password):
        return {"ok": False, "error": "Invalid email or password."}
    token = "tok_" + secrets.token_hex(20)
    db.execute("INSERT INTO sessions(token,user_id) VALUES(?,?)", (token, row["id"]))
    db.commit()
    return {"ok": True, "token": token,
            "user": {"id":row["id"],"name":row["name"],"email":row["email"],
                     "income":row["income"],"dependents":row["dependents"],"city":row["city"]}}

def get_user(token):
    if not token: return None
    row = db.execute("""SELECT u.id,u.name,u.email,u.income,u.dependents,u.city
        FROM sessions s JOIN users u ON s.user_id=u.id WHERE s.token=?""", (token,)).fetchone()
    return dict(row) if row else None

def update_profile(uid, income, dependents, city):
    db.execute("UPDATE users SET income=?,dependents=?,city=? WHERE id=?", (income, dependents, city, uid))
    db.commit()

def save_msg(user_id, session_id, sender, message):
    db.execute("INSERT INTO chat_history(user_id,session_id,sender,message) VALUES(?,?,?,?)",
               (user_id, session_id, sender, message))
    db.commit()

def load_history(user_id, session_id):
    rows = db.execute(
        "SELECT sender,message,timestamp FROM chat_history WHERE user_id=? OR session_id=? ORDER BY id ASC LIMIT 200",
        (user_id, session_id)).fetchall()
    return [dict(r) for r in rows]

def clear_history(user_id, session_id):
    db.execute("DELETE FROM chat_history WHERE user_id=? OR session_id=?", (user_id, session_id))
    db.commit()

# ── Financial Engine ──────────────────────────────────────────────────────────
def calc_7020_10(income):
    income = int(income)
    needs  = int(math.floor(income * 0.70))
    save   = int(math.floor(income * 0.20))
    buf    = income - needs - save
    return {"income":income,"needs":needs,"save":save,"buf":buf,
            "daily":int(math.floor(save/30)),
            "em3":save*3,"em6":save*6}

def nums_in(text):
    found = []
    for m in re.findall(r"(\d+(?:\.\d+)?)\s*(?:k|thousand)", text, re.I): found.append(int(float(m)*1000))
    for m in re.findall(r"(\d+(?:\.\d+)?)\s*(?:lakh|lac)",   text, re.I): found.append(int(float(m)*100000))
    for r in re.findall(r"(?:₹|rs\.?|inr)?\s*(\b\d{2,7}\b)", text, re.I):
        v = int(r)
        if v not in found and v >= 10: found.append(v)
    return found

SYSTEM_PROMPT = """You are Arthik Sathi, an empathetic, mathematically rigorous Personal Financial Advisor for low-income Indian households.
Rules:
1. Respond in the same language the user writes (Hindi/English/Hinglish).
2. 100% accurate math — 70% Needs / 20% Save+Debt / 10% Buffer.
3. If user wants a plan but hasn't shared income → ask for income, dependents, city first.
4. Recommend micro-goals: ₹20-₹50/day savings. NOT "save 6 months instantly".
5. Recommend: PM Jan Dhan, PMSBY, PMJJBY, APY, MUDRA Shishu, PM SVANidhi when relevant.
6. Refuse crypto/stocks/trading advice firmly.
7. Always end with one clear action step.
8. Give detailed, personalised, unique answers every time — never repeat the same generic advice."""

def local_response(msg, profile=None):
    ml = msg.lower()
    ns = nums_in(msg)
    inc = profile.get("income", 0) if profile else 0
    dep = profile.get("dependents", 1) if profile else 1

    if ns:
        mx = max(ns)
        if 2000 <= mx <= 500000 and any(w in ml for w in ["salary","income","kama","earn","rupay","mahina","month","paisa"]):
            inc = mx

    # Guardrail
    if any(k in ml for k in ["crypto","bitcoin","stock","trading","intraday","forex","double money","lottery","satta"]):
        return ("🛡️ **Capital Protection Alert**\n\n"
                "Main speculative trading, crypto ya stock tips nahi de sakta.\n\n"
                "**Safer Wealth Building Hierarchy:**\n"
                "1. ₹2,000-₹5,000 Emergency Reserve → PMJDY zero-balance account\n"
                "2. PMSBY Insurance → only ₹20/year for ₹2 lakh accidental cover\n"
                "3. High-interest debt clear karo pehle\n"
                "4. APY (Atal Pension Yojana) → guaranteed pension for life\n\n"
                "*Koi aur financial sawaal ho toh puchho!*")

    # Gatekeeper
    if any(w in ml for w in ["plan","budget","kharcha","manage my money","bachat","financial plan","suggest"]) and not inc and not ns:
        return ("📋 **Personalized Plan ke liye kuch details chahiye:**\n\n"
                "1. **Monthly Income** — Kitna income hota hai per month?\n"
                "2. **Dependents** — Kitne log is income par depend karte hain?\n"
                "3. **City/Area** — Kahan rehte ho?\n"
                "4. **Koi existing loan?** — Koi moneylender ya bank loan hai?\n\n"
                "*Yeh details share karo, main ek zero-error personalized plan banaunga!*")

    # Budget calc
    if inc > 0 and (ns or any(w in ml for w in ["budget","plan","salary","income","70","calculate","divide","kaise","kharch"])):
        c = calc_7020_10(inc)
        debt_pay = int(inc * 0.12)
        rem_save = c["save"] - debt_pay
        return (f"📊 **₹{c['income']:,}/month ke liye Verified 70/20/10 Budget**\n\n"
                f"**✅ 70% Needs = ₹{c['needs']:,}/month**\n"
                f"- Ration/groceries, rent, electricity, gas, medicines, school fees\n\n"
                f"**💰 20% Savings & Debt = ₹{c['save']:,}/month (₹{c['daily']:,}/day)**\n"
                f"- 🔴 Pehle debt clear: ₹{debt_pay:,}/month moneylender ko\n"
                f"- 🟢 Emergency fund: ₹{max(0,rem_save):,}/month PMJDY account mein\n"
                f"- 🎯 3-month target: **₹{c['em3']:,}**\n"
                f"- 🎯 6-month target: **₹{c['em6']:,}**\n\n"
                f"**🔄 10% Buffer = ₹{c['buf']:,}/month**\n"
                f"- Medical emergency, urgent transport, unavoidable personal needs\n\n"
                f"{'👨‍👩‍👧 ' + str(dep) + f' dependents ke liye per-person allocation: ₹{c[\"needs\"]//dep:,}/month' if dep > 1 else ''}\n\n"
                f"⚡ **Aaj ka Action**: ₹{c['daily']:,} ab PMJDY account mein transfer karo!\n\n"
                f"*📌 Disclaimer: Educational guidance only. Professional advisor se consult karein bade financial decisions ke liye.*")

    if any(w in ml for w in ["emergency fund","emergency","bachat kaise","limited income","choti income","kam income"]):
        return ("🆘 **Limited Income mein Emergency Fund — 4 Step Plan**\n\n"
                "**Step 1: Micro-Target Set Karo (₹1,500 First)**\n"
                "6-month fund ka mat socho abhi — pehla ₹1,500 ka 'shock absorber' banao. Yeh ek medical emergency ya repair bill se bachayega.\n\n"
                "**Step 2: ₹30-50/day Lagatar Bachao**\n"
                "- ₹30/day = ₹900/month = ₹10,800/year\n"
                "- ₹50/day = ₹1,500/month = ₹18,000/year\n\n"
                "**Step 3: Invisible Leaks Dhundo**\n"
                "- Roz ₹10-20 ke chhote kharch track karo 7 din ke liye\n"
                "- Daily chai-samosa = ₹40/day = ₹1,200/month waste!\n"
                "- Sachets ki jagah bulk ration lena → 30-40% savings\n\n"
                "**Step 4: Separate 'Untouchable' Account**\n"
                "- PMJDY Zero-Balance Account kholwao (Aadhaar + photo → any bank)\n"
                "- Bachat wala paisa wahan daalo — pocket mein nahi rakhna\n\n"
                "⚡ **Action**: Aaj raat ₹50 PMJDY account mein daalo. Bas yahi ek kaam!")

    if any(w in ml for w in ["svanidhi","thela","vendor","hawker","street","rehri","patri"]):
        return ("🛒 **PM SVANidhi — Street Vendors ke liye Free Working Capital**\n\n"
                "| Tranche | Amount | Condition |\n"
                "|---------|--------|-----------|\n"
                "| 1st | **₹10,000** | First loan |\n"
                "| 2nd | **₹20,000** | Timely repayment |\n"
                "| 3rd | **₹50,000** | Regular customer |\n\n"
                "**Benefits:**\n"
                "- 7% interest subsidy directly to your bank account\n"
                "- UPI payments pe ₹1,200/year cashback\n"
                "- No collateral required\n\n"
                "**Apply Karo:** `pmsvanidhi.mohua.gov.in` ya nearest CSC center\n"
                "**Documents:** Vendor Certificate ya ULB recommendation letter\n\n"
                "⚡ **Action**: Kal subah apne ward office mein Vendor Certificate ke liye apply karo!")

    if any(w in ml for w in ["debt","karz","karza","loan","sahukar","moneylender","byaaj","interest","udhaar","chhutkara"]):
        return ("⛓️ **Moneylender Debt se Azaadi — 3 Step Escape Plan**\n\n"
                "**Problem:** Local sahukar 5-10%/month = 60-120%/year interest lete hain!\n\n"
                "**Step 1: Avalanche Method**\n"
                "Sabse zyada interest wala loan list karo. Har extra rupaya pehle uspe lagao.\n\n"
                "**Step 2: Formal Micro-Credit se Replace Karo**\n"
                "- **PM MUDRA Shishu Loan**: Upto ₹50,000 @ 9-12%/year (NO collateral)\n"
                "- Isse sahukar ka loan clear karo — instantly 5x-10x interest bachega!\n\n"
                "**Step 3: SHG Join Karo**\n"
                "- NRLM/NULM Self-Help Group → emergency credit @ 7-9%/year\n"
                "- Apni gram panchayat ya ward office mein enquire karo\n\n"
                "⚡ **Action**: Nearest bank mein MUDRA Shishu Loan form maango aaj!")

    if any(w in ml for w in ["jan dhan","pmjdy","bank account","khata","zero balance","bank"]):
        return ("🏦 **PM Jan Dhan Yojana (PMJDY) — Complete Guide**\n\n"
                "**✅ Key Benefits:**\n"
                "- Zero minimum balance — ₹0 pe bhi koi penalty nahi\n"
                "- Free RuPay Debit Card + **₹2 Lakh accidental insurance** free!\n"
                "- ₹10,000 overdraft facility (6 months baad)\n"
                "- Sab government DBT subsidies seedha isme aati hain\n\n"
                "**📄 Documents (sirf 2 cheezein):**\n"
                "- Aadhaar Card\n"
                "- 2 Passport-size photos\n\n"
                "**🏧 Kahan Kholein:**\n"
                "- Any nationalized bank branch\n"
                "- Bank Mitra/BC kiosk (gaon mein bhi milega)\n\n"
                "⚡ **Action**: Kal nearest bank mein jaao — 30 minute mein account khul jayega!")

    if any(w in ml for w in ["insurance","bima","pmsby","pmjjby","suraksha","jeevan jyoti"]):
        return ("🛡️ **Government Micro-Insurance — ₹1.25/day mein Family Protection**\n\n"
                "| Scheme | Coverage | Premium | Eligibility |\n"
                "|--------|----------|---------|-------------|\n"
                "| **PMSBY** | ₹2 Lakh (accidental) | **₹20/year** | 18-70 yrs |\n"
                "| **PMJJBY** | ₹2 Lakh (any death) | **₹436/year** | 18-50 yrs |\n\n"
                "**Combined cost: ₹456/year = ₹38/month = ₹1.25/day**\n"
                "**Combined coverage: ₹4 Lakh for your family!**\n\n"
                "**Kaise Enroll Karein:**\n"
                "- Bank account se auto-debit set karo\n"
                "- Bank branch ya net banking se activate karein\n\n"
                "⚡ **Action**: Apni bank app ya branch mein PMSBY+PMJJBY activate karo aaj!")

    if any(w in ml for w in ["apy","pension","retirement","bhi jawani","atal"]):
        return ("👴 **Atal Pension Yojana (APY) — Guaranteed Lifetime Pension**\n\n"
                "| Age | ₹1,000/month pension ke liye | ₹5,000/month pension ke liye |\n"
                "|-----|-------------------------------|-------------------------------|\n"
                "| 18 yrs | ₹42/month | ₹210/month |\n"
                "| 25 yrs | ₹76/month | ₹376/month |\n"
                "| 30 yrs | ₹116/month | ₹577/month |\n\n"
                "**Features:**\n"
                "- Government guaranteed pension after age 60\n"
                "- Nominee ko full corpus milega death pe\n"
                "- Tax benefit under Section 80CCD\n\n"
                "**Eligibility:** 18-40 yrs, Bank account, Aadhaar\n\n"
                "⚡ **Action**: PMJDY account se APY ke liye apply karo — bank branch ya net banking!")

    return ("Namaste! Main **Arthik Sathi** hoon — aapka Personal Financial Advisor. 🙏\n\n"
            "Aap mujhse yeh puch sakte ho:\n\n"
            "💰 **Budget Plan** — Apni income batao, main exact 70/20/10 breakdown dunga\n"
            "🆘 **Emergency Fund** — Limited income mein savings kaise karein\n"
            "⛓️ **Debt Freedom** — Moneylender loan se kaise bachein\n"
            "🏦 **Jan Dhan Account** — Zero-balance bank account kholna\n"
            "🛡️ **Micro Insurance** — ₹20/year PMSBY, ₹436/year PMJJBY\n"
            "🛒 **SVANidhi Loan** — Street vendors ke liye ₹10,000-₹50,000\n"
            "👴 **APY Pension** — Guaranteed retirement income\n\n"
            "**Aaj aapka kya sawaal hai?** 😊")

# ── LLM call ─────────────────────────────────────────────────────────────────
import urllib.request

def call_groq(msg, history, profile):
    if not GROQ_API_KEY: return None
    messages = [{"role":"system","content":SYSTEM_PROMPT}]
    if profile and profile.get("income", 0) > 0:
        messages[0]["content"] += f"\n\nUser Profile: Income=₹{profile['income']:,}/month, Dependents={profile['dependents']}, City={profile.get('city','N/A')}"
    for h in history[-6:]:
        role = "user" if h["sender"]=="user" else "assistant"
        messages.append({"role":role,"content":h["message"]})
    messages.append({"role":"user","content":msg})
    try:
        payload = json.dumps({"model":"llama-3.1-8b-instant","messages":messages,"temperature":0.5,"max_tokens":900}).encode()
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions", data=payload,
            headers={"Content-Type":"application/json","Authorization":f"Bearer {GROQ_API_KEY}"})
        with urllib.request.urlopen(req, timeout=12) as r:
            res = json.loads(r.read())
            return res["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print("Groq error:", e)
        return None

def call_gemini(msg, history, profile):
    if not GEMINI_API_KEY: return None
    prompt = SYSTEM_PROMPT
    if profile and profile.get("income",0)>0:
        prompt += f"\n\nUser Profile: Income=₹{profile['income']:,}/month, Dependents={profile['dependents']}, City={profile.get('city','N/A')}"
    prompt += "\n\n"
    for h in history[-4:]:
        prompt += f"{h['sender'].capitalize()}: {h['message']}\n"
    prompt += f"User: {msg}\nAssistant:"
    try:
        payload = json.dumps({"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"temperature":0.5,"maxOutputTokens":900}}).encode()
        req = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}",
            data=payload, headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=12) as r:
            res = json.loads(r.read())
            return res["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        print("Gemini error:", e)
        return None

def get_response(msg, history, profile):
    time.sleep(1.5)  # 1.5s "thinking" delay for better UX
    resp = call_groq(msg, history, profile) or call_gemini(msg, history, profile) or local_response(msg, profile)
    return resp

# ── PDF Generator ─────────────────────────────────────────────────────────────
def make_pdf(chat_history, user):
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Table, TableStyle
        from reportlab.lib.units import cm

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
        styles = getSampleStyleSheet()
        story = []

        # Header
        story.append(Paragraph("💰 ArthikAI — Financial Chat Statement", ParagraphStyle("title", fontSize=20, textColor=colors.HexColor("#10b981"), spaceAfter=4, fontName="Helvetica-Bold")))
        story.append(Paragraph("Personal Financial Inclusion Assistant | SDG 1: No Poverty", ParagraphStyle("sub", fontSize=11, textColor=colors.grey, spaceAfter=12)))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#10b981")))
        story.append(Spacer(1, 10))

        # User info
        if user:
            data = [
                ["Name", user.get("name","—"), "Email", user.get("email","—")],
                ["Monthly Income", f"₹{user.get('income',0):,}", "Dependents", str(user.get("dependents",1))],
                ["City", user.get("city","—"), "Generated", datetime.now().strftime("%d %b %Y %H:%M")],
            ]
            t = Table(data, colWidths=[3.5*cm,5.5*cm,3.5*cm,5.5*cm])
            t.setStyle(TableStyle([
                ("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#f0fdf4")),
                ("TEXTCOLOR",(0,0),(0,-1),colors.HexColor("#10b981")),
                ("TEXTCOLOR",(2,0),(2,-1),colors.HexColor("#10b981")),
                ("FONTNAME",(0,0),(0,-1),"Helvetica-Bold"),
                ("FONTNAME",(2,0),(2,-1),"Helvetica-Bold"),
                ("FONTSIZE",(0,0),(-1,-1),9),
                ("ROWBACKGROUNDS",(0,0),(-1,-1),[colors.HexColor("#f0fdf4"),colors.HexColor("#dcfce7")]),
                ("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#10b981")),
                ("INNERGRID",(0,0),(-1,-1),0.25,colors.lightgrey),
                ("PADDING",(0,0),(-1,-1),6),
            ]))
            story.append(t)
            story.append(Spacer(1,16))

        story.append(Paragraph("📜 Chat History", ParagraphStyle("ch", fontSize=13, fontName="Helvetica-Bold", textColor=colors.HexColor("#1e293b"), spaceAfter=8)))

        user_style = ParagraphStyle("user_msg", fontSize=9, textColor=colors.HexColor("#1e40af"),
                                     backColor=colors.HexColor("#eff6ff"), leftIndent=30,
                                     borderPad=6, spaceAfter=6, borderWidth=0, fontName="Helvetica")
        bot_style  = ParagraphStyle("bot_msg",  fontSize=9, textColor=colors.HexColor("#1e293b"),
                                     backColor=colors.HexColor("#f0fdf4"), leftIndent=0,
                                     borderPad=6, spaceAfter=6, borderWidth=0, fontName="Helvetica")

        for h in chat_history:
            sender = h.get("sender","")
            msg    = h.get("message","").replace("\n","<br/>").replace("**","").replace("*","")
            ts     = h.get("timestamp","")[:16] if h.get("timestamp") else ""
            label  = f"<b>{'You' if sender=='user' else 'ArthikAI'}</b> {ts}"
            story.append(Paragraph(label, ParagraphStyle("lbl",fontSize=8,textColor=colors.grey,spaceAfter=2)))
            story.append(Paragraph(msg, user_style if sender=="user" else bot_style))

        story.append(Spacer(1,12))
        story.append(HRFlowable(width="100%",thickness=0.5,color=colors.lightgrey))
        story.append(Paragraph("Generated by ArthikAI · For educational purposes only · Not financial advice",
                                ParagraphStyle("footer",fontSize=7,textColor=colors.grey,alignment=1,spaceBefore=6)))

        doc.build(story)
        return buf.getvalue()
    except ImportError:
        # Fallback: plain text
        lines = ["ArthikAI — Financial Chat Statement", "="*50, ""]
        if user:
            lines += [f"Name: {user.get('name','')}", f"Email: {user.get('email','')}", f"Income: ₹{user.get('income',0):,}/month", ""]
        lines.append("CHAT HISTORY")
        lines.append("-"*40)
        for h in chat_history:
            lines.append(f"[{h.get('sender','').upper()}]: {h.get('message','')}")
            lines.append("")
        lines.append(f"\nGenerated: {datetime.now().strftime('%d %b %Y %H:%M')}")
        lines.append("ArthikAI — Educational purposes only.")
        return "\n".join(lines).encode("utf-8")

# ── CSS Injection ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

*, *::before, *::after { box-sizing: border-box; margin: 0; }

html, body, .stApp {
    font-family: 'Inter', sans-serif;
    background: #0a0f1a !important;
    color: #e2e8f0;
}

/* Hide default streamlit chrome */
#MainMenu, header, footer { visibility: hidden; }
.block-container { padding: 0 !important; max-width: 100% !important; }

/* Auth card */
.auth-wrap {
    min-height: 100vh;
    display: flex; align-items: center; justify-content: center;
    background: linear-gradient(135deg,#0a0f1a 0%,#0f1e2e 60%,#0a1628 100%);
}
.auth-card {
    background: rgba(15,30,46,.85);
    backdrop-filter: blur(24px);
    border: 1px solid rgba(16,185,129,.2);
    border-radius: 20px;
    padding: 2.5rem 2rem;
    width: 100%; max-width: 440px;
    box-shadow: 0 25px 60px rgba(0,0,0,.5), 0 0 0 1px rgba(16,185,129,.08);
}
.auth-logo { font-size: 2.2rem; margin-bottom: .3rem; }
.auth-title { font-size: 1.6rem; font-weight:700; color:#10b981; margin-bottom:.25rem; }
.auth-subtitle { font-size:.85rem; color:#94a3b8; margin-bottom:1.5rem; }

/* Chat area */
.chat-header {
    background: rgba(15,30,46,.9);
    backdrop-filter: blur(20px);
    border-bottom: 1px solid rgba(16,185,129,.15);
    padding: .9rem 1.4rem;
    display: flex; align-items: center; gap:.8rem;
    position: sticky; top:0; z-index:100;
}
.chat-logo { font-size:1.6rem; }
.chat-title { font-weight:700; font-size:1.1rem; color:#10b981; }
.chat-sub   { font-size:.72rem; color:#64748b; }

.msg-user {
    background: linear-gradient(135deg,#1d4ed8,#1e40af);
    color:#fff; border-radius:18px 18px 4px 18px;
    padding:.75rem 1rem; max-width:75%;
    margin: .4rem 0 .4rem auto;
    font-size:.88rem; line-height:1.55;
    box-shadow: 0 4px 15px rgba(29,78,216,.3);
}
.msg-bot {
    background: rgba(15,30,46,.8);
    border:1px solid rgba(16,185,129,.15);
    color:#e2e8f0; border-radius:18px 18px 18px 4px;
    padding:.75rem 1rem; max-width:85%;
    margin: .4rem auto .4rem 0;
    font-size:.88rem; line-height:1.6;
    box-shadow: 0 4px 15px rgba(0,0,0,.3);
}
.msg-bot strong { color:#10b981; }

.thinking-anim {
    display:flex; gap:5px; align-items:center; padding:.75rem 1rem;
    background:rgba(15,30,46,.8); border:1px solid rgba(16,185,129,.15);
    border-radius:18px; width:fit-content; margin:.4rem 0;
}
.dot { width:7px; height:7px; border-radius:50%; background:#10b981;
        animation:bounce .9s infinite; }
.dot:nth-child(2) { animation-delay:.2s; }
.dot:nth-child(3) { animation-delay:.4s; }
@keyframes bounce { 0%,60%,100%{transform:translateY(0)} 30%{transform:translateY(-8px)} }

/* Input */
.stTextInput > div > div > input {
    background: rgba(15,30,46,.8) !important;
    border: 1px solid rgba(16,185,129,.25) !important;
    color: #e2e8f0 !important;
    border-radius: 12px !important;
    font-family: 'Inter', sans-serif !important;
}
.stTextInput > div > div > input:focus {
    border-color: rgba(16,185,129,.6) !important;
    box-shadow: 0 0 0 2px rgba(16,185,129,.15) !important;
}

/* Buttons */
.stButton > button {
    background: linear-gradient(135deg,#10b981,#059669) !important;
    color:#fff !important; border:none !important;
    border-radius:10px !important; font-weight:600 !important;
    transition: all .2s !important;
}
.stButton > button:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 20px rgba(16,185,129,.4) !important;
}

/* Selectbox & Form */
.stSelectbox > div > div, .stForm {
    background: rgba(15,30,46,.5) !important;
}

/* Sidebar */
.css-1d391kg, [data-testid="stSidebar"] {
    background: rgba(10,15,26,.95) !important;
    border-right: 1px solid rgba(16,185,129,.1) !important;
}

/* Welcome banner */
.welcome-banner {
    background: linear-gradient(135deg,rgba(16,185,129,.12),rgba(5,150,105,.08));
    border: 1px solid rgba(16,185,129,.2);
    border-radius: 14px; padding: 1.2rem 1.4rem; margin: 1rem 0;
}
.welcome-banner h3 { color:#10b981; font-size:1rem; margin-bottom:.5rem; }
.quick-btn { display:inline-block; background:rgba(16,185,129,.1); border:1px solid rgba(16,185,129,.25);
    color:#10b981; border-radius:20px; padding:.3rem .8rem; font-size:.78rem;
    margin:.2rem; cursor:pointer; transition:all .2s; }

/* Metric cards */
.metric-card {
    background:rgba(15,30,46,.7); border:1px solid rgba(16,185,129,.15);
    border-radius:12px; padding:1rem; text-align:center;
}
.metric-value { font-size:1.4rem; font-weight:700; color:#10b981; }
.metric-label { font-size:.72rem; color:#64748b; margin-top:.2rem; }

hr { border-color: rgba(16,185,129,.1) !important; }
</style>
""", unsafe_allow_html=True)

# ── Session State Init ────────────────────────────────────────────────────────
def ss(k, v):
    if k not in st.session_state: st.session_state[k] = v

ss("token", None); ss("user", None); ss("messages", [])
ss("session_id", "sess_"+secrets.token_hex(8))
ss("auth_mode", "login"); ss("show_profile", False)
ss("show_clear_confirm", False)

# ── Auth Page ─────────────────────────────────────────────────────────────────
if not st.session_state.token:
    col1, col2, col3 = st.columns([1,1.2,1])
    with col2:
        st.markdown("""
        <div style='min-height:20px'></div>
        <div style='text-align:center; margin-bottom:2rem'>
            <div style='font-size:3rem'>💰</div>
            <div style='font-size:1.8rem;font-weight:800;color:#10b981'>ArthikAI</div>
            <div style='color:#64748b;font-size:.85rem'>SDG 1 · Financial Inclusion Assistant</div>
        </div>
        """, unsafe_allow_html=True)

        mode = st.radio("", ["🔐 Login", "✨ Sign Up"], horizontal=True, key="auth_radio",
                        index=0 if st.session_state.auth_mode=="login" else 1, label_visibility="collapsed")
        st.session_state.auth_mode = "login" if "Login" in mode else "signup"

        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

        if st.session_state.auth_mode == "login":
            with st.form("login_form", clear_on_submit=False):
                email = st.text_input("📧 Email", placeholder="you@example.com", key="l_email")
                pwd   = st.text_input("🔒 Password", type="password", placeholder="Your password", key="l_pwd")
                submitted = st.form_submit_button("Login →", use_container_width=True)
                if submitted:
                    if not email or not pwd:
                        st.error("Please fill in all fields.")
                    else:
                        r = login(email, pwd)
                        if r["ok"]:
                            st.session_state.token = r["token"]
                            st.session_state.user  = r["user"]
                            st.session_state.messages = load_history(r["user"]["id"], st.session_state.session_id)
                            st.rerun()
                        else:
                            st.error(r["error"])
        else:
            with st.form("signup_form", clear_on_submit=False):
                name  = st.text_input("👤 Full Name", placeholder="Priya Sharma", key="s_name")
                email = st.text_input("📧 Email",     placeholder="you@example.com", key="s_email")
                pwd   = st.text_input("🔒 Password",  type="password", placeholder="Min 6 characters", key="s_pwd")
                c1, c2 = st.columns(2)
                with c1: income = st.number_input("💵 Monthly Income (₹)", min_value=0, value=0, step=500, key="s_inc")
                with c2: dep    = st.number_input("👨‍👩‍👧 Dependents", min_value=1, value=1, step=1, key="s_dep")
                city = st.text_input("🏙️ City", placeholder="Mumbai", key="s_city")
                submitted = st.form_submit_button("Create Account →", use_container_width=True)
                if submitted:
                    if not name or not email or not pwd:
                        st.error("Name, email and password are required.")
                    elif len(pwd) < 6:
                        st.error("Password must be at least 6 characters.")
                    else:
                        r = signup(name, email, pwd, int(income), int(dep), city)
                        if r["ok"]:
                            st.session_state.token = r["token"]
                            st.session_state.user  = r["user"]
                            st.success(f"Welcome, {name}! 🎉")
                            time.sleep(0.8)
                            st.rerun()
                        else:
                            st.error(r["error"])

        st.markdown("<div style='text-align:center;color:#475569;font-size:.78rem;margin-top:1.5rem'>🔒 Secured with PBKDF2 encryption · ₹ Free forever</div>", unsafe_allow_html=True)
    st.stop()

# ── Logged-in App ─────────────────────────────────────────────────────────────
user = st.session_state.user

# Sidebar
with st.sidebar:
    st.markdown(f"""
    <div style='text-align:center;padding:1rem 0'>
        <div style='font-size:2.5rem'>💰</div>
        <div style='font-weight:700;color:#10b981;font-size:1.1rem'>ArthikAI</div>
        <div style='color:#64748b;font-size:.75rem'>Financial Inclusion Assistant</div>
    </div>
    <hr>
    <div style='color:#94a3b8;font-size:.8rem;padding:.5rem 0'>
        👤 <b style="color:#e2e8f0">{user.get("name","User")}</b><br>
        📧 {user.get("email","")}<br>
        💵 ₹{user.get("income",0):,}/month<br>
        👨‍👩‍👧 {user.get("dependents",1)} dependents
    </div>
    <hr>
    """, unsafe_allow_html=True)

    st.markdown("**⚙️ Update Profile**")
    with st.form("profile_form"):
        new_income = st.number_input("Monthly Income (₹)", value=int(user.get("income",0)), min_value=0, step=500)
        new_dep    = st.number_input("Dependents", value=int(user.get("dependents",1)), min_value=1, step=1)
        new_city   = st.text_input("City", value=user.get("city",""))
        if st.form_submit_button("💾 Save Profile", use_container_width=True):
            update_profile(user["id"], int(new_income), int(new_dep), new_city)
            st.session_state.user["income"]     = int(new_income)
            st.session_state.user["dependents"] = int(new_dep)
            st.session_state.user["city"]       = new_city
            user = st.session_state.user
            st.success("Profile updated! ✅")

    st.markdown("<hr>", unsafe_allow_html=True)

    # Download PDF
    if st.session_state.messages:
        pdf_bytes = make_pdf(st.session_state.messages, user)
        ext  = "pdf" if isinstance(pdf_bytes, bytes) and pdf_bytes[:4]==b"%PDF" else "txt"
        mime = "application/pdf" if ext=="pdf" else "text/plain"
        st.download_button("📄 Download Statement", data=pdf_bytes,
                           file_name=f"ArthikAI_Statement_{datetime.now().strftime('%d%b%Y')}.{ext}",
                           mime=mime, use_container_width=True)

    st.markdown("<hr>", unsafe_allow_html=True)

    # Clear history
    if not st.session_state.show_clear_confirm:
        if st.button("🗑️ Clear Chat History", use_container_width=True):
            st.session_state.show_clear_confirm = True
            st.rerun()
    else:
        st.warning("⚠️ This will permanently delete all your chat history!")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("✅ Yes, Clear", use_container_width=True):
                clear_history(user["id"], st.session_state.session_id)
                st.session_state.messages = []
                st.session_state.show_clear_confirm = False
                st.rerun()
        with c2:
            if st.button("❌ Cancel", use_container_width=True):
                st.session_state.show_clear_confirm = False
                st.rerun()

    st.markdown("<hr>", unsafe_allow_html=True)
    if st.button("🚪 Logout", use_container_width=True):
        st.session_state.token    = None
        st.session_state.user     = None
        st.session_state.messages = []
        st.rerun()

# ── Main Chat Area ────────────────────────────────────────────────────────────
st.markdown(f"""
<div class='chat-header'>
    <div class='chat-logo'>💰</div>
    <div>
        <div class='chat-title'>ArthikAI — Arthik Sathi</div>
        <div class='chat-sub'>SDG 1 · Financial Inclusion · Namaste, {user.get("name","")
}! 🙏</div>
    </div>
</div>
""", unsafe_allow_html=True)

# Profile metrics strip
if user.get("income",0) > 0:
    c = calc_7020_10(user["income"])
    m1,m2,m3,m4 = st.columns(4)
    with m1: st.markdown(f"<div class='metric-card'><div class='metric-value'>₹{c['needs']:,}</div><div class='metric-label'>70% Needs/mo</div></div>", unsafe_allow_html=True)
    with m2: st.markdown(f"<div class='metric-card'><div class='metric-value'>₹{c['save']:,}</div><div class='metric-label'>20% Savings/mo</div></div>", unsafe_allow_html=True)
    with m3: st.markdown(f"<div class='metric-card'><div class='metric-value'>₹{c['daily']:,}</div><div class='metric-label'>Save/Day</div></div>", unsafe_allow_html=True)
    with m4: st.markdown(f"<div class='metric-card'><div class='metric-value'>₹{c['em3']:,}</div><div class='metric-label'>3-mo Emergency</div></div>", unsafe_allow_html=True)
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

# Welcome banner if no chat
if not st.session_state.messages:
    st.markdown("""
    <div class='welcome-banner'>
        <h3>👋 Namaste! Main Arthik Sathi hoon</h3>
        <p style='color:#94a3b8;font-size:.85rem;margin-bottom:.8rem'>
            Aapka personal financial advisor — budget planning, emergency fund, debt relief, aur govt schemes ke liye
        </p>
        <div>
            <span class='quick-btn'>💰 Budget Plan banao</span>
            <span class='quick-btn'>🆘 Emergency Fund kaise banayein</span>
            <span class='quick-btn'>⛓️ Moneylender loan se bachao</span>
            <span class='quick-btn'>🏦 Jan Dhan Account</span>
            <span class='quick-btn'>🛡️ ₹20/year Insurance</span>
            <span class='quick-btn'>🛒 SVANidhi Loan</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

# Render chat history
for msg in st.session_state.messages:
    sender = msg.get("sender","")
    text   = msg.get("message","")
    if sender == "user":
        st.markdown(f"<div style='display:flex;justify-content:flex-end'><div class='msg-user'>{text}</div></div>", unsafe_allow_html=True)
    else:
        st.markdown(f"<div class='msg-bot'>{text}</div>", unsafe_allow_html=True)

# ── Input ─────────────────────────────────────────────────────────────────────
user_input = st.chat_input("Apna financial sawaal yahan likho... (Type in Hindi or English)")

if user_input and user_input.strip():
    q = user_input.strip()

    # Add user message
    save_msg(user["id"], st.session_state.session_id, "user", q)
    st.session_state.messages.append({"sender":"user","message":q,"timestamp":datetime.now().isoformat()})
    st.markdown(f"<div style='display:flex;justify-content:flex-end'><div class='msg-user'>{q}</div></div>", unsafe_allow_html=True)

    # Thinking animation
    thinking = st.empty()
    thinking.markdown("""
    <div class='thinking-anim'>
        <div class='dot'></div><div class='dot'></div><div class='dot'></div>
        <span style='color:#64748b;font-size:.8rem;margin-left:6px'>Soch raha hoon...</span>
    </div>
    """, unsafe_allow_html=True)

    # Get AI response
    resp = get_response(q, st.session_state.messages[:-1], user)
    thinking.empty()

    # Save and render bot message
    save_msg(user["id"], st.session_state.session_id, "assistant", resp)
    st.session_state.messages.append({"sender":"assistant","message":resp,"timestamp":datetime.now().isoformat()})
    st.markdown(f"<div class='msg-bot'>{resp}</div>", unsafe_allow_html=True)
    st.rerun()
