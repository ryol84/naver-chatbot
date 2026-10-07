# LV-2602 아기 추빨대 추 (Silicone Straw Weight)

실리콘 비중 **1.8** 기준 무게 **9 g** (부피 **5.0 cm³**)을 목표로 한 아기용 추빨대 추 디자인입니다.

## 디자인 컨셉 — 이슬방울 (Dewdrop)

| 항목 | 내용 |
|------|------|
| 형태 | 부드러운 물방울/이슬 실루엣 — 날카로운 모서리 없음 |
| 재질 | 전체 실리콘 (100%) |
| 목표 무게 | 9.0 g @ SG 1.8 |
| 실측 부피 | ≈ 4992 mm³ → ≈ **8.99 g** |
| 전체 크기 | 약 **40.8 × 21.2 × 16.3 mm** |

### 왜 이 형태인가

1. **예뻐 보이는 실루엣** — 단순 타원 블롭 대신 볼륨감 있는 이슬방울 + 부드러운 crest
2. **세척 용이** — 앞쪽 오픈 인테이크 + 십자형 플러시 포트 + 관통 보어 (막힌 공동 없음)
3. **호스 고정** — Ø4.5 mm 스템 + 테이퍼 선단 + Ø5.4 mm 이중 리브

## 빨대/호스 연결부

| 치수 | 값 | 역할 |
|------|-----|------|
| 스템 외경 | **4.5 mm** (실측 유지) | 실리콘 호스 삽입 기준 |
| 스템 길이 | 11 mm | 충분한 결속 길이 |
| 선단 테이퍼 | tip ≈ Ø3.9 mm → Ø4.5 mm | 삽입 쉽게 |
| 고정 리브 | Ø5.4 mm × 2개 | 실리콘-실리콘 이탈 방지 |
| 내부 보어 | Ø2.2 mm | 음용 유로 |

> 실리콘 호스 내경이 약 4.0–4.3 mm일 때, Ø4.5 mm 스템이 살짝 늘어나며 들어가고 리브가 걸려 **쉽게 끼워지고 잘 빠지지 않습니다.**

## 세척 포인트

- 전면 오픈 마우스 → 솔/수돗물로 바로 헹굼
- 측면·상하 플러시 포트 → 내부 잔여물 배출
- 관통 보어 → 호스 쪽까지 한 번에 통수
- 외부는 연속 곡면 — 틈새·각진 홈 최소화

## 파일

```
products/baby-straw-weight/
├── stl/
│   ├── LV-2602-straw-weight-9g.stl      ← 최종 모델
│   ├── LV-2602-straw-weight-9g-v1.stl
│   ├── reference-LV-2602-001.stl        ← 기존 참고
│   └── reference-LV-2602-002.stl
├── scripts/generate_straw_weight.py     ← 파라메트릭 생성기
├── renders/preview_3view.png
├── docs/design_metrics.json
└── docs/DESIGN_KO.md
```

## 재생성

```bash
pip install trimesh manifold3d scipy shapely networkx numpy-stl matplotlib fast-simplification
python3 products/baby-straw-weight/scripts/generate_straw_weight.py
```

바디 Y/Z만 미세 조정해 부피 5 cm³를 맞추므로 **스템 Ø4.5 mm는 스케일되지 않습니다.**

## 기존 모델 대비

| | 기존 참고 STL | 신규 디자인 |
|--|---------------|-------------|
| 부피 | ≈ 2.93 cm³ | ≈ 5.00 cm³ |
| 무게 @1.8 | ≈ 5.3 g | ≈ 9.0 g |
| 메시 | non-watertight | watertight |
| 세척 | 복잡/좁은 슬릿 | 오픈 인테이크 + 플러시 |
| 호스 연결 | 불명확 | Ø4.5 + 리브 명시 |
