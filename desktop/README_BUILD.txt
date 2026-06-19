RIBBON TRACKER — DESKTOP BUILD NOTES
====================================

WHAT GETS BUILT
  * Windows: dist\RibbonTracker\RibbonTracker.exe (one-folder), zipped as
    RibbonTracker-Windows.zip. Built by CI (.github/workflows/build-windows.yml)
    on windows-latest, gated by a BOOT SELF-TEST. Techs download the zip from
    the permanent GitHub Release tag `windows-build`.
  * macOS: dist/RibbonTracker.app, also copied to ~/Desktop/RibbonTracker.app.
    Built locally with ./build-mac.sh.

PORT
  8512. Each desktop app must own its port so the launchers don't see each
  other's /_stcore/health and open the wrong app. Registry: Secret Sauce 8501,
  SpliceReport 8503, Uni 8505, OTDR Suite 8510, Ribbon Tracker 8512.

TOOLCHAIN PINS (do not drift)
  * Python 3.11 for Windows (NOT 3.12 — it removed pkgutil.ImpImporter which
    setuptools 65.5.1 needs at boot; a 3.12 build crashes at launch).
  * macOS build uses /usr/bin/python3 (3.9.x) — any < 3.12 is fine.
  * setuptools==65.5.1, re-pinned LAST so transitive bumps don't win.
  * jaraco.* / more_itertools / packaging / platformdirs / appdirs /
    ordered_set installed as real top-level packages AND collect_all'd in the
    spec, so pkg_resources' extern importer has a runtime fallback.

AUTO-UPDATE
  On launch the launcher tries to fetch ribbon_parser.py / error_reporter.py /
  ribbon_tracker_app.py from raw.githubusercontent.com/<owner>/ribbon-issue-
  tracker/main, validates them all-or-nothing (non-empty + 'def ' + compile()),
  and runs the fresh copies. On ANY failure it falls back to the copies bundled
  in the build. So a code-only fix ships by pushing to main — no rebuild — but
  only while the repo's raw files are publicly reachable. A change to
  launcher.py / the spec / Python version / bundled deps needs a fresh build.

ERROR REPORTING
  error_reporter.report_error posts scrubbed (no trace data) tech-side errors
  to Slack via RT_ERROR_WEBHOOK. CI bakes the URL into the build from the
  SLACK_ERROR_WEBHOOK repo secret (step "Bake error-report webhook") into
  desktop/_webhook.cfg, which the spec bundles only if present. No secret ->
  reporting ships OFF. NEVER commit _webhook.cfg (it's gitignored).

CI GATES
  Before the build (source-level, fail fast):
  1. tests/test_parse.py — synthetic report -> parser finds the grid sheet,
     parses ribbons/tubes, classifies a reburn + a bend.
  2. test_ui.py — PORT==8512 guard; AppTest landing page 0 exceptions; folder
     roll-up produces 2 reports + a repeat-offender callout.
  3. tests/test_audit.py — 22-check click-through + ingestion audit (weird
     filenames, junk skip, corrupt/no-grid no-crash, duplicate names,
     tabs/filters, auto-save dedup/clean/off).

  After the build (frozen-bundle, the real Windows packaging proof):
  4. FROZEN PIPELINE SELF-TEST — run the .exe with RT_SELFTEST=1; it exercises
     openpyxl read+write, the parser, pandas ExcelWriter, and altair->vega->
     jsonschema->rfc3987 chart rendering INSIDE the bundle and exits non-zero
     (with a logged traceback in ~/.ribbonTracker/selftest.log) on any missing
     bundled data file. This is what catches a Windows packaging gap that
     /_stcore/health would miss.
  5. BOOT SELF-TEST — launch the exe, poll /_stcore/health=ok within 90s, then
     scan the launcher log for tracebacks. On any failure the Release is NOT
     updated (a DOA build can't reach techs).

  To run the frozen self-test locally:  RT_SELFTEST=1 RibbonTracker(.exe)
  (or the Mac binary inside RibbonTracker.app/Contents/MacOS/).

MAC GATEKEEPER (unsigned build)
  First run on a fresh Mac: right-click RibbonTracker.app -> Open -> Open, or
  run:  xattr -dr com.apple.quarantine ~/Desktop/RibbonTracker.app
  For a no-nag experience, sign + notarize with an Apple Developer ID (TODO).

LOCAL BUILDS
  macOS:    ./build-mac.sh
  Windows:  build.bat   (on a Windows PC with Python 3.11; skips the boot test —
            push and let CI run the authoritative boot self-test before shipping)
