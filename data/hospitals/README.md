# 동물병원 사이트 데이터 정리 (korea-vet-db)

기준일: 2026-09-19T22:18:09  
원본 폴더: Google Drive `korea-vet-db`

## 원본 구성
| 파일 | 내용 |
|------|------|
| `homepage-public.json` / spreadsheet | **사이트 공개용 33곳** (verify public 게이트) |
| `gwangju-honam-profiles.json` | 광주·호남 심층 26곳 (public 2 / internal 2 / hold 22) |
| `korea-animal-hospitals.csv` | 전국 마스터 5,480곳 (인허가·좌표·24시 상호 플래그) |
| `korea-animal-hospitals.xlsx` | 동일 DB + 시도/시군구 요약 |

## 이번 산출물 (`data/hospitals/`)
- `site-hospitals.json` — 상세 정규화(분과·장비·진료시간·근거)
- `site-hospitals-slim.json` — UI/챗봇용 요약
- `site-hospitals.csv` / `site-hospitals-overview.md` — 검토용
- `site-add-candidates.json` / `.csv` — 아직 사이트에 올리면 안 되는 추가 후보

## 공개 33곳 요약
- 역할: {'2차 의료센터': 19, '대학동물병원': 11, '재활 특화': 2, '2차(+재활실)': 1}
- 24시: {'yes': 17, 'unknown': 9, 'partial': 5, 'no': 2}
- 응급: {'yes': 24, 'unknown': 8, 'no': 1}
- 분과 태그 빈도: {'영상(CT/MRI)': 30, '응급': 23, '신경': 9, '종양': 6, '정형외과': 6, '재활': 6, '최소침습': 4, '안과': 4, '심장': 3, '치과': 2, '투석': 2, '고양이 특화': 2, '일반외과': 2, '내과': 1, '말(대동물)': 1}
- 장비 태그 빈도: {'CT': 23, 'MRI': 19, 'X-ray': 10, '초음파': 8, '내시경': 4, '수중런닝/수중보행': 3, 'C-arm': 2, '심장초음파': 2, '고압산소': 2, '복강경': 1, 'ICU': 1, '인공호흡기': 1, 'PET-CT': 1}

## 사이트에 바로 넣을 수 있는 필드
1. **기본**: 이름, 시도/시군구, 전화, 주소, 역할(2차/대학/재활특화)
2. **진료시간**: `hours_24h`, `emergency`, `weekday_hours`, `weekend_hours`, `night_hours`, `hours_note`
3. **분과**: treatments 코드 → 한글 라벨
4. **제공 시술/서비스**: `services`
5. **주력 질환**: `focus_conditions`
6. **장비**: kind/item/model + 근거 레벨
7. **한 줄 강점**: `strength_plain` (+ `avoid_hype`)
8. **신뢰도**: confidence, verification grade/score, sources

## 보완하면 좋은 점 (site_gaps)
- `no_official_equipment_proof`: 33곳
- `hours_unconfirmed`: 9곳
- `emergency_unconfirmed`: 8곳
- `phone_missing`: 4곳
- `hours_note_missing`: 4곳
- `stale_source`: 3곳
- `departments_sparse`: 2곳
- `hours_token_gap`: 1곳

### 우선 조치
1. 전화 없는 병원 채우기 (노원N, 전남대, 충남대, 온누리)
2. hours_note 없는 곳 영업시간 확보 (재활 특화·노아)
3. 장비 official 근거 보강
4. 24시 unknown 전화 재확인
5. 분과 비어 있는 곳(경상국립대, 서울대검진센터) 공식 분과 반영

## 추가 가능한 병원 (아직 public 아님)
- internal 2곳 / hold 22곳
- 승격 조건: 장비·분과 근거 + master 매칭 + 과장 제거
- 24시 바덴동물메디컬 (전남광주통합특별시 광산구) · 24시=yes · C-arm, CT
- 공감동물메디컬센터 (전남광주통합특별시 광산구) · 24시=yes · CT, MRI

### hold 요약
근거 부족으로 비공개 유지. 상세는 `site-add-candidates.csv`.

## 전국 마스터(5,480) 활용
검색·지도·지역 목록용. 상호 `24시` 토큰 ≠ 실제 야간 진료. 분과/장비/확정 시간은 상세 프로필 33곳만 노출 권장.
