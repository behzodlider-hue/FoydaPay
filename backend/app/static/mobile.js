/* FoydaPay mobile app: onboarding, quick check, plan with real vacancies, calendar, security, chat, guided tour. */
'use strict';

/* ================= basics ================= */
let SID = null, STATE = null, PLAN = null, LLM = false;
let JOBS = null;           // {state: 'loading'|'ok'|'error', data} for the current session
let DEMO = null;           // during the tour: the user's real session, saved while Jasur's demo is shown
const $ = id => document.getElementById(id);
const store = {
  get(k, d){ try { const v = localStorage.getItem('fp_' + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v){ try { localStorage.setItem('fp_' + k, JSON.stringify(v)); } catch (e) {} },
  del(k){ try { localStorage.removeItem('fp_' + k); } catch (e) {} },
};
let USER = store.get('user', null);   // {lang, name, region, gender, age, education, work_status}; stays on this phone
let LANG = (USER && USER.lang) || store.get('lang', null) || 'en';
function t(key, vars){
  let s = (I18N[LANG] && I18N[LANG][key]) ?? I18N.en[key] ?? key;
  if (vars && typeof s === 'string') s = s.replace(/\{(\w+)\}/g, (m, k) => vars[k] ?? m);
  return s;
}
const spaced = n => n ? String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ' ') : '';
const fmt = n => (Math.round(n) < 0 ? '−' : '') + (spaced(Math.abs(n)) || '0') + ' ' + t('cur');
const digits = v => parseInt(String(v).replace(/[^\d]/g, '').slice(0, 12) || '0', 10);
const subName = n => (t('subn') || {})[n] || n;  // built-in subscription names come from the server in English
// Uzbek vacancy titles are stored in Cyrillic; the app writes Uzbek in Latin script.
const CYR = { а:'a',б:'b',в:'v',г:'g',д:'d',е:'e',ё:'yo',ж:'j',з:'z',и:'i',й:'y',к:'k',л:'l',м:'m',н:'n',о:'o',п:'p',р:'r',с:'s',т:'t',у:'u',ф:'f',х:'x',ц:'s',ч:'ch',ш:'sh',ъ:"'",ь:'',э:'e',ю:'yu',я:'ya',ў:"o'",қ:'q',ғ:"g'",ҳ:'h' };
const toLatin = s => s.replace(/[Ѐ-ӿ]/g, ch => { const lo = ch.toLowerCase(), r = CYR[lo] ?? ch; return ch === lo ? r : r.charAt(0).toUpperCase() + r.slice(1); });
const regionName = code => { const r = REGIONS.find(x => x[0] === code) || REGIONS[0]; return r[{ en: 1, ru: 2, uz: 3 }[LANG]]; };
function el(tag, attrs = {}, ...kids){
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') e.className = v; else if (k === 'text') e.textContent = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v); else if (v !== false && v != null) e.setAttribute(k, v);
  }
  kids.flat().forEach(k => k != null && k !== false && e.append(k.nodeType ? k : document.createTextNode(k)));
  return e;
}
// replaceChildren() would print null/false as text, so skip them
const fill = (node, ...kids) => node.replaceChildren(...kids.flat().filter(k => k != null && k !== false));
const svg = d => { const s = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); s.setAttribute('viewBox', '0 0 24 24'); s.setAttribute('fill', 'none'); s.setAttribute('stroke', 'currentColor'); s.setAttribute('stroke-width', '2'); s.innerHTML = d; return s; };
const ICON = {
  plan: '<path d="M4 19V5M4 19h16M8 15l3-4 3 2 5-6"/>', shield: '<path d="M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6z"/><path d="M9 12l2 2 4-4"/>',
  alert: '<path d="M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6z"/><path d="M12 8v5M12 16h.01"/>', play: '<circle cx="12" cy="12" r="9"/><path d="M10 8l6 4-6 4z"/>',
  back: '<path d="M15 18l-6-6 6-6"/>', ext: '<path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
};
async function api(path, body){
  const r = await fetch(path, { method: body ? 'POST' : 'GET', headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) {
    const msg = typeof d.detail === 'string' ? d.detail : Array.isArray(d.detail) && d.detail[0] ? String(d.detail[0].msg).replace(/^Value error, /, '') : 'Please check the numbers and try again.';
    const err = new Error(msg); err.status = r.status; throw err;
  }
  return d;
}
function toast(text){ const x = el('div', { class: 'toast', role: 'status', text }); document.body.append(x); setTimeout(() => x.remove(), 4500); }
const hasProfile = () => !!DEMO || !!(STATE && STATE.custom);
const link = (href, text) => el('a', { href, target: '_blank', rel: 'noopener' }, text, ' ↗');
const srcLine = (href, text) => el('p', { class: 'src' }, t('src') + ': ', link(href, text));
function applyStatic(){
  document.documentElement.lang = LANG;
  document.querySelectorAll('[data-t]').forEach(n => n.textContent = t(n.dataset.t));
  $('histBtn').setAttribute('aria-label', t('history')); $('newChatBtn').setAttribute('aria-label', t('new_chat'));
  $('q').placeholder = t('msg_ph_chat'); $('qLabel').textContent = t('msg_ph_chat'); $('sendBtn').setAttribute('aria-label', t('send'));
  $('modeBadge').textContent = LLM ? t('chat_status_ai') : t('chat_status_rules');
}

/* ================= dates ================= */
const DAY = 864e5;
const today = () => { const d = new Date(); d.setHours(0, 0, 0, 0); return d; };
const pad = n => String(n).padStart(2, '0');
const iso = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const parseIso = s => { const [y, m, d] = s.split('-').map(Number); return new Date(y, m - 1, d); };
const addDays = (d, n) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
const dayOf = (y, m, day) => new Date(y, m, Math.min(day, new Date(y, m + 1, 0).getDate()));
const nice = d => `${d.getDate()} ${t('months')[d.getMonth()]}`;
function nextDate(day){ const x = today(); let d = dayOf(x.getFullYear(), x.getMonth(), day); if (d < x) d = dayOf(x.getFullYear(), x.getMonth() + 1, day); return d; }

/* ================= navigation ================= */
const NAV_OF = { plan: 'check', calendar: 'home', security: 'home' };
function go(tab){
  if (tab === 'check' && PLAN && hasProfile() && !go.editing) tab = 'plan';
  go.editing = false;
  document.querySelectorAll('section[data-tab]').forEach(s => s.hidden = s.dataset.tab !== tab);
  $('nav').hidden = tab === 'welcome';
  const navTab = NAV_OF[tab] || tab;
  document.querySelectorAll('nav button').forEach(b => b.dataset.go === navTab ? b.setAttribute('aria-current', 'page') : b.removeAttribute('aria-current'));
  ({ welcome: renderWelcome, home: renderHome, plan: renderPlan, calendar: renderCalendar, security: renderSecurity, chat: renderChat, check: renderStep })[tab]();
  window.scrollTo(0, 0);
}
document.addEventListener('click', e => { const b = e.target.closest('[data-go]'); if (b && !TOUR.on) go(b.dataset.go); });
const current = () => (document.querySelector('section[data-tab]:not([hidden])') || {}).dataset?.tab;
const topbar = title => el('div', { class: 'topbar' },
  el('button', { class: 'icon', 'aria-label': t('back_home'), onclick: () => go('home') }, svg(ICON.back)), el('h2', { text: title }));
function tile(icon, cls, title, sub, onclick, tour){
  return el('button', { class: 'tile', onclick, 'data-tour': tour }, el('span', { class: 'ic ' + cls }, svg(icon)),
    el('span', { class: 'grow' }, el('b', { text: title }), el('span', { class: 'muted', text: sub })), el('span', { class: 'chev', 'aria-hidden': 'true', text: '›' }));
}
function chip(text, on, onclick){ return el('button', { class: 'chip', 'aria-pressed': on ? 'true' : 'false', text, onclick }); }
function setLang(l){
  LANG = l; store.set('lang', l);
  if (USER) { USER.lang = l; store.set('user', USER); }
  applyStatic();
  const cur = current(); if (cur) go(cur);
}

/* ================= onboarding ================= */
let OB = { step: USER ? 1 : 0, draft: null };
function renderWelcome(){
  const sec = document.querySelector('section[data-tab="welcome"]');
  if (OB.step === 0) {
    const langs = [['uz', "O'zbekcha"], ['ru', 'Русский'], ['en', 'English']];
    fill(sec, el('div', { class: 'ob' },
      el('p', { class: 'logo' }, 'Foyda', el('b', { text: 'Pay' })),
      el('h2', { text: "Tilni tanlang · Выберите язык · Choose your language" }),
      langs.map(([code, name]) => el('button', { class: 'langbtn', lang: code, onclick: () => { setLang(code); OB.step = 1; renderWelcome(); } }, el('span', { text: code.toUpperCase(), 'aria-hidden': 'true' }), name))));
    return;
  }
  if (OB.step === 1) {
    const d = OB.draft = OB.draft || { name: '', region: '1726', gender: '', age: '', education: '', work_status: '', ...(USER || {}) };
    const err = el('p', { class: 'muted', role: 'alert' });
    const group = (label, key, opts) => el('div', { class: 'f' }, el('span', { class: 'muted', text: label }),
      el('div', { class: 'chips' }, opts.map(([v, k]) => chip(t(k), d[key] === v, () => { d[key] = d[key] === v ? '' : v; renderWelcome(); }))));
    const region = el('select', { id: 'obRegion' }, REGIONS.map(r => el('option', { value: r[0], text: r[{ en: 1, ru: 2, uz: 3 }[LANG]] })));
    region.value = d.region; region.onchange = () => d.region = region.value;
    fill(sec, el('div', { class: 'ob' },
      el('div', { class: 'row between' }, el('p', { class: 'logo' }, 'Foyda', el('b', { text: 'Pay' })),
        el('div', { class: 'langs' }, ['uz', 'ru', 'en'].map(l => chip(l.toUpperCase(), LANG === l, () => setLang(l))))),
      el('div', { class: 'card' },
        el('h2', { text: t('ob_about') }), el('p', { class: 'muted', text: t('ob_about_sub') }),
        el('label', { class: 'f' }, t('ob_name'), el('input', { value: d.name, maxlength: '30', placeholder: t('ob_name_ph'), autocomplete: 'given-name', oninput: e => d.name = e.target.value })),
        el('label', { class: 'f', for: 'obRegion' }, t('ob_region'), region),
        group(t('ob_gender'), 'gender', [['male', 'g_male'], ['female', 'g_female'], ['none', 'g_none']]),
        el('label', { class: 'f' }, t('ob_age'), el('input', { inputmode: 'numeric', value: d.age, maxlength: '3', oninput: e => d.age = e.target.value.replace(/\D/g, '') })),
        group(t('ob_edu'), 'education', [['school', 'edu_school'], ['college', 'edu_college'], ['bachelor', 'edu_bachelor'], ['master', 'edu_master']]),
        group(t('ob_work'), 'work_status', [['employed', 'w_employed'], ['self_employed', 'w_self_employed'], ['student', 'w_student'], ['unemployed', 'w_unemployed'], ['retired', 'w_retired']]),
        el('p', { class: 'tip', text: t('ob_privacy') }), err,
        el('button', { class: 'primary block', text: t('ob_continue'), onclick: () => {
          if (!d.name.trim()) { err.textContent = t('ob_need_name'); return; }
          const age = d.age ? +d.age : null;
          if (age != null && (age < 14 || age > 100)) { err.textContent = t('ob_need_age'); return; }
          const first = !USER;
          USER = { ...d, name: d.name.trim(), age, lang: LANG }; store.set('user', USER);
          if (hasProfile() && !DEMO) sendProfile().catch(() => {});  // region or language changed: refresh the plan and vacancies
          if (first) { OB.step = 2; renderWelcome(); } else go('home');
        } }))));
    return;
  }
  fill(sec, el('div', { class: 'ob' },
    el('p', { class: 'logo' }, 'Foyda', el('b', { text: 'Pay' })),
    el('div', { class: 'card hero' },
      el('h2', { text: t('ob_tour_title') }), el('p', { class: 'muted', text: t('ob_tour_sub') }),
      el('button', { class: 'primary block', text: t('ob_tour_start'), onclick: () => startTour() }),
      el('button', { class: 'ghost block', text: t('ob_tour_skip'), onclick: () => { store.set('toured', 1); go('check'); } }))));
}

/* ================= home ================= */
function renderHome(){
  const h = $('home');
  if (!STATE) { fill(h, el('p', { class: 'muted', text: t('connecting') })); return; }
  const footer = el('div', { class: 'row wrap', style: 'justify-content:center' },
    el('span', { class: 'muted small', text: t('lang_label') + ':' }), el('span', { class: 'langs' }, ['uz', 'ru', 'en'].map(l => chip(l.toUpperCase(), LANG === l, () => setLang(l)))),
    el('button', { class: 'link', text: t('edit_details'), onclick: () => { OB = { step: 1, draft: null }; go('welcome'); } }),
    el('button', { class: 'link', text: t('delete_data'), onclick: resetAll }));
  if (!hasProfile()) {
    fill(h,
      el('div', { class: 'card hero' },
        el('p', { class: 'muted', text: t('welcome', { name: USER ? USER.name : '' }) }),
        el('h2', { text: t('welcome_h') }), el('p', { class: 'muted', text: t('welcome_p') }),
        el('button', { class: 'primary block', text: t('start_check'), 'data-go': 'check' })),
      tile(ICON.play, 'ok', t('watch_tour'), t('watch_tour_sub'), () => startTour()),
      tile(ICON.shield, 'ok', t('security'), t('security_sub_new'), () => go('security')),
      footer, el('p', { class: 'muted small', style: 'text-align:center', text: t('sandbox_note') }));
    return;
  }
  const st = STATE, pct = st.debt_load * 100, len = Math.min(pct, 100) / 100 * 264;
  const ringColor = pct > 50 ? '#FF8A6B' : pct > 40 ? '#F2C46B' : '#4CC495';
  const ring = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  ring.setAttribute('class', 'ring'); ring.setAttribute('viewBox', '0 0 100 100'); ring.setAttribute('role', 'img'); ring.setAttribute('aria-label', `${pct.toFixed(0)}%`);
  ring.innerHTML = `<circle cx="50" cy="50" r="42" fill="none" stroke="rgba(255,255,255,.15)" stroke-width="10"/><circle cx="50" cy="50" r="42" fill="none" stroke="${ringColor}" stroke-width="10" stroke-linecap="round" stroke-dasharray="${len} 264" transform="rotate(-90 50 50)"/><text x="50" y="50" text-anchor="middle" dominant-baseline="central" fill="#EEF3EF" font-size="20" font-weight="800">${pct.toFixed(0)}%</text>`;
  const sec = st.security, upcoming = buildEvents(today(), addDays(today(), 45)).slice(0, 4);
  const short = PLAN && PLAN.shortfall > 0;
  const acts = [...st.subscriptions.filter(s => !s.active).map(s => t('act_cancelled', { x: subName(s.name) })),
    ...st.booked.map(b => t('act_booked', { x: `${b.shifts} × ${b.title.split(' - ')[0]}` })), ...st.sent.map(x => t('act_sent', { x: x.to })),
    ...st.bills.filter(b => b.paid).map(b => t('act_paid', { x: b.name }))];
  const payday = prof().payday || 25;
  fill(h,
    DEMO ? el('p', { class: 'badge', text: t('tour_demo') }) : null,
    el('div', { class: 'card hero', 'data-tour': 'hero' },
      el('div', { class: 'row between' },
        el('div', {}, el('p', { class: 'muted', text: t('hi', { name: DEMO ? t('demo_name') : (USER ? USER.name : st.name) }) }), el('p', { class: 'big', text: fmt(digits(st.card_balance)) }), el('p', { class: 'muted', text: t('on_card') })), ring),
      el('p', { class: 'muted', text: t('income_line', { income: fmt(st.income_raw), day: payday }) }),
      el('p', { class: 'muted', text: t('load_line', { pct: pct.toFixed(1), pay: fmt(digits(st.loan_payments)) }) + ' · ' + (pct > 50 ? t('load_bad') : t('load_ok')) }),
      el('p', { class: 'src', style: 'color:var(--on-brand-muted)' }, t('src') + ': ', el('a', { href: SOURCES.dti, target: '_blank', rel: 'noopener', style: 'color:var(--on-brand)' }, t('src_dti'), ' ↗'))),
    PLAN ? tile(ICON.plan, short ? 'bad' : 'ok', short ? t('short_tile', { x: fmt(PLAN.shortfall) }) : t('buffer_tile', { x: fmt(-PLAN.shortfall) }),
      short && PLAN.remaining_after_cuts <= 0 ? t('plan_closes') : t('open_plan'), () => go('plan'), 'plantile') : null,
    el('div', { class: 'card' },
      el('div', { class: 'row between' }, el('h3', { text: t('coming_up') }), el('button', { class: 'link', text: t('calendar'), onclick: () => go('calendar') })),
      upcoming.length ? el('div', {}, upcoming.map(evRow)) : el('p', { class: 'muted', text: t('nothing_soon') })),
    el('div', { class: 'card' },
      el('div', { class: 'row between' }, el('h3', { text: t('your_loans') }), el('span', { class: 'muted', text: t('per_month', { x: fmt(digits(st.loan_payments)) }) })),
      el('ul', { class: 'list' }, st.loans.map(l => {
        const next = l.due_day ? nextDate(l.due_day) : null;
        return el('li', {}, el('div', { class: 'grow' }, el('b', { text: l.label }),
          el('div', { class: 'muted', text: (l.lender !== l.label ? l.lender + ' · ' : '') + t('loan_meta', { rate: (l.rate * 100).toFixed(0), months: l.months, owed: fmt(l.balance) }) + (next ? ' · ' + t('next_pay', { d: nice(next) }) : '') })),
          el('span', { text: fmt(l.payment_raw) }));
      }))),
    tile(sec.attacks ? ICON.alert : ICON.shield, sec.attacks ? 'warn' : 'ok', t('security'), sec.attacks ? t('sec_bad', { n: sec.attacks }) : t('sec_ok'), () => go('security'), 'sectile'),
    acts.length ? el('div', { class: 'card' }, el('h3', { text: t('done_in_app') }), el('ul', { class: 'list' }, acts.map(a => el('li', {}, el('span', { text: a }), el('span', { text: '✓' }))))) : null,
    DEMO ? null : tile(ICON.play, 'ok', t('watch_tour'), t('watch_tour_sub'), () => startTour()),
    DEMO ? null : footer,
    el('p', { class: 'muted small', style: 'text-align:center', text: t('sandbox_custom') }));
}
function resetAll(){
  if (!confirm(t('delete_confirm'))) return;
  ['profile', 'sid', 'chats', 'chat_cur', 'reminders', 'fired', 'user', 'toured', 'lang'].forEach(store.del);
  location.reload();
}

/* ================= confirmations ================= */
function sheet(content){
  const wrap = el('div', { class: 'sheet-wrap', role: 'dialog', 'aria-modal': 'true' });
  wrap.append(el('div', { class: 'sheet' }, content));
  wrap.addEventListener('click', e => { if (e.target === wrap && !TOUR.on) wrap.remove(); });
  document.body.append(wrap); return wrap;
}
// The server words confirmations in English; known actions are re-worded in the app language from their facts.
function confirmText(ev){
  const f = ev.facts || {};
  if (ev.tool === 'cancel_subscriptions') {
    const names = (f.subscription_ids || []).map(id => (STATE.subscriptions[+id.slice(1) - 1] || {}).name).filter(Boolean).map(subName);
    const saves = (f.subscription_ids || []).reduce((a, id) => a + digits((STATE.subscriptions[+id.slice(1) - 1] || {}).amount || 0), 0);
    const lines = (f.subscription_ids || []).map(id => STATE.subscriptions[+id.slice(1) - 1]).filter(Boolean).map(x => `${subName(x.name)}: ${fmt(digits(x.amount))}${t('per_month_short')}`);
    return { title: t('cf_cancel_subscriptions', { x: names.join(' + ') }), details: [...lines, t('cf_saves', { x: fmt(saves) })] };
  }
  if (ev.tool === 'send_restructuring_request')
    return { title: t('cf_send_restructuring_request', { x: f.payee }), details: [t('cf_months', { n: f.months }), t('cf_bank_decides')] };
  return { title: ev.summary, details: ev.details };
}
function confirmSheet(ev, after){
  const c = confirmText(ev);
  const ok = el('button', { class: 'primary block', text: t('confirm') }), no = el('button', { class: 'ghost block', text: t('cancel') });
  const msg = el('p', { class: 'muted' });
  const w = sheet([el('p', { class: 'tier', text: t('needs_confirm') }), el('h3', { text: c.title }),
    el('ul', { class: 'list' }, c.details.map(d => el('li', {}, el('span', { text: d })))), msg, ok, no]);
  w.dataset.tour = 'sheet';
  const decide = async approve => {
    ok.disabled = no.disabled = true;
    try { const r = await api('/api/confirm', { session_id: SID, confirmation_id: ev.id, approve }); STATE = r.state; msg.textContent = approve ? t('confirmed') : t('cancelled'); after && after(r); refresh(); setTimeout(() => w.remove(), 900); }
    catch (e) { msg.textContent = e.message; }
  };
  ok.onclick = () => decide(true); no.onclick = () => decide(false);
  return w;
}
async function act(tool, args, onResult){
  try {
    const r = await api('/api/action', { session_id: SID, tool, args });
    STATE = r.state;
    if (r.event && r.event.type === 'confirm') confirmSheet(r.event, () => onResult && onResult(r));
    else { if (r.is_error && r.result.message) toast(r.result.message); onResult && onResult(r); }
    return r;
  } catch (e) { toast(e.message); }
}
function refresh(){ const open = current(); if (open && !['check', 'chat', 'welcome'].includes(open)) go(open); }

/* ================= quick check ================= */
const BLANK = { income: 0, payday: 25, balance: 0, rent: 0, groceries: 0, transport: 0, delivery: 0, cafes: 0, utilities: 0, other: 0,
  loans: [{ label: 'Bank loan', lender: '', balance: 0, rate: 24, months: 12, due_day: 5 }], subscriptions: [],
  weekend_days: 2, evenings: 2, hours_per_week: 10, formats: [], skills: [], skills_note: '', has_car: false };
let P = Object.assign(structuredClone(BLANK), store.get('profile', {}));
const DEMO_P = { payday: 25, utilities: 437000, formats: [] };  // Jasur's calendar numbers for the tour
const prof = () => DEMO ? DEMO_P : P;
let step = 0;
const SUBS = ['music', 'video', 'video2', 'gym', 'cloud', 'other'];
const LOAN_TYPES = [['Bank loan', 'lt_bank', 24], ['Microloan', 'lt_micro', 48], ['Installment (nasiya)', 'lt_nasiya', 0], ['Car loan', 'lt_car', 22], ['Mortgage', 'lt_mortgage', 18]];
const SKILLS = [['excel-basic', 'sk_excel'], ['smartphone', 'sk_phone'], ['car', 'sk_car'], ['languages', 'sk_lang'], ['design', 'sk_design']];
const FORMATS = [['day', 'f_day'], ['alternate', 'f_alt'], ['evening', 'f_evening'], ['night', 'f_night'], ['online', 'f_online']];

function moneyInput(get, set){
  const inp = el('input', { inputmode: 'numeric', autocomplete: 'off', placeholder: '0' });
  inp.value = spaced(get());
  inp.addEventListener('input', () => {  // keep the caret after the same digit while spaces are inserted
    const caret = inp.selectionStart ?? inp.value.length;
    const before = inp.value.slice(0, caret).replace(/\D/g, '').length;
    const n = digits(inp.value); set(n); inp.value = spaced(n);
    let i = 0, c = 0; while (i < inp.value.length && c < before) { if (/\d/.test(inp.value[i])) c++; i++; }
    try { inp.setSelectionRange(i, i); } catch (e) {}
  });
  return inp;
}
const money = (key, label) => el('label', { class: 'f' }, label, moneyInput(() => P[key], n => P[key] = n));
function counter(label, key, max, stepBy = 1, unit = ''){
  const v = el('span', { class: 'num', text: P[key] + unit });
  const set = d => { P[key] = Math.max(0, Math.min(max, P[key] + d)); v.textContent = P[key] + unit; };
  return el('div', { class: 'row between' }, el('span', { text: label }),
    el('div', { class: 'row' }, el('button', { class: 'ghost', 'aria-label': '−', text: '−', onclick: () => set(-stepBy) }), v, el('button', { class: 'ghost', 'aria-label': '+', text: '+', onclick: () => set(stepBy) })));
}
const toggleIn = (arr, v, on) => on ? [...new Set([...arr, v])] : arr.filter(x => x !== v);
const loanLabel = l => { const lt = LOAN_TYPES.find(x => x[0] === l); return lt ? t(lt[1]) : l; };

const STEPS = [
  { title: 's1_title', render: () => [
      el('p', { class: 'muted', text: t('s1_sub') }),
      money('income', t('income_after_tax')),
      el('div', { class: 'chips' }, [3, 5, 6, 8, 12].map(m => chip(t('mln', { n: m }), P.income === m * 1e6, () => { P.income = m * 1e6; renderStep(); }))),
      el('label', { class: 'f' }, t('payday_label'), el('input', { inputmode: 'numeric', value: String(P.payday), oninput: e => P.payday = Math.min(31, Math.max(1, digits(e.target.value) || 1)) })),
      money('balance', t('card_now'))],
    ok: () => P.income >= 100000 || t('need_income') },
  { title: 's2_title', render: () => [
      ...P.loans.map((l, i) => el('div', { class: 'card' },
        el('div', { class: 'row between' }, el('h3', { text: t('loan_n', { n: i + 1 }) }), P.loans.length > 1 ? el('button', { class: 'ghost', text: t('remove'), onclick: () => { P.loans.splice(i, 1); renderStep(); } }) : null),
        el('div', { class: 'chips' }, LOAN_TYPES.map(([v, k, r]) => chip(t(k), l.label === v, () => { l.label = v; l.rate = r; renderStep(); }))),
        el('label', { class: 'f' }, t('lender'), el('input', { value: l.lender, maxlength: '40', placeholder: t('lender_ph'), oninput: e => l.lender = e.target.value })),
        el('label', { class: 'f' }, t('owed'), moneyInput(() => l.balance, n => l.balance = n)),
        el('div', { class: 'grid2' },
          el('label', { class: 'f' }, t('rate_year'), el('input', { inputmode: 'decimal', value: String(l.rate), oninput: e => l.rate = parseFloat(e.target.value.replace(',', '.')) || 0 })),
          el('label', { class: 'f' }, t('months_left'), el('input', { inputmode: 'numeric', value: String(l.months), oninput: e => l.months = digits(e.target.value) }))),
        el('label', { class: 'f' }, t('due_day'), el('input', { inputmode: 'numeric', value: l.due_day ? String(l.due_day) : '', placeholder: t('due_ph'), oninput: e => l.due_day = Math.min(31, digits(e.target.value)) })))),
      P.loans.length < 5 ? el('button', { class: 'ghost block', text: t('add_loan'), onclick: () => { P.loans.push({ label: 'Microloan', lender: '', balance: 0, rate: 48, months: 12, due_day: 0 }); renderStep(); } }) : null],
    ok: () => P.loans.every(l => l.balance >= 100000 && l.months >= 1) || t('need_loans') },
  { title: 's3_title', render: () => {
      const other = P.subscriptions.find(s => s.key === 'other');
      return [
      el('div', { class: 'grid2' }, money('rent', t('rent')), money('utilities', t('utilities')), money('groceries', t('groceries')), money('transport', t('transport')),
        money('delivery', t('delivery')), money('cafes', t('cafes'))),
      money('other', t('other_spend')),
      el('p', { class: 'tip', text: t('other_tip') }),
      el('h3', { text: t('subs') }), el('p', { class: 'muted', text: t('subs_sub') }),
      el('div', { class: 'chips' }, SUBS.map(k => {
        const s = P.subscriptions.find(x => x.key === k), name = t('sub_' + k);
        return chip(!s ? name : s.used ? t('in_use', { x: name }) : t('not_used', { x: name }), !!s, () => {
          if (!s) { if (P.subscriptions.length >= 5) return; P.subscriptions.push(k === 'other' ? { key: k, used: true, name: '', amount: 0 } : { key: k, used: true }); }
          else if (s.used) s.used = false; else P.subscriptions = P.subscriptions.filter(x => x.key !== k);
          renderStep(); });
      })),
      other ? el('div', { class: 'card' },
        el('h3', { text: t('other_sub') }),
        el('label', { class: 'f' }, t('other_what'), el('input', { value: other.name, maxlength: '30', placeholder: t('other_what_ph'), oninput: e => other.name = e.target.value })),
        el('label', { class: 'f' }, t('other_price'), moneyInput(() => other.amount, n => other.amount = n)),
        el('p', { class: 'tip', text: t('other_sub_tip') })) : null];
    },
    ok: () => { const o = P.subscriptions.find(s => s.key === 'other'); return !o || o.amount >= 1000 || t('need_other_price'); } },
  { title: 's4_title', render: () => {
      const alt = P.formats.find(f => f.startsWith('alternate'));
      return [
      el('p', { class: 'muted', text: t('s4_sub') }),
      el('div', { class: 'card' }, counter(t('weekend_days'), 'weekend_days', 8), counter(t('evenings'), 'evenings', 20), counter(t('hours_week'), 'hours_per_week', 60, 2, t('h'))),
      el('h3', { text: t('when_work') }),
      el('div', { class: 'chips' }, FORMATS.map(([k, key]) => {
        const on = k === 'alternate' ? !!alt : P.formats.includes(k);
        return chip(t(key), on, () => { P.formats = k === 'alternate' ? (alt ? P.formats.filter(f => f !== alt) : [...P.formats, 'alternate_even']) : toggleIn(P.formats, k, !on); renderStep(); });
      })),
      alt ? el('div', { class: 'chips' }, el('span', { class: 'muted', text: t('which_days') }),
        chip(t('even_days'), alt === 'alternate_even', () => { P.formats = [...P.formats.filter(f => f !== alt), 'alternate_even']; renderStep(); }),
        chip(t('odd_days'), alt === 'alternate_odd', () => { P.formats = [...P.formats.filter(f => f !== alt), 'alternate_odd']; renderStep(); })) : null,
      el('h3', { text: t('what_know') }),
      el('div', { class: 'chips' }, SKILLS.map(([k, key]) => {
        const on = k === 'car' ? P.has_car : P.skills.includes(k);
        return chip(t(key), on, () => { if (k === 'car') P.has_car = !on; else P.skills = toggleIn(P.skills, k, !on); renderStep(); });
      })),
      el('label', { class: 'f' }, t('else_can'), el('textarea', { maxlength: '200', placeholder: t('else_ph'), oninput: e => P.skills_note = e.target.value }, P.skills_note))];
    }, ok: () => true },
  { title: 's5_title', render: () => {
      const spend = P.rent + P.groceries + P.transport + P.delivery + P.cafes + P.utilities + P.other;
      const fm = P.formats.map(f => t({ day: 'f_day', alternate_even: 'even_days', alternate_odd: 'odd_days', evening: 'f_evening', night: 'f_night', online: 'f_online' }[f]));
      return [el('ul', { class: 'list card' },
        el('li', {}, el('span', { text: t('sum_income') }), el('span', { text: fmt(P.income) })),
        el('li', {}, el('span', { text: t('sum_loans', { n: P.loans.length }) }), el('span', { text: t('sum_owed', { x: fmt(P.loans.reduce((a, l) => a + l.balance, 0)) }) })),
        el('li', {}, el('span', { text: t('sum_spend') }), el('span', { text: t('per_month', { x: fmt(spend) }) })),
        el('li', {}, el('span', { text: t('sum_subs') }), el('span', { text: String(P.subscriptions.length) })),
        el('li', {}, el('span', { text: t('sum_work') }), el('span', { text: t('sum_hours', { h: P.hours_per_week }) })),
        fm.length ? el('li', {}, el('span', { text: fm.join(', ') })) : null),
        el('p', { class: 'muted', text: t('s5_note') })];
    }, ok: () => true },
];
function renderStep(){
  fill($('stepBar'), STEPS.map((_, i) => el('i', { class: i <= step ? 'on' : '' })));
  fill($('stepBody'), el('div', { class: 'card' }, el('p', { class: 'muted small', text: t('step_of', { n: step + 1, total: STEPS.length }) }), el('h2', { text: t(STEPS[step].title) }), STEPS[step].render()),
    el('p', { class: 'muted', id: 'stepErr', role: 'alert' }));
  $('backBtn').hidden = step === 0; $('backBtn').textContent = t('back');
  $('nextBtn').textContent = step === STEPS.length - 1 ? t('get_plan') : t('next');
}
$('backBtn').onclick = () => { step = Math.max(0, step - 1); renderStep(); };
$('nextBtn').onclick = async () => {
  const ok = STEPS[step].ok();
  if (ok !== true) { $('stepErr').textContent = ok; return; }
  if (step < STEPS.length - 1) { step++; renderStep(); window.scrollTo(0, 0); return; }
  $('nextBtn').disabled = true; $('nextBtn').textContent = t('building');
  try { await sendProfile(); store.set('profile', P); go('plan'); }
  catch (e) { $('stepErr').textContent = e.message; }
  $('nextBtn').disabled = false; $('nextBtn').textContent = t('get_plan');
};
async function sendProfile(){
  const u = USER || {};
  const r = await api('/api/profile', { session_id: SID, ...P, name: u.name || 'friend', lang: LANG, region: u.region || '1726',
    age: u.age || null, education: u.education || '', work_status: u.work_status || '' });
  PLAN = r.plan; STATE = r.state; JOBS = null;
}

/* ================= plan ================= */
function cutText(c){ const p = { ...c.params }; if (p.name) p.name = subName(p.name); ['cap', 'now'].forEach(k => p[k] != null && (p[k] = fmt(p[k]))); return c.code ? t('c_' + c.code, p) : c.what; }
function adviceText(a){ const p = { ...a.params }; if (p.name) p.name = subName(p.name); if (p.share != null) p.share = Math.round(p.share * 100); if (p.amount != null) p.amount = fmt(p.amount); return a.code ? t('a_' + a.code, p) : a.text; }
function loadJobs(){
  if (JOBS && JOBS.state !== 'error') return;
  JOBS = { state: 'loading' };
  const sid = SID;
  api('/api/jobs', { session_id: sid }).then(d => { if (sid === SID) JOBS = { state: 'ok', data: d }; })
    .catch(() => { if (sid === SID) JOBS = { state: 'error' }; })
    .finally(() => { if (sid === SID && current() === 'plan') renderEarn(); });
}
function renderEarn(){
  const box = $('earnBox'); if (!box || !PLAN) return;
  const gap = PLAN.remaining_after_cuts, region = regionName(DEMO ? '1726' : (USER && USER.region) || '1726');
  if (!JOBS || JOBS.state === 'loading') { fill(box, el('div', { class: 'row' }, el('span', { class: 'spin', 'aria-hidden': 'true' }), el('p', { class: 'muted', text: t('earn_wait', { region }) }))); return; }
  if (JOBS.state === 'error') { fill(box, el('p', { class: 'muted', text: t('jobs_error') }), el('button', { class: 'ghost', text: t('jobs_retry'), onclick: () => { JOBS = null; loadJobs(); renderEarn(); } })); return; }
  const d = JOBS.data;
  fill(box,
    el('p', { text: gap > 0 ? t('earn_gap', { x: fmt(gap) }) : t('earn_nogap') }),
    d.vacancies.length ? el('div', {}, d.vacancies.slice(0, 5).map(v => el('div', { class: 'job' },
      el('div', { class: 'row between' }, el('b', { text: LANG === 'uz' && v.title_uz ? toLatin(v.title_uz) : v.title }),
        gap > 0 && v.salary >= gap ? el('span', { class: 'pill ok', text: t('covers_gap') }) : null),
      el('span', { class: 'muted small', text: `${v.company} · ${v.region_code ? regionName(v.region_code) : v.region}` }),
      el('span', { class: 'small' }, el('b', { text: fmt(v.salary) + t('per_month_short') }), ' · ', v.rate === 1 ? t('full_time') : t('part_rate', { r: v.rate })),
      el('div', { class: 'row' }, el('a', { href: v.url, target: '_blank', rel: 'noopener', class: 'small' }, t('open_vacancy'), ' ↗'),
        el('button', { class: 'link small', text: t('remind_apply'), onclick: () => reminderSheet({ title: t('apply_title', { x: v.title }), date: iso(addDays(today(), 1)), time: '10:00' }) }))))) :
      el('p', { class: 'muted', text: t('jobs_none') }),
    USER && USER.work_status === 'employed' && !DEMO ? el('p', { class: 'muted small', text: t('jobs_employed') }) : null,
    el('div', { class: 'row wrap' }, link(d.more.hh, t('more_hh')), link(d.more.official, t('more_official'))),
    el('p', { class: 'src', text: t('jobs_note') }),
    srcLine(SOURCES.vacancies, 'ish.mehnat.uz'));
}
function renderPlan(){
  const sec = document.querySelector('section[data-tab="plan"]');
  if (!PLAN) { fill(sec, topbar(t('your_plan')), el('p', { class: 'muted', text: t('run_check_first') }), el('button', { class: 'primary', text: t('start_check'), 'data-go': 'check' })); return; }
  const p = PLAN, short = p.shortfall > 0, n = p.negotiate;
  const activeIds = new Set(STATE.subscriptions.map((s, i) => s.active ? 'S' + (i + 1) : null));
  const cutsSubs = p.cut.items.filter(c => c.subscription_id && activeIds.has(c.subscription_id)).map(c => c.subscription_id);
  const spare = p.cut.total - p.shortfall;
  fill(sec,
    DEMO ? el('p', { class: 'badge', text: t('tour_demo') }) : null,
    el('div', { class: 'row between' }, topbar(t('your_plan')), DEMO ? null : el('button', { class: 'ghost', text: t('edit_answers'), onclick: () => { step = 0; go.editing = true; go('check'); } })),
    el('div', { class: 'banner ' + (short ? 'bad' : 'ok') },
      el('p', { class: 'muted', text: short ? t('short_next') : t('buffer_next') }),
      el('p', { class: 'big', text: fmt(Math.abs(p.shortfall)) }),
      el('p', { text: t('loans_take', { pct: (p.debt_load * 100).toFixed(1), pay: fmt(p.loan_payments) }) + (p.debt_load > 0.5 ? ' ' + t('above_limit') : '') }),
      srcLine(SOURCES.dti, t('src_dti'))),
    el('div', { class: 'card', 'data-tour': 'cut' },
      el('div', { class: 'row between' }, el('h3', { text: t('cut_title') }), el('span', { class: 'pill ok', text: '+' + fmt(p.cut.total) })),
      p.cut.items.length ? el('ul', { class: 'list' }, p.cut.items.map(c => el('li', {}, el('span', { text: cutText(c) }), el('span', { text: fmt(c.saves) })))) : el('p', { class: 'muted', text: t('no_cuts') }),
      el('p', { class: 'src', text: t('based_on_numbers') }),
      cutsSubs.length ? el('button', { class: 'block', 'data-tour': 'cancelbtn', text: t('cancel_unused'), onclick: () => act('cancel_subscriptions', { subscription_ids: cutsSubs }) }) : null),
    p.advice && p.advice.length ? el('div', { class: 'card' }, el('h3', { text: t('worth_look') }), el('ul', { class: 'list' }, p.advice.map(a => el('li', {}, el('span', { text: adviceText(a) }))))) : null,
    el('div', { class: 'card', 'data-tour': 'earn' }, el('h3', { text: t('earn_title') }), el('div', { id: 'earnBox' })),
    el('div', { class: 'card', 'data-tour': 'negotiate' },
      el('div', { class: 'row between' }, el('h3', { text: t('neg_title') }), el('span', { class: 'pill warn', text: '−' + fmt(n.saves_per_month) + t('per_month_short') })),
      el('p', { text: t('neg_text', { lender: n.lender, months: n.months, pct: (n.new_debt_load * 100).toFixed(1), extra: fmt(n.extra_interest_total) }) }),
      STATE.sent.length ? el('p', { class: 'pill ok', text: t('request_sent') }) :
      el('button', { class: 'block', text: t('draft_request'), onclick: () => act('draft_restructuring_request', { months: n.months }, r => {
        const res = r.result.result;
        sheet([el('h3', { text: t('draft_title') }), el('pre', { text: res.letter }), el('p', { class: 'muted', text: t('not_legal') }),
          el('button', { class: 'primary block', text: t('send_to', { x: n.lender }), onclick: e => { e.target.closest('.sheet-wrap').remove(); act('send_restructuring_request', { months: n.months }); } })]);
      }) }),
      srcLine(SOURCES.consumer[LANG], t('src_consumer'))),
    el('div', { class: 'banner ' + (!short || p.remaining_after_cuts <= 0 ? 'ok' : 'warn') },
      el('p', { text: !short ? t('no_gap') : p.remaining_after_cuts <= 0 ? t('spare', { x: fmt(spare) }) : t('still_missing', { x: fmt(p.remaining_after_cuts) }) })),
    DEMO ? null : el('div', { class: 'grid2' },
      el('button', { class: 'ghost', text: t('see_calendar'), onclick: () => go('calendar') }),
      el('button', { class: 'ghost', text: t('ask_it'), onclick: () => { go('chat'); $('q').value = t('ask_plan_q'); $('q').focus(); } })));
  loadJobs(); renderEarn();
}

/* ================= calendar ================= */
const KIND = { loan: ['k-loan', 'k_loan'], payday: ['k-payday', 'k_payday'], bank: ['k-bank', 'k_bank'], rem: ['k-rem', 'k_rem'], bill: ['k-bill', 'k_bill'] };
let CAL = { month: null, sel: null };
function reminders(){ return store.get('reminders', []); }
function buildEvents(from, to){
  if (!hasProfile()) return [];
  const ev = [], st = STATE, pr = prof(), payday = pr.payday || 25;
  for (let o = -1; o <= 3; o++) {
    const base = new Date(from.getFullYear(), from.getMonth() + o, 1), y = base.getFullYear(), m = base.getMonth();
    ev.push({ date: dayOf(y, m, payday), kind: 'payday', title: t('ev_payday'), amount: st.income_raw, sign: '+' });
    if (pr.utilities) ev.push({ date: dayOf(y, m, 10), kind: 'bill', title: t('ev_bills'), amount: pr.utilities });
  }
  st.loans.forEach((l, i) => {  // the next payments from today, while months are left
    if (!l.due_day) return;
    const first = nextDate(l.due_day);
    for (let k = 0; k < Math.min(l.months, 6); k++)
      ev.push({ date: dayOf(first.getFullYear(), first.getMonth() + k, l.due_day), kind: 'loan', title: t('ev_pay', { x: l.label }), sub: l.lender, amount: l.payment_raw, loan: i });
  });
  if (st.sent.length) ev.push({ date: addDays(today(), 7), kind: 'bank', title: t('ev_bank', { x: st.sent[0].to }), sub: t('ev_bank_sub') });
  if (!DEMO) reminders().forEach(r => {
    const first = parseIso(r.date);
    for (let o = 0; o <= (r.repeat === 'monthly' ? 6 : 0); o++) {
      const d = o ? dayOf(first.getFullYear(), first.getMonth() + o, first.getDate()) : first;
      ev.push({ date: d, kind: 'rem', title: r.title, sub: r.time + (r.repeat === 'monthly' ? ' · ' + t('every_month') : ''), rem: r.id });
    }
  });
  return ev.filter(e => e.date >= from && e.date <= to).sort((a, b) => a.date - b.date || a.kind.localeCompare(b.kind));
}
function evRow(e){
  return el('div', { class: 'ev' },
    el('div', { class: 'date' }, el('b', { text: e.date.getDate() }), el('span', { text: t('months')[e.date.getMonth()] })),
    el('span', { class: 'dot ' + KIND[e.kind][0], 'aria-hidden': 'true' }),
    el('div', { class: 'grow' }, el('div', { text: e.title }),
      e.sub || e.amount ? el('div', { class: 'muted small', text: [e.amount ? (e.sign || '') + fmt(e.amount) : '', e.sub].filter(Boolean).join(' · ') }) : null),
    e.kind === 'loan' && !DEMO ? el('button', { class: 'link small', text: t('remind'), onclick: () => remindFor(e) }) : null,
    e.rem ? el('button', { class: 'link small', text: t('del'), onclick: () => { store.set('reminders', reminders().filter(r => r.id !== e.rem)); renderCalendar(); } }) : null);
}
function renderCalendar(){
  const sec = document.querySelector('section[data-tab="calendar"]');
  if (!hasProfile()) { fill(sec, topbar(t('calendar')), el('p', { class: 'muted', text: t('cal_first') }), el('button', { class: 'primary', text: t('start_check'), 'data-go': 'check' })); return; }
  const x = today();
  CAL.month = CAL.month || new Date(x.getFullYear(), x.getMonth(), 1); CAL.sel = CAL.sel || x;
  const m = CAL.month, start = addDays(m, -((m.getDay() + 6) % 7));
  const evs = buildEvents(start, addDays(start, 41)), byDay = {};
  evs.forEach(e => (byDay[iso(e.date)] = byDay[iso(e.date)] || []).push(e));
  const cells = [];
  for (let i = 0; i < 42; i++) {
    const d = addDays(start, i), k = iso(d), list = byDay[k] || [];
    cells.push(el('button', { class: (d.getMonth() !== m.getMonth() ? 'out ' : '') + (k === iso(x) ? 'today' : ''), 'aria-pressed': k === iso(CAL.sel) ? 'true' : 'false',
      'aria-label': nice(d) + (list.length ? ', ' + t('events_n', { n: list.length }) : ''), onclick: () => { CAL.sel = d; renderCalendar(); } },
      el('span', { text: d.getDate() }), el('span', { class: 'dots' }, [...new Set(list.map(e => e.kind))].slice(0, 3).map(kd => el('i', { class: KIND[kd][0] })))));
  }
  const selList = byDay[iso(CAL.sel)] || [], later = buildEvents(addDays(CAL.sel, 1), addDays(CAL.sel, 30)).slice(0, 3);
  fill(sec, DEMO ? el('p', { class: 'badge', text: t('tour_demo') }) : null, topbar(t('calendar')),
    el('div', { class: 'card', 'data-tour': 'month' },
      el('div', { class: 'row between' },
        el('button', { class: 'icon', 'aria-label': t('prev_month'), onclick: () => { CAL.month = new Date(m.getFullYear(), m.getMonth() - 1, 1); renderCalendar(); } }, svg(ICON.back)),
        el('h3', { text: `${t('months')[m.getMonth()]} ${m.getFullYear()}` }),
        el('button', { class: 'icon', 'aria-label': t('next_month'), style: 'transform:scaleX(-1)', onclick: () => { CAL.month = new Date(m.getFullYear(), m.getMonth() + 1, 1); renderCalendar(); } }, svg(ICON.back))),
      el('div', { class: 'cal' }, t('wd').map(w => el('span', { class: 'wd', text: w })), cells),
      el('div', { class: 'row between' }, el('h3', { text: nice(CAL.sel) }), DEMO ? null : el('button', { class: 'link', text: t('reminder_short'), onclick: () => reminderSheet({ date: iso(CAL.sel) }) })),
      selList.length ? el('div', {}, selList.map(evRow)) : el('p', { class: 'muted', text: t('nothing_day') }),
      !selList.length && later.length ? el('div', {}, el('p', { class: 'muted small', text: t('coming_next') }), later.map(evRow)) : null),
    el('div', { class: 'legend' }, Object.values(KIND).map(([c, k]) => el('span', {}, el('i', { class: 'dot ' + c }), t(k)))),
    DEMO ? null : el('button', { class: 'primary block', text: t('add_reminder'), onclick: () => reminderSheet({}) }),
    el('p', { class: 'muted small', text: t('cal_note') }));
}

/* ---- reminders ---- */
function remindFor(e){ const d = addDays(e.date, -1); reminderSheet({ title: t('r_tomorrow', { x: e.title }), date: iso(d < today() ? today() : d), time: '10:00', repeat: 'monthly' }); }
function reminderSheet(r){
  r = { title: '', date: iso(today()), time: '10:00', repeat: 'none', ...r };
  const title = el('input', { value: r.title, maxlength: '60', placeholder: t('r_what_ph') });
  const date = el('input', { type: 'date', value: r.date }), time = el('input', { type: 'time', value: r.time });
  const repeat = el('select', {}, el('option', { value: 'none', text: t('r_once') }), el('option', { value: 'monthly', text: t('r_monthly') }));
  repeat.value = r.repeat;
  const err = el('p', { class: 'muted', role: 'alert' });
  const save = () => {
    const x = { id: r.id || 'r' + Date.now().toString(36), title: title.value.trim(), date: date.value, time: time.value || '10:00', repeat: repeat.value };
    if (!x.title || !x.date) { err.textContent = t('r_need'); return null; }
    store.set('reminders', [...reminders().filter(y => y.id !== x.id), x]);
    if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission().catch(() => {});
    return x;
  };
  const w = sheet([el('h3', { text: t('reminder') }), el('label', { class: 'f' }, t('r_what'), title),
    el('div', { class: 'grid2' }, el('label', { class: 'f' }, t('r_date'), date), el('label', { class: 'f' }, t('r_time'), time)),
    el('label', { class: 'f' }, t('r_repeat'), repeat), err,
    el('button', { class: 'primary block', text: t('r_save'), onclick: () => { if (save()) { w.remove(); toast(t('r_saved')); refresh(); } } }),
    el('button', { class: 'ghost block', text: t('r_save_ics'), onclick: () => { const x = save(); if (x) { downloadIcs(x); w.remove(); refresh(); } } })]);
  title.focus();
}
function downloadIcs(r){
  const dt = r.date.replace(/-/g, '') + 'T' + r.time.replace(':', '') + '00', esc = s => s.replace(/[\\;,]/g, m => '\\' + m);
  const ics = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//FoydaPay//Reminder//EN', 'BEGIN:VEVENT', `UID:${r.id}@foydapay`, `DTSTAMP:${new Date().toISOString().replace(/[-:]/g, '').slice(0, 15)}Z`,
    `DTSTART:${dt}`, `SUMMARY:${esc(r.title)}`, r.repeat === 'monthly' ? 'RRULE:FREQ=MONTHLY' : null,
    'BEGIN:VALARM', 'ACTION:DISPLAY', `DESCRIPTION:${esc(r.title)}`, 'TRIGGER:PT0M', 'END:VALARM', 'END:VEVENT', 'END:VCALENDAR'].filter(Boolean).join('\r\n');
  const a = el('a', { href: URL.createObjectURL(new Blob([ics], { type: 'text/calendar' })), download: 'foydapay-reminder.ics' });
  document.body.append(a); a.click(); a.remove();
}
function checkReminders(){
  const now = new Date(), fired = store.get('fired', {});
  let changed = false;
  for (const r of reminders()) {
    const first = parseIso(r.date), [hh, mm] = r.time.split(':').map(Number);
    for (let o = 0; o <= (r.repeat === 'monthly' ? 12 : 0); o++) {
      const d = dayOf(first.getFullYear(), first.getMonth() + o, first.getDate()); d.setHours(hh, mm);
      const key = r.id + '@' + iso(d);
      if (d > now || now - d > DAY || fired[key]) continue;
      fired[key] = 1; changed = true;
      toast('⏰ ' + r.title);
      try { if ('Notification' in window && Notification.permission === 'granted') new Notification('FoydaPay', { body: r.title }); } catch (e) {}
    }
  }
  if (changed) store.set('fired', fired);
}

