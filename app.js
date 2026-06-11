/**
 * FlashSpend — Flashcard Expense Tracker
 * app.js — Frontend logic wired to the Python/Flask backend API
 */

'use strict';

/* ================================================================
   CONFIGURATION
   ================================================================ */

const API_BASE = 'http://localhost:5000/api';

const CATEGORIES = [
  { name: 'Housing',       icon: '🏠', color: '#6366f1', key: '1' },
  { name: 'Grocery',       icon: '🛒', color: '#10b981', key: '2' },
  { name: 'Transport',     icon: '🚗', color: '#3b82f6', key: '3' },
  { name: 'Lifestyle',     icon: '✨', color: '#a855f7', key: '4' },
  { name: 'Entertainment', icon: '🎬', color: '#ec4899', key: '5' },
  { name: 'Food',          icon: '🍽️', color: '#f59e0b', key: '6' },
  { name: 'Subscription',  icon: '📱', color: '#0ea5e9', key: '7' },
  { name: 'Travel',        icon: '✈️', color: '#06b6d4', key: '8' },
  { name: 'Investments',   icon: '📈', color: '#34d399', key: '9' },
  { name: 'Miscellaneous', icon: '📦', color: '#94a3b8', key: '0' },
];

const SAMPLE_CSV = `Date,Description,Amount
2024-01-02,Salary Deposit,3200.00
2024-01-03,Whole Foods Market,-89.45
2024-01-04,Shell Gas Station,-52.10
2024-01-05,Netflix,-15.99
2024-01-06,CVS Pharmacy,-23.75
2024-01-08,Chipotle Mexican Grill,-14.30
2024-01-09,Electric Bill Payment,-87.00
2024-01-10,Amazon Purchase,-134.99
2024-01-11,Gym Membership,-45.00
2024-01-12,Lyft Ride,-12.50
2024-01-14,Trader Joe's,-67.20
2024-01-15,Spotify,-9.99
2024-01-16,Rent Payment,-1800.00
2024-01-17,Starbucks,-6.85
2024-01-18,Target,-98.42
2024-01-19,Dental Appointment,-150.00
2024-01-20,Freelance Payment,800.00
2024-01-21,Uber Eats,-38.70
2024-01-22,Internet Bill,-59.99
2024-01-23,Movie Tickets,-32.00`;

/* ================================================================
   LOCAL UI STATE (mirrors server, used for immediate rendering)
   ================================================================ */

let uiState = {
  currentTx: null,
  session:   null,
  busy:      false,   // true while an API call is in-flight
  isEditMode: false,
};

/* ================================================================
   DOM REFERENCES
   ================================================================ */

const screens = {
  upload: document.getElementById('screen-upload'),
  triage: document.getElementById('screen-triage'),
  done:   document.getElementById('screen-done'),
};

const els = {
  dropzone:      document.getElementById('dropzone'),
  fileInput:     document.getElementById('file-input'),
  uploadError:   document.getElementById('upload-error'),
  btnLoadSample: document.getElementById('btn-load-sample'),

  progressFill:  document.getElementById('progress-fill'),
  progressLabel: document.getElementById('progress-label'),
  btnUndo:       document.getElementById('btn-undo'),
  btnSkip:       document.getElementById('btn-skip'),
  btnFinishAdding: document.getElementById('btn-finish-adding'),

  flashcard:       document.getElementById('flashcard'),
  cardAmount:      document.getElementById('card-amount'),
  cardType:        document.getElementById('card-type'),
  cardBadge:       document.getElementById('card-badge'),
  cardPersonLabel: document.getElementById('card-person-label'),
  cardPerson:      document.getElementById('card-person'),
  cardRemark:      document.getElementById('card-remark'),
  cardDate:        document.getElementById('card-date'),
  
  cardAmountEdit:  document.getElementById('card-amount-edit'),
  cardPersonEdit:  document.getElementById('card-person-edit'),
  cardDateEdit:    document.getElementById('card-date-edit'),

  categoriesGrid:  document.getElementById('categories-grid'),

  doneCount:   document.getElementById('done-count'),
  summaryGrid: document.getElementById('summary-grid'),
  btnExport:   document.getElementById('btn-export'),
  btnResetLocal: document.getElementById('btn-reset-local'),
  btnRestart:  document.getElementById('btn-restart'),
};

