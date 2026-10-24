# Accommodation evidence verification — October 2026

**Status:** Open  
**Purpose:** Establish authenticity and evidence provenance for user-owned or otherwise lawfully supplied accommodation correspondence and room photographs. This checklist is designed for a **public repository**. Do not commit guest names, correspondence, booking IDs, direct identifiers, or original private evidence.

## Tasks
- [ ] Preserve original photographs and correspondence screenshots offline with acquisition timestamps and lawful-custodian documentation.
- [ ] Calculate SHA-256 hashes locally; maintain a restricted evidence manifest, not a public dump.
- [ ] Distinguish screenshots of enquiries, confirmed reservations, cancellation events, invoices and actual check-in; do not conflate these.
- [ ] Inspect original photo metadata (EXIF/XMP if present); separate claimed date, filesystem timestamp and camera capture time.
- [ ] Compare supplied room photos with official publicly published hotel-room images; label visual matches as confirmed, probable, possible or unsupported.
- [ ] Check public property descriptions, floor plans and room configurations against the visual features actually present.
- [ ] Resolve any conflicting published address strings from official business and tourism listings.
- [ ] Where the booking holder authorises access, authenticate *their own* original confirmation message and subsequent booking-change correspondence.
- [ ] Produce a redacted evidence matrix including provenance, contradictions, confidence ratings and unresolved questions.
- [ ] Perform a privacy and evidentiary review before sharing findings externally.

## Tools

| Check | Suitable tools and sources | Use limits |
| --- | --- | --- |
| Preserve and hash files | Local `sha256sum`, `shasum -a 256` or PowerShell `Get-FileHash`; an offline evidence manifest | Keep originals and hashes in restricted storage; do not upload evidence to public hash or file-analysis services. |
| Inspect metadata | [ExifTool](https://exiftool.org/) | Work on copies; metadata can be missing, altered or misleading and is not proof of capture time. |
| Compare room images | [Google Lens](https://lens.google/) and [TinEye](https://tineye.com/) | Search publicly published reference images only. Do not upload private guest photos to third-party services without informed authorization. A visual match alone does not establish a stay. |
| Check historical property claims | [Internet Archive Wayback Machine](https://web.archive.org/) and the property's official site or relevant tourism authority | Record the exact URL and capture date; an archived page proves only what that page displayed, not that the claim was true. |
| Authenticate correspondence | The booking holder's own email or booking account, with their authorization | Preserve original messages and available headers; do not access another person's account or use credential-recovery or breach-search tools. |
| Prepare findings | An offline spreadsheet or text editor | Redact copies, remove identifying metadata and review the exported report before sharing. |

Do not use face recognition, people-search, guest-register, breach-data, or tracking tools for this task. Tool availability does not expand the lawful-custodian and privacy boundaries above.

## Boundaries
No collection of confidential guest registers, private bookings, third-party email/accounts, payment details, medical data, phone tracking or credential materials. A publicly advertised room capacity or forwarded message does not prove who attended a stay.

## Acceptance criteria
One reproducible, privacy-preserving evidence report. Every conclusion identifies its source and certainty. Missing guest identity or check-in records are explicitly recorded as **unverified**, never inferred.
