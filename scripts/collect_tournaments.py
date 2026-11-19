#!/usr/bin/env python3
"""Collect candidate screen-golf tournament links from public official pages.
Candidate links are NOT verified event registrations; do not invent dates or fees.
"""
import json
import os
import re
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

SOURCES = [
    ("프렌즈스크린", "https://www.friendsscreen.kr/main/contest"),
    ("골프존 GTOUR", "https://gtour.com/"),
]
KEYWORDS = ("대회", "이벤트", "contest", "tournament", "gtour", "챔피언십")
OUTPUT = "data/tournaments.json"

class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.href = None
        self.parts = []
        self.items = []
    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.href = dict(attrs).get("href")
            self.parts = []
    def handle_data(self, data):
        if self.href is not None:
            self.parts.append(data)
    def handle_endtag(self, tag):
        if tag == "a" and self.href is not None:
            self.items.append((self.href, " ".join(self.parts).strip()))
            self.href = None
            self.parts = []

def main():
    now = datetime.now(timezone.utc).isoformat()
    entries, checks, seen = [], [], set()
    for provider, source in SOURCES:
        try:
            req = urllib.request.Request(source, headers={"User-Agent": "GolfTournamentAlert/0.1 (+public tournament discovery)"})
            with urllib.request.urlopen(req, timeout=20) as response:
                html = response.read(2_000_000).decode("utf-8", "replace")
            parser = Links()
            parser.feed(html)
            count = 0
            for href, title in parser.items:
                url = urljoin(source, href)
                parsed = urlparse(url)
                if parsed.scheme != "https" or not parsed.netloc:
                    continue
                if not any(word in (title + " " + url).lower() for word in KEYWORDS):
                    continue
                if url in seen or url.rstrip("/") == source.rstrip("/"):
                    continue
                seen.add(url)
                entries.append({
                    "provider": provider, "title": title[:160] or "대회 관련 링크",
                    "official_url": url, "region": "미확인", "category": "스크린골프",
                    "start_date": None, "end_date": None, "entry_fee": None,
                    "registration_status": "미확인", "amateur_eligible": None,
                    "verification": "candidate_link_only"
                })
                count += 1
            checks.append({"provider": provider, "source_url": source, "ok": True, "candidate_count": count})
        except Exception as exc:
            checks.append({"provider": provider, "source_url": source, "ok": False, "error": str(exc)[:250]})
    os.makedirs("data", exist_ok=True)
    payload = {"schema_version": 1, "updated_at": now, "note": "공식 사이트에서 발견한 후보 링크이며 참가 가능 여부와 일정은 미검증", "sources": checks, "tournaments": entries}
    with open(OUTPUT, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=2)
        fp.write("\n")
    print(f"Wrote {len(entries)} candidate links; successful sources: {sum(c['ok'] for c in checks)}/{len(checks)}")

if __name__ == "__main__":
    main()