let summaryTargets = null;
let latestTransactionDateValue = '';

/* ================================================================
   SCREEN TRANSITIONS
   ================================================================ */

function showScreen(name) {
  Object.entries(screens).forEach(([key, el]) => {
    if (key === name) {
      el.classList.remove('slide-out');
      el.classList.add('active');
    } else if (el.classList.contains('active')) {
      el.classList.add('slide-out');
      setTimeout(() => el.classList.remove('active', 'slide-out'), 400);
    }
  });
}

/* ================================================================
   API HELPERS
   ================================================================ */

async function apiFetch(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  const json = await res.json();
  if (!json.ok) throw new Error(json.error || 'API error');
  return json.data;
}

/* ================================================================
   FORMATTING HELPERS
   ================================================================ */

function formatAmountDisplay(num) {
  const abs = Math.abs(num).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return num >= 0 ? `+₹${abs}` : `-₹${abs}`;
}

function formatDate(isoDate) {
  if (!isoDate) return '';
  const d = new Date(isoDate + 'T00:00:00');
  return d.toLocaleDateString('en-IN', { year: 'numeric', month: 'short', day: 'numeric' });
}

function formatMonthLabel(monthKey) {
  if (!monthKey) return 'No data yet';
  const [year, month] = monthKey.split('-').map(Number);
  if (!year || !month) return 'No data yet';
  const d = new Date(year, month - 1, 1);
  return d.toLocaleDateString('en-IN', { month: 'short', year: 'numeric' });
}

function normalizeDateKey(dateValue) {
  if (!dateValue) return '';

  if (/^\d{4}-\d{2}-\d{2}$/.test(dateValue)) {
    return dateValue;
  }

  const parsed = new Date(dateValue);
  if (Number.isNaN(parsed.getTime())) return '';
  return parsed.toISOString().slice(0, 10);
}

function setLastTransactionDisplay(dateValue) {
  const normalized = normalizeDateKey(dateValue);
  if (!normalized) return;

  if (latestTransactionDateValue && normalized < latestTransactionDateValue) return;

  latestTransactionDateValue = normalized;
  ensureHeaderSummary().forEach(target => {
    target.lastTransactionDate.textContent = formatDate(normalized);
  });
}

function createSummaryMarkup(className) {
  const stats = document.createElement('div');
  stats.className = className;
  stats.setAttribute('aria-label', 'Session summary');
  stats.innerHTML = `
    <div class="header-stat">
      <span class="header-stat-label">Last transaction</span>
      <span class="header-stat-value" data-role="last-transaction-date">No data yet</span>
    </div>
    <div class="header-stat header-stat-card">
      <div class="header-stat-split">
        <span class="header-stat-label">Credit card name</span>
        <span class="header-stat-label">Last updated month</span>
      </div>
      <div class="header-stat-split">
        <span class="header-stat-value" data-role="credit-card-name">Axis Bank Credit Card</span>
        <input class="header-stat-input" data-role="last-saved-month" type="month" />
      </div>
    </div>
  `;
  return stats;
}

function ensureHeaderSummary() {
  if (summaryTargets) return summaryTargets;

  const targets = [];

  const headerLeft = document.querySelector('.header-left');
  if (headerLeft) {
    headerLeft.classList.add('header-left--with-stats');
    const headerStats = createSummaryMarkup('header-stats');
    headerLeft.appendChild(headerStats);
    targets.push({
      lastTransactionDate: headerStats.querySelector('[data-role="last-transaction-date"]'),
      creditCardName: headerStats.querySelector('[data-role="credit-card-name"]'),
      lastSavedMonth: headerStats.querySelector('[data-role="last-saved-month"]'),
    });
  }

  const brand = document.querySelector('.brand');
  if (brand) {
    const brandChildren = Array.from(brand.children);
    const brandCopy = document.createElement('div');
    brandCopy.className = 'brand-copy';

    brandChildren.forEach(child => brandCopy.appendChild(child));

    const uploadStats = createSummaryMarkup('upload-stats');
    brand.classList.add('brand--with-stats');
    brand.appendChild(brandCopy);
    brand.appendChild(uploadStats);

    targets.push({
      lastTransactionDate: uploadStats.querySelector('[data-role="last-transaction-date"]'),
      creditCardName: uploadStats.querySelector('[data-role="credit-card-name"]'),
      lastSavedMonth: uploadStats.querySelector('[data-role="last-saved-month"]'),
    });
  }

  summaryTargets = targets;
  summaryTargets.forEach(target => {
    target.lastSavedMonth.addEventListener('change', onCreditCardMonthChange);
  });
  return summaryTargets;
}

