# 강아지·고양이 병원 데이터

기준일: 2026-09-20 · dog/cat only

## 공개 상세 32곳
- 장비모델 갭: 1 (Dr.dog)
- 사이트 없으면 네이버플레이스/카카오맵

## companion 4138곳
| 등급 | 수 |
|------|----|
| 대학 | 12 |
| 2차 | 498 |
| 1차 | 180 |
| 일반 동네 | 3427 |
| 재활·한방 | 21 |

### Place 보강
- 홈페이지 보유: 1943곳
- 2차 무홈페이지 잔여: 37곳 (Place/Daum URL·전화·과목은 대부분 확보)
- 전 병원 departments 채움
- 1차 Place depth (로컬 11+클라우드 진행): 영업시간·전화·주소교정(검단→인천)
- 대학: 서울대·건국·전남대 공식 VMTH 홈페이지 확보
- 2차 hours fill: 해밀(휴게/공휴일) 등

### Place waves (merged)
Neigh final wave1 100: Place enrich merge
Neigh final wave3 56: Place enrich merge
Neigh final wave2 100: Place enrich merge
Primary nohp final 113: Place enrich merge
Secondary nohp wave2 37: Place enrich merge
Secondary hours round3 9: Place enrich merge
Primary hours round3 26: Place enrich merge
Misc residual neigh 31: Place enrich merge
Chungnam neigh wave2 20: Place enrich merge
Gyeonggi neigh wave4 79: Place enrich merge
Busan neigh wave2 7: Place enrich merge
Gyeongnam neigh wave2 30: Place enrich merge
Gyeonggi neigh wave3 100: Place enrich merge
Gyeongbuk neigh wave2 61: Place enrich merge
Seoul neigh wave4 32: Place enrich merge
Gwangju neigh wave1 95: Place enrich merge
- Daejeon neighborhood wave1: 85 (hit 73 / ambiguous 9 / CLOSED 3); homepage 25 / hours 65
- Jeju neighborhood wave1: 84 (hit 52 / no_hit 29 / ambiguous 1 / CLOSED 2); homepage 7 / hours 36
- Ulsan neighborhood wave1: 45 (hit 33 / no_hit 9 / ambiguous 1 / CLOSED 2); homepage 9 reported (0 new) / hours 31
- Gangwon neighborhood wave1: 100 (hit 86 / no_hit 2 / CLOSED 5 / LARGE_ANIMAL 7); homepage 5 / hours 41
- Chungbuk neighborhood wave1: 89 (hit 68 / no_hit 12 / CLOSED 4 / LARGE_ANIMAL 5); homepage 10 / hours 35
- Seoul neighborhood wave3: 112 (hit 95 / no_hit 10 / CLOSED 6 / LARGE_ANIMAL 1 물고기병원); homepage 2 (이윤세·우리와) / hours 92
- Jeonbuk neighborhood wave1: 100 (hit 82 / no_hit 6 / CLOSED 9 / LARGE_ANIMAL 3); homepage 6 / hours 31
- Jeonnam neighborhood wave1: 100 (hit 84 / ambiguous 6 / CLOSED 5 / LARGE_ANIMAL 5); homepage 0 / hours 14
- Gyeonggi neighborhood wave2: 100 (hit 85 / no_hit 6 / ambiguous 1 / CLOSED 8); homepage 2 (덕소·애플펫) / hours 41
- Gyeongbuk neighborhood wave1: 100 (hit 85 / no_hit 4 / ambiguous 1 / CLOSED 4 / LARGE_ANIMAL 6); homepage 0 / hours 23; phone +7
- Chungnam neighborhood wave1: 92 (hit 74 / no_hit 4 / ambiguous 3 / CLOSED 5 / LARGE_ANIMAL 6); homepage 2 / hours 22
- Gyeongnam neighborhood wave1: 100 (hit 87 / no_hit 6 / ambiguous 2 / CLOSED 5); homepage 1 (참좋은) / hours 37
- Incheon neighborhood wave1: 80 (hit 76 / ambiguous 2 / no_hit 2); homepage 3 / hours 43; CLOSED 3
- Daegu neighborhood wave1: 72 (hit 64 / no_hit 3 / ambiguous 1 / CLOSED 4); homepage 2 / hours 41
- hours round2: primary 29 (hit 27, hours_raw 3) + secondary 25 (hit 19 / ambiguous 6 skipped; homepage 18 reported, hours_raw 16)
- primary nohp wave 122: hit 118 / ambiguous 4 / no_hit 0; official homepage 0; hours hint/raw 77
- Seoul neighborhood wave2: 100 (hit 90 / no_hit 9 / ambiguous 1); homepage 1 (온 동물병원) / hours 72
- Busan neighborhood wave1: 93 (hit 84 / no_hit 9); homepage 1 (박 동물종합병원 daum cafe) / hours 54
- primary hours remaining 41: hit 39 / ambiguous 1 / no_hit 1; hours_raw 2 (참누리·웰니스부산 dirs); homepage 1 (참누리); CLOSED_EXCLUDE 5
- Gyeonggi neighborhood wave1: 100 (hit 91 / no_hit 7 / ambiguous 2); homepage 5 / hours 57
- special (대학·재활): 14 — 제주대·탑스 홈페이지 추가
- secondary hours fill: 6
- Seoul neighborhood wave1: 80 (hit 67 / no_hit 11 / ambiguous 2)
- primary depth 61 (cloud): hit 55 / ambiguous 2 / no_hit 4; 참누리·위드펫 홈페이지

- 제외: 경북대 상주 분원 (대동물 전용)
- primary nohp local 8: 모란→24시 hours; 가든·건국(성남 시민로) 폐업 제외
- secondary nohp wave: 37 (hit 29 / ambiguous 6 / no_hit 2; 공식 홈페이지 0)
- special remaining (대학·재활 잔여): 8 (hit 7 / no_hit 1; 경북대 상주분원 LARGE_ANIMAL_ONLY_EXCLUDE + knuvmth.co.kr)
- special remaining merge: 민간「대학동물병원」4곳 care_level→neighborhood; 한양·행복드림 hours
- 제외: 서울대공원 동물원동물병원 (동물원 진료)
- 제외(폐업): 한국종합동물병원·웰니스클리닉동물병원·장원종합동물병원·웰니스클리닉동물병원·서부종합동물병원
- 제외(대구 폐업): 박동물병원·킴스동물병원·아양동물병원·제일동물병원
- 제외(인천 폐업): 쿨펫동물병원·펫가든동물병원·다비드동물병원
- 제외(경남 폐업): 우리수산동물병원·송하동물병원·아주동물병원·현대수산동물병원·힘참동물병원
- 제외(충남 폐업): 참좋은동물병원·드림컨설팅동물병원·미소동물병원·한샘애견동물병원·한샘동물병원
- 제외(충남 대동물/축산): 당진축협동물병원·세종팜스동물병원·우사랑동물병원·한길동물병원·천성가축약품병원·천안축협동물병원
