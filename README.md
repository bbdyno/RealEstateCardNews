# RealEstateCardNews

전국 아파트·오피스텔·빌라 실거래가와 재개발 정보를 보여 주는 정적 웹사이트(+ 이후 인스타 카드뉴스).
벤치마크는 아파트썸(@apt_sum, aptsum.kr). 차이는 **아파트 밖(오피스텔·빌라·재개발)과 전국**, 그리고
**단지·동·지역마다 고유 주소가 있는 페이지**(검색 유입 → 애드센스)다. 사이트 브랜드는 '집값레이더'(`config.yaml`, 2026-09-30 확정).

## 구조

```
collector/   국토부 실거래 수집(8종) · 재개발 파일 가져오기 · 샘플 데이터
  sigungu.json   전국 250개 시군구(2022 법정동 코드 + 이후 행정구역 변경 보정)
analytics/   단지·지역 통계(기준월, 평당가, 신고가, 전세가율, 오피스텔 수익률, 빌라 대지지분 평당가)
web/         정적 사이트 빌드(Jinja2 템플릿 · 서버 렌더 SVG 차트 · CSS)
scripts/     check_links·check_html · make_icons·make_og · daily.sh(로컬에서 돌릴 때만 — 평소엔 GitHub Actions)
docs/        MORNING.md(지금 상태·할 일) · MONETIZATION.md(광고·유료 설계) · DESIGN.md
data/        realestate.db (git 제외)
dist/        빌드 결과 (git 제외)
```

## 명령

```bash
python3.14 -m venv .venv && .venv/bin/pip install httpx jinja2 pyyaml python-dotenv pytest

.venv/bin/python -m collector.collect --plan          # 할 일만 센다(호출 없음)
.venv/bin/python -m collector.collect                 # 36개월 중 빠진 달 채우기 + 최근 3개월 다시 받기
.venv/bin/python -m collector.demo [--clear]          # 개발용 샘플 데이터 넣기/지우기
.venv/bin/python -m collector.redevelop 파일.csv --sido 서울 --source "…" --dry-run
.venv/bin/python -m web.build                         # dist/ 생성
.venv/bin/python scripts/check_links.py               # 내부 링크 검사
.venv/bin/python -m pytest -q tests
```

## 클라우드 실행(맥 없이)

`.github/workflows/daily.yml` 이 매일 06:00(한국 시각) GitHub Actions 에서 돈다.
DB 는 릴리스 `db` 의 `realestate.db.zst` 로 보관하고(받기 → 수집 → 되올리기), 사이트는 GitHub Pages 로 배포한다.
인증키는 저장소 Secrets 의 `DATA_GO_KR_KEY`. 사이트가 950MB 를 넘으면 배포를 건너뛰고 경고를 남긴다(Pages 한도 1GB).

## 원칙

- 공공데이터만 쓴다. 네이버 등 플랫폼 매물 수집·가공은 하지 않는다(네이버 vs 다윈중개, DB권 침해 배상 판결).
- 개별 매물 광고를 받지 않는다(공인중개사법 제18조의2 ③).
- 샘플 데이터(demo=1)가 있으면 모든 페이지에 배너·noindex, robots 는 전체 차단, daily.sh 는 빌드를 멈춘다.
- 빌드 결과는 같은 데이터면 같은 파일이다(증분 배포). 새 거래 한 건 → 바뀌는 파일 8개 안팎.