async function refreshHeaderSummary() {
  const targets = ensureHeaderSummary();
  if (!targets.length) return;

  try {
    const data = await apiFetch('/header_summary');
    const lastTransactionText = data.last_transaction_date
      ? formatDate(data.last_transaction_date)
      : 'No data yet';
    const lastSavedMonthValue = data.last_saved_month || '';
    latestTransactionDateValue = data.last_transaction_date || '';

    targets.forEach(target => {
      target.lastTransactionDate.textContent = lastTransactionText;
      target.creditCardName.textContent = 'Axis Bank Credit Card';
      target.lastSavedMonth.value = lastSavedMonthValue;
    });
  } catch (err) {
    console.error('Failed to load header summary:', err);
    targets.forEach(target => {
      target.lastTransactionDate.textContent = 'No data yet';
      target.creditCardName.textContent = 'Axis Bank Credit Card';
      target.lastSavedMonth.value = '';
    });
    latestTransactionDateValue = '';
  }
}

async function onCreditCardDetailsChange() {
  const targets = ensureHeaderSummary();
  const primaryTarget = targets[0];
  const monthValue = primaryTarget?.lastSavedMonth.value || '';
  const creditCardName = 'Axis Bank Credit Card';

  if (!monthValue) return;

  try {
    const data = await apiFetch('/header_summary', {
      method: 'POST',
      body: JSON.stringify({
        credit_card_month: monthValue,
        credit_card_name: creditCardName,
      }),
    });

    const lastTransactionText = data.last_transaction_date
      ? formatDate(data.last_transaction_date)
      : 'No data yet';
    latestTransactionDateValue = data.last_transaction_date || '';

    targets.forEach(target => {
      target.lastTransactionDate.textContent = lastTransactionText;
      target.creditCardName.textContent = 'Axis Bank Credit Card';
      target.lastSavedMonth.value = data.last_saved_month || monthValue;
    });
  } catch (err) {
    console.error('Failed to update credit card details:', err);
    refreshHeaderSummary();
  }
}

async function onCreditCardMonthChange() {
  await onCreditCardDetailsChange();
}

/* ================================================================
   RENDER ACTIVE CARD
   ================================================================ */

function renderCard(tx) {
  exitEditMode();
  if (!tx) return;
  uiState.currentTx = tx;

  const isCredit = tx.is_credit;

  // Amount
  els.cardAmount.textContent = formatAmountDisplay(tx.amount);
  els.cardAmount.className   = `card-amount ${isCredit ? 'credit' : 'debit'}`;

  // Credit / Debit badge
  els.cardType.textContent = isCredit ? 'Credit' : 'Debit';
  els.cardType.className   = `card-type ${isCredit ? 'credit' : ''}`;

  els.cardBadge.hidden = true;

  // Sender / Receiver
  const person = isCredit ? tx.receive_from : tx.sent_to;
  els.cardPersonLabel.textContent = isCredit ? 'Received from' : 'Sent to';
  els.cardPerson.textContent = person || tx.description || '—';

  // Remark
  if (tx.comment) {
    els.cardRemark.textContent = `“${tx.comment}”`;
    els.cardRemark.hidden = false;
  } else {
    els.cardRemark.hidden = true;
  }

  // Date
  const datePart = formatDate(tx.date);
  const timePart = tx.time ? ` · ${tx.time}` : '';
  els.cardDate.textContent = datePart + timePart;
  setLastTransactionDisplay(tx.date);
}

function renderProgress(session) {
  if (!session) return;
  uiState.session = session;
  const pct = session.progress_pct;
  els.progressFill.style.width = `${pct}%`;

  const cardNum = session.done_count + 1;
  els.progressLabel.textContent = session.is_complete
    ? `All ${session.total} cards done!`
    : `Card ${cardNum} of ${session.total}`;

  // Undo button dim when nothing to undo
  els.btnUndo.style.opacity = session.can_undo ? '1' : '0.35';
  els.btnUndo.style.pointerEvents = session.can_undo ? '' : 'none';
}

