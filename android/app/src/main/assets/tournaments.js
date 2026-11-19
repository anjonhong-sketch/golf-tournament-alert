'use strict';

const UNKNOWN = '미확인';
const $ = id => document.getElementById(id);
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char =>
    ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'})[char]);
const known = value => value || UNKNOWN;
const areas = {충청: ['충청', '충남', '충북'], 전라: ['전라', '전남', '전북'], 경상: ['경상', '경남', '경북']};
let active = 'screen';
let feed = {tournaments: [], candidates: []};

function readList(key) {
    try {
        const list = JSON.parse(localStorage.getItem(key));
        return Array.isArray(list) ? list : [];
    } catch {
        return [];
    }
}

let custom = readList('golf_custom');
const favorites = new Set(readList('golf_favorites'));

function save() {
    localStorage.setItem('golf_favorites', JSON.stringify([...favorites]));
    localStorage.setItem('golf_custom', JSON.stringify(custom));
}

function safeUrl(value) {
    try {
        const url = new URL(value);
        return url.protocol === 'https:' && !url.username && !url.password ? url.href : '';
    } catch {
        return '';
    }
}

function normalize(event) {
    const type = {'스크린골프': 'screen', '아마추어 필드골프': 'field'}[event.category] || '';
    const start = event.start_date;
    const end = event.end_date;
    return {
        id: event.id, name: event.title, provider: event.provider, type,
        region: known(event.region), dates: start === end ? start : [start, end].filter(Boolean).join(' ~ '),
        status: known(event.registration_status), eventStatus: known(event.event_status),
        fee: event.entry_fee, note: event.eligibility, url: event.official_url || event.discovery_url,
        candidate: event.verification === 'candidate_link_only',
    };
}

function showFeed(data, message) {
    if (data && Array.isArray(data.tournaments)) feed = data;
    const updated = new Date(feed.updated_at);
    $('feed-status').textContent = message || (Number.isNaN(updated.getTime()) ? '대회 정보가 없습니다.'
        : '최근 갱신 ' + updated.toLocaleString('ko-KR', {timeZone: 'Asia/Seoul'}));
    render();
}

function storedStatus(status) {
    return {'접수중': '접수 중', '접수예정': '접수 예정', '접수마감': '접수 마감',
        '확인필요': UNKNOWN}[status] || known(status);
}

function renderCard(item) {
    const id = escapeHtml(item.id);
    const status = storedStatus(item.status);
    const eventStatus = item.eventStatus || '';
    const badge = eventStatus === '종료' || status === '접수 마감' ? 'closed' : status === UNKNOWN ? 'check' : '';
    const url = safeUrl(item.url);
    const type = {screen: '🏌️ 스크린골프', field: '⛳ 필드골프'}[item.type] || UNKNOWN;
    const room = !item.custom && !item.candidate && /^[a-z0-9-]{1,80}$/.test(item.id);
    return `<article class="card">
        <div class="row"><span class="pill ${badge}">${escapeHtml([eventStatus, status].filter(Boolean).join(' · '))}</span>
        <span class="muted">${type}</span></div>
        <h3>${escapeHtml(item.name)}</h3>
        <div class="meta">📍 ${escapeHtml([known(item.region), item.venue].filter(Boolean).join(' · '))}<br>
        📅 ${escapeHtml(known(item.dates))}<br>💳 참가비: ${escapeHtml(known(item.fee))}</div>
        ${item.note ? `<p class="note">${escapeHtml(item.note)}</p>` : ''}
        <div class="actions">
            ${url ? `<a href="${escapeHtml(url)}" rel="noopener noreferrer">${item.candidate ? '후보 출처' : '공식 정보'} ↗</a>` : ''}
            <button data-fav="${id}">${favorites.has(item.id) ? '★ 저장됨' : '☆ 즐겨찾기'}</button>
            ${item.custom ? `<button data-edit="${id}">편집</button>` : ''}
        </div>
        ${room ? `<div class="actions"><button data-room="chat" data-event="${id}">대회 채팅</button>
            <button data-room="reviews" data-event="${id}">참가 후기</button></div>` : ''}
    </article>`;
}

function render() {
    const query = $('search').value.trim().toLowerCase();
    const region = $('region').value;
    const status = $('status').value;
    const scope = $('scope').value;
    const entries = [...custom, ...feed.tournaments.map(normalize), ...(feed.candidates || []).map(normalize)];
    const items = entries.filter(item => {
        const ended = item.eventStatus === '종료' || (item.custom && storedStatus(item.status) === '접수 마감');
        const inScope = scope === 'candidate' ? item.candidate
            : !item.candidate && (scope === 'archive' ? ended : !ended);
        const matchRegion = !region || item.region?.startsWith('전국') ||
            (areas[region] || [region]).some(area => item.region?.startsWith(area));
        return (active === 'fav' ? favorites.has(item.id) : inScope && (active === 'screen' ? item.type === 'screen' : item.type === active))
            && matchRegion && (!status || storedStatus(item.status) === status)
            && [item.name, item.venue, item.region, item.provider, item.note].join(' ').toLowerCase().includes(query);
    });
    $('count').textContent = `${items.length}개 대회 표시`;
    $('cards').innerHTML = items.length ? items.map(renderCard).join('')
        : '<div class="empty">조건에 맞는 대회가 없습니다.</div>';
}

