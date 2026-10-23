#!/usr/bin/env python3
"""link_checker.py - audits the links found in a Markdown file.

What it does
------------
Extracts every http(s) URL from the input file and probes it. GET is the
default method, because many JavaScript-rendered sites answer 404 to HEAD but
200 to GET; checking with HEAD alone produces false "dead" results.

With --method head the script runs a fast HEAD pre-check and, when the HEAD
answer is not conclusive, retries the same URL with GET before classifying it.

Classification
--------------
  DEAD         404, 410, 451
  BLOCKED      400, 401, 403, 406, 412, 429, 444   WAF, geo-restriction or login wall
  SERVER_ERROR  500-599   origin/server error; retry or inspect later
  REDIRECT     the URL redirects elsewhere; update it to the canonical form
  NO_RESPONSE  timeout, DNS failure or connection refused
  OK           other HTTP response; this does not authenticate linked content

Output
------
The normal mode DOES perform HTTP requests. If no output file is given, nothing
is written to disk. Use --limit to bound how many URLs are probed.

Usage
-----
    python3 scripts/link_checker.py
    python3 scripts/link_checker.py README.md
    python3 scripts/link_checker.py README.md audit/links-status-2026-09-25.csv --all
    python3 scripts/link_checker.py README.md out.csv --workers 30
    python3 scripts/link_checker.py README.md --method head --limit 50
    python3 scripts/link_checker.py README.md --dry-run

Example output
--------------
    $ python3 scripts/link_checker.py README.md audit/links-status.csv --all
    Link checker -> README.md  (1027 unique URLs)
    OK            703
    REDIRECT      140
    BLOCKED       150
    NO_RESPONSE    33
    DEAD            1
    CSV written: audit/links-status.csv  (1027 rows)
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor

import requests


URL_RE = re.compile(r'https?://[^\s\)\]\>"\',`]+')
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
DEAD = {404, 410, 451}
BLOCKED = {400, 401, 403, 406, 412, 429, 444}
HEAD_RETRY = BLOCKED | DEAD | {405} | set(range(500, 600))
FIELDS = ["url", "status", "http", "final_url", "source_line", "note"]
ORDER = ("OK", "REDIRECT", "BLOCKED", "SERVER_ERROR", "NO_RESPONSE", "DEAD")
TIMEOUT = 15

def extract_urls(path):
    """Return {url: first line number where it appears}."""
    found = {}
    with open(path, encoding="utf-8", errors="ignore") as fh:
        for lineno, line in enumerate(fh, 1):
            for match in URL_RE.findall(line):
                found.setdefault(match.rstrip(".,;:"), lineno)
    return found

def classify(url, method="get"):
    """Probe one URL and return [url, status, http, final_url, note]."""
    code = ""
    final = url
    attempts = ("get",) if method == "get" else (method, "get")
    for attempt in attempts:
        try:
            resp = requests.request(
                attempt, url, headers=HEADERS, timeout=TIMEOUT,
                allow_redirects=True, stream=True,
            )
            code, final = resp.status_code, resp.url
            resp.close()
        except requests.exceptions.SSLError:
            if attempt == "head":
                continue
            return [url, "NO_RESPONSE", "", "", "TLS error"]
        except Exception as exc:  # timeout, DNS failure, connection refused
            if attempt == "head":
                continue
            return [url, "NO_RESPONSE", "", "", type(exc).__name__]
        if attempt == "head" and code in HEAD_RETRY:
            continue
        break

    if isinstance(code, int) and code in DEAD:
        return [url, "DEAD", code, final, "link is down: replace or remove"]
    if isinstance(code, int) and code in BLOCKED:
        return [url, "BLOCKED", code, final, "WAF, geo-restriction or login wall: check in a browser"]
    if isinstance(code, int) and 500 <= code <= 599:
        return [url, "SERVER_ERROR", code, final, "server returned 5xx: retry later; do not mark as verified"]
    if final.rstrip("/") != url.rstrip("/"):
        return [url, "REDIRECT", code, final, "update to the canonical URL"]
    return [url, "OK", code, final, ""]

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Audit the links found in a Markdown file.",
        epilog="The normal mode performs HTTP requests; use --limit to bound them.",
    )
    parser.add_argument("input", nargs="?", default="README.md",
                        help="Markdown file to read (default: README.md)")
    parser.add_argument("output", nargs="?",
                        help="CSV output path; if omitted nothing is written to disk")
    parser.add_argument("--method", choices=["get", "head"], default="get",
                        help="primary HTTP method (default: get, as configured in lychee.toml)")
    parser.add_argument("--workers", type=int, default=40,
                        help="number of concurrent workers (default: 40)")
    parser.add_argument("--limit", type=int, default=0,
                        help="probe only the first N URLs (default: all)")
    parser.add_argument("--dry-run", action="store_true",
                        help="list the URLs that would be probed and exit without any HTTP request")
    parser.add_argument("--all", action="store_true",
                        help="include OK rows in the CSV as well; without it the CSV holds non-OK rows only")
    parser.add_argument("--debug", action="store_true",
                        help="print one line per URL with its status, HTTP code and URL")
    args = parser.parse_args(argv)

    if not os.path.isfile(args.input):
        print(f"error: input file not found: {args.input}", file=sys.stderr)
        return 2
    if args.workers < 1:
        parser.error("--workers must be at least 1")
    if args.limit < 0:
        parser.error("--limit cannot be negative")

    urls = extract_urls(args.input)
    if not urls:
        print(f"error: no URLs found in {args.input}", file=sys.stderr)
        return 2
    targets = list(urls)
    if args.limit:
        targets = targets[: args.limit]

    if args.dry_run:
        for url in targets:
            print(url)
        print(f"{len(targets)} URLs would be probed (dry-run: no HTTP requests made)")
        return 0

    print(f"Link checker -> {args.input}  ({len(urls)} unique URLs)")
    rows = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for row in pool.map(lambda u: classify(u, args.method), targets):
            rows.append(row)
    for row in rows:
        row.insert(4, urls.get(row[0], ""))

    counts = {}
    for row in rows:
        counts[row[1]] = counts.get(row[1], 0) + 1
    for status in ORDER:
        print(f"{status:<13}{counts.get(status, 0):>5}")

    if args.debug:
        for row in rows:
            print(f"  {row[1]:<12}{str(row[2]):<6}{row[0]}")

    if not args.output:
        print("no output path given: nothing written to disk")
        return 0

    directory = os.path.dirname(args.output)
    if directory:
        os.makedirs(directory, exist_ok=True)
    export = [r for r in rows if args.all or r[1] != "OK"]
    with open(args.output, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(FIELDS)
        writer.writerows(export)
    print(f"CSV written: {args.output}  ({len(export)} rows)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
