"""
Ribbon Issue Tracker  (Streamlit)
=================================
Drop in one or many EXFO-style reburn / splice report workbooks.  The app finds
the detailed ribbon x splice grid in each (handling multi-sheet workbooks),
extracts every flagged event, and rolls them up ACROSS all loaded reports to
answer: which ribbons / tube positions are more likely to have issues?

Run:  streamlit run ribbon_tracker_app.py --server.port 8512
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

# ─────────────────────────────────────────────────────────────────────────────
#  Engine import — auto-update aware (mirrors SpliceReport desktop_app.py)
# ─────────────────────────────────────────────────────────────────────────────
# The launcher sets RT_ENGINE_DIR when it has downloaded + validated a fresh
# engine into ~/.ribbonTracker/engine. If set, prepend it so `import
# ribbon_parser` resolves to the freshly-downloaded copy; otherwise fall back
# to the bundled copy next to the frozen exe (or alongside this file in dev).
_ENGINE_DIR = os.environ.get("RT_ENGINE_DIR")
if _ENGINE_DIR and os.path.isdir(_ENGINE_DIR):
    sys.path.insert(0, _ENGINE_DIR)
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
for _p in (_HERE, _REPO_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from ribbon_parser import CATEGORIES, parse_report  # noqa: E402

try:  # error reporting is best-effort; never let its absence break the app
    from error_reporter import report_error
except Exception:  # noqa: BLE001
    def report_error(exc, where="", context=None):  # type: ignore
        return None

st.set_page_config(page_title="Ribbon Issue Tracker", page_icon="🎗️", layout="wide")

# Categories considered "needs-action" for the headline ribbon ranking.
ACTION_CATS = {"reburn_ab", "break", "ref", "launch", "bend", "gainer"}


# --------------------------------------------------------------------------- #
# Input helpers
# --------------------------------------------------------------------------- #
_REPORT_EXTS = (".xlsx", ".xlsm")


def _is_report_member(name: str) -> bool:
    """A real report workbook inside a zip / folder (skip Excel lock files &
    macOS junk). Extension match is case-insensitive so FOO.XLSX loads too."""
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    return (
        name.lower().endswith(_REPORT_EXTS)
        and not base.startswith("~$")
        and "__MACOSX" not in name
        and not base.startswith(".")
    )


def _xlsx_from_zip(zip_bytes: bytes) -> list[tuple[str, bytes]]:
    """Extract every report .xlsx from a zip (recurses into nested folders)."""
    out = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for info in zf.infolist():
            if info.is_dir() or not _is_report_member(info.filename):
                continue
            out.append((info.filename.rsplit("/", 1)[-1], zf.read(info)))
    return out


def pick_folder_native() -> str:
    """Open the native macOS / OS folder chooser (works because this is a
    LOCAL desktop app). Runs tkinter in a short-lived subprocess so it never
    fights Streamlit's own event loop. Returns '' if cancelled/unavailable."""
    code = (
        "import tkinter as tk;"
        "from tkinter import filedialog;"
        "r=tk.Tk();r.withdraw();r.attributes('-topmost',True);"
        "print(filedialog.askdirectory());r.destroy()"
    )
    try:
        res = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, timeout=120,
        )
        return res.stdout.strip()
    except Exception:
        return ""


# --------------------------------------------------------------------------- #
# Parsing (cached on file bytes so re-runs are instant)
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner=False)
def _parse_bytes(name: str, data: bytes) -> dict:
    # Write to a temp DIR then load — not a NamedTemporaryFile reopened by
    # name, which raises PermissionError on Windows (the file is still open
    # and Windows won't let openpyxl reopen a locked handle).
    #
    # The on-disk temp name is a FIXED, OS-safe constant ("report.xlsx") so we
    # can ingest a report no matter what characters its real filename contains
    # (unicode, spaces, colons from zip entries, reserved Windows names, etc.).
    # The real name is passed to parse_report as report_name purely for display.
    import shutil
    tmpdir = tempfile.mkdtemp(prefix="ribbon_")
    try:
        fpath = os.path.join(tmpdir, "report.xlsx")
        with open(fpath, "wb") as fh:
            fh.write(data)
        rp = parse_report(fpath, report_name=Path(str(name)).stem)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return {
        "report": rp.report,
        "route": rp.route,
        "grid_sheet": rp.grid_sheet,
        "sheets": rp.sheets,
        "n_ribbons": rp.n_ribbons,
        "n_splice_cols": rp.n_splice_cols,
        "warnings": rp.warnings,
        "summary_stats": rp.summary_stats,
        "events": [e.as_row() for e in rp.events],
    }