/* ================================================================
   CATEGORY BUTTONS
   ================================================================ */

function buildCategoryButtons(categories) {
  els.categoriesGrid.innerHTML = '';
  categories.forEach((cat, i) => {
    const btn = document.createElement('button');
    btn.className = 'category-btn';
    btn.id = `cat-btn-${i}`;
    btn.style.setProperty('--cat-color', cat.color);
    btn.setAttribute('aria-label', `Categorize as ${cat.name}`);
    btn.innerHTML = `
      <span class="cat-icon" role="img" aria-hidden="true">${cat.icon}</span>
      <span class="cat-label">${cat.name}</span>
    `;
    btn.addEventListener('click', () => onCategoryClick(cat, btn));
    els.categoriesGrid.appendChild(btn);
  });
}

/* ================================================================
   CORE ACTION — CATEGORISE
   ================================================================ */

async function onCategoryClick(cat, btnEl) {
  if (uiState.busy) return;
  uiState.busy = true;

  const wasEditMode = uiState.isEditMode;

  // Visual press on the button
  btnEl?.classList.add('pressing');
  setTimeout(() => btnEl?.classList.remove('pressing'), 150);

  if (wasEditMode) {
    // Save manual transaction first
    try {
      await apiFetch('/transactions', {
        method: 'POST',
        body: JSON.stringify({
          date: els.cardDateEdit.value,
          description: els.cardPersonEdit.value.trim() || 'Manual',
          amount: parseFloat(els.cardAmountEdit.value) || 0,
          is_credit: parseFloat(els.cardAmountEdit.value) >= 0
        })
      });
      // Ensure categories are built if starting from empty state
      if (els.categoriesGrid.children.length === 0) {
        try {
          const cats = await apiFetch('/categories?active_only=true');
          buildCategoryButtons(cats.length ? cats : CATEGORIES);
        } catch {
          buildCategoryButtons(CATEGORIES);
        }
      }
    } catch (err) {
      console.error(err);
      uiState.busy = false;
      return; // Stop if failed to add
    }
  }

  // Animate the card out (left for expenses, right for income)
  const swipeClass = (cat.name === 'Income') ? 'swipe-right' : 'swipe-left';
  els.flashcard.classList.add(swipeClass);

  try {
    const data = await apiFetch('/categorise', {
      method: 'POST',
      body: JSON.stringify({ category: cat.name }),
    });
    refreshHeaderSummary();

    setTimeout(() => {
      els.flashcard.classList.remove(swipeClass);

      if (data.session.is_complete && !wasEditMode) {
        showDoneScreen(data);
      } else {
        renderCard(data.current);
        renderProgress(data.session);

        if (wasEditMode) {
          // Instantly give them a new blank card to keep adding!
          setTimeout(() => enterEditMode(), 50);
        }
        
        els.flashcard.classList.add('pop-in');
        setTimeout(() => els.flashcard.classList.remove('pop-in'), 400);
      }

      uiState.busy = false;
    }, 280);

  } catch (err) {
    els.flashcard.classList.remove(swipeClass);
    console.error('Categorise error:', err);
    uiState.busy = false;
  }
}

/* ================================================================
   UNDO
   ================================================================ */

async function doUndo() {
  if (uiState.busy) return;
  const session = uiState.session;
  if (!session?.can_undo) return;

  uiState.busy = true;

  // Fade card out
  els.flashcard.style.opacity = '0';
  els.flashcard.style.transform = 'translateY(20px) scale(0.95)';

  try {
    const data = await apiFetch('/undo', { method: 'POST' });

    setTimeout(() => {
      renderCard(data.current);
      renderProgress(data.session);
      // Fade back in
      els.flashcard.style.transition = 'opacity 0.25s ease, transform 0.25s ease';
      els.flashcard.style.opacity = '1';
      els.flashcard.style.transform = '';
      setTimeout(() => { els.flashcard.style.transition = ''; }, 300);
      uiState.busy = false;
    }, 100);

  } catch (err) {
    els.flashcard.style.opacity = '1';
    els.flashcard.style.transform = '';
    console.error('Undo error:', err);
    uiState.busy = false;
  }
}

/* ================================================================
   SKIP
   ================================================================ */

