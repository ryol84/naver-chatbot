# 강아지·고양이 병원 데이터

기준일: 2026-09-20 · dog/cat only

## 공개 상세 32곳
- 장비모델 갭: 1 (Dr.dog)
- 사이트 없으면 네이버플레이스/카카오맵

## companion 4296곳
| 등급 | 수 |
|------|----|
| 대학 | 12 |
| 2차 | 499 |
| 1차 | 187 |
| 일반 동네 | 3577 |
| 재활·한방 | 21 |

### Place 보강
- 홈페이지 보유: 1900곳
- 2차 무홈페이지 잔여: 37곳 (Place/Daum URL·전화·과목은 대부분 확보)
- 전 병원 departments 채움
- 1차 Place depth (로컬 11+클라우드 진행): 영업시간·전화·주소교정(검단→인천)
- 대학: 서울대·건국·전남대 공식 VMTH 홈페이지 확보
- 2차 hours fill: 해밀(휴게/공휴일) 등

### Place waves (merged)
- Gyeonggi neighborhood wave1: 100 (hit 91 / no_hit 7 / ambiguous 2); homepage 5 / hours 57
- special (대학·재활): 14 — 제주대·탑스 홈페이지 추가
- secondary hours fill: 6
- Seoul neighborhood wave1: 80 (hit 67 / no_hit 11 / ambiguous 2)
- primary depth 61 (cloud): hit 55 / ambiguous 2 / no_hit 4; 참누리·위드펫 홈페이지
- primary hours remaining 41: hit 39 / ambiguous 1 / no_hit 1; hours_raw 2 (참누리·웰니스부산 dirs); homepage 1 (참누리); CLOSED_EXCLUDE 5 (한국종합·웰니스부산·장원·웰니스아산·서부천안)

- 제외: 경북대 상주 분원 (대동물 전용)
- primary nohp local 8: 모란→24시 hours; 가든·건국(성남 시민로) 폐업 제외
- secondary nohp wave: 37 (hit 29 / ambiguous 6 / no_hit 2; 공식 홈페이지 0)
- special remaining (대학·재활 잔여): 8 (hit 7 / no_hit 1; 경북대 상주분원 LARGE_ANIMAL_ONLY_EXCLUDE + knuvmth.co.kr)
- special remaining merge: 민간「대학동물병원」4곳 care_level→neighborhood; 한양·행복드림 hours
- 제외: 서울대공원 동물원동물병원 (동물원 진료)