def events_dataframe(parsed: list[dict]) -> pd.DataFrame:
    rows = []
    for p in parsed:
        for e in p["events"]:
            rows.append(e)
    if not rows:
        return pd.DataFrame(
            columns=["report", "route", "ribbon_num", "tube", "fiber_range",
                     "splice", "category", "category_label", "text"]
        )
    df = pd.DataFrame(rows)
    df["ribbon_num"] = df["ribbon_num"].astype("Int64")
    return df


# --------------------------------------------------------------------------- #
# Cross-report ribbon roll-up
# --------------------------------------------------------------------------- #
def ribbon_rollup(df: pd.DataFrame, n_reports: int) -> pd.DataFrame:
    """One row per ribbon number, aggregated across every loaded report."""
    if df.empty:
        return df

    # representative tube per ribbon (mode)
    tube_map = (
        df.dropna(subset=["tube"])
        .groupby("ribbon_num")["tube"]
        .agg(lambda s: s.value_counts().index[0])
    )

    g = df.groupby("ribbon_num")
    out = pd.DataFrame({
        "ribbon": g.size().index,
        "tube": [tube_map.get(rb, "") for rb in g.size().index],
        "total_events": g.size().values,
        "reports_flagged": g["report"].nunique().values,
        "action_events": g.apply(
            lambda x: int(x["category"].isin(ACTION_CATS).sum()), include_groups=False
        ).values,
    })
    out["pct_of_reports"] = (out["reports_flagged"] / max(n_reports, 1) * 100).round(1)

    # per-category counts
    cat_pivot = (
        df.pivot_table(index="ribbon_num", columns="category",
                       values="text", aggfunc="count", fill_value=0)
    )
    for cat in CATEGORIES:
        if cat in cat_pivot.columns:
            out[cat] = out["ribbon"].map(cat_pivot[cat]).fillna(0).astype(int)

    out = out.rename(columns={"ribbon": "ribbon_num"})
    out = out.sort_values(
        ["reports_flagged", "action_events", "total_events"],
        ascending=False
    ).reset_index(drop=True)
    out.insert(0, "rank", range(1, len(out) + 1))
    return out


# --------------------------------------------------------------------------- #
# Excel export
# --------------------------------------------------------------------------- #
def build_export(df_events, df_rollup, df_reports) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xl:
        df_rollup.to_excel(xl, sheet_name="Ribbon Ranking", index=False)
        df_events.to_excel(xl, sheet_name="All Events", index=False)
        df_reports.to_excel(xl, sheet_name="Reports Loaded", index=False)
    return buf.getvalue()


def _stamp() -> str:
    """Filename-safe local timestamp — no colons (illegal on Windows)."""
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def _report_filename() -> str:
    return f"Ribbon Issue Tracker {_stamp()}.xlsx"


def _default_out_dir() -> Path:
    """Where auto-saved reports land by default: ~/Desktop/Ribbon Tracker Reports
    (falls back to the home dir if there's no Desktop)."""
    desktop = Path.home() / "Desktop"
    base = desktop if desktop.is_dir() else Path.home()
    return base / "Ribbon Tracker Reports"


def _unique_path(target: Path) -> Path:
    """Avoid clobbering if two analyses land in the same second."""
    if not target.exists():
        return target
    stem, suffix = target.stem, target.suffix
    i = 2
    while True:
        cand = target.with_name(f"{stem} ({i}){suffix}")
        if not cand.exists():
            return cand
        i += 1


# --------------------------------------------------------------------------- #
# UI
# --------------------------------------------------------------------------- #
st.title("🎗️ Ribbon Issue Tracker")
st.caption(
    "Load one or more reburn / splice reports. The app finds each report's "
    "ribbon × splice grid and ranks which ribbons (tube positions) are most "
    "often flagged across all loaded reports."
)