function setTab(tab) {
    active = tab;
    document.querySelectorAll('[data-type]').forEach(button => {
        const selected = button.dataset.type === tab;
        button.classList.toggle('active', selected);
        button.setAttribute('aria-pressed', String(selected));
    });
    $('scope').disabled = tab === 'fav';
    render();
}

document.querySelectorAll('[data-type]').forEach(button => {
    button.onclick = () => setTab(button.dataset.type);
});
['search', 'region', 'status', 'scope'].forEach(id => $(id).addEventListener('input', render));
$('reset').onclick = () => {
    for (const id of ['search', 'region', 'status']) $(id).value = '';
    $('scope').value = 'current';
    setTab('screen');
};
$('refresh').onclick = () => { location.href = 'golf-alert://refresh'; };

let editingId = null;
const form = $('add');
const details = form.closest('details');
const submit = form.querySelector('[type="submit"]');
const deleteInEditor = document.createElement('button');
deleteInEditor.type = 'button';
deleteInEditor.textContent = '삭제';
deleteInEditor.hidden = true;
form.appendChild(deleteInEditor);
const cancelEdit = document.createElement('button');
cancelEdit.type = 'button';
cancelEdit.textContent = '편집 취소';
cancelEdit.hidden = true;
form.appendChild(cancelEdit);
function resetEditor() {
    editingId = null;
    form.reset();
    submit.textContent = '내 대회 목록에 추가';
    deleteInEditor.hidden = true;
    cancelEdit.hidden = true;
}
cancelEdit.onclick = resetEditor;
function editLocal(id) {
    const item = custom.find(entry => entry.id === id);
    if (!item) return;
    editingId = id;
    for (const key of ['name','type','region','venue','dates','fee','status','url']) {
        if (form.elements.namedItem(key)) form.elements.namedItem(key).value = item[key] || '';
    }
    submit.textContent = '변경사항 저장';
    deleteInEditor.hidden = false;
    cancelEdit.hidden = false;
    details.open = true;
    details.scrollIntoView({behavior:'smooth',block:'start'});
}
function confirmLocalDeletion(id) {
    const overlay = document.createElement('div');
    overlay.setAttribute('role','dialog');
    overlay.setAttribute('aria-modal','true');
    overlay.setAttribute('aria-label','대회 삭제 확인');
    overlay.style.cssText = 'position:fixed;inset:0;background:#0008;z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px';
    const panel = document.createElement('div');
    panel.style.cssText = 'background:white;border-radius:18px;padding:24px;width:min(100%,360px);box-shadow:0 10px 35px #0003;color:#183b30';
    const message = document.createElement('p');
    message.textContent = '정말 삭제하시겠습니까?';
    message.style.cssText = 'font-size:19px;font-weight:bold;margin:0 0 20px';
    const actions = document.createElement('div');
    actions.style.cssText = 'display:flex;gap:12px';
    const no = document.createElement('button');
    no.textContent = '아니오';
    const yes = document.createElement('button');
    yes.textContent = '예';
    for (const b of [no,yes]) b.style.cssText = 'flex:1;padding:12px;border-radius:10px';
    no.onclick = () => overlay.remove();
    yes.onclick = () => {
        custom = custom.filter(item => item.id !== id);
        favorites.delete(id);
        save();
        resetEditor();
        details.open = false;
        overlay.remove();
        render();
    };
    actions.append(no,yes);
    panel.append(message,actions);
    overlay.append(panel);
    document.body.append(overlay);
    no.focus();
}
deleteInEditor.onclick = () => {
    if (editingId) confirmLocalDeletion(editingId);
};
$('cards').onclick = event => {
    const button = event.target.closest('button');
    if (!button) return;
    const {fav, edit, room, event: id} = button.dataset;
    if (room) {
        location.href = 'golf-alert://room/' + room + '/' + encodeURIComponent(id);
        return;
    }
    if (edit) { editLocal(edit); return; }
    if (!fav) return;
    if (favorites.has(fav)) favorites.delete(fav);
    else favorites.add(fav);
    save();
    render();
};
form.onsubmit = event => {
    event.preventDefault();
    const fields = new FormData(form);
    const url = safeUrl(fields.get('url'));
    if (!url) {
        alert('https:// 로 시작하는 공식 링크를 입력해 주세요.');
        return;
    }
    const values = {
        custom: true,
        name: String(fields.get('name')), type: String(fields.get('type')),
        region: String(fields.get('region')), venue: String(fields.get('venue')),
        dates: String(fields.get('dates')), fee: String(fields.get('fee')),
        status: storedStatus(fields.get('status')), url,
    };
    if (editingId) {
        const index = custom.findIndex(item => item.id === editingId);
        if (index < 0) { alert('수정할 대회를 찾지 못했습니다.'); return; }
        custom[index] = {...custom[index], ...values};
    } else {
        custom.unshift({id:'custom-' + Date.now(), ...values});
    }
    save();
    resetEditor();
    details.open = false;
    render();
};

setTab('screen');

// Account actions are handled by the native Android authentication screen.
for (const id of ['login','signup','my-events']) {
  $(id).addEventListener('click', () => { location.href = 'golf-alert://' + (id === 'my-events' ? 'manage' : id); });
}
function setAccountState(signedIn, organizer) {
  $('login').hidden = signedIn;
  $('signup').hidden = signedIn;
  $('my-events').hidden = !signedIn || !organizer;
}
