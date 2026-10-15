# 반려견 영양제 종류별 성분스택 DB

- 버전: 1.1.0
- 업데이트: 2026-10-15
- 범위: 유럽(EU), 미국(US), 한국(KR), 일본(JP)
- 용도: 네이버 챗봇/상세 성분 매칭, 목적별 안내
- 규모: 카테고리 9 / 성분 36 / 포뮬러 27
- Drive: `DB/영양제` (folder id `1swCmiqKRiMok_8g9kMxxcyHCPsVr_e5c`)

## 파일
1. `반려견_영양제_종류별_성분스택_DB` (Google Sheet) — 포뮬러 flat 테이블 (권장 보기)
2. `supplement_type_stack_db.csv` — 포뮬러(종류×지역) CSV
3. `supplement_category_region_summary.csv` — 카테고리×지역 요약
4. `supplement_ingredient_master.csv` — 성분 마스터
5. `supplement_type_stack_db.formulas.json` — 포뮬러 JSON
6. `supplement_type_stack_db.ingredients.json` — 성분 JSON
7. `supplement_type_stack_db.categories_1.json` — 카테고리(관절·치아·두뇌)
8. `supplement_type_stack_db.categories_2.json` — 카테고리(종합·항산화·장)
9. `supplement_type_stack_db.categories_3.json` — 카테고리(피부·진정·간)

## 카테고리
관절, 치아, 종합건강, 항산화, 장·소화, 피부·피모, 진정·스트레스, 간, 두뇌

## v1.1.0 변경 (2026-10-15)
- `digestive_enzymes`(판크립신) / `mos` / `erythritol` 성분 추가
- gut: KR 지역·벳타제·드시모네펫 매칭
- dental: JP 퓨레 포맷·HÜGBIO·에리트리톨·SHMP
- 포뮬러: US-GUT-ENZYME, KR-GUT-ENZYME, KR-GUT-DESIMONE, JP-DENTAL-PUREE

## 주의
- 치료·완치 클레임 금지
- 완전·균형 사료 급여 시 영양제가 필수는 아닐 수 있음
- 용량·질환은 수의사 상담 우선
- 에리트리톨 ≠ 자일리톨(독성) — 혼동 금지
