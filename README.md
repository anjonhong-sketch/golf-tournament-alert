# 골프대회 알리미

전국 스크린골프 및 아마추어 골프대회 정보 앱을 위한 데이터 수집 저장소입니다.

## 자동 수집
GitHub Actions가 매시간 17분(UTC)에 공식 사이트의 공개 페이지를 확인하여 `data/tournaments.json`을 갱신합니다. 예약 실행은 지연되거나 생략될 수 있습니다.

현재 수집기는 **대회 후보 링크 탐색기**입니다. 참가 가능 여부, 대회 날짜, 참가비, 접수 상태를 검증하지 않으며 모두 미확인으로 표시합니다. 일부 사이트가 자바스크립트로 내용을 표시하거나 자동 접근을 제한하면 후보를 찾지 못할 수 있습니다. 수집 성공은 실제 대회 발견을 보장하지 않습니다.

## 수동 실행
Actions → Update screen golf tournament candidates → Run workflow.

## 데이터 주소
https://raw.githubusercontent.com/anjonhong-sketch/golf-tournament-alert/main/data/tournaments.json

## 다음 단계
공식 사이트별 구조에 맞춘 수집기, 대회 상세 검증, Android 앱의 JSON 연동, 중복 제거와 변경 이력 관리가 필요합니다. `verification: candidate_link_only`인 항목을 참가 가능한 확정 대회로 표시하지 마세요.