async function doSkip() {
  const miscCat = CATEGORIES.find(c => c.name === 'Miscellaneous');
  const miscBtn = document.getElementById(`cat-btn-${CATEGORIES.indexOf(miscCat)}`);
  await onCategoryClick(miscCat, miscBtn);
}

/* ================================================================
   DONE SCREEN
   ================================================================ */

async function showDoneScreen(data) {
  // Fetch full results (includes per-category totals)
  let results;
  try {
    results = await apiFetch('/results');
  } catch {
    results = { totals: [], session: data?.session };
  }

  const session = results.session || data?.session;
  els.doneCount.textContent = session?.done_count ?? 0;

  // Build summary cards
  els.summaryGrid.innerHTML = '';
  (results.totals || []).forEach((item, i) => {
    const cat = CATEGORIES.find(c => c.name === item.category) || { icon: '📦' };
    const isPositive = item.total_amount >= 0;
    const card = document.createElement('div');
    card.className = 'summary-card';
    card.style.animationDelay = `${i * 0.06}s`;
    card.innerHTML = `
      <div class="summary-cat-header">
        <span class="summary-cat-icon">${cat.icon}</span>
        <span class="summary-cat-name">${item.category}</span>
      </div>
      <div class="summary-amount ${isPositive ? 'positive' : ''}">${formatAmountDisplay(item.total_amount)}</div>
      <div class="summary-count">${item.count} transaction${item.count !== 1 ? 's' : ''}</div>
    `;
    els.summaryGrid.appendChild(card);
  });

  showScreen('done');
}

/* ================================================================
   SAVE TOTALS & RESET LOCAL
   ================================================================ */

async function doSaveTotals() {
  const btn = els.btnExport;
  const originalText = btn.innerHTML;
  btn.innerHTML = 'Saving...';
  btn.disabled = true;

  try {
    const data = await apiFetch('/save_totals', { method: 'POST' });
    refreshHeaderSummary();
    btn.innerHTML = `✓ Saved!`;
    setTimeout(() => {
      btn.innerHTML = originalText;
      btn.disabled = false;
    }, 2000);
  } catch (err) {
    alert(err.message || 'Failed to save totals.');
    btn.innerHTML = originalText;
    btn.disabled = false;
  }
}

async function doResetLocal() {
  const backupName = prompt("By what name should the file be saved? (without .json)", "backup_" + new Date().toISOString().split('T')[0]);
  if (!backupName) {
    return; // User cancelled
  }

  const btn = els.btnResetLocal;
  if (!btn) return;

  const originalText = btn.innerHTML;
  btn.innerHTML = 'Resetting...';
  btn.disabled = true;

  try {
    const data = await apiFetch('/reset_totals', { 
      method: 'POST',
      body: JSON.stringify({ backup_name: backupName })
    });
    refreshHeaderSummary();
    btn.innerHTML = `✓ Reset!`;
    setTimeout(() => {
      btn.innerHTML = originalText;
      btn.disabled = false;
    }, 2000);
  } catch (err) {
    alert(err.message || 'Failed to reset local file.');
    btn.innerHTML = originalText;
    btn.disabled = false;
  }
}

/* ================================================================
   FILE UPLOAD
   ================================================================ */

async function handleFile(file) {
  if (!file) {
    showUploadError('No file selected.');
    return;
  }

  // Case-insensitive extension check (.csv / .CSV / .Csv all accepted)
  const ext = file.name.split('.').pop().toLowerCase();
  if (ext !== 'csv') {
    showUploadError(`Unsupported file type ".${ext}". Please upload a .csv file.`);
    return;
  }

  hideUploadError();
  showUploadLoading(file.name);

  const formData = new FormData();
  formData.append('file', file);

  try {
    const res  = await fetch(`${API_BASE}/upload`, { method: 'POST', body: formData });
    const json = await res.json();

    hideUploadLoading();

    if (!json.ok) {
      showUploadError(json.error || 'Failed to parse the CSV.');
      return;
    }

    startTriage(json.data);
  } catch (err) {
    hideUploadLoading();
    // Network / server not running
    if (err.name === 'TypeError' && err.message.includes('fetch')) {
      showUploadError('Cannot reach the server. Make sure the Flask backend is running (python main.py).');
    } else {
      showUploadError(err.message || 'Failed to parse the CSV.');
    }
  }
}

