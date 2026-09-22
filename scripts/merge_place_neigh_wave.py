#!/usr/bin/env python3
"""Merge a Place neighborhood wave jsonl into companion hospitals.

Usage:
  python3 scripts/merge_place_neigh_wave.py \\
    --wave place-neigh-gyeongbuk-wave1 \\
    --jsonl data/hospitals/place-neigh-gyeongbuk-wave1.jsonl \\
    --meta-key gyeongbuk_neigh_wave1 \\
    --source-branch cursor/place-neigh-gyeongbuk-ac30 \\
    --ledger-action merge_place_neigh_gyeongbuk_wave1
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOSP = ROOT / "data" / "hospitals"
COMPANION = HOSP / "companion-hospitals.jsonl"
COMPANION_CSV = HOSP / "companion-hospitals.csv"
META = HOSP / "companion-meta.json"
LEDGER = HOSP / "companion-accumulation-ledger.json"
README = HOSP / "README.md"

REJECT_HP = re.compile(
    r"(instagram\.com|facebook\.com|youtube\.com|saramin\.|"
    r"mypet-119|animal\.go\.kr|carmap\.|jobkorea|wanted\.co)",
    re.I,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def has_hours(r: dict) -> bool:
    h = r.get("hours")
    if isinstance(h, dict):
        return bool(h.get("raw") or h.get("by_day"))
    return bool(h)


def homepage_ok(url: str | None) -> bool:
    if not url or not str(url).strip():
        return False
    return not REJECT_HP.search(url)


def merge_depts(existing: list | None, keywords: list | None) -> tuple[list, bool]:
    base = list(existing or [])
    changed = False
    for k in keywords or []:
        k = (k or "").strip()
        if not k:
            continue
        if k not in base:
            base.append(k)
            changed = True
    return base, changed


def recompute_stats(rows: list[dict]) -> dict:
    return {
        "with_homepage": sum(1 for r in rows if (r.get("homepage") or "").strip()),
        "with_hours": sum(1 for r in rows if has_hours(r)),
        "with_phone": sum(1 for r in rows if (r.get("phone") or "").strip()),
        "hours_24h_yes": sum(1 for r in rows if r.get("hours_24h") == "yes"),
    }


def write_csv(rows_by_id: dict[str, dict], remove_ids: set[str]) -> None:
    """Patch existing CSV (CRLF) to avoid wholesale rewrites."""
    import io

    raw = COMPANION_CSV.read_bytes()
    nl = "\r\n" if b"\r\n" in raw[:800] else "\n"
    text = raw.decode()
    rdr = csv.DictReader(io.StringIO(text))
    fields = list(rdr.fieldnames or [])
    out: list[dict] = []
    for row in rdr:
        hid = row.get("id")
        if not hid or hid in remove_ids:
            continue
        j = rows_by_id.get(hid)
        if not j:
            continue
        phone = j.get("phone") or ""
        if phone and (row.get("phone") or "") != phone:
            row["phone"] = phone
        hp = j.get("homepage") or ""
        if hp and (row.get("homepage") or "") != hp:
            row["homepage"] = hp
            row["has_homepage"] = "True"
        deps = j.get("departments")
        if isinstance(deps, list):
            row["departments"] = "|".join(deps)
        if j.get("place_search_url"):
            row["place_search_url"] = j["place_search_url"]
        out.append(row)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore", lineterminator=nl)
    w.writeheader()
    w.writerows(out)
    COMPANION_CSV.write_bytes(buf.getvalue().encode())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl", required=True, type=Path)
    ap.add_argument("--meta-key", required=True)
    ap.add_argument("--source-branch", required=True)
    ap.add_argument("--ledger-action", required=True)
    ap.add_argument("--readme-line", default="")
    args = ap.parse_args()

    place_rows = load_jsonl(args.jsonl)
    companion = load_jsonl(COMPANION)
    by_id = {r["id"]: r for r in companion}
    ts = now_iso()

    stats = {
        "hit_applied": 0,
        "homepage_set": 0,
        "phone_set": 0,
        "hours_set": 0,
        "dept_merged": 0,
        "no_hit": 0,
        "ambiguous_skip": 0,
        "exclude_closed": 0,
        "exclude_large_animal": 0,
        "missing_id": 0,
    }
    excluded: list[dict] = []
    remove_ids: set[str] = set()

    status_counts = {"hit": 0, "no_hit": 0, "ambiguous": 0, "CLOSED_EXCLUDE": 0, "LARGE_ANIMAL_ONLY_EXCLUDE": 0}

    for p in place_rows:
        status = (p.get("place_status") or "").strip()
        status_counts[status] = status_counts.get(status, 0) + 1
        hid = p.get("id")
        if not hid:
            stats["missing_id"] += 1
            continue

        if status in ("CLOSED_EXCLUDE", "CLOSED"):
            stats["exclude_closed"] += 1
            if hid in by_id:
                remove_ids.add(hid)
                excluded.append(
                    {
                        "id": hid,
                        "name": p.get("name") or by_id[hid].get("name"),
                        "reason": f"CLOSED: {(p.get('place_notes') or '')[:180]}",
                        "excluded_at": ts,
                    }
                )
            continue

        if status in ("LARGE_ANIMAL_ONLY_EXCLUDE", "LARGE_ANIMAL"):
            stats["exclude_large_animal"] += 1
            if hid in by_id:
                remove_ids.add(hid)
                excluded.append(
                    {
                        "id": hid,
                        "name": p.get("name") or by_id[hid].get("name"),
                        "reason": f"LARGE_ANIMAL: {(p.get('place_notes') or '')[:180]}",
                        "excluded_at": ts,
                    }
                )
            continue

        if status == "no_hit":
            stats["no_hit"] += 1
            continue
        if status == "ambiguous":
            stats["ambiguous_skip"] += 1
            continue
        if status != "hit":
            continue

        row = by_id.get(hid)
        if not row:
            stats["missing_id"] += 1
            continue

        stats["hit_applied"] += 1
        hp = p.get("place_homepage")
        if homepage_ok(hp) and not (row.get("homepage") or "").strip():
            row["homepage"] = hp
            row["has_homepage"] = True
            row["info_source_priority"] = "homepage"
            stats["homepage_set"] += 1

        phone = (p.get("place_phone") or "").strip()
        if phone and not (row.get("phone") or "").strip():
            row["phone"] = phone
            stats["phone_set"] += 1

        hours_raw = p.get("place_hours_raw")
        if hours_raw and isinstance(row.get("hours"), dict) and not row["hours"].get("raw"):
            row["hours"]["raw"] = hours_raw
            if row["hours"].get("hours_24h") == "unknown":
                # keep unknown unless literal 24h in raw
                if re.search(r"24\s*시간|00:00\s*[-–~]\s*24:00|00:00\s*[-–~]\s*00:00", str(hours_raw)):
                    row["hours"]["hours_24h"] = "yes"
                    row["hours"]["is_24h_daily"] = True
                    row["hours_24h"] = "yes"
            stats["hours_set"] += 1

        depts, changed = merge_depts(row.get("departments"), p.get("place_dept_keywords"))
        if changed:
            row["departments"] = depts
            src = row.get("departments_source") or "care_level_default"
            if "place" not in src:
                row["departments_source"] = f"{src}+place" if src else "place"
            stats["dept_merged"] += 1

        if p.get("place_search_url"):
            row["place_search_url"] = p["place_search_url"]
        row["place_enriched_at"] = ts
        if p.get("place_notes"):
            row["place_enrichment_notes"] = p["place_notes"][:300]
        if row.get("info_source_priority") == "place_or_daum_needed":
            row["info_source_priority"] = "place_verified"

    new_rows = [r for r in companion if r["id"] not in remove_ids]
    write_jsonl(COMPANION, new_rows)
    write_csv({r["id"]: r for r in new_rows}, remove_ids)

    # copy jsonl into data/hospitals if not already there
    dest = HOSP / args.jsonl.name
    if args.jsonl.resolve() != dest.resolve():
        dest.write_text(args.jsonl.read_text())

    meta = json.loads(META.read_text())
    meta["n"] = len(new_rows)
    meta["excluded_n"] = int(meta.get("excluded_n") or 0) + len(excluded)
    names = meta.setdefault("excluded_names", [])
    for e in excluded:
        if e["name"] not in names:
            names.append(e["name"])
    stats_block = recompute_stats(new_rows)
    meta["stats"] = stats_block
    meta["with_homepage"] = stats_block["with_homepage"]
    pe = meta.setdefault("place_enrichment", {})
    pe.setdefault("post_filter_exclusions", []).extend(excluded)
    pe[args.meta_key] = {
        "n": len(place_rows),
        "hit": status_counts.get("hit", 0),
        "no_hit": status_counts.get("no_hit", 0),
        "ambiguous": status_counts.get("ambiguous", 0),
        "closed_exclude": stats["exclude_closed"],
        "large_animal_exclude": stats["exclude_large_animal"],
        "homepages_reported": sum(1 for p in place_rows if homepage_ok(p.get("place_homepage"))),
        "hours_reported": sum(1 for p in place_rows if p.get("place_hours_raw")),
        "merged_at": ts,
        "source_branch": args.source_branch,
        "merge_stats": stats,
    }
    from collections import Counter

    meta["care_level_counts"] = dict(Counter(r.get("care_level") for r in new_rows))
    META.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")

    ledger = json.loads(LEDGER.read_text())
    ledger.setdefault("entries", []).append(
        {
            "ts": ts,
            "action": args.ledger_action,
            "stats": stats,
            "excluded": [{"id": e["id"], "name": e["name"], "reason": e["reason"][:120]} for e in excluded],
            "source_branch": args.source_branch,
        }
    )
    ledger["as_of"] = ts[:10]
    LEDGER.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n")

    if args.readme_line:
        text = README.read_text()
        # bump companion count line
        text = re.sub(r"## companion \d+곳", f"## companion {len(new_rows)}곳", text)
        text = re.sub(r"- 홈페이지 보유: \d+곳", f"- 홈페이지 보유: {stats_block['with_homepage']}곳", text)
        marker = "### Place waves (merged)\n"
        if marker in text and args.readme_line not in text:
            text = text.replace(marker, marker + args.readme_line.rstrip() + "\n")
        # care level table
        counts = meta["care_level_counts"]
        text = re.sub(r"\| 대학 \| \d+ \|", f"| 대학 | {counts.get('university', 0)} |", text)
        text = re.sub(r"\| 2차 \| \d+ \|", f"| 2차 | {counts.get('secondary', 0)} |", text)
        text = re.sub(r"\| 1차 \| \d+ \|", f"| 1차 | {counts.get('primary', 0)} |", text)
        text = re.sub(r"\| 일반 동네 \| \d+ \|", f"| 일반 동네 | {counts.get('neighborhood', 0)} |", text)
        text = re.sub(r"\| 재활·한방 \| \d+ \|", f"| 재활·한방 | {counts.get('rehab_specialty', 0)} |", text)
        README.write_text(text)

    print(json.dumps({"n": len(new_rows), "stats": stats, "meta_stats": stats_block, "excluded": len(excluded)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
