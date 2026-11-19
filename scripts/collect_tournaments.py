#!/usr/bin/env python3
"""Publish organizer-verified events and keep discovery results separate."""
import hashlib
import html
import json
import os
import re
import unicodedata
import urllib.request
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data/tournaments.json"
VERIFIED = ROOT / "data/verified_tournaments.json"
KST = timezone(timedelta(hours=9))
SOURCES = [
    ("프렌즈스크린", "https://www.friendsscreen.kr/main/kakao-intro", "스크린골프"),
    ("골프존", "https://news.golfzon.com/ko/category/press-center/press-release/", "스크린골프"),
    ("SG골프", "https://screen.sggolf.com/store/cupList", "스크린골프"),
    ("대한골프협회", "https://kgagolf.or.kr/web/life/schedule", "아마추어 필드골프"),
    ("한국미드아마추어골프연맹", "https://www.kmagf.co.kr/tour/list", "아마추어 필드골프"),
]
SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
NAVER_SEARCH_URL = "https://openapi.naver.com/v1/search"
SEARCH_TERMS = [
    "스크린골프 대회", "스크린대회", "스크린 대회", "스크린골프 대회 참가",
    "아마추어 골프대회", "아마추어 골프대회 참가 신청", "생활체육 골프대회",
    "필드 골프대회", "골프 챔피언십", "골프 토너먼트", "골프 오픈대회",
    "골프 친선대회", "골프 클럽 챔피언십", "골프 인비테이셔널",
    "골프 매장대회", "골프 동호회 대회", "여성 골프대회", "주니어 골프대회",
    "시니어 골프대회", "타이틀리스트 골프대회", "팀 타이틀리스트 챔피언십",
    "스릭슨 브레이브 챔피언십", "스릭슨 골프대회", "던롭 골프대회",
    "브랜드 주최 아마추어 골프대회", "젝시오 골프대회", "캘러웨이 골프대회",
    "테일러메이드 골프대회", "핑 골프대회", "브리지스톤 골프대회",
    "골프존 대회", "프렌즈스크린 대회", "SG골프 대회",
    "직장인 골프대회", "직장인 골프 챔피언십", "직장인 골프 최강전",
    "직장인 스크린골프대회", "기업 골프대회", "회사 골프대회",
    "직장인 골프리그", "직장인 골프 결과", "골프대회 우승자", "골프대회 최종 순위",
    "DB증권 직장인 골프챔피언십", "직장인 골프 대항전", "직장인 골프 대회 모집",
    "KPGA 대회", "KLPGA 대회", "대한골프협회 대회", "미드아마추어 골프대회",
    "파크골프 대회", "파크골프 챔피언십",
    "시장배 골프대회", "군수배 골프대회", "도지사배 골프대회",
    "구청장배 골프대회", "체육회장배 골프대회", "협회장배 골프대회",
    "천안시장배 골프대회", "천안시골프협회 대회", "천안 상록 골프대회",
    "충남 시장배 골프대회", "지역 골프대회 참가 모집",
]
LOCAL_TERMS = [
    "천안 스크린대회", "천안 스크린 대회", "천안 매장대회",
    "천안 아마추어 골프대회", "충남 골프대회", "대전 골프대회",
    "천안시장배 골프대회", "천안시 골프협회장배", "천안 직장인 골프대회",
    "아산시장배 골프대회", "충남도지사배 골프대회",
]
EVENT = re.compile(
    r"팔도페스티벌|스크린\s*대회|매장\s*대회|"
    r"(?:골프|파크골프|타이틀리스트|스릭슨|브레이브|젝시오|캘러웨이|테일러메이드|브리지스톤|KPGA|KLPGA|GTOUR).{0,40}"
    r"(?:대회|챔피언십|인비테이셔널|토너먼트|클래식|오픈|컵|페스티벌)|"
    r"(?:대회|챔피언십|인비테이셔널|토너먼트|클래식|오픈|컵).{0,40}(?:골프|파크골프)|"
    r"(?:직장인|기업|회사원).{0,40}(?:골프|대회|챔피언십|최강전)|"
    r"(?:시장배|군수배|도지사배|구청장배|체육회장배|협회장배).{0,30}(?:골프|대회)|"
    r"아마추어.{0,32}(?:대회|클래식|챔피언십)|대항전"
)
EXCLUDED = re.compile(r"생중계|대회\s*후기", re.IGNORECASE)
UNKNOWN = "미확인"

