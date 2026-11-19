'use strict';

const UNKNOWN = '미확인';
const $ = id => document.getElementById(id);
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char =>
    ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'})[char]);
const known = value => value || UNKNOWN;
const areas = {충청: ['충청', '충남', '충북'], 전라: ['전라', '전남', '전북'], 경상: ['경상', '경남', '경북']};
let active = 'all';
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
            ${item.custom ? `<button data-delete="${id}">삭제</button>` : ''}
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
        return (active === 'fav' ? favorites.has(item.id) : inScope && (active === 'all' || item.type === active))
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
    setTab('all');
};
$('refresh').onclick = () => { location.href = 'golf-alert://refresh'; };
$('cards').onclick = event => {
    const button = event.target.closest('button');
    if (!button) return;
    const {fav, delete: remove, room, event: id} = button.dataset;
    if (room) {
        location.href = 'golf-alert://room/' + room + '/' + encodeURIComponent(id);
        return;
    }
    if (fav) {
        if (favorites.has(fav)) favorites.delete(fav);
        else favorites.add(fav);
    } else if (remove && confirm('등록한 대회를 삭제할까요?')) {
        custom = custom.filter(item => item.id !== remove);
        favorites.delete(remove);
    } else {
        return;
    }
    save();
    render();
};

$('add').onsubmit = event => {
    event.preventDefault();
    const fields = new FormData(event.target);
    const url = safeUrl(fields.get('url'));
    if (!url) {
        alert('https:// 로 시작하는 공식 링크를 입력해 주세요.');
        return;
    }
    custom.unshift({
        id: 'custom-' + Date.now(), custom: true,
        name: String(fields.get('name')), type: String(fields.get('type')),
        region: String(fields.get('region')), venue: String(fields.get('venue')),
        dates: String(fields.get('dates')), fee: String(fields.get('fee')),
        status: storedStatus(fields.get('status')), url,
    });
    save();
    event.target.reset();
    render();
};

setTab('all');