/* ================= security ================= */
const SAMPLES = [
  ['smp_collector', 'Debt collection department. Transfer 2 100 000 UZS to card 8600 3141 5926 5358 today, otherwise we file to court tomorrow.'],
  ['smp_job', 'Telegram job offer: Warehouse picker, 400 000 per shift. Pay 300 000 for uniform and registration fee first.'],
  ['smp_loan', 'Approved! 5 000 000 UZS microloan in 5 minutes, no documents. Close your old loans today!']];
function securityStatus(){
  const st = STATE ? STATE.security : { attacks: 0, events: [], log_intact: true };
  return el('div', { 'data-tour': 'secstatus' },
    el('div', { class: 'banner ' + (st.attacks ? 'warn' : 'ok') },
      el('h3', { text: st.attacks ? t('sec_stopped', { n: st.attacks }) : t('sec_safe') }), el('p', { text: st.attacks ? t('sec_stopped_p') : t('sec_safe_p') })),
    st.events.length ? el('div', { class: 'card' }, el('ul', { class: 'list' }, st.events.map(e => el('li', {}, el('span', {},
      el('span', { class: 'pill ' + (e.level === 'blocked' ? 'bad' : 'warn'), text: e.level === 'blocked' ? t('blocked') : t('ignored') }), ' ', t('sk_' + e.kind) === 'sk_' + e.kind ? e.text : t('sk_' + e.kind), el('br'),
      el('span', { class: 'muted small', text: new Date(e.at).toLocaleString(LANG === 'uz' ? 'uz-UZ' : LANG) })))))) : null);
}
function renderSecurity(){
  const sec = document.querySelector('section[data-tab="security"]');
  const text = el('textarea', { id: 'scamText', maxlength: '1500', placeholder: t('msg_ph') });
  const result = el('div', {}), btn = el('button', { class: 'primary block', text: t('msg_check') });
  let statusBox = securityStatus();
  btn.onclick = async () => {
    const v = text.value.trim(); if (!v) return;
    btn.disabled = true;
    try {
      const r = await api('/api/action', { session_id: SID, tool: 'analyze_message', args: { text: v } });
      STATE = r.state;
      const res = r.result.result, cls = { high: 'bad', medium: 'warn', low: 'ok' }[res.risk];
      const kind = res.kind !== 'other' ? t('kind_' + res.kind) : '';
      fill(result, el('div', { class: 'banner ' + cls }, el('h3', { text: t('r_' + res.risk) }), kind ? el('p', { text: kind }) : null),
        res.reason_codes.length ? el('div', { class: 'card' }, el('h3', { text: t('why') }), el('ul', { class: 'list' }, res.reason_codes.map(c => el('li', {}, el('span', { text: t('rc_' + c) }))))) : null,
        el('div', { class: 'card' }, el('h3', { text: t('what_do') }), el('ul', { class: 'list' }, ['wd1', 'wd2', 'wd3'].map(k => el('li', {}, el('span', { text: t(k) })))),
          srcLine(SOURCES.fraud, t('oh_cbu_fraud'))));
      const fresh = securityStatus(); statusBox.replaceWith(fresh); statusBox = fresh;
    } catch (e) { fill(result, el('p', { class: 'muted', text: e.message })); }
    btn.disabled = false;
  };
  const s = STATE ? STATE.security : { log_intact: true };
  fill(sec, DEMO ? el('p', { class: 'badge', text: t('tour_demo') }) : null, topbar(t('security')), statusBox,
    el('div', { class: 'card' }, el('h3', { text: t('how_protect') }), el('ul', { class: 'list' },
      ['hp1', 'hp2', 'hp3'].map(k => el('li', {}, el('span', { text: t(k) }))), el('li', {}, el('span', { text: s.log_intact ? t('hp4_ok') : t('hp4_bad') })))),
    el('div', { class: 'card' }, el('h3', { text: t('official_help') }), el('ul', { class: 'list' },
      el('li', {}, el('span', {}, t('oh_selfban'), el('br'), link(SOURCES.selfban, 'portal.infokredit.uz'), ' · ', link(SOURCES.selfban_news, 'kun.uz'))),
      el('li', {}, el('span', {}, t('oh_consumer'), el('br'), link(SOURCES.consumer[LANG], 'cbu.uz'))),
      el('li', {}, el('span', { text: t('oh_police') })))),
    el('div', { class: 'card', 'data-tour': 'msgcheck' }, el('h3', { text: t('msg_title') }), el('p', { class: 'muted', text: t('msg_sub') }),
      el('label', { class: 'f', for: 'scamText' }, t('msg_label'), text),
      el('div', { class: 'chips' }, SAMPLES.map(([k, v]) => chip(t(k), false, () => { text.value = v; }))), btn),
    result);
}

