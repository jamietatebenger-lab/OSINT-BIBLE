#!/usr/bin/env python3
"""validate_data.py - schema and content checks for the data layer.

Validates
---------
1. data/tools.json against data/tools.schema.json (manual enum / pattern check;
   jsonschema is preferred in CI but is not always available locally).
2. data/sources.yml against schema/sources.schema.json (manual YAML parse;
   the same caveat applies).
3. Unique ids and urls within each dataset.
4. No HTTP (HTTPS-only).
5. Every country in countries.json with exists=true has a file on disk.

Usage
-----
    python3 scripts/validate_data.py
    python3 scripts/validate_data.py --check-links --limit 30
    python3 scripts/validate_data.py --json report.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit, parse_qsl, urlencode, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "data" / "tools.json"
TOOLS_SCHEMA = ROOT / "data" / "tools.schema.json"
SOURCES = ROOT / "data" / "sources.yml"
SOURCES_SCHEMA = ROOT / "schema" / "sources.schema.json"
COUNTRIES = ROOT / "data" / "countries.json"
COUNTRIES_DIR = ROOT / "countries"

TRACKING = {"utm_source", "utm_medium", "utm_campaign", "utm_term",
            "utm_content", "fbclid", "gclid", "ref", "mc_cid", "mc_eid"}
DEFAULT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


# ---------- YAML loader for sources.yml ----------

# Imported lazily so validate_data.py can be invoked even if the helper module
# is moved; the parser handles exactly the structure used by this repo.
def _load_sources(path: Path) -> list[dict]:
    import importlib.util
    helper = Path(__file__).parent / "_yaml.py"
    spec = importlib.util.spec_from_file_location("_yaml", helper)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.load_sources_yml(path)


def normalise(url: str) -> str:
    p = urlsplit(url)
    q = [(k, v) for k, v in parse_qsl(p.query) if k.lower() not in TRACKING]
    path = p.path.rstrip("/") or "/"
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), path, urlencode(q), ""))


# ---------- Validators ----------

def _validate_tools() -> list[str]:
    errors: list[str] = []
    if not TOOLS.exists():
        return [f"{TOOLS}: not found"]
    if not TOOLS_SCHEMA.exists():
        return [f"{TOOLS_SCHEMA}: not found"]
    schema = json.loads(TOOLS_SCHEMA.read_text(encoding="utf-8"))
    doc = json.loads(TOOLS.read_text(encoding="utf-8"))
    item_schema = schema["properties"]["tools"]["items"]
    allowed = set(item_schema["properties"].keys())
    required = set(item_schema["required"])
    enum_cats = set(item_schema["properties"]["category"]["enum"])
    enum_types = set(item_schema["properties"]["type"]["enum"])
    enum_lics = set(item_schema["properties"]["license"]["enum"])
    enum_cost = set(item_schema["properties"]["cost"]["enum"])
    enum_status = set(item_schema["properties"]["status"]["enum"])
    id_re = re.compile(item_schema["properties"]["id"]["pattern"])
    url_re = re.compile(item_schema["properties"]["url"]["pattern"])
    tag_re = re.compile(item_schema["properties"]["tags"]["items"]["pattern"])

    seen_ids, seen_urls = set(), set()
    for i, t in enumerate(doc.get("tools", [])):
        tid = t.get("id", f"#{i}")
        for r in required:
            if r not in t:
                errors.append(f"tools[{tid}]: missing required field {r!r}")
        for k in t:
            if k not in allowed:
                errors.append(f"tools[{tid}]: extra property {k!r}")
        if t.get("id") in seen_ids:
            errors.append(f"tools[{tid}]: duplicate id")
        seen_ids.add(t.get("id"))
        if t.get("url"):
            if t["url"] in seen_urls:
                errors.append(f"tools[{tid}]: duplicate url")
            seen_urls.add(t["url"])
            if not url_re.match(t["url"]):
                errors.append(f"tools[{tid}]: url not HTTPS: {t['url']}")
        if not id_re.match(t.get("id", "")):
            errors.append(f"tools[{tid}]: id pattern mismatch")
        for field, allowed_enum in (("category", enum_cats), ("type", enum_types),
                                    ("license", enum_lics), ("cost", enum_cost),
                                    ("status", enum_status)):
            v = t.get(field)
            if v is not None and v not in allowed_enum:
                errors.append(f"tools[{tid}]: {field}={v!r} not in enum")
        purpose = t.get("purpose", "")
        if len(purpose) < 8:
            errors.append(f"tools[{tid}]: purpose too short")
        for tag in t.get("tags", []):
            if not tag_re.match(tag):
                errors.append(f"tools[{tid}]: tag {tag!r} bad pattern")
    return errors


def _validate_sources() -> list[str]:
    errors: list[str] = []
    if not SOURCES.exists():
        return [f"{SOURCES}: not found"]
    if not SOURCES_SCHEMA.exists():
        return [f"{SOURCES_SCHEMA}: not found"]
    schema = json.loads(SOURCES_SCHEMA.read_text(encoding="utf-8"))
    src_def = schema["$defs"]["source"]
    required = set(src_def["required"])
    enum_cats = set(src_def["properties"]["category"]["enum"])
    enum_status = set(src_def["properties"]["status"]["enum"])
    id_re = re.compile(src_def["properties"]["id"]["pattern"])
    url_re = re.compile(src_def["properties"]["url"]["pattern"])

    doc = _load_sources(SOURCES)
    sources = doc
    seen_ids, seen_urls = set(), set()
    for s in sources:
        sid = s.get("id", "?")
        for r in required:
            if r not in s:
                errors.append(f"sources[{sid}]: missing required field {r!r}")
        if s.get("id") in seen_ids:
            errors.append(f"sources[{sid}]: duplicate id")
        seen_ids.add(s.get("id"))
        url = s.get("url", "")
        if url in seen_urls:
            errors.append(f"sources[{sid}]: duplicate url")
        seen_urls.add(url)
        if not url_re.match(url):
            errors.append(f"sources[{sid}]: url not HTTPS: {url}")
        if not id_re.match(s.get("id", "")):
            errors.append(f"sources[{sid}]: id pattern mismatch")
        for field, allowed in (("category", enum_cats), ("status", enum_status)):
            v = s.get(field)
            if v is not None and v not in allowed:
                errors.append(f"sources[{sid}]: {field}={v!r} not in enum")
        if len(s.get("purpose", "")) < 8:
            errors.append(f"sources[{sid}]: purpose too short")
    return errors


def _validate_countries() -> list[str]:
    errors: list[str] = []
    if not COUNTRIES.exists():
        return [f"{COUNTRIES}: not found"]
    doc = json.loads(COUNTRIES.read_text(encoding="utf-8"))
    allowed_status = {"ok", "blocked", "redirect", "dead", "unverified"}
    for c in doc.get("countries", []):
        if c.get("exists") and not (COUNTRIES_DIR / c["file"]).exists():
            errors.append(f"countries[{c['code']}]: missing file {c['file']}")
        for grp, items in c.get("sources", {}).items():
            for it in items:
                if it.get("status") not in allowed_status:
                    errors.append(f"countries[{c['code']}].{grp}: bad status {it.get('status')!r}")
    return errors


def _check_links(urls: list[str], workers: int) -> list[dict]:
    import requests
    headers = {"User-Agent": DEFAULT_UA, "Accept": "*/*"}
    DEAD, BLOCKED = {404, 410, 451}, {400, 401, 403, 406, 412, 429, 444}

    def probe(u: str) -> dict:
        try:
            r = requests.get(u, headers=headers, timeout=15,
                             allow_redirects=True, stream=True)
            code = r.status_code
            final = r.url
            r.close()
            status = ("DEAD" if code in DEAD else
                      "BLOCKED" if code in BLOCKED else
                      "SERVER_ERROR" if isinstance(code, int) and 500 <= code <= 599 else
                      "REDIRECT" if final.rstrip("/") != u.rstrip("/") else "OK")
            return {"url": u, "status": status, "http": code, "final": final}
        except Exception as exc:  # noqa: BLE001
            return {"url": u, "status": "NO_RESPONSE", "http": 0, "note": str(exc)[:120]}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(probe, urls))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check-links", action="store_true",
                    help="probe a sample of URLs from the data layer")
    ap.add_argument("--limit", type=int, default=20,
                    help="max URLs to probe when --check-links is set")
    ap.add_argument("--workers", type=int, default=20)
    ap.add_argument("--json", dest="json_out", default=None)
    args = ap.parse_args()

    errors = []
    errors += _validate_tools()
    errors += _validate_sources()
    errors += _validate_countries()

    for e in errors:
        print(f"  ERROR {e}")
    report: dict = {"errors": errors}
    if errors:
        print(f"\nFAILED: {len(errors)} error(s)")
        if args.json_out:
            Path(args.json_out).write_text(json.dumps(report, indent=2), encoding="utf-8")
        return 1

    print("OK: data layer is schema-valid")

    if args.check_links:
        # Collect URLs from tools + sources
        urls: list[str] = []
        for t in json.loads(TOOLS.read_text(encoding="utf-8"))["tools"]:
            urls.append(t["url"])
        if SOURCES.exists():
            doc = _load_sources(SOURCES)
            for s in doc:
                urls.append(s["url"])
        if args.limit:
            urls = urls[: args.limit]
        results = _check_links(urls, args.workers)
        counts = Counter(r["status"] for r in results)
        report["links"] = results
        print("\nLink status: " + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))
        for r in results:
            if r["status"] in {"DEAD", "NO_RESPONSE", "SERVER_ERROR"}:
                print(f"  {r['status']:<12} {r['url']}")
        if counts.get("DEAD"):
            print("\nFAILED: dead links present")
            if args.json_out:
                Path(args.json_out).write_text(json.dumps(report, indent=2), encoding="utf-8")
            return 1

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