if "folder_path" not in st.session_state:
    st.session_state.folder_path = ""

with st.sidebar:
    st.header("Reports")
    _src = os.environ.get("RT_ENGINE_SOURCE")
    if _src:
        st.caption(f"Engine: {_src}")
    uploads = st.file_uploader(
        "Drop report files — .xlsx and/or a .zip of reports",
        type=["xlsx", "zip"], accept_multiple_files=True,
        help="Select several .xlsx files at once, or a single .zip containing "
             "a folder of reports (nested folders are searched too).",
    )

    st.markdown("**…or load a folder on this Mac**")
    bcol, _ = st.columns([1, 1])
    if bcol.button("📂 Browse…", use_container_width=True):
        chosen_dir = pick_folder_native()
        if chosen_dir:
            st.session_state.folder_path = chosen_dir
    folder = st.text_input(
        "Folder path", key="folder_path",
        placeholder="/Users/you/Desktop/Reports",
        help="Every .xlsx in this folder (and its subfolders) is loaded. "
             "The Browse button fills this in for you.",
    )

    st.divider()
    cat_labels = {k: v for k, v in CATEGORIES.items()}
    chosen = st.multiselect(
        "Issue categories to include",
        options=list(CATEGORIES.keys()),
        default=list(CATEGORIES.keys()),
        format_func=lambda k: cat_labels[k],
    )

    st.divider()
    st.markdown("**Report output**")
    autosave = st.checkbox(
        "Auto-save a timestamped Excel report", value=True,
        help="Writes a dated .xlsx to the folder below each time a new set of "
             "reports is analyzed.",
    )
    out_dir = st.text_input(
        "Save reports to", value=str(_default_out_dir()),
        help="Folder where auto-saved reports are written (created if missing).",
    )

# ---- gather inputs ----
inputs: list[tuple[str, bytes]] = []
_seen_hashes: set[str] = set()
_used_names: dict[str, int] = {}

def _add(name: str, data: bytes):
    import hashlib
    # Exact-duplicate guard: the SAME file loaded twice (e.g. uploaded and also
    # in the scanned folder) is counted once, by content — not by name.
    h = hashlib.md5(data).hexdigest()
    if h in _seen_hashes:
        return
    _seen_hashes.add(h)
    # Distinct files that happen to share a filename both load — disambiguate
    # the display name so the cross-report count stays correct.
    orig = str(name)
    n = _used_names.get(orig, 0) + 1
    _used_names[orig] = n
    if n == 1:
        label = orig
    else:
        stem, ext = os.path.splitext(orig)
        label = f"{stem} ({n}){ext}"
    inputs.append((label, data))

for uf in uploads or []:
    if uf.name.lower().endswith(".zip"):
        members = _xlsx_from_zip(uf.getvalue())
        if not members:
            st.sidebar.warning(f"No report files (.xlsx/.xlsm) found inside {uf.name}")
        for mname, mdata in members:
            _add(mname, mdata)
    elif uf.name.lower().endswith(_REPORT_EXTS):
        _add(uf.name, uf.getvalue())
    else:
        st.sidebar.warning(f"Skipped {uf.name} — not a report (.xlsx/.xlsm/.zip).")

if folder.strip():
    fp = Path(folder.strip()).expanduser()
    if fp.is_dir():
        hits = sorted(x for x in fp.rglob("*")
                      if x.is_file() and _is_report_member(x.name))
        for x in hits:
            try:
                _add(x.name, x.read_bytes())
            except Exception as exc:  # noqa: BLE001
                st.sidebar.warning(f"Could not read {x.name}: {exc}")
        st.sidebar.caption(f"📁 {len(hits)} report(s) found in {fp.name}/")
    else:
        st.sidebar.error(f"Not a folder: {fp}")

if not inputs:
    st.info("⬅️  Add at least one report to begin.")
    st.stop()

