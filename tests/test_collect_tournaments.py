import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

from scripts import collect_tournaments as collector


class CollectorTests(unittest.TestCase):
    def test_event_end_uses_korea_calendar(self):
        before_midnight = datetime(2026, 12, 9, 14, 59, tzinfo=timezone.utc)
        midnight = datetime(2026, 12, 9, 15, tzinfo=timezone.utc)
        def quantum_at(instant):
            feed = collector.collect({}, instant, offline=True)
            return next(event for event in feed["tournaments"] if event["id"] == "friends-2026-quantum-9x-autumn")

        current = quantum_at(before_midnight)
        ended = quantum_at(midnight)
        self.assertEqual(current["event_status"], "진행 중")
        self.assertEqual(ended["event_status"], "종료")
        self.assertEqual(ended["registration_status"], "접수 마감")

    def test_ongoing_listing_does_not_invent_dates(self):
        event = {"id": "ongoing", "schedule_type": "ongoing", "start_date": None, "end_date": None,
                 "registration_status": "매장 참여"}
        listing = collector.event_status(event, date(2026, 11, 19))
        self.assertEqual(listing["event_status"], "상시 안내")
        self.assertIsNone(listing["end_date"])

    def test_registration_window_separate_from_tournament(self):
        event = {"id": "example", "start_date": "2026-12-10", "end_date": "2026-12-11",
                 "registration_start": "2026-12-01", "registration_end": "2026-12-03"}
        self.assertEqual(collector.event_status(event, date(2026, 12, 1))["registration_status"], "접수 중")
        closed = collector.event_status(event, date(2026, 12, 4))
        self.assertEqual((closed["event_status"], closed["registration_status"]), ("예정", "접수 마감"))

    def test_deduplicates_tracking_urls_and_curated_titles(self):
        official = {"official_url": "https://one.example/event", "title": "골프존마켓 스크린골프 대회"}
        def result(title, url):
            return collector.candidate("example", title, url, "스크린골프")
        candidates = [
            result("골프존마켓 스크린골프 대회 개최", "https://two.example/post"),
            result("다른 골프대회", "https://three.example/post?utm_source=test&id=1"),
            result("중복 골프대회", "https://three.example/post/?id=1#details"),
        ]
        unique, number = collector.deduplicate([official], candidates)
        self.assertEqual(len(unique), 1)
        self.assertEqual(number, 2)

    def test_friends_listing_extracts_dates_but_not_eligibility_or_fee(self):
        html = ("<script>가짜 대회 오픈 이벤트 기간 2026-11-01 - 2026-11-02</script>"
                "<div>대회 진행중</div><h3>26년 11월 '겨울 퀀텀 대항전' 대회 오픈</h3>"
                "<p>이벤트 기간 2026-11-20 - 2026-12-01</p>")
        with patch.object(collector, "fetch", return_value=html):
            results = collector.official_candidates("프렌즈스크린", "https://example.org/", "스크린골프")
        self.assertEqual(len(results), 1)
        event = results[0]
        self.assertEqual(event["title"], "겨울 퀀텀 대항전")
        self.assertEqual(event["end_date"], "2026-12-01")
        self.assertIsNone(event["entry_fee"])
        self.assertIsNone(event["amateur_eligible"])

    def test_sg_store_list_keeps_eligibility_unconfirmed(self):
        html = ("<tr><td>진행</td><td>경남</td><td>테라스크린 골프대회"
                "<span>기간 : 2026-11-19 ~ 2026-12-27</span>"
                "<span>주최매장 : 테라스크린골프</span><span>코스 : A</span></td></tr>")
        with patch.object(collector, "fetch", return_value=html):
            events = collector.official_candidates("SG골프", "https://example.org/", "스크린골프")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["region"], "경남 테라스크린골프")
        self.assertIsNone(events[0]["amateur_eligible"])
        self.assertEqual(events[0]["registration_status"], "미확인")

    def test_failed_source_preserves_cached_candidates(self):
        item = collector.candidate("골프존", "다른 골프대회", "https://example.com/1", "스크린골프")
        with patch.object(collector, "fetch", side_effect=TimeoutError):
            feed = collector.collect({"candidates": [item]}, datetime.now(timezone.utc))
        self.assertIn(item, feed["candidates"])
        self.assertGreaterEqual(len(feed["tournaments"]), 4)

    def test_naver_searches_blog_and_cafe_with_local_variants(self):
        payload = '{"items":[{"title":"<b>천안</b> 11월 스크린대회","link":"https://blog.naver.com/example/1"}]}'
        with patch.object(collector, "fetch", return_value=payload) as fetch:
            entries = collector.naver_candidates("client", "secret")
        urls = [call.args[0] for call in fetch.call_args_list]
        self.assertTrue(any("/blog.json?" in url for url in urls))
        self.assertTrue(any("/cafearticle.json?" in url for url in urls))
        self.assertIn("천안 스크린대회", [collector.parse_qsl(collector.urlsplit(url).query)[0][1] for url in urls])
        self.assertEqual(entries[0]["title"], "천안 11월 스크린대회")
        self.assertIsNone(entries[0]["official_url"])

    def test_web_results_do_not_claim_organizer_verification(self):
        results = '{"web":{"results":[{"title":"전국 아마추어 골프대회","url":"https://example.com/e"}]}}'
        with patch.object(collector, "fetch", return_value=results):
            entry = collector.web_candidates("test", date(2026, 11, 19))[0]
        self.assertIsNone(entry["official_url"])
        self.assertIsNone(entry["entry_fee"])
        self.assertEqual(entry["discovery_url"], "https://example.com/e")
