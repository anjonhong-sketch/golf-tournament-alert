# 골프대회 알리미

전국 스크린골프 대회와 일반 아마추어가 조건에 따라 참가할 수 있는 필드골프 대회를 모읍니다. 갤럭시에서 실행할 수 있는 Android 앱 소스는 `android/`에 있습니다.

## 대회 데이터

앱은 시작 시와 새로고침 시 [공개 JSON](https://raw.githubusercontent.com/anjonhong-sketch/golf-tournament-alert/main/data/tournaments.json)을 읽습니다. 연결에 실패하면 기기에 보관한 마지막 목록을 표시합니다. 첫 버전의 검색, 필터, 즐겨찾기, 직접 등록 구성을 사용하며 직접 등록한 대회는 기기에 저장합니다.

- `tournaments`에는 주최 측 자료를 확인한 대회와 프렌즈스크린·SG골프 공식 목록에서 일정이 추출된 대회가 들어갑니다. `official_schedule`이면 일정 외에 참가 자격과 참가비 등은 미확인일 수 있습니다. 확인된 대회는 `data/verified_tournaments.json`에서 관리합니다.
- `candidates`에는 추가 확인이 필요한 링크가 들어갑니다. 웹 검색 링크는 `discovery_url`에 넣으며 주최 측 원문이 확인되지 않으면 `official_url`은 `null`입니다. 자격과 참가비 등 확인하지 못한 값은 `null` 또는 미확인으로 표시합니다.
- 대회 상태와 접수 상태는 각각 표시합니다. 날짜 계산은 한국 시간 기준이며 종료일 당일까지 진행 중으로 봅니다. 링크 추적 파라미터와 확인된 대회 제목의 중복을 제거합니다. 서로 다른 제목의 기사까지 모두 같은 대회로 판정할 수는 없습니다.

## 자동 업데이트

Actions의 **Update golf tournaments**가 매시 17분에 프렌즈스크린, 골프존 뉴스룸, SG골프, 대한골프협회, 한국미드아마추어골프연맹의 공개 페이지를 확인합니다. 프렌즈스크린·SG골프는 페이지에 명시된 일부 일정을 자동 추출합니다. 수집 코드나 확인 목록이 main에 반영될 때도 실행합니다. 나머지 사이트에서 찾은 새 링크와 웹 검색 결과는 후보로 공개하고, 참가 자격과 일정 등을 확인한 항목은 확인 목록에 추가합니다. 페이지 구조 변경, 자바스크립트 렌더링, 자동 접속 제한에 따라 일부 대회가 빠질 수 있습니다.

웹 검색을 활성화하려면 저장소의 Actions 비밀값 `BRAVE_SEARCH_API_KEY`에 Brave Search API 키를 등록합니다. 검색은 매일 오전 9시 17분(한국 시간)과 수동 실행 때 수행합니다. 키가 없으면 공식 사이트 수집은 계속되며 검색 상태가 JSON에 표시됩니다. **Run workflow**로 즉시 실행하거나, 다음 명령으로 오프라인 테스트를 실행할 수 있습니다.

```sh
python -m unittest discover -s tests -v
python scripts/collect_tournaments.py --offline
```

## 갤럭시 앱과 커뮤니티

Android Studio에서 `android/`를 열고 JDK 17, Android SDK 36, Gradle 8.11.1로 빌드합니다. **Test collector and build Android**의 성공한 실행에서 테스트용 APK를 받을 수 있습니다. 커뮤니티 연결 설정 없이도 대회 목록과 원문을 이용할 수 있습니다.

실시간 채팅과 참가 후기를 활성화하려면 Firebase 프로젝트에 Android 패키지 `com.golf.tournamentalert`을 등록하고, **익명 인증**과 **Cloud Firestore**를 사용하도록 설정합니다. 받은 `google-services.json`을 `android/app/`에 두고 다음 명령으로 이 저장소의 Firestore 규칙을 프로젝트에 적용한 다음 APK를 다시 빌드합니다.

```sh
firebase deploy --only firestore:rules --project YOUR_PROJECT_ID
gradle --project-dir android assembleDebug
```

채팅과 후기는 대회 고유 ID 단위로 분리됩니다. 다른 사용자는 익명 참가자로 표시되며 글 작성자는 자신의 글을 삭제할 수 있습니다. Firebase 프로젝트와 연결된 두 기기에서 같은 대회에 접속해 채팅 전송, 후기 등록, 본인 글 삭제를 확인할 수 있습니다.