# ---- parse ----
parsed = []
for name, data in inputs:
    try:
        parsed.append(_parse_bytes(name, data))
    except Exception as exc:  # noqa: BLE001
        st.error(f"Failed to read **{name}**: {exc}")
        report_error(exc, where="parse_report",
                     context={"n_bytes": len(data),
                              "ext": Path(name).suffix.lower()})

if not parsed:
    st.stop()

n_reports = len(parsed)
df_events_all = events_dataframe(parsed)
df_events = df_events_all[df_events_all["category"].isin(chosen)].copy()

# ---- reports-loaded table ----
df_reports = pd.DataFrame([{
    "report": p["report"],
    "route": p["route"],
    "grid_sheet": p["grid_sheet"],
    "ribbons": p["n_ribbons"],
    "splice_cols": p["n_splice_cols"],
    "events": len(p["events"]),
    "sheets": ", ".join(p["sheets"]),
    "warnings": "; ".join(p["warnings"]),
} for p in parsed])

# ---- headline metrics ----
c1, c2, c3, c4 = st.columns(4)
c1.metric("Reports loaded", n_reports)
c2.metric("Total flagged events", len(df_events))
ribbons_with_issue = df_events["ribbon_num"].nunique()
c3.metric("Ribbons with ≥1 issue", int(ribbons_with_issue))
action_n = int(df_events["category"].isin(ACTION_CATS).sum())
c4.metric("Action events", action_n, help="Reburn, break, ref, launch, bend, gainer")

for p in parsed:
    for w in p["warnings"]:
        st.warning(f"**{p['report']}**: {w}")

df_rollup = ribbon_rollup(df_events, n_reports)


