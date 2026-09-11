# 🪙 ArthikAI — SDG 1 Financial Inclusion Assistant

**Next Gen Chatbot Arena (3-Hour SDG Web-Based Chatbot Challenge)**  
*Track 1: SDG 1 – No Poverty (Financial Inclusion Assistant)*

---

## 📌 Project Overview
**ArthikAI** is a purpose-built, accessible conversational agent and API designed to bridge the economic gap for individuals and households living on low or irregular incomes. 

Rather than overwhelming users with Wall Street jargon or unrealistic "save 6 months of salary" mantras, ArthikAI provides:
1. **Practical Emergency Fund Micro-Steps**: Real-world plans starting from ₹20–₹50/day.
2. **70/20/10 Survival-to-Security Budgeting**: Adapted specifically for tight household budgets.
3. **Public Welfare & Social Protection Guidance**: Enrolling in PM Jan Dhan Yojana, PM Suraksha Bima, PM Jeevan Jyoti Bima, Atal Pension Yojana, and Mudra micro-loans.
4. **Predatory Debt Relief Strategies**: Escaping informal 60–120% APR local money lenders.
5. **Responsible AI Guardrails**: Strict refusals for cryptocurrency, intraday stock speculation, and unlicensed financial advice, backed by clear educational disclaimers.

---

## 🚀 Quick Start (Local Setup)

### 1. Run Server
Open your terminal in this directory and execute:
```bash
py server.py
```
*Note: Uses Python standard library (`http.server`, `json`, `urllib`). Zero third-party dependencies required!*

Server runs at:
- **Web Interface**: `http://localhost:5000`
- **Arena API Endpoint**: `POST http://localhost:5000/chat`
- **Health Check**: `GET http://localhost:5000/health`

### 2. Optional: Add Gemini API Key
To enable cloud LLM generation, create a `.env` file (or copy `.env.example`):
```env
GEMINI_API_KEY=your_gemini_api_key_here
```
*If no key is provided, ArthikAI automatically runs its ultra-fast built-in domain intelligence engine!*

---

## 📡 Arena API Contract

### Request:
```http
POST /chat HTTP/1.1
Host: localhost:5000
Content-Type: application/json

{
  "message": "I have a limited monthly income. What practical steps can I take to manage my expenses and build a small emergency fund?"
}
```

### Response:
```json
{
  "response": "### 4 Practical Steps to Manage Expenses & Build an Emergency Fund on a Limited Income\n\n1. **Set a Realistic Micro-Target (₹1,000 to ₹3,000 First)**..."
}
```

---

## 🧪 Automated Arena Compliance Tests
Run the evaluation test suite to verify scoring rubric compliance:
```bash
py test_eval.py
```

---

## 🌐 Public URL Deployment for Submission
To provide the organizers with a live public URL and API endpoint:

### Option A: Using Ngrok (Instant Tunnel)
```bash
ngrok http 5000
```
Use the generated `https://xxxx.ngrok-free.app` URL for the submission form.

### Option B: Using Localtunnel
```bash
npx localtunnel --port 5000
```

---

## 📊 Evaluation Rubric Alignment (100 Points)

| Rubric Criterion | Max Pts | ArthikAI Implementation |
|---|---|---|
| **SDG Relevance & Problem Fit** | 20 | Directly addresses SDG 1 poverty reduction, financial literacy, and social protection schemes. |
| **Response Quality & Helpfulness** | 20 | Actionable micro-savings habits (₹20-₹50/day), 70/20/10 budget calculations, and empathetic tone. |
| **Accuracy & Reliability** | 20 | Accurate government scheme parameters (PMJDY overdraft, PMSBY ₹20 premium, Mudra limits). |
| **Functionality & Tech Quality** | 15 | Robust `POST /chat` with JSON schema, CORS headers, responsive UI, and error handling. |
| **Safety & Responsible AI** | 10 | Clear disclaimers ("Educational guidance only; not licensed advice") + intercepting crypto/stock gambles. |
| **Conversation & UX** | 10 | Glassmorphic dark/light UI, interactive budget slider, emergency fund calculator, and one-click plan export. |
| **Innovation** | 5 | In-chat real-time Micro-Budget Simulator & Emergency Days Calculator. |
