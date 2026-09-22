#!/usr/bin/env python3
"""Build companion hospital agent-pack for download / other agents."""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOSP = ROOT / "data" / "hospitals"
PACK = HOSP / "agent-pack"
ART = Path("/opt/cursor/artifacts")
AS_OF = "2026-09-20"
VERSION = "2026-09-20.1"

CORE_FIELDS = [
    "id",
    "name",
    "care_level",
    "care_level_ko",
    "role",
    "role_label",
    "sido",
    "sigungu",
    "address",
    "lat",
    "lng",
    "phone",
    "homepage",
    "has_homepage",
    "hours_24h",
    "hours",
    "weekday_hours",
    "weekend_hours",
    "departments",
    "departments_source",
    "species_scope",
    "place_search_url",
    "daum_map_url",
    "info_source_priority",
]

REJECT_HP = ("instagram.com", "facebook.com", "youtube.com", "pf.kakao.com")

SCHEMA = {
    "title": "Korea companion (dog/cat) veterinary hospitals",
    "version": VERSION,
    "as_of": AS_OF,
    "species_scope": ["dog", "cat"],
    "primary_files": {
        "companion-hospitals.jsonl": "Canonical records, one JSON object per line (UTF-8).",
        "companion-hospitals.csv": "Flat export; departments joined with |.",
        "companion-meta.json": "Counts, care_level taxonomy, enrichment summary.",
        "schema.json": "Field dictionary + rules.",
        "AGENT.md": "How another agent should load and use the pack.",
        "samples.json": "One sample row per care_level.",
        "secondary-24h.jsonl": "secondary + hours_24h=yes subset.",
    },
    "care_level": {
        "university": "대학동물병원 (VMTH)",
        "secondary": "2차 의료센터 / AMC",
        "primary": "1차 종합·특화 진료",
        "neighborhood": "일반 동네병원",
        "rehab_specialty": "재활·한방 특화",
    },
    "hours_24h_enum": ["yes", "no", "unknown"],
    "hours_24h_rule": (
        "Set yes only when Place/source literally says 24시간 or 00:00–24:00. "
        "Do not infer from name alone."
    ),
    "homepage_rules": [
        "Prefer hospital-owned .kr/.com or blog.naver.com/{hospital}",
        "Reject: Instagram, Facebook, YouTube, Kakao channel, job boards, aggregators",
        "If homepage_unreliable is true, treat as no official site",
    ],
    "id_format": "nat_<12 hex> — stable nationwide id",
    "fields": {
        "id": {"type": "string", "required": True},
        "name": {"type": "string", "required": True},
        "care_level": {
            "type": "enum",
            "values": [
                "university",
                "secondary",
                "primary",
                "neighborhood",
                "rehab_specialty",
            ],
        },
        "care_level_ko": {"type": "string"},
        "sido": {"type": "string"},
        "sigungu": {"type": "string"},
        "address": {"type": "string"},
        "lat": {"type": "number|null"},
        "lng": {"type": "number|null"},
        "phone": {"type": "string|null"},
        "homepage": {"type": "string|null"},
        "has_homepage": {"type": "boolean"},
        "hours_24h": {"type": "enum", "values": ["yes", "no", "unknown"]},
        "hours": {
            "type": "object",
            "props": {
                "raw": "string|null",
                "by_day": "object mon..sun or daily",
                "hours_24h": "yes|no|unknown",
                "is_24h_daily": "boolean",
                "breaks": "array of {start,end,raw}",
            },
        },
        "departments": {"type": "string[]"},
        "species_scope": {"type": "string[]", "typical": ["dog", "cat"]},
        "place_search_url": {"type": "string"},
        "daum_map_url": {"type": "string"},
        "info_source_priority": {"type": "string"},
    },
    "branch": "cursor/hospital-site-data-ac30",
    "repo_path": "data/hospitals/agent-pack/",
}


def slim(r: dict) -> dict:
    out = {k: r[k] for k in CORE_FIELDS if k in r}
    hp = (out.get("homepage") or "").strip()
    if hp and any(x in hp.lower() for x in REJECT_HP):
        out["homepage_unreliable"] = True
        out["homepage_note"] = "SNS/channel URL — do not treat as official site"
        out["has_homepage"] = False
    else:
        out["has_homepage"] = bool(hp)
    return out


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()


