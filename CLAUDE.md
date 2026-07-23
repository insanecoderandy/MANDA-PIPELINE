# SEC M&A Transaction Monitor — Project Rules

This is an internship project that monitors SEC EDGAR daily for M&A-related filings
(tender offers, mergers), extracts deal details, and displays them in a Streamlit dashboard.

## Workflow rules (non-negotiable)

- The project has 3 phases, each ending in a checkpoint that a supervisor reviews.
  NEVER start work on the next phase until I explicitly say the checkpoint was approved.
  If I ask for something in a later phase prematurely, remind me of the checkpoint.
- Phase 1: fetcher.py (query EDGAR full-text search, filter, dedupe, store raw JSON)
- Phase 2: scanner.py (fetch filing documents, extract structured deal fields) — SC TO-T and S-4 only
- Phase 3: pipeline.py + dashboard.py (CSV/JSON output + Streamlit dashboard)
- Stretch (8-K scanning) only after all 3 phases are approved.
- After writing or changing code, run it and show me the real output. Don't declare
  success from reading the code alone.

## SEC API rules (breaking these gets us blocked or produces silently wrong data)

- EVERY request to any SEC host must send the header:
  User-Agent: "<MY NAME> <MY EMAIL>"   (ask me for the real values once, then reuse)
- Rate limit: max 10 requests/second combined across www.sec.gov and efts.sec.gov.
  Use time.sleep(0.15) or more between requests. Stay well under the cap.
- Full-text search endpoint (note UPPERCASE /LATEST/, lowercase 404s):
  https://efts.sec.gov/LATEST/search-index?q=&forms=...&startdt=YYYY-MM-DD&enddt=YYYY-MM-DD
- Submissions endpoint requires CIK zero-padded to 10 digits:
  https://data.sec.gov/submissions/CIK0000320017.json  (unpadded returns nothing)
- The Archives path accepts unpadded CIKs:
  https://www.sec.gov/Archives/edgar/data/{cik}/{accession-no-dashes}/
- CIKs are STRINGS with leading zeros. Never cast a CIK to int; the padding matters.
- Search results are paginated at 100 per response. Compare hits.total.value to
  received count; page with the `from` parameter until all results are fetched.

## Data-correctness rules (the "code runs fine, output is garbage" traps)

1. AMENDMENTS: querying forms=SC+TO-T also returns SC TO-T/A amendments (same for
   S-4/A). An original filing and its amendments share a file number (file_num).
   Group by file_num so one deal = one record. Keep pre- and post-dedup counts —
   the checkpoint requires both.
2. ACQUIRER vs TARGET: the search response's ciks/display_names arrays contain both
   parties but do NOT say which is which. NEVER infer roles from array order — it's
   an undocumented coincidence. The filing index page labels them explicitly:
   "(Subject)" = target, "(Filed by)" = acquirer. Parse those labels. This is the
   project's #1 known silent-failure risk.
3. General principle from my supervisor: always prefer a source that states a fact
   explicitly over one where the fact is inferred from position or convention.
4. Take file_date, form, adsh (accession number), and file_num from search metadata.
   Take acquirer/target roles from the index page labels. Use document text ONLY for
   what metadata doesn't carry: price, consideration, deal description.

## Parsing rules (Phase 2)

- Filings are HTML; parse with BeautifulSoup, extract text via soup.get_text().
- str.find() first-match is usually cover-page boilerplate, not the real disclosure.
  "per share" appears in legalese long before the actual offer price.
- S-4s open with a table of contents, so early matches for "the merger" are TOC
  entries. Filter candidates: require matches to be substantive prose (e.g., >40
  words following the match), collect several matches and choose, don't take the first.
- Before writing extraction logic for a form type, dump soup.get_text() of one real
  filing to a file so we can read it and see the actual structure.

## Stack

Python. Dependencies: requests, pandas, streamlit, beautifulsoup4, python-dateutil.
File layout: fetcher.py, scanner.py, pipeline.py, dashboard.py, data/, requirements.txt.
Store raw fetched JSON under data/raw/ named by date so we never re-fetch a day we
already have.