class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.href = None
        self.parts = []
        self.items = []
        self.visible = []
        self.hidden = False

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden = True
        if tag == "a":
            self.href = dict(attrs).get("href")
            self.parts = []

    def handle_data(self, data):
        if not self.hidden and data.strip():
            self.visible.append(data.strip())
        if self.href is not None:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = False
        if tag == "a" and self.href is not None:
            self.items.append((self.href, " ".join(" ".join(self.parts).split())))
            self.href = None


def fetch(url, headers=None):
    request = urllib.request.Request(
        url, headers={"User-Agent": "GolfTournamentAlert/1.0", **(headers or {})}
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read(2_000_000).decode("utf-8", "replace")


def canonical(url):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return ""
    query = urlencode(sorted(
        (key, value) for key, value in parse_qsl(parsed.query)
        if not key.lower().startswith("utm_") and key.lower() not in {"fbclid", "gclid"}
    ))
    return urlunsplit(("https", parsed.netloc.lower(), parsed.path.rstrip("/") or "/", query, ""))


def title_key(title):
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", title).casefold())


def candidate(provider, title, url, category):
    return {
        "id": hashlib.sha256(url.encode()).hexdigest()[:24],
        "provider": provider, "title": title[:180], "official_url": url,
        "category": category, "region": UNKNOWN, "entry_fee": None,
        "start_date": None, "end_date": None, "event_status": UNKNOWN,
        "registration_status": UNKNOWN, "amateur_eligible": None,
        "verification": "candidate_link_only",
    }


def official_candidates(provider, source, category):
    parser = Links()
    parser.feed(fetch(source))
    matches = []
    for href, title in parser.items:
        url = canonical(urljoin(source, href))
        if url and url != canonical(source) and EVENT.search(title) and not EXCLUDED.search(title):
            matches.append(candidate(provider, title, url, category))
    if provider == "프렌즈스크린":
        matches.extend(friends_events(" ".join(parser.visible), source))
    if provider == "SG골프":
        matches.extend(sg_events(" ".join(parser.visible), source))
    return matches


def friends_events(text, source):
    pattern = re.compile(
        r"(?P<title>[^.?!]{3,120}?)\s*대회\s*오픈\s*이벤트\s*기간\s*"
        r"(?P<start>\d{4}-\d{2}-\d{2})\s*[-~–]\s*(?P<end>\d{4}-\d{2}-\d{2})"
    )
    found = []
    for match in pattern.finditer(text):
        title = re.split(r"대회\s*(?:진행\s*중|종료|예정)|\bImage\b", match["title"])[-1].strip()
        title = re.sub(r"^\d{2,4}년\s*\d{1,2}월\s*", "", title).strip(" '\"‘’")
        if not title or len(title) > 90 or EXCLUDED.search(title):
            continue
        start, end = date.fromisoformat(match["start"]), date.fromisoformat(match["end"])
        if start > end:
            continue
        identifier = hashlib.sha256(f"{title_key(title)}:{start}".encode()).hexdigest()[:20]
        found.append({
            **candidate("프렌즈스크린", title, source, "스크린골프"),
            "id": f"friends-{identifier}", "start_date": str(start), "end_date": str(end),
            "verification": "official_schedule",
        })
    return found


def sg_events(text, source):
    provinces = "서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주"
    pattern = re.compile(
        rf"(?:예정|진행|종료)\s+({provinces})\s+(.{{2,100}}?)\s*기간\s*:\s*"
        r"(\d{4}-\d{2}-\d{2})\s*~\s*(\d{4}-\d{2}-\d{2})\s*"
        r"주최매장\s*:\s*(.{2,80}?)(?=\s*(?:코스\s*:|참여매장))"
    )
    entries = []
    for region, title, start_text, end_text, venue in pattern.findall(text):
        title = title.strip()
        venue = venue.strip()
        if not re.search(r"대회|챔피언십|토너먼트", title) or EXCLUDED.search(title):
            continue
        start, end = date.fromisoformat(start_text), date.fromisoformat(end_text)
        if start > end:
            continue
        key = f"{title_key(title)}:{region}:{title_key(venue)}:{start}"
        identifier = hashlib.sha256(key.encode()).hexdigest()[:20]
        entries.append({
            **candidate("SG골프", title, source, "스크린골프"),
            "id": f"sg-{identifier}", "region": f"{region} {venue}",
            "start_date": str(start), "end_date": str(end), "verification": "official_schedule",
        })
    return entries


def web_candidates(api_key, today):
    matches = []
    for term in SEARCH_TERMS:
        query = urlencode({"q": f"{today.year} {term}", "country": "KR",
                           "search_lang": "ko", "count": 15})
        content = json.loads(fetch(SEARCH_URL + "?" + query, {"X-Subscription-Token": api_key}))
        matches.extend(search_results("웹 검색", content.get("web", {}).get("results", []), "url"))
    return matches


def naver_candidates(client_id, secret):
    headers = {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": secret}
    matches = []
    for channel in ("blog", "cafearticle", "news"):
        for term in [*SEARCH_TERMS, *LOCAL_TERMS]:
            query = urlencode({"query": term if term in LOCAL_TERMS else f"2026 {term}", "display": 30, "sort": "date"})
            try:
                response = json.loads(fetch(f"{NAVER_SEARCH_URL}/{channel}.json?{query}", headers))
                matches.extend(search_results("네이버 블로그·카페·뉴스", response.get("items", []), "originallink" if channel == "news" else "link"))
            except (OSError, ValueError, KeyError, TypeError):
                continue
    return matches


def search_results(provider, results, url_key):
    entries = []
    for item in results:
        title = html.unescape(re.sub(r"<[^>]+>", "", item["title"])).strip()
        url = canonical(item.get(url_key) or item.get("link", ""))
        if url and EVENT.search(title) and not EXCLUDED.search(title):
            entry = candidate(provider, title, url, "스크린골프" if re.search(r"스크린|GTOUR|골프존|SG골프", title, re.IGNORECASE) else "아마추어 필드골프")
            entry["discovery_url"] = entry.pop("official_url")
            entry["official_url"] = None
            entries.append(entry)
    return entries

def event_status(event, today):
    if event.get("schedule_type") == "ongoing" and not event["start_date"] and not event["end_date"]:
        return {**event, "event_status": "상시 안내",
                "verification": event.get("verification", "organizer_verified")}
    start = date.fromisoformat(event["start_date"])
    end = date.fromisoformat(event["end_date"])
    if start > end:
        raise ValueError(f"Invalid event range: {event['id']}")
    event_state = "종료" if today > end else "예정" if today < start else "진행 중"
    registration = event.get("registration_status", UNKNOWN)
    if event_state == "종료" and event.get("verification") != "official_schedule":
        registration = "접수 마감"
    elif event.get("registration_start") and event.get("registration_end"):
        opens = date.fromisoformat(event["registration_start"])
        closes = date.fromisoformat(event["registration_end"])
        if today < opens:
            registration = "접수 예정"
        elif today > closes:
            registration = "접수 마감"
        else:
            registration = "접수 중"
    elif registration == "매장 참여" and event_state == "예정":
        registration = "참여 예정"
    return {**event, "event_status": event_state, "registration_status": registration,
            "verification": event.get("verification", "organizer_verified")}


def deduplicate(verified, candidates):
    known_urls = {
        canonical(url) for event in verified
        for url in [event.get("official_url"), event.get("discovery_url"), *event.get("source_urls", [])]
        if url
    }
    known_titles = [title_key(event["title"]) for event in verified]
    candidates_by_url = {}
    duplicate_count = 0
    for item in candidates:
        url = canonical(item.get("official_url") or item["discovery_url"])
        title = title_key(item["title"])
        if url in known_urls or any(len(key) >= 12 and key in title for key in known_titles):
            duplicate_count += 1
        elif url in candidates_by_url:
            duplicate_count += 1
        else:
            candidates_by_url[url] = item
    return list(candidates_by_url.values()), duplicate_count


def official_schedule_changes(verified, html_text):
    """Flag date and venue discrepancies on KMAGF's published schedule for human review."""
    parser = Links()
    parser.feed(html_text)
    visible = " ".join(parser.visible)
    changes = []
    date_pattern = re.compile(r"\d{4}[./-]\d{2}[./-]\d{2}")
    for event in verified:
        if event.get("provider") != "한국미드아마추어골프연맹" or not event.get("id", "").startswith("kmagf-2026-"):
            continue
        title = event["title"]
        position = visible.find(title)
        if position < 0:
            continue  # Missing from a page is not evidence of cancellation.
        # Bound extraction to the next listing so dates from adjacent events are not mixed.
        fragment = visible[position + len(title):position + len(title) + 280]
        dates = date_pattern.findall(fragment)
        if len(dates) >= 2:
            start, end = [date.fromisoformat(value.replace(".", "-").replace("/", "-")).isoformat()
                          for value in dates[:2]]
            if start <= end and (start != event.get("start_date") or end != event.get("end_date")):
                changes.append({"id": event["id"], "title": title, "field": "event_dates",
                                "registered": [event.get("start_date"), event.get("end_date")],
                                "official": [start, end],
                                "source_url": "https://www.kmagf.co.kr/tour/schedule"})
        # Venue is only flagged when a recognizable course name appears in this listing.
        venues = re.findall(r"[가-힣A-Za-z0-9· ]{2,35}(?:CC|GC|골프클럽|컨트리클럽)", fragment[:160])
        if venues and event.get("region"):
            venue = venues[0].strip()
            registered = event["region"]
            if venue not in registered and not any(part in venue for part in registered.split() if len(part) >= 4):
                changes.append({"id": event["id"], "title": title, "field": "venue",
                                "registered": registered, "official": venue,
                                "source_url": "https://www.kmagf.co.kr/tour/schedule"})
    return changes


def audit_coverage(verified, candidates, checks):
    """Report discoverable gaps without pretending they are verified events."""
    categories = {
        "지역·지자체": r"시장배|군수배|도지사배|구청장배|체육회장배|협회장배",
        "직장인·기업": r"직장인|기업|회사원|DB증권",
        "브랜드": r"스릭슨|타이틀리스트|브리지스톤|캘러웨이|젝시오|테일러메이드|핑",
        "미드아마추어": r"미드아마|KMAGF|호연배|벤제프|프랭크버거",
        "주니어": r"주니어|초등|중등|학생",
    }
    groups = {}
    for label, pattern in categories.items():
        groups[label] = {
            "registered": sum(bool(re.search(pattern, e["title"], re.I)) for e in verified),
            "unverified_leads": sum(bool(re.search(pattern, e["title"], re.I)) for e in candidates),
        }
    return {
        "scope": "검색된 자료와 등록 목록 비교. 전국 대회 전체 대비 누락률이 아닙니다.",
        "registered": len(verified),
        "unverified_leads": len(candidates),
        "failed_sources": [c["provider"] for c in checks if c.get("ok") is False],
        "skipped_sources": [c["provider"] for c in checks if c.get("ok") is None],
        "by_group": groups,
        "review_queue": [
            {"title": e["title"], "discovery_url": e.get("discovery_url"), "provider": e["provider"]}
            for e in candidates[:100]
        ],
    }


def collect(previous, now, offline=False):
    today = now.astimezone(KST).date()
    verified = [event_status(event, today) for event in json.loads(VERIFIED.read_text(encoding="utf-8"))]
    ids = [event["id"] for event in verified]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate verified event IDs")
    verified.sort(key=lambda event: event["start_date"] or "", reverse=True)
    checks = []
    results = []
    official_changes = []
    try:
        if not offline:
            official_changes = official_schedule_changes(verified, fetch("https://www.kmagf.co.kr/tour/schedule"))
    except (OSError, ValueError, KeyError, TypeError):
        checks.append({"provider": "KMAGF 일정 변경 감시", "source_url": "https://www.kmagf.co.kr/tour/schedule", "ok": False, "error": "ScheduleCheckFailed"})
    old = [*previous.get("candidates", []), *(
        event for event in previous.get("tournaments", [])
        if event["verification"] == "official_schedule" and event["id"] not in ids
    )]

    def check(provider, source, discover, skipped=None):
        status = {"provider": provider, "source_url": source}
        entries = [item for item in old if item["provider"] == provider]
        if skipped:
            status.update(ok=None, detail=skipped)
        else:
            try:
                entries = discover()
                # Keep official schedules after they disappear from the current listing.
                if provider in {"프렌즈스크린", "SG골프"}:
                    new_ids = {item["id"] for item in entries}
                    entries.extend(item for item in old if item["provider"] == provider
                                   and item["verification"] == "official_schedule"
                                   and item["id"] not in new_ids)
                status.update(ok=True, cached=False)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                # Do not publish request details or credential-bearing errors.
                status.update(ok=False, cached=bool(entries), error=type(exc).__name__)
        status["candidate_count"] = sum(item["verification"] == "candidate_link_only" for item in entries)
        status["schedule_count"] = sum(item["verification"] == "official_schedule" for item in entries)
        checks.append(status)
        results.extend(entries)

    for provider, source, category in SOURCES:
        check(provider, source, lambda: official_candidates(provider, source, category),
              "오프라인 실행" if offline else None)
    api_key = os.getenv("BRAVE_SEARCH_API_KEY")
    skip_search = ("오프라인 실행" if offline else "검색 키 미설정" if not api_key
                   else "다음 검색 실행 대기" if os.getenv("RUN_WEB_SEARCH", "true") != "true" else None)
    check("웹 검색", SEARCH_URL, lambda: web_candidates(api_key, today), skip_search)
    naver_id = os.getenv("NAVER_SEARCH_CLIENT_ID")
    naver_secret = os.getenv("NAVER_SEARCH_CLIENT_SECRET")
    skip_naver = ("오프라인 실행" if offline else "검색 키 미설정" if not (naver_id and naver_secret)
                  else "다음 검색 실행 대기" if os.getenv("RUN_WEB_SEARCH", "true") != "true" else None)
    check("네이버 블로그·카페·뉴스", NAVER_SEARCH_URL,
          lambda: naver_candidates(naver_id, naver_secret), skip_naver)
    automatic = {}
    known_titles = {title_key(event["title"]) for event in verified}
    duplicate_schedules = 0
    for event in results:
        if event["verification"] != "official_schedule":
            continue
        key = title_key(event["title"])
        if key in known_titles or event["id"] in automatic:
            duplicate_schedules += 1
        else:
            automatic[event["id"]] = event_status(event, today)

    verified.extend(automatic.values())
    verified.sort(key=lambda event: event["start_date"] or "", reverse=True)
    candidates, duplicate_count = deduplicate(
        verified, [event for event in results if event["verification"] == "candidate_link_only"]
    )
    duplicate_count += duplicate_schedules
    return {
        "schema_version": 1, "updated_at": now.isoformat(),
        "note": "확인된 대회와 출처 검토가 필요한 후보를 분리합니다. null과 미확인은 정보 미확인입니다.",
        "sources": checks, "tournaments": verified, "candidates": candidates,
        "duplicates_suppressed": duplicate_count,
        "coverage_audit": {**audit_coverage(verified, candidates, checks), "official_changes_to_review": official_changes},
    }


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    previous = json.loads(OUTPUT.read_text(encoding="utf-8")) if OUTPUT.exists() else {}
    payload = collect(previous, datetime.now(timezone.utc), args.offline)
    temporary = OUTPUT.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(OUTPUT)
    print(f"{len(payload['tournaments'])} verified events, {len(payload['candidates'])} candidates, "
          f"{payload['duplicates_suppressed']} duplicates suppressed")


if __name__ == "__main__":
    main()