async function handleSampleData() {
  hideUploadError();
  try {
    const data = await apiFetch('/parse-text', {
      method: 'POST',
      body: JSON.stringify({ csv: SAMPLE_CSV }),
    });
    startTriage(data);
  } catch (err) {
    showUploadError(err.message);
  }
}

function startTriage(data) {
  // Fetch categories from backend so the button list is always in sync
  apiFetch('/categories?active_only=true')
    .then(cats => buildCategoryButtons(cats.length ? cats : CATEGORIES))
    .catch(() => buildCategoryButtons(CATEGORIES));

  renderCard(data.current);
  renderProgress(data.session);
  refreshHeaderSummary();
  showScreen('triage');
}

/* ================================================================
   UPLOAD ERROR UI
   ================================================================ */

function showUploadError(msg) {
  els.uploadError.textContent = `⚠️ ${msg}`;
  els.uploadError.hidden = false;
  els.uploadError.style.background = 'rgba(244,63,94,0.12)';
  els.uploadError.style.borderColor = 'rgba(244,63,94,0.3)';
  els.uploadError.style.color = '#fda4af';
}

function hideUploadError() {
  els.uploadError.hidden = true;
  els.uploadError.textContent = '';
}

function showUploadLoading(filename) {
  els.uploadError.hidden = false;
  els.uploadError.textContent = `📤 Uploading ${filename}...`;
  els.uploadError.style.background = 'rgba(124,58,237,0.1)';
  els.uploadError.style.borderColor = 'rgba(124,58,237,0.3)';
  els.uploadError.style.color = '#a78bfa';
}

function hideUploadLoading() {
  // Only clear if it's still showing the loading message
  if (els.uploadError.textContent.startsWith('📤')) {
    els.uploadError.hidden = true;
    els.uploadError.textContent = '';
  }
}

/* ================================================================
   KEYBOARD SHORTCUTS  (Ctrl+Z = undo, Space = skip only)
   ================================================================ */

document.addEventListener('keydown', e => {
  if (!screens.triage.classList.contains('active')) return;
  // Don't fire shortcuts when typing in inputs
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
  // Don't fire shortcuts when typing in the add-category modal
  if (document.getElementById('modal-add-category').classList.contains('open')) return;

  if ((e.ctrlKey || e.metaKey) && e.key === 'z') {
    e.preventDefault();
    doUndo();
    return;
  }

  if (e.key === ' ' && !e.ctrlKey) {
    e.preventDefault();
    doSkip();
  }
});

/* ================================================================
   EVENT LISTENERS
   ================================================================ */

els.dropzone.addEventListener('click', () => els.fileInput.click());
els.dropzone.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') els.fileInput.click(); });

els.fileInput.addEventListener('change', e => {
  if (e.target.files[0]) handleFile(e.target.files[0]);
  e.target.value = '';
});

els.dropzone.addEventListener('dragover', e => { e.preventDefault(); els.dropzone.classList.add('drag-over'); });
els.dropzone.addEventListener('dragleave', e => { if (!els.dropzone.contains(e.relatedTarget)) els.dropzone.classList.remove('drag-over'); });
els.dropzone.addEventListener('drop', e => {
  e.preventDefault();
  els.dropzone.classList.remove('drag-over');
  handleFile(e.dataTransfer.files[0]);
});

els.btnLoadSample.addEventListener('click', handleSampleData);
els.btnUndo.addEventListener('click', doUndo);
els.btnSkip.addEventListener('click', doSkip);
els.btnExport.addEventListener('click', doSaveTotals);
if (els.btnResetLocal) els.btnResetLocal.addEventListener('click', doResetLocal);

els.btnRestart.addEventListener('click', async () => {
  try { await apiFetch('/session/reset', { method: 'POST' }); } catch { /* ignore */ }
  uiState = { currentTx: null, session: null, busy: false };
  refreshHeaderSummary();
  showScreen('upload');
});


/* ================================================================
   ADD CATEGORY MODAL
   ================================================================ */

const modal          = document.getElementById('modal-add-category');
const modalForm      = document.getElementById('modal-cat-form');
const modalName      = document.getElementById('modal-cat-name');
const modalIcon      = document.getElementById('modal-cat-icon');
const modalColor     = document.getElementById('modal-cat-color');
const modalError     = document.getElementById('modal-cat-error');
const btnAddCat      = document.getElementById('btn-add-category');
const btnModalClose  = document.getElementById('btn-modal-close');
const btnModalCancel = document.getElementById('btn-modal-cancel');

