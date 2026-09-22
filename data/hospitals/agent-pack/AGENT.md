# Companion hospital agent pack

**Version:** `2026-09-20.1` · **as_of:** `2026-09-20` · **n:** 4137 dog/cat hospitals (Korea)

Handoff surface for other agents. Prefer this pack over raw Place/Google wave jsonl.

## Quick start

```bash
pack=data/hospitals/agent-pack
python3 - <<'PY'
import json
from pathlib import Path
rows=[json.loads(l) for l in Path('data/hospitals/agent-pack/companion-hospitals.jsonl').read_text().splitlines() if l.strip()]
print(len(rows), rows[0]['name'], rows[0]['care_level'])
PY
```

Or unzip `companion-hospitals-agent-pack-2026-09-20.1.zip` and read `AGENT.md` + `companion-hospitals.jsonl`.

## Files

| File | Use |
|------|-----|
| `companion-hospitals.jsonl` | Canonical DB (one hospital / line) |
| `companion-hospitals.csv` | Flat table; departments is pipe-joined |
| `companion-meta.json` | Counts + enrichment summary |
| `schema.json` | Field dictionary + rules |
| `samples.json` | One example per care_level |
| `secondary-24h.jsonl` | 2차 + hours_24h=yes subset (189 rows) |
| `MANIFEST.json` | Checksums + paths |

## Care levels

| care_level | KO | count |
|------------|----|------:|
| university | 대학 | 12 |
| secondary | 2차 | 498 |
| primary | 1차 | 180 |
| neighborhood | 동네 | 3426 |
| rehab_specialty | 재활·한방 | 21 |

## Coverage

- reliable homepage: **1629**
- phone: **3959**
- hours_24h=yes: **226**
- hours.raw present: **3328**

## Rules other agents MUST follow

1. Species: dog/cat companion only (`species_scope`).
2. `hours_24h=yes` only when source literally says 24시간 / 00:00–24:00. Never infer from name token alone.
3. If `homepage_unreliable` is true (SNS), treat as no official site; use `place_search_url` / `daum_map_url`.
4. Do not invent phone, hours, or URLs. Leave null / unknown.
5. IDs (`nat_…`) are stable — use them as merge keys.
6. Place/Google residual waves are exhausted for actionable panels; further site discovery yield is very low.

## Suggested product uses

- Regional finder: filter `sido` + `sigungu`
- ER / night routing: secondary/primary with `hours_24h == yes` (see `secondary-24h.jsonl`)
- Deep link: `homepage` else `place_search_url` else `daum_map_url`

## Source

- Branch: `cursor/hospital-site-data-ac30`
- Full working tree (waves, ledger): `data/hospitals/`
- PR: https://github.com/ryol84/naver-chatbot/pull/4
