# scripts

Command-line utilities for working with the collection in this repository.
The HTTP-enabled utilities use `requests`; `build_readme.py` also requires `PyYAML`.

## Installation

```bash
python3 -m pip install requests
python3 -m pip install pyyaml  # only needed by build_readme.py
```

## Scripts

| Name | Purpose | Input | Output |
|---|---|---|---|
| `osint_bible.py` | Search, validate, inspect and export the tool and country registries; optionally check tool links | Subcommand and options | Results on stdout; CSV/JSON export optional |
| `validate_data.py` | Validate the tools, sources and country data; optionally probe a sample of links | Options | Validation summary; JSON report optional |
| `build_readme.py` | Regenerate registry-driven README tables or check for drift | `data/sources.yml` | Writes `README.md` unless `--check` |
| `link_checker.py` | Audits links in a Markdown file and classifies them as `OK`, `REDIRECT`, `BLOCKED`, `SERVER_ERROR`, `NO_RESPONSE` or `DEAD` | Markdown file | Summary on stdout; CSV optional |
| `dork_builder.py` | Builds passive-reconnaissance search queries for one or more domains | One or more domains | Query text on stdout or to a file |
| `username_check.py` | Checks whether a username route responds on supported platforms | One or more usernames | Table on stdout; CSV optional |

## Usage

```bash
python3 scripts/osint_bible.py stats
python3 scripts/osint_bible.py check --limit 20
python3 scripts/validate_data.py
python3 scripts/link_checker.py README.md audit/links-status.csv --all
python3 scripts/build_readme.py --check
python3 scripts/dork_builder.py --domain example.com --output all
python3 scripts/username_check.py torvalds --platforms github,keybase
```

## Important notes on behaviour

- `osint_bible.py check`, `validate_data.py --check-links`, `link_checker.py` and `username_check.py` **perform HTTP requests** in normal mode. Use `--limit` to bound URL probes.
- `osint_bible.py check` distinguishes confirmed dead links from blocked, server-error and no-response results; `--strict` fails only when dead links are confirmed.
- Pass `--dry-run` to the link checker or username checker to list targets without making requests. `dork_builder.py` never makes requests; it only renders text.
- If no output path is given, `link_checker.py` writes nothing to disk; it only prints the summary.
- By default, the link-checker CSV contains only non-`OK` rows. Pass `--all` to include every unique URL, as used by the reports in `audit/`.
- `BLOCKED` results (`400`, `401`, `403`, `406`, `412`, `429`, `444`) usually indicate a WAF, geo-restriction or login wall. They are not automatically dead links and should be confirmed in a browser.
- `SERVER_ERROR` means an HTTP 5xx response. It is not a working source and is not proof that the document was removed; retry or inspect the official portal.
- `NO_RESPONSE` means the request could not be completed. Retry before changing or removing a link.
- HTTP `OK` confirms transport only. It does **not** authenticate a document, its signatures, or the accuracy of its content.
- `username_check.py` reports `UNKNOWN` when a platform blocks automated access. `FOUND` only means that the profile route responded; it does not confirm account ownership.
- Use these utilities only for lawful, authorized and ethical research.
