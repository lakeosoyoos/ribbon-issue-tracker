#!/bin/zsh
# Double-click launcher for the Ribbon Issue Tracker
cd "$(dirname "$0")"
exec streamlit run ribbon_tracker_app.py --server.port 8512