/* ================= chat ================= */
let CHATS = store.get('chats', []), CUR = store.get('chat_cur', null), BUSY = false;
const curChat = () => CHATS.find(c => c.id === CUR);
const saveChats = () => { CHATS = CHATS.slice(-20); store.set('chats', CHATS); store.set('chat_cur', CUR); };
function richText(target, text){
  text.split('\n').forEach((line, i) => {
    if (i) target.append('\n');
    line = line.replace(/^(\s*)[*-]\s+/, '$1• ').replace(/`/g, '');
    // **bold** and bare https links; everything else stays plain text
    line.split(/(\*\*[^*]+\*\*|https:\/\/[^\s)]+)/g).forEach(part => {
      if (/^\*\*[^*]+\*\*$/.test(part)) target.append(el('b', { text: part.slice(2, -2) }));
      else if (/^https:\/\//.test(part)) { const u = part.replace(/[.,;]+$/, ''); target.append(el('a', { href: u, target: '_blank', rel: 'noopener', text: u.replace(/^https:\/\//, '').slice(0, 48) }), part.slice(u.length)); }
      else if (part) target.append(part.replace(/\*+/g, ''));
    });
  });
}
const hhmm = x => { const d = new Date(x); return pad(d.getHours()) + ':' + pad(d.getMinutes()); };
function bubble(m){
  const b = el('div', { class: 'msg' });
  m.role === 'assistant' ? richText(b, m.text) : b.textContent = m.text;
  if (m.t) b.append(el('time', { text: hhmm(m.t) }));
  return m.role === 'assistant' ? el('div', { class: 'mrow agent' }, el('div', { class: 'avatar sm', 'aria-hidden': 'true', text: 'F' }), b) : el('div', { class: 'mrow user' }, b);
}
function suggestions(){ return !PLAN ? t('sug_none') : PLAN.shortfall > 0 ? t('sug_short') : t('sug_ok'); }
function renderChat(){
  const box = $('msgs'), c = curChat();
  box.replaceChildren();
  $('chatForm').hidden = !hasProfile();
  if (!hasProfile()) { box.append(bubble({ role: 'assistant', text: t('chat_need_check') }), el('button', { class: 'primary', text: t('start_check'), 'data-go': 'check' })); return; }
  box.append(bubble({ role: 'assistant', text: t('chat_hello', { name: DEMO ? t('demo_name') : (USER ? USER.name : STATE.name) }) }));
  if (!DEMO) (c ? c.msgs : []).forEach(m => box.append(bubble(m)));
  if (DEMO || !c || !c.msgs.length) box.append(el('div', { class: 'chips' }, suggestions().slice(0, 3).map(x => chip(x, false, () => !DEMO && sendChat(x)))));
  box.lastChild.scrollIntoView({ block: 'end' });
}
function actionCard(ev){
  const c = confirmText(ev);
  const ok = el('button', { class: 'primary', text: t('confirm') }), no = el('button', { class: 'ghost', text: t('cancel') });
  const card = el('div', { class: 'actioncard' }, el('p', { class: 'tier', text: t('needs_confirm') }), el('b', { text: c.title }),
    el('ul', { class: 'list' }, c.details.map(d => el('li', {}, el('span', { text: d })))), el('div', { class: 'row' }, ok, no));
  const decide = async approve => {
    ok.disabled = no.disabled = true;
    try { const r = await api('/api/confirm', { session_id: SID, confirmation_id: ev.id, approve }); STATE = r.state; card.replaceWith(el('p', { class: 'muted small', text: approve ? t('confirmed') : t('cancelled') })); pushMsg('assistant', r.reply); }
    catch (e) { toast(e.message); ok.disabled = no.disabled = false; }
  };
  ok.onclick = () => decide(true); no.onclick = () => decide(false);
  return el('div', { class: 'mrow agent' }, el('div', { class: 'avatar sm', 'aria-hidden': 'true', text: 'F' }), card);
}
function pushMsg(role, text){
  let c = curChat();
  if (!c) { c = { id: 'c' + Date.now().toString(36), created: Date.now(), title: '', msgs: [] }; CHATS.push(c); CUR = c.id; }
  if (!c.title && role === 'user') c.title = text.slice(0, 48);
  const m = { role, text, t: Date.now() };
  c.msgs.push(m); saveChats();
  const box = $('msgs'); box.querySelectorAll('.chips').forEach(x => x.remove());
  const b = bubble(m); box.append(b); b.scrollIntoView({ block: 'end' });
}
async function sendChat(text){
  text = text.trim(); if (!text || BUSY || DEMO) return;
  BUSY = true; pushMsg('user', text);
  const typing = el('div', { class: 'mrow agent' }, el('div', { class: 'avatar sm', 'aria-hidden': 'true', text: 'F' }), el('div', { class: 'msg typing', 'aria-label': t('typing') }, el('i'), el('i'), el('i')));
  $('msgs').append(typing); typing.scrollIntoView({ block: 'end' });
  try {
    const r = await api('/api/chat', { session_id: SID, message: text });
    typing.remove(); STATE = r.state; pushMsg('assistant', r.reply);
    (r.events || []).forEach(ev => { if (ev.type === 'confirm') { const a = actionCard(ev); $('msgs').append(a); a.scrollIntoView({ block: 'end' }); } });
  } catch (e) {
    typing.remove();
    if (e.status === 404) { await reconnect(); pushMsg('assistant', t('reconnected')); } else pushMsg('assistant', e.message);
  }
  BUSY = false;
}
async function openChat(id){
  CUR = id; saveChats();
  const c = curChat();
  try { await api('/api/chat/reset', { session_id: SID, history: c ? c.msgs.slice(-40).map(m => ({ role: m.role, text: m.text.slice(0, 4000) })) : [] }); } catch (e) {}
  renderChat();
}
$('newChatBtn').onclick = () => { if (DEMO) return; CUR = null; saveChats(); openChat(null); };
$('histBtn').onclick = () => {
  if (DEMO) return;
  const list = [...CHATS].reverse();
  const w = sheet([el('div', { class: 'row between' }, el('h3', { text: t('your_chats') }), el('button', { class: 'link', text: t('new_chat_btn'), onclick: () => { w.remove(); $('newChatBtn').click(); } })),
    list.length ? el('ul', { class: 'list' }, list.map(c => el('li', {},
      el('button', { class: 'link', style: 'text-align:left;font-weight:500;color:var(--text)', onclick: () => { w.remove(); openChat(c.id); } },
        el('span', { text: c.title || t('new_chat') }), el('br'), el('span', { class: 'muted small', text: `${nice(new Date(c.created))} · ${t('n_messages', { n: c.msgs.length })}` })),
      el('button', { class: 'link small', text: t('del'), onclick: () => { CHATS = CHATS.filter(x => x.id !== c.id); if (CUR === c.id) CUR = null; saveChats(); w.remove(); $('histBtn').click(); renderChat(); } }))))
      : el('p', { class: 'muted', text: t('no_chats') }),
    el('p', { class: 'muted small', text: t('chats_local') })]);
};
$('chatForm').addEventListener('submit', e => { e.preventDefault(); const v = $('q').value; $('q').value = ''; $('q').style.height = ''; sendChat(v); });
$('q').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); $('chatForm').requestSubmit(); } });
$('q').addEventListener('input', () => { const q = $('q'); q.style.height = 'auto'; q.style.height = Math.min(140, q.scrollHeight) + 'px'; });

/* ================= guided tour (auto mode on the demo user Jasur) ================= */
const TOUR = { on: false, i: 0, paused: false, muted: store.get('tour_muted', false), audio: null, timer: null, script: null, els: null };
// Each step opens a screen, then points at one element. Texts and voice come from /static/tour/script.json.
const TOUR_STEPS = {
  intro: { show: () => go('home'), target: '[data-tour="hero"]' },
  plan: { show: () => go('home'), target: '[data-tour="plantile"]' },
  cut: { show: () => go('plan'), target: '[data-tour="cut"]' },
  confirm: { show: async () => { go('plan'); await act('cancel_subscriptions', { subscription_ids: ['S3', 'S4'] }); }, target: '[data-tour="sheet"] .sheet', leave: () => document.querySelectorAll('.sheet-wrap').forEach(w => w.remove()) },
  earn: { show: () => go('plan'), target: '[data-tour="earn"]' },
  negotiate: { show: () => go('plan'), target: '[data-tour="negotiate"]' },
  calendar: { show: () => go('calendar'), target: '[data-tour="month"]' },
  security: { show: () => go('security'), target: '[data-tour="secstatus"]' },
  message: { show: () => { go('security'); const x = $('scamText'); if (x) x.value = SAMPLES[0][1]; }, target: '[data-tour="msgcheck"]' },
  chat: { show: () => { go('chat'); $('q').value = t('tour_chat_sample'); }, target: '[data-tour="composer"]' },
  outro: { show: () => go('home'), target: '[data-tour="navcheck"]' },
};
async function startTour(){
  if (TOUR.on) return;
  TOUR.on = true; TOUR.i = 0; TOUR.paused = false;
  const block = el('div', { class: 'tour-block' }), spot = el('div', { class: 'tour-spot' });
  const arrow = el('div', { class: 'tour-arrow', 'aria-hidden': 'true' });
  const card = el('div', { class: 'tour-card bottom', role: 'dialog', 'aria-live': 'polite' }, el('p', { text: t('tour_loading') }));
  document.body.append(block, spot, arrow, card);
  TOUR.els = { block, spot, arrow, card };
  try {
    TOUR.script = TOUR.script || await fetch('/static/tour/script.json').then(r => r.json());
    // Jasur's demo account lives in its own session; the user's session is kept aside and restored at the end.
    DEMO = { SID, STATE, PLAN, JOBS };
    const r = await api('/api/session', {}); SID = r.session_id; STATE = r.state; JOBS = null;
    const plan = await api('/api/action', { session_id: SID, tool: 'build_rescue_plan', args: {} }); PLAN = plan.result.result; STATE = plan.state;
    const atk = await api('/api/action', { session_id: SID, tool: 'transfer_to_card', args: { card_number: '8600123412349012', amount: 2100000 } }); STATE = atk.state;
    loadJobs();
  } catch (e) { toast(e.message); return endTour(); }
  tourStep();
}
function tourPlace(){
  if (!TOUR.on) return;
  const st = TOUR_STEPS[TOUR.script.steps[TOUR.i]], target = document.querySelector(st.target), { spot, arrow, card } = TOUR.els;
  if (!target) { spot.style.opacity = 0; arrow.style.opacity = 0; return; }
  const r = target.getBoundingClientRect(), pad = 6, vh = innerHeight;
  Object.assign(spot.style, { opacity: 1, left: r.left - pad + 'px', top: r.top - pad + 'px', width: r.width + pad * 2 + 'px', height: Math.min(r.height, vh * .6) + pad * 2 + 'px' });
  const below = r.top + Math.min(r.height, vh * .6) / 2 < vh / 2;  // target in the upper half: caption at the bottom, arrow under the target
  card.classList.toggle('bottom', below); card.classList.toggle('top', !below);
  arrow.style.opacity = 1; arrow.className = 'tour-arrow ' + (below ? 'up' : 'down');
  arrow.style.left = Math.max(8, Math.min(innerWidth - 52, r.left + r.width / 2 - 22)) + 'px';
  arrow.style.top = below ? Math.min(vh - 120, r.top + Math.min(r.height, vh * .6) + pad + 6) + 'px' : Math.max(8, r.top - pad - 58) + 'px';
  const dir = below ? 'up' : 'down';
  if (arrow.dataset.dir !== dir) {  // one drawing per direction; the bounce animation owns the svg's transform
    arrow.dataset.dir = dir;
    fill(arrow, svg(below ? '<path d="M12 21V6M5 12l7-7 7 7" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>'
                          : '<path d="M12 3v15M5 12l7 7 7-7" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>'));
  }
}
async function tourStep(){
  clearTimeout(TOUR.timer); if (TOUR.audio) { TOUR.audio.pause(); TOUR.audio = null; }
  const id = TOUR.script.steps[TOUR.i], st = TOUR_STEPS[id], text = TOUR.script[LANG][id];
  await st.show();
  await new Promise(r => setTimeout(r, 120));
  const target = document.querySelector(st.target);
  if (target) target.scrollIntoView({ block: target.offsetHeight > innerHeight * 0.55 ? 'start' : 'center', behavior: 'smooth' });
  setTimeout(tourPlace, 450);
  const { card } = TOUR.els, n = TOUR.script.steps.length;
  fill(card,
    el('div', { class: 'row between' }, el('span', { class: 'badge', text: t('tour_demo') }),
      el('button', { class: 'link small', text: TOUR.muted ? '🔇 ' + t('tour_sound_off') : '🔊 ' + t('tour_sound_on'), onclick: () => { TOUR.muted = !TOUR.muted; store.set('tour_muted', TOUR.muted); tourStep(); } })),
    el('p', { text }),
    el('div', { class: 'tour-dots' }, TOUR.script.steps.map((_, k) => el('i', { class: k <= TOUR.i ? 'on' : '' }))),
    el('div', { class: 'tour-ctl' },
      el('button', { class: 'ghost', 'aria-label': TOUR.paused ? t('tour_play') : t('tour_pause'), text: TOUR.paused ? '▶' : '⏸', onclick: () => { TOUR.paused = !TOUR.paused; TOUR.paused ? (clearTimeout(TOUR.timer), TOUR.audio && TOUR.audio.pause()) : tourStep(); if (TOUR.paused) tourStep.redraw(); } }),
      el('button', { class: 'primary grow', text: TOUR.i === n - 1 ? t('start_check') : t('tour_next') + ' ›', onclick: tourNext }),
      el('button', { class: 'link', text: t('tour_skip'), onclick: endTour })));
  if (TOUR.paused) return;
  const advance = () => { if (TOUR.on && !TOUR.paused) TOUR.timer = setTimeout(tourNext, 900); };
  const fallback = () => { TOUR.timer = setTimeout(tourNext, Math.max(4500, text.length * 65)); };
  if (TOUR.muted) return fallback();
  const a = new Audio(`/static/tour/${LANG}/${id}.mp3`); TOUR.audio = a;
  a.onended = advance;
  a.onerror = () => { if (TOUR.audio === a) fallback(); };
  a.play().catch(() => { if (TOUR.audio === a) fallback(); });
}
tourStep.redraw = () => { const b = TOUR.els.card.querySelector('.tour-ctl .ghost'); if (b) { b.textContent = '▶'; b.setAttribute('aria-label', t('tour_play')); } };
function tourNext(){
  if (!TOUR.on) return;
  const st = TOUR_STEPS[TOUR.script.steps[TOUR.i]];
  if (st.leave) st.leave();
  if (TOUR.i >= TOUR.script.steps.length - 1) return endTour(true);
  TOUR.i++; tourStep();
}
function endTour(toCheck){
  clearTimeout(TOUR.timer); if (TOUR.audio) TOUR.audio.pause();
  TOUR.on = false; TOUR.audio = null;
  if (TOUR.els) Object.values(TOUR.els).forEach(x => x.remove());
  document.querySelectorAll('.sheet-wrap').forEach(w => w.remove());
  $('q').value = '';
  if (DEMO) { ({ SID, STATE, PLAN, JOBS } = DEMO); DEMO = null; }
  store.set('toured', 1);
  go(toCheck === true || !(STATE && STATE.custom) ? 'check' : 'home');
}
addEventListener('resize', () => TOUR.on && tourPlace());
addEventListener('scroll', () => TOUR.on && tourPlace(), { passive: true });

/* ================= start ================= */
async function reconnect(){
  const r = await api('/api/session', {}); SID = r.session_id; STATE = r.state; store.set('sid', SID);
  if (store.get('profile', null)) { await sendProfile(); if (CUR) await openChat(CUR); }
}
(async () => {
  applyStatic();
  if (!USER) { go('welcome'); }
  else renderHome();
  try {
    const h = await api('/healthz');
    LLM = h.mode === 'llm'; applyStatic();
    const sid = store.get('sid', null);
    let alive = false;
    if (sid) { try { STATE = await api('/api/state?session_id=' + encodeURIComponent(sid)); SID = sid; alive = true; } catch (e) {} }
    if (alive && STATE.custom) { const r = await api('/api/action', { session_id: SID, tool: 'build_rescue_plan', args: {} }); PLAN = r.result.result; STATE = r.state; }
    else await reconnect();
  } catch (e) { fill($('home'), el('p', { class: 'muted', text: t('could_not_connect', { e: e.message }) })); return; }
  if (USER && current() !== 'welcome') go('home');
  checkReminders(); setInterval(checkReminders, 30000);
})();