function showAddModal() {
  modalName.value  = '';
  modalIcon.value  = String.fromCodePoint(0x1F4E6);
  modalColor.value = '#a78bfa';
  modalError.hidden = true;
  modal.classList.add('open');
  setTimeout(() => modalName.focus(), 50);
}

function hideAddModal() {
  modal.classList.remove('open');
}

async function submitAddCategory(e) {
  e.preventDefault();
  const name  = modalName.value.trim();
  const icon  = modalIcon.value.trim() || String.fromCodePoint(0x1F4E6);
  const color = modalColor.value;
  if (!name) {
    modalError.textContent = 'Category name is required.';
    modalError.hidden = false;
    return;
  }
  try {
    await apiFetch('/categories', {
      method: 'POST',
      body: JSON.stringify({ name, icon, color, active: true }),
    });
    const cats = await apiFetch('/categories?active_only=true');
    buildCategoryButtons(cats.length ? cats : CATEGORIES);
    hideAddModal();
  } catch (err) {
    modalError.textContent = err.message || 'Failed to add category.';
    modalError.hidden = false;
  }
}

btnAddCat?.addEventListener('click', showAddModal);
btnModalClose?.addEventListener('click', hideAddModal);
btnModalCancel?.addEventListener('click', hideAddModal);
modalForm?.addEventListener('submit', submitAddCategory);
modal?.addEventListener('click', e => { if (e.target === modal) hideAddModal(); });
/* ================================================================
   INLINE MANUAL TRANSACTION ENTRY
   ================================================================ */

const btnAddTxUpload   = document.getElementById('btn-add-tx-upload-card');
const btnAddTxTriage   = document.getElementById('btn-add-tx-triage');

async function enterEditMode() {
  uiState.isEditMode = true;
  els.cardAmount.hidden = true;
  els.cardPerson.hidden = true;
  els.cardDate.hidden = true;
  
  els.cardAmountEdit.hidden = false;
  els.cardPersonEdit.hidden = false;
  els.cardDateEdit.hidden = false;

  els.btnUndo.hidden = true;
  els.btnSkip.hidden = true;
  document.getElementById('btn-add-tx-triage').hidden = true;
  els.btnFinishAdding.hidden = false;

  els.cardAmountEdit.value = '';
  els.cardPersonEdit.value = '';
  els.cardDateEdit.value = new Date().toISOString().split('T')[0];

  els.cardType.textContent = 'Type: (-) Exp / (+) Inc';
  els.cardType.className   = 'card-type';
  els.cardPersonLabel.textContent = 'Description or Party';
  els.cardRemark.hidden = true;
  els.cardBadge.hidden = true;
  
  showScreen('triage');
  setTimeout(() => els.cardAmountEdit.focus(), 100);

  // If there are no category buttons yet, fetch and render them
  if (els.categoriesGrid.children.length === 0) {
    try {
      const cats = await apiFetch('/categories?active_only=true');
      buildCategoryButtons(cats.length ? cats : CATEGORIES);
    } catch {
      buildCategoryButtons(CATEGORIES);
    }
  }
}

function exitEditMode() {
  uiState.isEditMode = false;
  els.cardAmount.hidden = false;
  els.cardPerson.hidden = false;
  els.cardDate.hidden = false;
  
  els.cardAmountEdit.hidden = true;
  els.cardPersonEdit.hidden = true;
  els.cardDateEdit.hidden = true;

  els.btnUndo.hidden = false;
  els.btnSkip.hidden = false;
  document.getElementById('btn-add-tx-triage').hidden = false;
  els.btnFinishAdding.hidden = true;
}

btnAddTxUpload?.addEventListener('click', enterEditMode);
btnAddTxTriage?.addEventListener('click', enterEditMode);
els.btnFinishAdding?.addEventListener('click', () => {
  exitEditMode();
  if (uiState.session && uiState.session.is_complete) {
    showDoneScreen({ session: uiState.session });
  } else if (!uiState.currentTx) {
    showScreen('upload');
  } else {
    // We have pending cards
    renderCard(uiState.currentTx);
  }
});

