# 지금 상태와 할 일 (2026-10-01)

## 돌아가는 것

- **사이트**: https://jipgapradar.kr (GitHub Pages, 무료). 가비아 도메인, HTTPS 강제, www → 맨 주소로 이동.
- **매일 자동**: `.github/workflows/daily.yml` — 06:00(한국) 국토부 수집 → DB 를 릴리스 `db` 에 되올림 → 빌드·검사 → 950MB 이하면 배포.
  맥이 꺼져 있어도 된다. 실행 기록: https://github.com/bbdyno/RealEstateCardNews/actions
- **검색 등록**: 구글 서치콘솔(도메인 속성, 사이트맵 제출), 네이버 서치어드바이저(소유 확인·사이트맵 제출).
- **광고 코드**: 애드센스(자동 광고 + 자리별 단위 + 멀티플렉스) → 애드핏 순차, 쿠팡 맥락 블록, 직접 광고 카드 — ID 를 넣으면 켜진다.
- **통계 코드**: GA4 측정 ID 를 넣으면 방문자·페이지뷰·유입 경로 + 주요 클릭 이벤트가 쌓인다.

## 해 주셔야 하는 것

1. **애드센스 신청** — https://adsense.google.com 에서 사이트 jipgapradar.kr 추가(본인 정보·약관 동의는 직접).
   발급되는 `ca-pub-…` 를 알려 주면 `config.yaml` `ads.adsense.client` 에 넣는다 → 사이트 확인 코드 + ads.txt 가 자동으로 들어간다.
   승인 뒤: 광고 단위(디스플레이 4개: top·mid·bottom·list, 멀티플렉스 1개: related)를 만들어 번호를 알려 주고,
   애드센스 화면 → 광고 → 자동 광고에서 **전면 광고·앵커·사이드 레일**을 켠다.
2. **구글 애널리틱스(GA4)** — 속성 만들기에 약관 동의가 필요하다. 허락해 주면 Chrome 에서 만들고 측정 ID(G-…)를 넣는다.
3. **쿠팡 파트너스 가입**, **카카오 애드핏 제휴 문의**(초대·승인제).
4. **인스타 @jipgapradar** 가입(프로필: `web/static/instagram-profile.png`).
5. **광고·제휴 문의 메일 주소** → `config.yaml` `site.contact_email`.
6. **재개발 자료** — 서울 정비사업 공개 파일 다운로드 허락. 자료가 없으면 재개발 메뉴·페이지는 자동으로 숨는다.

## 확인 중

- GitHub 도메인 소유 확인(Settings → Pages): TXT 는 모든 공용 DNS 에 보이는데 아직 Unverified — GitHub 반영 대기(최대 24시간).
