#!/usr/bin/env python3
"""Merge Google enrich wave jsonl into companion hospitals.

Applies google_homepage / google_hours_raw / google_phone when companion
fields are empty (or hours_raw is Place status fluff). Rejects aggregator
and SNS URLs. Does not set hours_24h unless literal 24h / 00:00–24:00.

Usage:
  python3 scripts/merge_google_wave.py \\
    --jsonl data/hospitals/google-secondary-nohp.jsonl \\
    --meta-key google_secondary_nohp \\
    --source-branch cursor/google-sec-prim-hrs-ac30 \\
    --ledger-action merge_google_secondary_nohp
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
from collections import Counter
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
    r"mypet-119|animal\.go\.kr|carmap\.|jobkorea|wanted\.co|"
    r"onkorea\.co|purpleo\.co|hospitalk\.|fitpet|ban-life\.|"
    r"mustarddata|peton\.me|114\.co\.kr|pf\.kakao\.com|"
    r"daangn\.com|udanax\.|seenthis\.|bizno\.net)",
    re.I,
)

PLACE_FLUFF = re.compile(
    r"^(Place:\s*)?(진료\s*중|영업\s*중|상세\s*요일|접수마감\s*안내)",
    re.I,
)

H24 = re.compile(r"24\s*시간|00:00\s*[-–~]\s*24:00|00:00\s*[-–~]\s*00:00")


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


def clean_hours(raw: str | None) -> str | None:
    if not raw:
        return None
    s = str(raw).strip()
    # drop trailing source parentheticals like "(peton/...)"
    s = re.sub(r"\s*\([^)]*(peton|업체창고|aggregator|소개\s*블로그|hospitalk|mungclub)[^)]*\)\s*$", "", s, flags=re.I)
    return s.strip() or None


def hours_is_fluff(raw: str | None) -> bool:
    if not raw:
        return True
    return bool(PLACE_FLUFF.search(str(raw).strip()))


def recompute_stats(rows: list[dict]) -> dict:
    return {
        "with_homepage": sum(1 for r in rows if (r.get("homepage") or "").strip()),
        "with_hours": sum(1 for r in rows if has_hours(r)),
        "with_phone": sum(1 for r in rows if (r.get("phone") or "").strip()),
        "hours_24h_yes": sum(1 for r in rows if r.get("hours_24h") == "yes"),
    }


def write_csv(rows_by_id: dict[str, dict]) -> None:
    raw = COMPANION_CSV.read_bytes()
    nl = "\r\n" if b"\r\n" in raw[:800] else "\n"
    text = raw.decode()
    rdr = csv.DictReader(io.StringIO(text))
    fields = list(rdr.fieldnames or [])
    out: list[dict] = []
    for row in rdr:
        hid = row.get("id")
        if not hid:
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
        h = j.get("hours")
        if isinstance(h, dict) and h.get("raw"):
            if "hours_raw" in row:
                row["hours_raw"] = h["raw"]
            if "hours_24h" in row:
                row["hours_24h"] = j.get("hours_24h") or h.get("hours_24h") or row.get("hours_24h")
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

    google_rows = load_jsonl(args.jsonl)
    companion = load_jsonl(COMPANION)
    by_id = {r["id"]: r for r in companion}
    ts = now_iso()

    stats = {
        "rows": len(google_rows),
        "homepage_set": 0,
        "hours_set": 0,
        "hours_upgraded": 0,
        "phone_set": 0,
        "skipped_no_companion": 0,
        "skipped_reject_hp": 0,
        "directory_only": 0,
        "ambiguous": 0,
        "hit": 0,
    }
    status_counts: dict[str, int] = {}

    for g in google_rows:
        status = (g.get("google_status") or "").strip()
        status_counts[status] = status_counts.get(status, 0) + 1
        if status == "directory_only":
            stats["directory_only"] += 1
        elif status == "ambiguous":
            stats["ambiguous"] += 1
        elif status == "hit":
            stats["hit"] += 1

        hid = g.get("id")
        row = by_id.get(hid) if hid else None
        if not row:
            stats["skipped_no_companion"] += 1
            continue

        hp = g.get("google_homepage")
        if homepage_ok(hp) and not (row.get("homepage") or "").strip():
            row["homepage"] = hp
            row["has_homepage"] = True
            if row.get("info_source_priority") in (None, "", "place_or_daum_needed", "place_verified"):
                row["info_source_priority"] = "homepage"
            stats["homepage_set"] += 1
        elif hp and not homepage_ok(hp):
            stats["skipped_reject_hp"] += 1

        phone = (g.get("google_phone") or "").strip()
        if phone and not (row.get("phone") or "").strip():
            row["phone"] = phone
            stats["phone_set"] += 1

        hours_raw = clean_hours(g.get("google_hours_raw"))
        notes = (g.get("google_notes") or "") + " " + str(g.get("google_hours_raw") or "")
        # reject hours clearly from peton/aggregators when not a hit with hospital blog
        aggregator_hours = bool(
            re.search(r"\(peton|업체창고|onkorea|purpleo|hospitalk", str(g.get("google_hours_raw") or ""), re.I)
        )
        if hours_raw and not aggregator_hours:
            if not isinstance(row.get("hours"), dict):
                row["hours"] = {"raw": None, "by_day": None, "hours_24h": "unknown", "is_24h_daily": False}
            existing = row["hours"].get("raw")
            if not existing:
                row["hours"]["raw"] = hours_raw
                if H24.search(hours_raw):
                    row["hours"]["hours_24h"] = "yes"
                    row["hours"]["is_24h_daily"] = True
                    row["hours_24h"] = "yes"
                stats["hours_set"] += 1
            elif hours_is_fluff(existing):
                row["hours"]["raw"] = hours_raw
                if H24.search(hours_raw):
                    row["hours"]["hours_24h"] = "yes"
                    row["hours"]["is_24h_daily"] = True
                    row["hours_24h"] = "yes"
                elif row.get("hours_24h") == "yes" and not H24.search(hours_raw):
                    # upgraded from fluff; don't invent 24h
                    pass
                stats["hours_upgraded"] += 1

        row["google_enriched_at"] = ts
        if g.get("google_search_url"):
            row["google_search_url"] = g["google_search_url"]
        if g.get("google_notes"):
            row["google_enrichment_notes"] = g["google_notes"][:300]
        if g.get("google_status"):
            row["google_status"] = g["google_status"]

    write_jsonl(COMPANION, companion)
    write_csv(by_id)

    dest = HOSP / args.jsonl.name
    if args.jsonl.resolve() != dest.resolve():
        dest.write_text(args.jsonl.read_text())

    meta = json.loads(META.read_text())
    stats_block = recompute_stats(companion)
    meta["n"] = len(companion)
    meta["stats"] = stats_block
    meta["with_homepage"] = stats_block["with_homepage"]
    ge = meta.setdefault("google_enrichment", {})
    ge[args.meta_key] = {
        "n": len(google_rows),
        "status_counts": status_counts,
        "homepages_reported": sum(1 for g in google_rows if homepage_ok(g.get("google_homepage"))),
        "hours_reported": sum(1 for g in google_rows if g.get("google_hours_raw")),
        "merged_at": ts,
        "source_branch": args.source_branch,
        "merge_stats": stats,
    }
    meta["care_level_counts"] = dict(Counter(r.get("care_level") for r in companion))
    META.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")

    ledger = json.loads(LEDGER.read_text())
    ledger.setdefault("entries", []).append(
        {
            "ts": ts,
            "action": args.ledger_action,
            "stats": stats,
            "status_counts": status_counts,
            "source_branch": args.source_branch,
        }
    )
    ledger["as_of"] = ts[:10]
    LEDGER.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n")

    if args.readme_line:
        text = README.read_text()
        text = re.sub(r"## companion \d+곳", f"## companion {len(companion)}곳", text)
        text = re.sub(r"- 홈페이지 보유: \d+곳", f"- 홈페이지 보유: {stats_block['with_homepage']}곳", text)
        marker = "### Place waves (merged)\n"
        google_marker = "### Google waves (merged)\n"
        if google_marker not in text and marker in text:
            text = text.replace(marker, google_marker + marker)
        if google_marker in text and args.readme_line not in text:
            text = text.replace(google_marker, google_marker + args.readme_line.rstrip() + "\n")
        counts = meta["care_level_counts"]
        text = re.sub(r"\| 대학 \| \d+ \|", f"| 대학 | {counts.get('university', 0)} |", text)
        text = re.sub(r"\| 2차 \| \d+ \|", f"| 2차 | {counts.get('secondary', 0)} |", text)
        text = re.sub(r"\| 1차 \| \d+ \|", f"| 1차 | {counts.get('primary', 0)} |", text)
        text = re.sub(r"\| 일반 동네 \| \d+ \|", f"| 일반 동네 | {counts.get('neighborhood', 0)} |", text)
        text = re.sub(r"\| 재활·한방 \| \d+ \|", f"| 재활·한방 | {counts.get('rehab_specialty', 0)} |", text)
        README.write_text(text)

    print(json.dumps({"n": len(companion), "stats": stats, "meta_stats": stats_block, "status_counts": status_counts}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
