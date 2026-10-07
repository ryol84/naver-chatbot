# LV-2602 아기 추빨대 추 (rev2)

원형 **납작 타원** 실루엣을 유지한 실리콘 추입니다.  
젖병(플라스틱) 안에서 아이가 어떤 방향으로 기울여도 추가 바닥으로 미끄러져 내려가, **하단 구멍**으로 분유/우유를 빨 수 있게 합니다.

## 핵심 포인트

1. **추 모양 유지** — 기존 LV-2602과 같은 납작 타원(flat oval), 둥근 dewdrop으로 바꾸지 않음  
2. **하단 흡입 구멍 3개** — 추가 바닥에 앉았을 때 액체가 들어옴  
3. **저마찰** — 상·하면 크라운 곡면으로 젖병과의 접촉면 최소화 → 쉽게 미끄러짐  
4. **연결부 단순** — Ø4.5 mm 직선 스템 + 선단 테이퍼만 (리브/비드 없음 → 세척 쉬움)  
5. **무게** — SG 1.8 기준 **≈9 g** (부피 ≈5.0 cm³)

## 스펙

| 항목 | 값 |
|------|-----|
| 크기 | 약 **44 × 23.5 × 11.6 mm** (원형 비율 유지, 부피 스케일) |
| 납작비 (Z/Y) | ≈0.50 (원형 ≈0.47) |
| 스템 | **Ø4.5 × L9 mm**, tip 테이퍼만 |
| 하단 구멍 | Ø3.6 mm × 3 |
| 보어 | Ø2.2 mm 관통 |
| 무게 @1.8 | ≈ **8.99 g** |

## 파일

- `stl/LV-2602-straw-weight-9g.stl` — 최종
- `stl/reference-LV-2602-001.stl` — 원형 참고
- `scripts/generate_straw_weight.py` — 파라메트릭 생성기
- `docs/DESIGN_KO.md` — 설계 설명

```bash
pip install -r products/baby-straw-weight/requirements.txt
python3 products/baby-straw-weight/scripts/generate_straw_weight.py
```
