// ArthikAI — Enterprise Client Application Logic
document.addEventListener('DOMContentLoaded', () => {
  // Global State
  let authToken = localStorage.getItem('arthik_token') || '';
  let sessionId = localStorage.getItem('arthik_session_id') || ('sess_' + Math.random().toString(36).substring(2, 12));
  localStorage.setItem('arthik_session_id', sessionId);
  let currentUser = null;
  let currentLang = 'en'; // 'en', 'hi', 'hinglish'

  // DOM Elements
  const chatMessages = document.getElementById('chatMessages');
  const chatForm = document.getElementById('chatForm');
  const userInput = document.getElementById('userInput');
  const thinkingIndicator = document.getElementById('thinkingIndicator');
  const themeToggle = document.getElementById('themeToggle');
  const downloadPdfBtn = document.getElementById('downloadPdfBtn');
  const clearChatBtn = document.getElementById('clearChatBtn');
  const toolsBtn = document.getElementById('toolsBtn');
  const closeToolsBtn = document.getElementById('closeToolsBtn');
  const toolsPanel = document.getElementById('toolsPanel');
  const langToggle = document.getElementById('langToggle');
  const langText = document.getElementById('langText');
  const micBtn = document.getElementById('micBtn');

  // Auth Elements
  const authBtn = document.getElementById('authBtn');
  const authLabel = document.getElementById('authLabel');
  const authModal = document.getElementById('authModal');
  const closeAuthModal = document.getElementById('closeAuthModal');
  const tabLogin = document.getElementById('tabLogin');
  const tabSignup = document.getElementById('tabSignup');
  const loginForm = document.getElementById('loginForm');
  const signupForm = document.getElementById('signupForm');
  const loginError = document.getElementById('loginError');
  const signupError = document.getElementById('signupError');

  // Clear Modal Elements
  const clearModal = document.getElementById('clearModal');
  const cancelClearBtn = document.getElementById('cancelClearBtn');
  const confirmClearBtn = document.getElementById('confirmClearBtn');

  // Budget Simulator Elements
  const incomeSlider = document.getElementById('incomeSlider');
  const incomeDisplay = document.getElementById('incomeDisplay');
  const needsVal = document.getElementById('needsVal');
  const savingsVal = document.getElementById('savingsVal');
  const bufferVal = document.getElementById('bufferVal');
  const insertBudgetBtn = document.getElementById('insertBudgetBtn');

  // Emergency Calculator Elements
  const goalSlider = document.getElementById('goalSlider');
  const goalDisplay = document.getElementById('goalDisplay');
  const dailySlider = document.getElementById('dailySlider');
  const dailyDisplay = document.getElementById('dailyDisplay');
  const daysNeeded = document.getElementById('daysNeeded');
  const monthsNeeded = document.getElementById('monthsNeeded');

  // Leak Detector Elements
  const leakSlider = document.getElementById('leakSlider');
  const leakDisplay = document.getElementById('leakDisplay');
  const monthlyLeak = document.getElementById('monthlyLeak');
  const yearlyLeak = document.getElementById('yearlyLeak');
  const scanLeakBtn = document.getElementById('scanLeakBtn');

  // In-Memory Conversation Log (for PDF generator)
  let conversationHistory = [];

  // -------------------------------------------------------------
  // 1. Authentication & User Profile Management
  // -------------------------------------------------------------
  async function initAuth() {
    if (!authToken) {
      updateAuthUI(null);
      return;
    }
    try {
      const res = await fetch('/api/auth/me', {
        headers: { 'Authorization': `Bearer ${authToken}` }
      });
      if (res.ok) {
        const data = await res.json();
        currentUser = data.user;
        updateAuthUI(currentUser);
      } else {
        localStorage.removeItem('arthik_token');
        authToken = '';
        currentUser = null;
        updateAuthUI(null);
      }
    } catch (e) {
      console.warn('Auth check failed:', e);
    }
  }

  function updateAuthUI(user) {
    if (user) {
      authLabel.textContent = `${user.name} (₹${(user.income || 0).toLocaleString('en-IN')})`;
      authBtn.title = `Logged in as ${user.name} (${user.email}). Click to Log Out.`;
      if (user.income > 0) {
        incomeSlider.value = user.income;
        updateBudgetSimulator();
      }
    } else {
      authLabel.textContent = 'Log In / Sign Up';
      authBtn.title = 'User Login & Profile';
    }
  }

  authBtn.addEventListener('click', () => {
    if (currentUser) {
      if (confirm(`Logged in as ${currentUser.name} (${currentUser.email})\nDo you want to log out?`)) {
        localStorage.removeItem('arthik_token');
        authToken = '';
        currentUser = null;
        updateAuthUI(null);
      }
    } else {
      authModal.classList.remove('hidden');
      loginError.classList.add('hidden');
      signupError.classList.add('hidden');
    }
  });

  closeAuthModal.addEventListener('click', () => {
    authModal.classList.add('hidden');
  });

  tabLogin.addEventListener('click', () => {
    tabLogin.classList.add('active');
    tabSignup.classList.remove('active');
    loginForm.classList.remove('hidden');
    signupForm.classList.add('hidden');
    loginError.classList.add('hidden');
  });

  tabSignup.addEventListener('click', () => {
    tabSignup.classList.add('active');
    tabLogin.classList.remove('active');
    signupForm.classList.remove('hidden');
    loginForm.classList.add('hidden');
    signupError.classList.add('hidden');
  });

  // Handle Login Submit
  loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    loginError.classList.add('hidden');
    const email = document.getElementById('loginEmail').value.trim();
    const password = document.getElementById('loginPassword').value.trim();

    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      });
      const data = await res.json();
      if (!res.ok) {
        loginError.textContent = data.error || 'Login failed. Please check credentials.';
        loginError.classList.remove('hidden');
        return;
      }
      authToken = data.token;
      currentUser = data.user;
      localStorage.setItem('arthik_token', authToken);
      updateAuthUI(currentUser);
      authModal.classList.add('hidden');
      loadChatHistory(); // Reload history associated with user
    } catch (err) {
      loginError.textContent = 'Network error during login.';
      loginError.classList.remove('hidden');
    }
  });

  // Handle Signup Submit
  signupForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    signupError.classList.add('hidden');
    const name = document.getElementById('signupName').value.trim();
    const email = document.getElementById('signupEmail').value.trim();
    const password = document.getElementById('signupPassword').value.trim();
    const income = parseInt(document.getElementById('signupIncome').value || 0, 10);
    const dependents = parseInt(document.getElementById('signupDependents').value || 1, 10);
    const city = document.getElementById('signupCity').value.trim();

    try {
      const res = await fetch('/api/auth/signup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, email, password, income, dependents, city })
      });
      const data = await res.json();
      if (!res.ok) {
        signupError.textContent = data.error || 'Signup failed.';
        signupError.classList.remove('hidden');
        return;
      }
      authToken = data.token;
      currentUser = data.user;
      localStorage.setItem('arthik_token', authToken);
      updateAuthUI(currentUser);
      authModal.classList.add('hidden');
    } catch (err) {
      signupError.textContent = 'Network error during signup.';
      signupError.classList.remove('hidden');
    }
  });

  // -------------------------------------------------------------
  // 2. Persistent Chat History (Loads on Refresh)
  // -------------------------------------------------------------
  async function loadChatHistory() {
    try {
      const headers = {};
      if (authToken) headers['Authorization'] = `Bearer ${authToken}`;
      const res = await fetch(`/api/chat/history?session_id=${sessionId}`, { headers });
      if (res.ok) {
        const data = await res.json();
        const history = data.history || [];
        if (history.length > 0) {
          // Clear current screen messages
          chatMessages.innerHTML = '';
          conversationHistory = [];
          history.forEach(item => {
            if (item.sender === 'user') {
              appendUserMessage(item.message);
            } else {
              appendAssistantMessage(item.message);
            }
            conversationHistory.push({ sender: item.sender, text: item.message });
          });
          scrollToBottom();
        }
      }
    } catch (e) {
      console.warn('Could not fetch chat history from server:', e);
    }
  }

  // -------------------------------------------------------------
  // 3. Clear Chat Routine
  // -------------------------------------------------------------
  clearChatBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    clearModal.classList.remove('hidden');
  });

  cancelClearBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    clearModal.classList.add('hidden');
  });

  // Clicking backdrop overlay closes clearModal
  clearModal.addEventListener('click', (e) => {
    if (e.target === clearModal) {
      clearModal.classList.add('hidden');
    }
  });

  // Clicking backdrop overlay closes authModal
  authModal.addEventListener('click', (e) => {
    if (e.target === authModal) {
      authModal.classList.add('hidden');
    }
  });

  // Escape key closes open modals
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      clearModal.classList.add('hidden');
      authModal.classList.add('hidden');
      toolsPanel.classList.add('closed');
    }
  });

  confirmClearBtn.addEventListener('click', async (e) => {
    e.stopPropagation();
    // 1. Instantly hide modal
    clearModal.classList.add('hidden');

    // 2. Instantly reset local state & screen
    conversationHistory = [];
    chatMessages.innerHTML = `
      <div class="message-wrapper assistant">
        <div class="avatar"><span>₹</span></div>
        <div class="message-bubble">
          <div class="message-header">
            <span class="sender-name">Arthik Sathi</span>
            <span class="badge-role">Personal Advisor</span>
          </div>
          <div class="message-body">
            <p>Chat history has been cleared. How can I assist you with your budget, savings, or government benefits today?</p>
          </div>
        </div>
      </div>
    `;

    // 3. Send DELETE request to server in background
    try {
      const headers = {};
      if (authToken) headers['Authorization'] = `Bearer ${authToken}`;
      await fetch(`/api/chat/history?session_id=${sessionId}`, {
        method: 'DELETE',
        headers
      });
    } catch (err) {
      console.warn('Error clearing server history:', err);
    }
  });

  // -------------------------------------------------------------
  // 4. Multi-Language Switcher
  // -------------------------------------------------------------
  const langDict = {
    en: {
      toggle: 'EN / हिंदी',
      placeholder: 'Ask about budgeting, emergency savings, or government schemes...',
      starters: [
        'Limited Income: Steps to Manage & Build Emergency Fund',
        'Low-Income 70/20/10 Budget Rule',
        'Government Schemes & Micro-Insurance',
        'Escape High-Interest Money Lenders'
      ]
    },
    hi: {
      toggle: 'हिंदी / Hinglish',
      placeholder: 'बजट, इमरजेंसी बचत या सरकारी योजनाओं के बारे में पूछें...',
      starters: [
        'कम आमदनी: बजट और इमरजेंसी फंड के उपाय',
        '70/20/10 बजट का सरल नियम',
        'सरकारी योजनाएं (जन धन, बीमा, पेंशन)',
        'साहूकार के कर्ज और ब्याज से कैसे बचें'
      ]
    },
    hinglish: {
      toggle: 'Hinglish / EN',
      placeholder: 'Salary, kharcha, loan ya schemes ke bare me pucho...',
      starters: [
        'Kam income me emergency fund kaise banaye?',
        '70/20/10 budget rule kya hai?',
        'Govt schemes (Jan Dhan, PMSBY) ke fayde',
        'Local moneylender ke karz se chhutkara'
      ]
    }
  };

  langToggle.addEventListener('click', () => {
    if (currentLang === 'en') currentLang = 'hi';
    else if (currentLang === 'hi') currentLang = 'hinglish';
    else currentLang = 'en';

    const conf = langDict[currentLang];
    langText.textContent = conf.toggle;
    userInput.placeholder = conf.placeholder;

    // Update starter chips text
    const chips = document.querySelectorAll('.starter-chip .chip-label');
    chips.forEach((c, idx) => {
      if (conf.starters[idx]) c.textContent = conf.starters[idx];
    });
  });

  // -------------------------------------------------------------
  // 5. Voice Input & Speech-to-Text
  // -------------------------------------------------------------
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SpeechRecognition) {
    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;

    recognition.onstart = () => {
      micBtn.style.backgroundColor = 'rgba(244, 63, 94, 0.3)';
      micBtn.style.borderColor = '#f43f5e';
      userInput.placeholder = 'Listening... Bolna shuru kijiye...';
    };

    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      userInput.value = transcript;
      userInput.style.height = 'auto';
      userInput.style.height = Math.min(userInput.scrollHeight, 120) + 'px';
      micBtn.style.backgroundColor = '';
      micBtn.style.borderColor = '';
      userInput.placeholder = langDict[currentLang].placeholder;
    };

    recognition.onerror = () => {
      micBtn.style.backgroundColor = '';
      micBtn.style.borderColor = '';
      userInput.placeholder = 'Voice not detected. Please type.';
    };

    recognition.onend = () => {
      micBtn.style.backgroundColor = '';
      micBtn.style.borderColor = '';
    };

    micBtn.addEventListener('click', () => {
      recognition.lang = currentLang === 'hi' ? 'hi-IN' : 'en-IN';
      try { recognition.start(); } catch (e) { recognition.stop(); }
    });
  } else {
    micBtn.style.opacity = '0.5';
    micBtn.title = 'Voice recognition not supported in this browser';
  }

  // Audio Voice Reader (Text-to-Speech)
  function speakText(text) {
    if (!('speechSynthesis' in window)) return;
    window.speechSynthesis.cancel();
    const clean = text
      .replace(/[#*_`~>-]/g, ' ')
      .replace(/₹/g, ' Rupees ')
      .replace(/https?:\/\/\S+/g, '')
      .slice(0, 500);

    const utterance = new SpeechSynthesisUtterance(clean);
    utterance.rate = 1.0;
    utterance.pitch = 1.0;
    window.speechSynthesis.speak(utterance);
  }

  // -------------------------------------------------------------
  // 6. Tools & Drawer Interactions
  // -------------------------------------------------------------
  toolsBtn.addEventListener('click', () => toolsPanel.classList.toggle('closed'));
  closeToolsBtn.addEventListener('click', () => toolsPanel.classList.add('closed'));

  // Theme Toggle
  const savedTheme = localStorage.getItem('arthik_theme');
  if (savedTheme === 'light') {
    document.body.classList.add('light-theme');
    themeToggle.querySelector('.theme-icon').textContent = '☀️';
  }
  themeToggle.addEventListener('click', () => {
    document.body.classList.toggle('light-theme');
    const isLight = document.body.classList.contains('light-theme');
    themeToggle.querySelector('.theme-icon').textContent = isLight ? '☀️' : '🌙';
    localStorage.setItem('arthik_theme', isLight ? 'light' : 'dark');
  });

  // Micro-Budget Simulator Slider
  function updateBudgetSimulator() {
    const income = parseInt(incomeSlider.value, 10);
    incomeDisplay.textContent = '₹' + income.toLocaleString('en-IN');

    // 70 / 20 / 10 math with zero error
    const needs = Math.floor(income * 0.70);
    const savings = Math.floor(income * 0.20);
    const buffer = income - needs - savings;

    needsVal.textContent = '₹' + needs.toLocaleString('en-IN');
    savingsVal.textContent = '₹' + savings.toLocaleString('en-IN');
    bufferVal.textContent = '₹' + buffer.toLocaleString('en-IN');
  }
  incomeSlider.addEventListener('input', updateBudgetSimulator);
  updateBudgetSimulator();

  insertBudgetBtn.addEventListener('click', () => {
    const income = incomeSlider.value;
    const prompt = `Meri monthly income ₹${income} hai. 70/20/10 low-income rule ke hisab se: Essentials ₹${needsVal.textContent}, Debt & Savings ₹${savingsVal.textContent}, aur Buffer ₹${bufferVal.textContent} banta hai. Isko real life me kaise apply karu aur emergency fund kaise banau?`;
    sendUserMessage(prompt);
    if (window.innerWidth < 900) toolsPanel.classList.add('closed');
  });

  // Emergency Fund Goal Tracker
  function updateEmergencyCalculator() {
    const goal = parseInt(goalSlider.value, 10);
    const daily = parseInt(dailySlider.value, 10);
    goalDisplay.textContent = '₹' + goal.toLocaleString('en-IN');
    dailyDisplay.textContent = '₹' + daily + ' / day';

    const days = Math.ceil(goal / daily);
    const months = (days / 30).toFixed(1);
    daysNeeded.textContent = days;
    monthsNeeded.textContent = months;
  }
  goalSlider.addEventListener('input', updateEmergencyCalculator);
  dailySlider.addEventListener('input', updateEmergencyCalculator);
  updateEmergencyCalculator();

  // Leak Detector
  if (leakSlider) {
    function updateLeakDetector() {
      const dailySpend = parseInt(leakSlider.value, 10);
      leakDisplay.textContent = '₹' + dailySpend + ' / day';
      const monthly = dailySpend * 30;
      const yearly = monthly * 12;
      monthlyLeak.textContent = '₹' + monthly.toLocaleString('en-IN') + ' / mo';
      yearlyLeak.textContent = '₹' + yearly.toLocaleString('en-IN');
    }
    leakSlider.addEventListener('input', updateLeakDetector);
    updateLeakDetector();

    scanLeakBtn.addEventListener('click', () => {
      const val = leakSlider.value;
      const prompt = `Main roz ₹${val} chhote-mote kharcho (chai, samosa, snacks, unneeded top-ups) me spend karta hu. Is expense leak ko rok kar main emergency fund me kaise badal sakta hu?`;
      sendUserMessage(prompt);
      if (window.innerWidth < 900) toolsPanel.classList.add('closed');
    });
  }

  // Quick Action Chips & Pills
  document.querySelectorAll('.starter-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      const prompt = chip.getAttribute('data-prompt');
      if (prompt) sendUserMessage(prompt);
    });
  });

  document.querySelectorAll('.pill-btn').forEach(pill => {
    pill.addEventListener('click', () => {
      const text = pill.getAttribute('data-text');
      if (text) sendUserMessage(text);
    });
  });

  document.querySelectorAll('.scheme-item').forEach(item => {
    item.addEventListener('click', () => {
      const scheme = item.querySelector('strong').textContent;
      sendUserMessage(`Can you explain the eligibility, benefits, and how to apply for ${scheme}?`);
      if (window.innerWidth < 900) toolsPanel.classList.add('closed');
    });
  });

  // Auto-resize textarea
  userInput.addEventListener('input', () => {
    userInput.style.height = 'auto';
    userInput.style.height = Math.min(userInput.scrollHeight, 120) + 'px';
  });

  userInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      chatForm.dispatchEvent(new Event('submit'));
    }
  });

  chatForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const message = userInput.value.trim();
    if (!message) return;
    userInput.value = '';
    userInput.style.height = 'auto';
    sendUserMessage(message);
  });

  // -------------------------------------------------------------
  // 7. Message Routine with 2-Second Realistic Thinking Delay
  // -------------------------------------------------------------
  async function sendUserMessage(message) {
    appendUserMessage(message);
    conversationHistory.push({ sender: 'user', text: message });

    showThinking();
    const startTime = Date.now();

    try {
      const headers = { 'Content-Type': 'application/json' };
      if (authToken) headers['Authorization'] = `Bearer ${authToken}`;

      const responsePromise = fetch('/chat', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          message,
          session_id: sessionId
        })
      });

      // Enforce minimum 2.0 second thinking delay
      const [response] = await Promise.all([
        responsePromise,
        new Promise(resolve => setTimeout(resolve, 2000))
      ]);

      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      hideThinking();

      const botReply = data.response || 'I am sorry, I could not process that request.';
      appendAssistantMessage(botReply);
      conversationHistory.push({ sender: 'assistant', text: botReply });
    } catch (err) {
      hideThinking();
      appendAssistantMessage('I apologize, but I experienced an issue communicating with the server. Please check your connection.');
      console.error('Chat error:', err);
    }
  }

  function showThinking() {
    thinkingIndicator.classList.remove('hidden');
    scrollToBottom();
  }

  function hideThinking() {
    thinkingIndicator.classList.add('hidden');
  }

  function scrollToBottom() {
    setTimeout(() => { chatMessages.scrollTop = chatMessages.scrollHeight; }, 60);
  }

  // -------------------------------------------------------------
  // 8. Markdown Rendering
  // -------------------------------------------------------------
  function formatMarkdown(text) {
    if (!text) return '';
    let html = text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');

    html = html.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>');
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    html = html.replace(/^### (.*$)/gim, '<h3 style="margin-top:12px;margin-bottom:6px;color:var(--accent-emerald-light);font-size:1rem;">$1</h3>');
    html = html.replace(/^## (.*$)/gim, '<h2 style="margin-top:14px;margin-bottom:8px;color:var(--accent-emerald-light);font-size:1.1rem;">$1</h2>');
    html = html.replace(/^# (.*$)/gim, '<h1 style="margin-top:16px;margin-bottom:10px;font-size:1.2rem;">$1</h1>');
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');
    html = html.replace(/^> (.*$)/gim, '<div class="callout-box">$1</div>');
    html = html.replace(/^\s*[-*]\s+(.*$)/gim, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');

    const lines = html.split('\n');
    let formatted = '';
    lines.forEach(line => {
      const trimmed = line.trim();
      if (!trimmed) formatted += '<br/>';
      else if (trimmed.startsWith('<li>') || trimmed.startsWith('<ul>') || trimmed.startsWith('</ul>') || trimmed.startsWith('<h') || trimmed.startsWith('<div')) {
        formatted += trimmed;
      } else {
        formatted += `<p>${trimmed}</p>`;
      }
    });
    return formatted;
  }

  function appendUserMessage(text) {
    const wrapper = document.createElement('div');
    wrapper.className = 'message-wrapper user';
    wrapper.innerHTML = `
      <div class="avatar" aria-hidden="true"><span>👤</span></div>
      <div class="message-bubble">
        <div class="message-body">
          <p>${escapeHTML(text)}</p>
        </div>
      </div>
    `;
    chatMessages.appendChild(wrapper);
    scrollToBottom();
  }

  function appendAssistantMessage(text) {
    const wrapper = document.createElement('div');
    wrapper.className = 'message-wrapper assistant';

    const headerDiv = document.createElement('div');
    headerDiv.className = 'message-header';
    headerDiv.style.display = 'flex';
    headerDiv.style.justifyContent = 'space-between';
    headerDiv.style.alignItems = 'center';

    headerDiv.innerHTML = `
      <div style="display:flex;align-items:center;gap:8px;">
        <span class="sender-name">Arthik Sathi</span>
        <span class="badge-role">Personal Advisor</span>
      </div>
      <button class="icon-btn tts-btn" title="Listen to response (Audio Voice)" aria-label="Listen to response" style="width:28px;height:28px;font-size:0.8rem;border:none;background:transparent;cursor:pointer;">
        🔊
      </button>
    `;

    const bodyDiv = document.createElement('div');
    bodyDiv.className = 'message-body';
    bodyDiv.innerHTML = `
      ${formatMarkdown(text)}
      <div class="disclaimer-box">
        ⚖️ <em>Educational financial guidance only. Not licensed investment or financial advice.</em>
      </div>
    `;

    const bubbleDiv = document.createElement('div');
    bubbleDiv.className = 'message-bubble';
    bubbleDiv.appendChild(headerDiv);
    bubbleDiv.appendChild(bodyDiv);

    const avatarDiv = document.createElement('div');
    avatarDiv.className = 'avatar';
    avatarDiv.innerHTML = '<span>₹</span>';

    wrapper.appendChild(avatarDiv);
    wrapper.appendChild(bubbleDiv);

    const ttsBtn = headerDiv.querySelector('.tts-btn');
    ttsBtn.addEventListener('click', () => speakText(text));

    chatMessages.appendChild(wrapper);
    scrollToBottom();
  }

  function escapeHTML(str) {
    return str.replace(/[&<>'"]/g, tag => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[tag] || tag));
  }

  // -------------------------------------------------------------
  // 9. Professional PDF Financial Statement ("Made by ArthikAI")
  // -------------------------------------------------------------
  downloadPdfBtn.addEventListener('click', () => {
    const { jsPDF } = window.jspdf || {};
    if (!jsPDF) {
      alert('PDF generation library is loading, please try again in a moment.');
      return;
    }

    const doc = new jsPDF({ unit: 'pt', format: 'a4' });
    const user = currentUser || { name: 'Valued Client', email: 'Individual Consultation', income: parseInt(incomeSlider.value, 10), dependents: 1, city: 'India' };
    const income = user.income || parseInt(incomeSlider.value, 10);
    const needs = Math.floor(income * 0.70);
    const savings = Math.floor(income * 0.20);
    const buffer = income - needs - savings;
    const dailySave = Math.floor(savings / 30);

    // Primary Brand Header Banner
    doc.setFillColor(15, 23, 42); // Navy slate
    doc.rect(0, 0, 595, 85, 'F');

    doc.setTextColor(255, 255, 255);
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(20);
    doc.text('ARTHIK AI — PERSONAL FINANCIAL STATEMENT', 40, 42);

    doc.setFontSize(10);
    doc.setFont('helvetica', 'normal');
    doc.setTextColor(16, 185, 129); // Emerald
    doc.text('MADE BY ARTHIKAI • CONFIDENTIAL & VERIFIED FINANCIAL ASSESSMENT', 40, 62);

    // Section 1: Client Information Card
    doc.setFillColor(241, 245, 249);
    doc.roundedRect(40, 105, 515, 75, 4, 4, 'F');

    doc.setTextColor(15, 23, 42);
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(11);
    doc.text('CLIENT PROFILE & ASSESSMENT METRICS', 55, 125);

    doc.setFont('helvetica', 'normal');
    doc.setFontSize(9);
    doc.setTextColor(71, 85, 105);
    doc.text(`Client Name: ${user.name}`, 55, 142);
    doc.text(`Email / Contact: ${user.email}`, 55, 157);
    doc.text(`City / Region: ${user.city || 'National'}`, 55, 170);

    doc.text(`Date of Assessment: ${new Date().toLocaleDateString('en-IN')}`, 320, 142);
    doc.text(`Monthly Income: Rs. ${income.toLocaleString('en-IN')}`, 320, 157);
    doc.text(`Household Dependents: ${user.dependents || 1} Persons`, 320, 170);

    // Section 2: 70 / 20 / 10 Financial Allocation Table
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(12);
    doc.setTextColor(15, 23, 42);
    doc.text('1. VERIFIED MONTHLY 70/20/10 ALLOCATION (ZERO-ERROR)', 40, 210);

    // Table Header
    doc.setFillColor(16, 185, 129);
    doc.rect(40, 222, 515, 24, 'F');
    doc.setTextColor(255, 255, 255);
    doc.setFontSize(9);
    doc.text('CATEGORY', 50, 237);
    doc.text('PERCENTAGE', 230, 237);
    doc.text('MONTHLY AMOUNT', 340, 237);
    doc.text('PURPOSE', 450, 237);

    // Table Row 1 (Needs)
    doc.setFillColor(255, 255, 255);
    doc.rect(40, 246, 515, 24, 'F');
    doc.setTextColor(15, 23, 42);
    doc.text('Essentials & Needs', 50, 261);
    doc.text('70%', 230, 261);
    doc.setFont('helvetica', 'bold');
    doc.text(`Rs. ${needs.toLocaleString('en-IN')}`, 340, 261);
    doc.setFont('helvetica', 'normal');
    doc.text('Ration, Rent, Utilities, Healthcare', 450, 261);

    // Table Row 2 (Savings / Debt)
    doc.setFillColor(248, 250, 252);
    doc.rect(40, 270, 515, 24, 'F');
    doc.text('Debt Relief & Savings', 50, 285);
    doc.text('20%', 230, 285);
    doc.setFont('helvetica', 'bold');
    doc.text(`Rs. ${savings.toLocaleString('en-IN')}`, 340, 285);
    doc.setFont('helvetica', 'normal');
    doc.text('High-interest payoff + Emergency fund', 450, 285);

    // Table Row 3 (Buffer)
    doc.setFillColor(255, 255, 255);
    doc.rect(40, 294, 515, 24, 'F');
    doc.text('Discretionary Buffer', 50, 309);
    doc.text('10%', 230, 309);
    doc.setFont('helvetica', 'bold');
    doc.text(`Rs. ${buffer.toLocaleString('en-IN')}`, 340, 309);
    doc.setFont('helvetica', 'normal');
    doc.text('Unavoidable family personal buffer', 450, 309);

    // Section 3: Emergency Fund Micro-Milestones
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(12);
    doc.setTextColor(15, 23, 42);
    doc.text('2. EMERGENCY BUFFER SAVINGS MILESTONES', 40, 345);

    doc.setFillColor(241, 245, 249);
    doc.roundedRect(40, 355, 515, 80, 4, 4, 'F');

    doc.setFontSize(9);
    doc.setFont('helvetica', 'normal');
    doc.setTextColor(71, 85, 105);
    doc.text(`• Recommended Daily Micro-Deposit: Rs. ${dailySave.toLocaleString('en-IN')} / day into a zero-balance account.`, 55, 375);
    doc.text(`• Milestone 1 (Starter Shield - 30 Days): Rs. ${savings.toLocaleString('en-IN')} accumulated buffer.`, 55, 393);
    doc.text(`• Milestone 2 (3-Month Security Cushion): Rs. ${(savings * 3).toLocaleString('en-IN')} (Protects against medical clinic bills).`, 55, 411);
    doc.text(`• Milestone 3 (Full 6-Month Peace of Mind): Rs. ${(savings * 6).toLocaleString('en-IN')} accumulated buffer.`, 55, 425);

    // Section 4: Recommended Government Schemes
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(12);
    doc.setTextColor(15, 23, 42);
    doc.text('3. RECOMMENDED SOCIAL SECURITY & GOVERNMENT SCHEMES', 40, 460);

    const schemes = [
      ['PM Jan Dhan Yojana (PMJDY)', 'Zero-balance account + Free RuPay card + Rs. 2 Lakh accident cover.'],
      ['PM Suraksha Bima Yojana (PMSBY)', 'Accidental insurance of Rs. 2 Lakh for just Rs. 20 per YEAR.'],
      ['PM Jeevan Jyoti Bima (PMJJBY)', 'Life insurance of Rs. 2 Lakh for Rs. 436 per YEAR.'],
      ['PM SVANidhi / Mudra Shishu', 'Collateral-free micro-credit from Rs. 10,000 to Rs. 50,000 at formal bank rates.']
    ];

    let schemeY = 480;
    schemes.forEach(([title, desc]) => {
      doc.setFont('helvetica', 'bold');
      doc.setFontSize(9);
      doc.setTextColor(5, 150, 105);
      doc.text(`• ${title}:`, 55, schemeY);
      doc.setFont('helvetica', 'normal');
      doc.setTextColor(71, 85, 105);
      doc.text(desc, 235, schemeY);
      schemeY += 18;
    });

    // Recent Advice Summary
    if (conversationHistory.length > 1) {
      doc.setFont('helvetica', 'bold');
      doc.setFontSize(11);
      doc.setTextColor(15, 23, 42);
      doc.text('4. RECENT CONSULTATION SUMMARY', 40, 575);

      doc.setFont('helvetica', 'normal');
      doc.setFontSize(8);
      doc.setTextColor(71, 85, 105);
      const lastBotMsg = conversationHistory.filter(m => m.sender === 'assistant').pop();
      if (lastBotMsg) {
        const cleanAdvice = lastBotMsg.text.replace(/[#*_`~>-]/g, '').slice(0, 380);
        doc.text(cleanAdvice, 40, 595, { maxWidth: 515, lineHeightFactor: 1.4 });
      }
    }

    // Official Footer Stamp
    doc.setFillColor(15, 23, 42);
    doc.rect(0, 780, 595, 62, 'F');

    doc.setTextColor(255, 255, 255);
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(9);
    doc.text('OFFICIAL VERIFICATION STAMP: MADE BY ARTHIKAI FINANCIAL INTELLIGENCE', 40, 805);

    doc.setFont('helvetica', 'normal');
    doc.setFontSize(8);
    doc.setTextColor(148, 163, 184);
    doc.text('Disclaimer: This report provides general educational guidance and mathematical simulations. Not a certified investment prospectus.', 40, 822);

    // Trigger Download
    doc.save(`ArthikAI_Financial_Statement_${user.name.replace(/\s+/g, '_')}_${Date.now()}.pdf`);
  });

  // Initialize Auth & History on startup
  initAuth();
  loadChatHistory();
});
