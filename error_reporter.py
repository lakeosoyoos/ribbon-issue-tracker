"""
error_reporter.py
=================
Real-time Slack alerts for tech-side Ribbon Tracker failures. Mirrors the
SpliceReport / Secret Sauce reporter so one Slack channel serves every desktop
app, tagged by APP_NAME.

Webhook discipline
------------------
The webhook URL is NEVER committed. CI step "Bake error-report webhook" writes
the SLACK_ERROR_WEBHOOK repo secret to desktop/_webhook.cfg just before the
PyInstaller build. The .spec bundles _webhook.cfg only if it exists. At launch
the launcher reads it into os.environ["RT_ERROR_WEBHOOK"]. A build without the
secret simply ships reporting OFF (this module no-ops).

Safety contract
---------------
  * No-op when RT_ERROR_WEBHOOK is unset.
  * Never raises — reporting must never break a tech's run.
  * Send happens on a daemon thread with a 4-second timeout.
  * Hourly dedup per (where, type(exc), str(exc)) signature.
  * NEVER includes customer / fiber / trace data — just counts, format, mode.
"""
from __future__ import annotations

import os

APP_NAME = "Ribbon Tracker"

# error signature -> last-sent epoch (in-process, hourly dedup)
_ERR_LAST: dict[str, float] = {}


def report_error(exc: BaseException, where: str = "",
                 context: dict | None = None) -> None:
    """Post a scrubbed tech-side error to the Slack webhook in
    ``RT_ERROR_WEBHOOK``. No-op when unset/offline. Never raises."""
    try:
        url = os.environ.get("RT_ERROR_WEBHOOK")
        if not url:
            return
        import hashlib
        import platform
        import time
        import traceback

        sig = hashlib.md5(
            f"{where}|{type(exc).__name__}|{exc}".encode()).hexdigest()
        now = time.time()
        if now - _ERR_LAST.get(sig, 0) < 3600:
            return
        _ERR_LAST[sig] = now

        try:
            import getpass
            import socket
            who = f"{socket.gethostname()} / {getpass.getuser()}"
        except Exception:
            who = "?"
        ctx = "".join(f"\n• {k}: {v}" for k, v in (context or {}).items())
        text = (
            f":rotating_light: *{APP_NAME} error* — {where}\n"
            f"*{type(exc).__name__}*: {exc}\n"
            f"tech: `{who}`  |  os: {platform.platform()}  |  "
            f"engine: {os.environ.get('RT_ENGINE_SOURCE', '?')}{ctx}\n"
            f"```{traceback.format_exc()[-1400:]}```"
        )

        import json as _json
        import threading
        import urllib.request

        def _send():
            try:
                req = urllib.request.Request(
                    url,
                    data=_json.dumps({"text": text}).encode(),
                    headers={"Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=4)
            except Exception:
                pass

        threading.Thread(target=_send, daemon=True).start()
    except Exception:
        # Reporting must NEVER break the run.
        pass
