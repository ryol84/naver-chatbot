# 강아지·고양이 병원 데이터

기준일: 2026-09-20 · dog/cat only

## 공개 상세 (site-hospitals) 32곳
- 갭 없음: 31곳
- 장비모델 갭: 1곳 (Dr.dog CT모델)
- 사이트 없으면 **네이버플레이스 / 카카오맵**으로 확인·기재

## 전국 companion 4300곳 care_level
| 등급 | 의미 | 수 |
|------|------|----|
| university | 대학동물병원 | 17 |
| secondary | 2차 의료센터 | 496 |
| primary | 1차 진료 | 190 |
| neighborhood | 일반 동네병원 | 3576 |
| rehab_specialty | 재활·한방 특화 | 21 |

사이트 없는 병원은 `place_search_url` · `daum_map_url` 필드로 조회.
