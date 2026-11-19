#!/usr/bin/env python3
"""Publish organizer-verified events and keep discovery results separate."""
import hashlib
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
    ("골프존", "https://news.golfzon.com/ko/", "스크린골프"),
    ("SG골프", "https://screen.sggolf.com/store/cupList", "스크린골프"),
    ("대한골프협회", "https://kgagolf.or.kr/web/life/schedule", "아마추어 필드골프"),
    ("한국미드아마추어골프연맹", "https://www.kmagf.co.kr/tour/list", "아마추어 필드골프"),
]
SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
SEARCH_TERMS = [
    "스크린골프 대회 참가 접수 골프존 프렌즈스크린 전국",
    "아마추어 필드골프 골프대회 참가 신청 생활체육 전국 지역",
]
EVENT = re.compile(r"골프.{0,32}(?:대회|챔피언십)|대항전|아마추어.{0,32}(?:대회|클래식|챔피언십)")
EXCLUDED = re.compile(r"파크\s*골프|결과\s*발표|생중계|대회\s*후기")
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
                           "search_lang": "ko", "count": 15, "freshness": "py"})
        content = json.loads(fetch(SEARCH_URL + "?" + query, {"X-Subscription-Token": api_key}))
        for item in content.get("web", {}).get("results", []):
            title = item["title"]
            url = canonical(item["url"])
            if url and EVENT.search(title) and not EXCLUDED.search(title):
                entry = candidate("웹 검색", title, url, UNKNOWN)
                entry["discovery_url"] = entry.pop("official_url")
                entry["official_url"] = None
                matches.append(entry)
    return matches


def event_status(event, today):
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
        for url in [event["official_url"], *event.get("source_urls", [])]
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


def collect(previous, now, offline=False):
    today = now.astimezone(KST).date()
    verified = [event_status(event, today) for event in json.loads(VERIFIED.read_text(encoding="utf-8"))]
    ids = [event["id"] for event in verified]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate verified event IDs")
    verified.sort(key=lambda event: event["start_date"], reverse=True)
    checks = []
    results = []
    old = [*previous.get("candidates", []), *(
        event for event in previous.get("tournaments", [])
        if event["verification"] == "official_schedule"
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
    verified.sort(key=lambda event: event["start_date"], reverse=True)
    candidates, duplicate_count = deduplicate(
        verified, [event for event in results if event["verification"] == "candidate_link_only"]
    )
    duplicate_count += duplicate_schedules
    return {
        "schema_version": 1, "updated_at": now.isoformat(),
        "note": "확인된 대회와 출처 검토가 필요한 후보를 분리합니다. null과 미확인은 정보 미확인입니다.",
        "sources": checks, "tournaments": verified, "candidates": candidates,
        "duplicates_suppressed": duplicate_count,
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
