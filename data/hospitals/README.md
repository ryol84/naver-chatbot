# 동물병원 사이트 데이터 (상세 보강본)

기준일: 2026-09-20

## 소스
1. `homepage-public` — 검증된 상세 프로필 33곳
2. [동물병원_전국.csv](https://drive.google.com/file/d/1IoVXrRgjLUcu4cArEVNDhEFbAUrreCKq/view) — **4411곳** 영업시간·전화·홈페이지·좌표
3. 병원 공식 웹사이트 — 분과·장비·진료시간 상세 (self_claimed)

## 산출물
| 파일 | 내용 |
|------|------|
| `site-hospitals.json` / `slim` / `csv` | 공개 33곳 상세(보강) |
| `nationwide-hospitals.csv` / `.jsonl` | 전국 4411곳 정규화 |
| `nationwide-meta.json` | 전국 통계 |
| `website-enrichment.json` | 사이트 수집 원본 요약 |
| `site-add-candidates.*` | 아직 비공개 후보 |

## 공개 33곳 현황
- 24시: {'partial': 11, 'yes': 12, 'unknown': 4, 'no': 6}
- 응급: {'yes': 25, 'unknown': 5, 'no': 3}
- 홈페이지 연결: 27곳
- 사이트 스크랩 반영: 18곳
- 전화 확보: 33/33
- gaps: {'no_official_equipment_proof': 33, 'stale_source': 3, 'hours_token_gap': 1, 'emergency_unconfirmed': 4, 'departments_sparse': 1, 'hours_unconfirmed': 2}

## 전국 4411곳
- 홈페이지: 1900
- 영업시간: 3120
- 전화: 4036
- 매일 00–24: 179

## 사용 가이드
- 사이트 카드/상세: `site-hospitals-slim.json` (분과·장비·시간·홈페이지)
- 지도·검색: `nationwide-hospitals.csv`
- 전국 CSV 일부 좌표 오류 있음 → 프로필 주소·전화 우선