/* ================================================================
   DASHBOARD CHARTS
   ================================================================ */
let pieChartInstance = null;
let barChartInstance = null;

async function loadDashboardData() {
  try {
    const data = await apiFetch('/total_expenses', { method: 'GET' });
    const totals = data.totals || [];
    
    const now = new Date();
    const currentYear = now.getFullYear();
    const currentMonthIdx = now.getMonth();
    
    const monthNames = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
    const currentMonthName = monthNames[currentMonthIdx];
    
    document.getElementById('chart-month-label').textContent = `${currentMonthName} ${currentYear}`;
    
    const currentMonthEntry = totals.find(e => e.month === currentMonthName && e.year === currentYear);
    const currentMonthExpenses = currentMonthEntry ? currentMonthEntry.expenses : {};
    
    // For line chart: months until now
    const monthsUntilNow = monthNames.slice(0, currentMonthIdx + 1);
    const categoryData = {};
    
    totals.forEach(entry => {
      if (entry.year === currentYear && monthsUntilNow.includes(entry.month)) {
         for (const [cat, amt] of Object.entries(entry.expenses || {})) {
            if (!categoryData[cat]) categoryData[cat] = {};
            categoryData[cat][entry.month] = amt;
         }
      }
    });

    renderPieChart(currentMonthExpenses);
    renderLineChart(monthsUntilNow, categoryData);
  } catch (err) {
    console.error("Failed to load dashboard data:", err);
  }
}

function renderPieChart(expenses) {
  const ctx = document.getElementById('pieChart');
  const emptyMsg = document.getElementById('pie-empty');
  if (!ctx) return;
  
  if (pieChartInstance) pieChartInstance.destroy();
  
  const labels = Object.keys(expenses).filter(k => expenses[k] > 0);
  const data = labels.map(k => expenses[k]);
  
  if (data.length === 0) {
    ctx.style.display = 'none';
    emptyMsg.hidden = false;
    return;
  }
  
  ctx.style.display = 'block';
  emptyMsg.hidden = true;
  
  const colors = ['#7c3aed', '#0d9488', '#f59e0b', '#f43f5e', '#4f46e5', '#10b981', '#3b82f6', '#ec4899', '#8b5cf6', '#14b8a6'];
  
  pieChartInstance = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: labels,
      datasets: [{
        data: data,
        backgroundColor: colors.slice(0, labels.length),
        borderWidth: 0,
        hoverOffset: 4
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: 'right', labels: { color: '#f1f5f9', font: { size: 10 } } }
      }
    }
  });
}

function renderLineChart(months, categoryData) {
  const ctx = document.getElementById('barChart');
  const emptyMsg = document.getElementById('bar-empty');
  if (!ctx) return;
  
  if (barChartInstance) barChartInstance.destroy();
  
  const colors = ['#7c3aed', '#0d9488', '#f59e0b', '#f43f5e', '#4f46e5', '#10b981', '#3b82f6', '#ec4899', '#8b5cf6', '#14b8a6'];
  const datasets = [];
  let colorIdx = 0;
  
  for (const cat in categoryData) {
    // Check if category has any expenses > 0
    let hasExpenses = false;
    const dataPoints = months.map(m => {
      const val = categoryData[cat][m] || 0;
      if (val > 0) hasExpenses = true;
      return val;
    });
    
    if (hasExpenses) {
      datasets.push({
        label: cat,
        data: dataPoints,
        borderColor: colors[colorIdx % colors.length],
        backgroundColor: colors[colorIdx % colors.length],
        tension: 0.3,
        fill: false
      });
      colorIdx++;
    }
  }
  
  if (datasets.length === 0) {
    ctx.style.display = 'none';
    emptyMsg.hidden = false;
    return;
  }
  
  ctx.style.display = 'block';
  emptyMsg.hidden = true;
  
  barChartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels: months,
      datasets: datasets
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { 
        legend: { position: 'right', labels: { color: '#f1f5f9', font: { size: 10 } } } 
      },
      scales: {
        y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#94a3b8' } },
        x: { grid: { display: false }, ticks: { color: '#94a3b8', font: { size: 10 } } }
      }
    }
  });
}

/* ================================================================
   INIT
   ================================================================ */

showScreen('upload');
ensureHeaderSummary();
refreshHeaderSummary();
loadDashboardData();
