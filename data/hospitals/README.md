# 강아지·고양이 병원 데이터

기준일: 2026-09-20  
범위: **dog / cat only** (축산·한우·말전문·야생 제외)

## 파일
| 파일 | 용도 |
|------|------|
| `site-hospitals*.json/csv` | 공개 상세 32곳 |
| `companion-hospitals.csv/jsonl` | 전국 소동물 4300곳 |
| `companion-accumulation-ledger.json` | 병원별 증거 축적 장부 |
| `website-enrichment.json` | 사이트 수집 요약 |

## 공개 32곳
- 24시: yes=12, partial=11, no=9
- 응급: yes=25, no=7, unknown=0
- 상태: verified_draft 32
- 제외: 제주대 말전문동물병원
- 남은 갭: {'no_official_equipment_proof': 30}

## 축적 방식
병원 하나씩 CSV·공식사이트·기존 프로필을 대조하고 `evidence_log`에 source와 함께 쌓습니다.