def main() -> None:
    if PACK.exists():
        shutil.rmtree(PACK)
    PACK.mkdir(parents=True)
    ART.mkdir(parents=True, exist_ok=True)

    rows = [
        json.loads(l)
        for l in (HOSP / "companion-hospitals.jsonl").read_text().splitlines()
        if l.strip()
    ]
    slim_rows = [slim(r) for r in rows]

    jsonl_path = PACK / "companion-hospitals.jsonl"
    with jsonl_path.open("w") as f:
        for r in slim_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    csv_fields = [
        "id",
        "name",
        "care_level",
        "care_level_ko",
        "sido",
        "sigungu",
        "address",
        "lat",
        "lng",
        "phone",
        "homepage",
        "has_homepage",
        "hours_24h",
        "weekday_hours",
        "weekend_hours",
        "departments",
        "place_search_url",
        "daum_map_url",
        "info_source_priority",
    ]
    csv_path = PACK / "companion-hospitals.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=csv_fields, extrasaction="ignore")
        w.writeheader()
        for r in slim_rows:
            row = {k: r.get(k) for k in csv_fields}
            deps = r.get("departments")
            if isinstance(deps, list):
                row["departments"] = "|".join(deps)
            w.writerow(row)

    meta_src = json.loads((HOSP / "companion-meta.json").read_text())
    counts = dict(Counter(r.get("care_level") for r in slim_rows))
    stats = {
        "n": len(slim_rows),
        "with_homepage_reliable": sum(1 for r in slim_rows if r.get("has_homepage")),
        "with_homepage_any_url": sum(1 for r in slim_rows if (r.get("homepage") or "").strip()),
        "with_phone": sum(1 for r in slim_rows if (r.get("phone") or "").strip()),
        "with_hours_raw": sum(
            1
            for r in slim_rows
            if isinstance(r.get("hours"), dict) and r["hours"].get("raw")
        ),
        "hours_24h_yes": sum(1 for r in slim_rows if r.get("hours_24h") == "yes"),
        "care_level_counts": counts,
        "sido_top": dict(Counter(r.get("sido") for r in slim_rows).most_common(10)),
    }
    meta = {
        "title": "Companion dog/cat hospitals — agent pack",
        "version": VERSION,
        "as_of": AS_OF,
        "source_branch": "cursor/hospital-site-data-ac30",
        "n": len(slim_rows),
        "stats": stats,
        "care_level_taxonomy": meta_src.get("care_level_taxonomy") or SCHEMA["care_level"],
        "enrichment_summary": {
            "place_waves": "exhausted actionable Place enrichment for companion set",
            "google_waves": meta_src.get("google_enrichment", {}),
            "note": "Google rarely finds official sites beyond Place; residuals mostly directory-only",
        },
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    (PACK / "companion-meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
    (PACK / "schema.json").write_text(json.dumps(SCHEMA, ensure_ascii=False, indent=2) + "\n")

    samples = {}
    for cl in ["university", "secondary", "primary", "neighborhood", "rehab_specialty"]:
        samples[cl] = next(r for r in slim_rows if r.get("care_level") == cl)
    (PACK / "samples.json").write_text(json.dumps(samples, ensure_ascii=False, indent=2) + "\n")

    er = [
        r
        for r in slim_rows
        if r.get("care_level") == "secondary" and r.get("hours_24h") == "yes"
    ]
    (PACK / "secondary-24h.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in er)
    )

    agent_md = "\n".join(
        [
            "# Companion hospital agent pack",
            "",
            f"**Version:** `{VERSION}` · **as_of:** `{AS_OF}` · **n:** {len(slim_rows)} dog/cat hospitals (Korea)",
            "",
            "Handoff surface for other agents. Prefer this pack over raw Place/Google wave jsonl.",
            "",
            "## Quick start",
            "",
            "```bash",
            "pack=data/hospitals/agent-pack",
            "python3 - <<'PY'",
            "import json",
            "from pathlib import Path",
            "rows=[json.loads(l) for l in Path('data/hospitals/agent-pack/companion-hospitals.jsonl').read_text().splitlines() if l.strip()]",
            "print(len(rows), rows[0]['name'], rows[0]['care_level'])",
            "PY",
            "```",
            "",
            f"Or unzip `companion-hospitals-agent-pack-{VERSION}.zip` and read `AGENT.md` + `companion-hospitals.jsonl`.",
            "",
            "## Files",
            "",
            "| File | Use |",
            "|------|-----|",
            "| `companion-hospitals.jsonl` | Canonical DB (one hospital / line) |",
            "| `companion-hospitals.csv` | Flat table; departments is pipe-joined |",
            "| `companion-meta.json` | Counts + enrichment summary |",
            "| `schema.json` | Field dictionary + rules |",
            "| `samples.json` | One example per care_level |",
            f"| `secondary-24h.jsonl` | 2차 + hours_24h=yes subset ({len(er)} rows) |",
            "| `MANIFEST.json` | Checksums + paths |",
            "",
            "## Care levels",
            "",
            "| care_level | KO | count |",
            "|------------|----|------:|",
            f"| university | 대학 | {counts.get('university', 0)} |",
            f"| secondary | 2차 | {counts.get('secondary', 0)} |",
            f"| primary | 1차 | {counts.get('primary', 0)} |",
            f"| neighborhood | 동네 | {counts.get('neighborhood', 0)} |",
            f"| rehab_specialty | 재활·한방 | {counts.get('rehab_specialty', 0)} |",
            "",
            "## Coverage",
            "",
            f"- reliable homepage: **{stats['with_homepage_reliable']}**",
            f"- phone: **{stats['with_phone']}**",
            f"- hours_24h=yes: **{stats['hours_24h_yes']}**",
            f"- hours.raw present: **{stats['with_hours_raw']}**",
            "",
            "## Rules other agents MUST follow",
            "",
            "1. Species: dog/cat companion only (`species_scope`).",
            "2. `hours_24h=yes` only when source literally says 24시간 / 00:00–24:00. Never infer from name token alone.",
            "3. If `homepage_unreliable` is true (SNS), treat as no official site; use `place_search_url` / `daum_map_url`.",
            "4. Do not invent phone, hours, or URLs. Leave null / unknown.",
            "5. IDs (`nat_…`) are stable — use them as merge keys.",
            "6. Place/Google residual waves are exhausted for actionable panels; further site discovery yield is very low.",
            "",
            "## Suggested product uses",
            "",
            "- Regional finder: filter `sido` + `sigungu`",
            "- ER / night routing: secondary/primary with `hours_24h == yes` (see `secondary-24h.jsonl`)",
            "- Deep link: `homepage` else `place_search_url` else `daum_map_url`",
            "",
            "## Source",
            "",
            "- Branch: `cursor/hospital-site-data-ac30`",
            "- Full working tree (waves, ledger): `data/hospitals/`",
            "- PR: https://github.com/ryol84/naver-chatbot/pull/4",
            "",
        ]
    )
    (PACK / "AGENT.md").write_text(agent_md)

    files = sorted(p for p in PACK.iterdir() if p.is_file() and p.name != "MANIFEST.json")
    manifest = {
        "version": VERSION,
        "as_of": AS_OF,
        "n": len(slim_rows),
        "built_at": meta["built_at"],
        "files": {p.name: {"bytes": p.stat().st_size, "sha256": sha256(p)} for p in files},
    }
    (PACK / "MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")

    zip_name = f"companion-hospitals-agent-pack-{VERSION}.zip"
    zip_pack = PACK / zip_name
    zip_art = ART / zip_name
    for zpath in (zip_pack, zip_art):
        with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for p in sorted(PACK.iterdir()):
                if p.is_file() and p.suffix != ".zip":
                    z.write(p, arcname=f"companion-hospitals-agent-pack/{p.name}")

    shutil.copy2(jsonl_path, ART / "companion-hospitals.jsonl")
    shutil.copy2(csv_path, ART / "companion-hospitals.csv")
    shutil.copy2(PACK / "AGENT.md", ART / "companion-hospitals-AGENT.md")
    shutil.copy2(PACK / "companion-meta.json", ART / "companion-hospitals-meta.json")
    shutil.copy2(PACK / "schema.json", ART / "companion-hospitals-schema.json")
    shutil.copy2(PACK / "secondary-24h.jsonl", ART / "companion-secondary-24h.jsonl")

    # Pointer in hospitals README
    readme = HOSP / "README.md"
    block = (
        "\n## Agent pack (download / handoff)\n"
        f"- Folder: `data/hospitals/agent-pack/` — see `AGENT.md`\n"
        f"- Zip: `data/hospitals/agent-pack/{zip_name}`\n"
        f"- Version `{VERSION}` · n={len(slim_rows)} · reliable homepage {stats['with_homepage_reliable']}\n"
    )
    text = readme.read_text()
    if "## Agent pack (download / handoff)" not in text:
        readme.write_text(text.rstrip() + "\n" + block)

    print(
        json.dumps(
            {
                "pack": str(PACK),
                "zip_art": str(zip_art),
                "zip_bytes": zip_art.stat().st_size,
                "n": len(slim_rows),
                "stats": stats,
                "files": [p.name for p in sorted(PACK.iterdir())],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
