# Ribbon Issue Tracker

Reads EXFO-style **reburn / splice report** workbooks and tracks **which ribbons
(tube positions) are most likely to have issues** across many reports.

## What it does
- Opens each workbook and **finds the detailed `Splice Report` ribbon × splice
  grid** even when the file has several sheets (Acquisition Parameters, Reburn
  Summary, Legend, Distributed Loss, …).
- Extracts **every flagged cell**, classifying it by the Legend type using the
  cell text token (`BEND`, `bidi`, `broke`, `ref`, `BAD_TAILBOX`, `(A)`, `(B)`)
  and fill color (pink = A+B reburn, yellow = bend, orange = launch, theme
  tints = single-direction A-only / B-fill, …).
- Rolls events up **across all loaded reports by ribbon number / tube code**, so
  a position flagged on multiple routes (a likely systematic cause) rises to the
  top of the ranking.

## Run
```
streamlit run ribbon_tracker_app.py --server.port 8512
```
or double-click `run.command`. Three ways to load reports (mix freely):

1. **Drop files** — select several `.xlsx` reports at once in the uploader.
2. **Upload a `.zip`** — a zip of a folder of reports; nested subfolders are
   searched and macOS junk (`__MACOSX`, `.DS_Store`, `~$` lock files) is skipped.
3. **Browse a folder on this Mac** — click **📂 Browse…** to open the native
   macOS folder chooser (works because this runs as a local desktop app), or
   paste a folder path. Every `.xlsx` under it (and subfolders) is loaded.

Note: a true in-browser "pick a folder" dialog isn't possible in Streamlit — the
Browse button is the local-desktop equivalent, and the `.zip` upload is the
portable equivalent.

## Output
- **Ribbon ranking** — repeat offenders first, with per-category breakdown.
- **Charts** — events per ribbon, ribbon × category heatmap, issue mix.
- **All events** — every flagged cell, filterable by route / category.
- **Auto-saved report** — each time a new set of reports is analyzed, a
  timestamped `Ribbon Issue Tracker YYYY-MM-DD_HH-MM-SS.xlsx` is written to
  `~/Desktop/Ribbon Tracker Reports/` (change the folder, or turn auto-save off,
  in the sidebar). Written once per distinct analysis, not on every click.
- **Download** — the same timestamped workbook on demand, with Ranking +
  All Events + Reports Loaded sheets.

## Files
- `ribbon_parser.py` — parsing + classification engine (no Streamlit; scriptable
  and unit-testable: `python3 ribbon_parser.py report1.xlsx report2.xlsx`).
- `ribbon_tracker_app.py` — Streamlit front-end.

Port **8512** (Secret Sauce 8501, SpliceReport 8503, Uni 8505, OTDR Suite 8510
are taken).
