#!/usr/bin/env python3
"""osint_bible.py - CLI toolkit for the OSINT-BIBLE data layer.

Sub-commands
------------
  stats       Show counts per category, type and license from data/tools.json.
  search      Full-text search across tools (name, purpose, url, tags).
  country     List everything registered for one country code (e.g. --code EG).
  validate    Schema-check data/tools.json + verify countries.json consistency.
  dorks       Generate passive-recon dorks for a domain.
  check       Concurrent link-health check of URLs found in the dataset.
  export      Export tools to CSV / JSON / Markdown.
  countries   Report country coverage: sources vs country files.

The check and export sub-commands are offline-friendly except `check` itself,
which performs HTTP probes and needs the `requests` package.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "data" / "tools.json"
COUNTRIES = ROOT / "data" / "countries.json"

REQUIRED_TOOL_FIELDS = {"id", "name", "url", "category", "type", "license", "purpose"}
VALID_TYPES = {"web", "cli", "cli+gui", "api", "browser-ext", "dataset", "registry", "mobile"}
VALID_LICENSES = {"open-source", "free", "freemium", "commercial", "public", "unknown"}


def _load(path: Path):
    if not path.exists():
        sys.exit(f"error: {path} not found (run from the repo root)")
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def cmd_stats(_args):
    data = _load(TOOLS)
    tools = data["tools"]
    by_cat, by_type, by_lic, by_cost = Counter(), Counter(), Counter(), Counter()
    for t in tools:
        by_cat[t["category"]] += 1
        by_type[t.get("type", "?")] += 1
        by_lic[t.get("license", "?")] += 1
        by_cost[t.get("cost", "?")] += 1
    print(f"schema version : {data.get('version')}")
    print(f"last_verified  : {data.get('last_verified')}")
    print(f"total tools    : {len(tools)}")
    for title, bucket in (("by category", by_cat), ("by type", by_type),
                          ("by license", by_lic), ("by cost", by_cost)):
        print(f"\n{title}")
        for k, v in sorted(bucket.items(), key=lambda kv: -kv[1]):
            print(f"  {v:4d}  {k}")


def cmd_search(args):
    data = _load(TOOLS)
    needle = args.query.lower()
    hits = []
    for t in data["tools"]:
        hay = " ".join([
            t.get("name", ""), t.get("purpose", ""), t.get("description", ""),
            t.get("url", ""), " ".join(t.get("tags", [])),
        ]).lower()
        if needle in hay:
            hits.append(t)
    hits = hits[: args.limit]
    print(f"{len(hits)} match(es) for {args.query!r}\n")
    for t in hits:
        print(f"- {t['name']}  [{t['category']}]  ({t.get('license','?')})")
        print(f"    {t['url']}")
        if t.get("purpose"):
            print(f"    {t['purpose']}")


def cmd_country(args):
    data = _load(COUNTRIES)
    code = args.code.upper()
    entry = next((c for c in data["countries"] if c["code"] == code), None)
    if not entry:
        sys.exit(f"no country with code {code}")
    print(f"{entry['name']} ({entry['code']}) - region {entry['region']}")
    print(f"file   : countries/{entry['file']}")
    print(f"review : {entry.get('last_reviewed')}")
    for group, items in entry.get("sources", {}).items():
        print(f"\n{group}")
        for it in items:
            note = f"  [{it.get('note')}]" if it.get('note') else ""
            print(f"  - {it['name']} [{it.get('status','?')}] : {it['url']}{note}")


def cmd_validate(_args):
    errors = []
    data = _load(TOOLS)
    seen = set()
    for i, t in enumerate(data["tools"]):
        missing = REQUIRED_TOOL_FIELDS - set(t)
        if missing:
            errors.append(f"tools[{i}] ({t.get('name','?')}): missing {sorted(missing)}")
        if t.get("id") in seen:
            errors.append(f"duplicate id: {t.get('id')}")
        seen.add(t.get("id"))
        if t.get("type") not in VALID_TYPES:
            errors.append(f"{t.get('id')}: invalid type {t.get('type')!r}")
        if t.get("license") not in VALID_LICENSES:
            errors.append(f"{t.get('id')}: invalid license {t.get('license')!r}")
        if not re.match(r"^https://", t.get("url", "")):
            errors.append(f"{t.get('id')}: url must start with https://")
        if t.get("purpose") and len(t["purpose"]) < 8:
            errors.append(f"{t.get('id')}: purpose too short ({len(t['purpose'])} chars)")
    if COUNTRIES.exists():
        cdata = _load(COUNTRIES)
        allowed_status = {"ok", "blocked", "redirect", "dead", "unverified"}
        for c in cdata["countries"]:
            if c.get("exists") is False:
                continue
            if not (ROOT / "countries" / c["file"]).exists():
                errors.append(f"countries.json -> missing file {c['file']}")
            for grp, items in c.get("sources", {}).items():
                for it in items:
                    if it.get("status") not in allowed_status:
                        errors.append(f"{c['code']}.{grp}: bad status {it.get('status')!r}")
    if errors:
        print(f"FAIL - {len(errors)} problem(s)")
        for e in errors:
            print("  -", e)
        return 1
    print(f"OK - {len(data['tools'])} tools, schema valid.")
    return 0


GOOGLE = [
    'site:{d} filetype:pdf | filetype:docx | filetype:xlsx',
    'site:{d} filetype:sql | filetype:bak | filetype:env | filetype:log',
    'site:{d} inurl:admin | inurl:dashboard | inurl:portal',
    'site:{d} intitle:"index of"',
    'site:{d} inurl:api | inurl:swagger | inurl:openapi | inurl:graphql',
    'site:{d} inurl:backup | inurl:old | inurl:staging | inurl:dev',
    'site:{d} inurl:.git | inurl:.svn | inurl:.env',
]


def cmd_dorks(args):
    for d in args.domain:
        print(f"# dorks for {d}")
        for tpl in GOOGLE:
            print(tpl.format(d=d))
        print()


def cmd_check(args):
    import concurrent.futures
    import requests

    data = _load(TOOLS)
    urls = sorted({t["url"] for t in data["tools"]})
    if args.limit:
        urls = urls[: args.limit]
    ua = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/126.0 Safari/537.36"}
    dead_codes = {404, 410, 451}
    blocked_codes = {400, 401, 403, 406, 412, 429, 444}

    def probe(u):
        try:
            r = requests.get(u, headers=ua, timeout=25, allow_redirects=True,
                             stream=True)
            code, final = r.status_code, r.url
            r.close()
            status = ("DEAD" if code in dead_codes else
                      "BLOCKED" if code in blocked_codes else
                      "SERVER_ERROR" if 500 <= code <= 599 else
                      "REDIRECT" if final.rstrip("/") != u.rstrip("/") else "OK")
            return (u, status, code, final, "")
        except requests.RequestException as exc:
            return (u, "NO_RESPONSE", None, "", type(exc).__name__)

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        rows = list(ex.map(probe, urls))
    counts = Counter(row[1] for row in rows)
    print(f"checked {len(rows)} urls")
    for status in ("OK", "REDIRECT", "BLOCKED", "SERVER_ERROR",
                   "NO_RESPONSE", "DEAD"):
        print(f"{status:<13}{counts.get(status, 0):>5}")
    for url, status, code, final, note in rows:
        if status != "OK":
            suffix = f" -> {final}" if final and final != url else ""
            if note:
                suffix += f" ({note})"
            print(f"  {status:<12}{str(code or ''):<6}{url}{suffix}")
    dead = counts.get("DEAD", 0)
    return 1 if dead and args.strict else 0


def cmd_export(args):
    data = _load(TOOLS)
    rows = data["tools"]
    if args.category:
        rows = [r for r in rows if r.get("category") == args.category]
    fields = ["id", "name", "url", "category", "type", "license", "cost",
              "purpose", "verified_on", "tags", "status"]
    if args.format == "csv":
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            row = {k: r.get(k, "") for k in fields}
            row["tags"] = "|".join(r.get("tags") or [])
            w.writerow(row)
        sys.stdout.write(buf.getvalue())
    elif args.format == "json":
        print(json.dumps(rows, indent=2, ensure_ascii=False))
    else:
        for r in rows:
            print(f"| [{r['name']}]({r['url']}) | {r.get('category','')} | "
                  f"{r.get('license','')} | {r.get('purpose','')} |")


def cmd_countries(_args):
    if not COUNTRIES.exists():
        sys.exit(f"error: {COUNTRIES} not found")
    data = _load(COUNTRIES)
    files = sorted(p.stem for p in (ROOT / "countries").glob("*.md")
                   if not p.stem.startswith("_"))
    codes = [c["code"] for c in data["countries"]]
    on_disk_codes = []
    for f in files:
        # Try to map file to ISO code (best-effort, may miss)
        on_disk_codes.append(f)
    print(f"Registry: {len(codes)} countries")
    print(f"  exist=true (file required): {sum(1 for c in data['countries'] if c.get('exists'))}")
    print(f"  exist=false (planned)     : {sum(1 for c in data['countries'] if not c.get('exists'))}")
    missing = [c["code"] for c in data["countries"]
               if c.get("exists") and not (ROOT / "countries" / c["file"]).exists()]
    if missing:
        print(f"\nmissing country files for: {', '.join(missing)}")
        return 1
    print("\nOK: all 'exists' countries have files on disk")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description="OSINT-BIBLE data-layer CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("stats").set_defaults(func=cmd_stats)

    s = sub.add_parser("search")
    s.add_argument("query")
    s.add_argument("--limit", type=int, default=25)
    s.set_defaults(func=cmd_search)

    c = sub.add_parser("country")
    c.add_argument("--code", required=True)
    c.set_defaults(func=cmd_country)

    sub.add_parser("validate").set_defaults(func=cmd_validate)

    d = sub.add_parser("dorks")
    d.add_argument("-d", "--domain", action="append", required=True)
    d.set_defaults(func=cmd_dorks)

    k = sub.add_parser("check")
    k.add_argument("--limit", type=int)
    k.add_argument("--workers", type=int, default=16)
    k.add_argument("--strict", action="store_true",
                   help="exit 1 when dead links exist")
    k.set_defaults(func=cmd_check)

    e = sub.add_parser("export")
    e.add_argument("--format", choices=["csv", "json", "markdown"], default="csv")
    e.add_argument("--category")
    e.set_defaults(func=cmd_export)

    sub.add_parser("countries",
                   help="report coverage: countries.json vs countries/*.md")\
        .set_defaults(func=cmd_countries)

    args = p.parse_args(argv)
    rc = args.func(args)
    raise SystemExit(rc if isinstance(rc, int) else 0)


if __name__ == "__main__":
    main()