def _emit_report():
    """Build the workbook, auto-save a timestamped copy (once per distinct
    analysis), and offer the download. Runs in BOTH the has-events and the
    clean-route (no events) paths so a report is always produced."""
    st.divider()
    xlsx = build_export(
        df_events[["report", "route", "ribbon_num", "tube", "fiber_range",
                   "splice", "category_label", "text"]],
        df_rollup, df_reports,
    )

    def _analysis_signature() -> str:
        import hashlib
        key = "|".join(sorted(p["report"] for p in parsed))
        key += f"::events={len(df_events)}::cats={','.join(sorted(chosen))}"
        return hashlib.md5(key.encode()).hexdigest()

    if autosave:
        sig = _analysis_signature()
        if st.session_state.get("_last_saved_sig") != sig:
            try:
                target_dir = Path(out_dir.strip() or str(_default_out_dir())).expanduser()
                target_dir.mkdir(parents=True, exist_ok=True)
                saved_path = _unique_path(target_dir / _report_filename())
                saved_path.write_bytes(xlsx)
                st.session_state["_last_saved_sig"] = sig
                st.session_state["_last_saved_path"] = str(saved_path)
            except Exception as exc:  # noqa: BLE001
                st.warning(f"Could not auto-save the report: {exc}")
                report_error(exc, where="auto_save_report",
                             context={"out_dir": out_dir})
        if st.session_state.get("_last_saved_path"):
            st.success(f"📄 Report saved: `{st.session_state['_last_saved_path']}`")

    st.download_button(
        "⬇️  Download cross-report tracker (.xlsx)",
        data=xlsx,
        file_name=_report_filename(),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


if df_events.empty:
    st.info("No flagged events in the selected categories — the report below "
            "records the reports reviewed with a clean result.")
    st.dataframe(df_reports, width="stretch", hide_index=True)
    _emit_report()
    st.stop()

tab_rank, tab_charts, tab_events, tab_reports = st.tabs(
    ["🏆 Ribbon ranking", "📊 Charts", "🔬 All events", "📁 Reports"]
)

# ---- ranking tab ----
with tab_rank:
    st.subheader("Which ribbons are most often flagged?")
    st.caption(
        "Ranked by number of reports the ribbon was flagged in, then action "
        "events, then total events. Tube code (A1, K1…) is the physical "
        "position — repeat offenders across routes point to a systematic cause."
    )
    repeat = df_rollup[df_rollup["reports_flagged"] > 1]
    if not repeat.empty:
        tubes = ", ".join(
            f"Ribbon {int(r.ribbon_num)} ({r.tube})" for r in repeat.itertuples()
        )
        st.info(f"🔁 **Repeat offenders** (flagged in >1 report): {tubes}")

    show_cats = [c for c in CATEGORIES if c in df_rollup.columns]
    nice = {
        "rank": "Rank", "ribbon_num": "Ribbon", "tube": "Tube",
        "reports_flagged": "Reports", "pct_of_reports": "% reports",
        "total_events": "Events", "action_events": "Action",
        **{c: CATEGORIES[c] for c in show_cats},
    }
    cols = ["rank", "ribbon_num", "tube", "reports_flagged", "pct_of_reports",
            "total_events", "action_events"] + show_cats
    st.dataframe(
        df_rollup[cols].rename(columns=nice),
        width="stretch", hide_index=True,
        column_config={
            "% reports": st.column_config.NumberColumn(format="%.1f%%"),
        },
    )

# ---- charts tab ----
with tab_charts:
    left, right = st.columns(2)
    with left:
        st.markdown("**Events per ribbon**")
        bar = (
            alt.Chart(df_rollup)
            .mark_bar()
            .encode(
                x=alt.X("total_events:Q", title="Flagged events"),
                y=alt.Y("ribbon_num:N", sort="-x", title="Ribbon"),
                color=alt.Color("reports_flagged:Q", title="Reports",
                                scale=alt.Scale(scheme="reds")),
                tooltip=["ribbon_num", "tube", "total_events",
                         "reports_flagged", "action_events"],
            )
            .properties(height=max(300, 18 * len(df_rollup)))
        )
        st.altair_chart(bar, use_container_width=True)
    with right:
        st.markdown("**Ribbon × issue category (heatmap)**")
        long = df_events.groupby(["ribbon_num", "category_label"]).size().reset_index(name="n")
        heat = (
            alt.Chart(long)
            .mark_rect()
            .encode(
                x=alt.X("category_label:N", title="", axis=alt.Axis(labelAngle=-40)),
                y=alt.Y("ribbon_num:N", title="Ribbon"),
                color=alt.Color("n:Q", title="Events", scale=alt.Scale(scheme="oranges")),
                tooltip=["ribbon_num", "category_label", "n"],
            )
            .properties(height=max(300, 18 * df_events["ribbon_num"].nunique()))
        )
        st.altair_chart(heat, use_container_width=True)

    st.markdown("**Issue mix across all reports**")
    mix = df_events.groupby("category_label").size().reset_index(name="n").sort_values("n")
    st.altair_chart(
        alt.Chart(mix).mark_bar().encode(
            x=alt.X("n:Q", title="Events"),
            y=alt.Y("category_label:N", sort="-x", title=""),
            tooltip=["category_label", "n"],
        ).properties(height=240),
        use_container_width=True,
    )

# ---- events tab ----
with tab_events:
    st.subheader("Every flagged event")
    fc1, fc2 = st.columns(2)
    routes = ["(all)"] + sorted(df_events["route"].unique().tolist())
    pick_route = fc1.selectbox("Route", routes)
    pick_cat = fc2.multiselect(
        "Category", [CATEGORIES[c] for c in CATEGORIES if c in df_events["category"].unique()]
    )
    view = df_events
    if pick_route != "(all)":
        view = view[view["route"] == pick_route]
    if pick_cat:
        view = view[view["category_label"].isin(pick_cat)]
    st.dataframe(
        view[["report", "route", "ribbon_num", "tube", "fiber_range",
              "splice", "category_label", "text"]]
        .rename(columns={"ribbon_num": "ribbon", "category_label": "category"}),
        width="stretch", hide_index=True,
    )

# ---- reports tab ----
with tab_reports:
    st.subheader("Reports loaded")
    st.dataframe(df_reports, width="stretch", hide_index=True)
    for p in parsed:
        if p["summary_stats"]:
            with st.expander(f"Report's embedded Reburn Summary — {p['report']}"):
                st.caption(
                    "This is the summary block stored inside the report by the "
                    "generator. It may predate manual edits a tech made to the "
                    "grid afterward — the tool's own counts above come from the "
                    "live grid, not this block.")
                st.json(p["summary_stats"])

# ---- export ----
_emit_report()
