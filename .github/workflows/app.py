import streamlit as st
import os
import shutil
import datetime
import requests
import pandas as pd
from pathlib import Path
import hmac
from screenshotone import Client, TakeOptions
from pyzotero import zotero
import re

# Page config
st.set_page_config(page_title="Job Posting Monitor", page_icon="🔍", layout="wide")

# Authentication (unchanged)
def check_password():
    def password_entered():
        if (
            hmac.compare_digest(st.session_state["password"], st.secrets["auth"]["password"])
            and st.session_state["username"] == st.secrets["auth"]["username"]
        ):
            st.session_state["authenticated"] = True
            del st.session_state["password"]
        else:
            st.session_state["authenticated"] = False

    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if not st.session_state["authenticated"]:
        st.title("🔒 Job Posting Monitor Login")
        st.markdown("Please log in to access your personal job monitoring dashboard.")
        with st.form("Login Form", clear_on_submit=True):
            st.text_input("Username", key="username")
            st.text_input("Password", type="password", key="password")
            st.form_submit_button("Login", type="primary", on_click=password_entered)

        if st.session_state.get("authenticated") == False:
            st.error("❌ Invalid username or password")
        return False
    else:
        return True

if not check_password():
    st.stop()

# Main App
st.title("🔍 Automated Job Posting Monitor")
st.markdown("""
Welcome, Ritika! Track job pages in Dublin with full Zotero integration for targets and archives.
""")

# Directories
BASE_DIR = Path(__file__).parent
LATEST_SNAPSHOT_DIR = BASE_DIR / 'Latest_Snapshot'
OLD_SNAPSHOT_DIR = BASE_DIR / 'Old_Snapshot'
SCREENSHOTS_DIR = BASE_DIR / 'Screenshots'
ARCHIVES_DIR = BASE_DIR / 'Archives'
INPUT_FILE = BASE_DIR / 'targets.xlsx'
OUTPUT_FILE = BASE_DIR / 'results.xlsx'

for dir_path in [LATEST_SNAPSHOT_DIR, OLD_SNAPSHOT_DIR, SCREENSHOTS_DIR, ARCHIVES_DIR]:
    dir_path.mkdir(exist_ok=True)

# Load targets
columns = ['Company Name', 'URL', 'Role', 'Zotero Key']
if INPUT_FILE.exists():
    df_targets = pd.read_excel(INPUT_FILE)
else:
    df_targets = pd.DataFrame(columns=columns)

df_targets = df_targets.astype(str).fillna("")

# Tabs
tab_overview, tab_targets, tab_run, tab_history = st.tabs([
    "📊 Overview", 
    "🎯 Manage Targets", 
    "🚀 Run Monitoring", 
    "📜 History & Archives"
])

# ── Overview Tab with Visa Sponsorship Summary ─────────────────────────────────
with tab_overview:
    st.header("📊 Dashboard Overview")
    
    # Metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Targets Monitored", len(df_targets))
    with col2:
        changes = 0
        if OUTPUT_FILE.exists():
            history_df = pd.read_excel(OUTPUT_FILE)
            changes = len(history_df[history_df['Status'].str.contains("Change|First", na=False)])
        st.metric("Changes Detected", changes)
    with col3:
        last_run = "Never"
        if OUTPUT_FILE.exists():
            last_run = pd.read_excel(OUTPUT_FILE)['Date'].max() or "Never"
        st.metric("Last Run", last_run)
    with col4:
        visa_yes_count = 0
        if OUTPUT_FILE.exists():
            history_df = pd.read_excel(OUTPUT_FILE)
            visa_yes_count = len(history_df[history_df['Visa Sponsorship'] == "Yes"])
        st.metric("Visa Sponsorship Found", visa_yes_count)

    st.markdown("### Quick Tips")
    with st.expander("How to get started"):
        st.write("""
        - Sync targets bidirectionally with Zotero in **Manage Targets**.
        - Run checks in **Run Monitoring** – detects Visa Sponsorship!
        - View archives in **History & Archives** with Zotero links or screenshots.
        """)

    # New: Visa Sponsorship Summary Table
    st.markdown("### 📋 Current Visa Sponsorship Status")
    if OUTPUT_FILE.exists():
        history_df = pd.read_excel(OUTPUT_FILE)
        # Get the most recent entry for each URL (unique company + role)
        latest_per_target = history_df.sort_values('Date', ascending=False).drop_duplicates(subset=['Company Name', 'Role'])
        visa_summary = latest_per_target[['Company Name', 'Role', 'URL', 'Visa Sponsorship', 'Date']].copy()
        visa_summary = visa_summary.sort_values('Visa Sponsorship', ascending=False)
        visa_summary['Date'] = pd.to_datetime(visa_summary['Date']).dt.strftime('%Y-%m-%d %H:%M')

        # Color coding
        def color_visa(val):
            color = 'green' if val == 'Yes' else 'red' if val == 'No' else 'gray'
            return f'background-color: {color}; color: white; padding: 5px; border-radius: 5px; text-align: center'

        styled_summary = visa_summary.style.applymap(color_visa, subset=['Visa Sponsorship'])

        st.dataframe(styled_summary, use_container_width=True, hide_index=True)
    else:
        st.info("No monitoring results yet. Run a check to see visa sponsorship status for each target.")

# ── Rest of the tabs remain exactly the same ───────────────────────────────────
with tab_targets:
    st.header("🎯 Manage Monitoring Targets")
    # ... (your full existing Manage Targets code here – unchanged)

with tab_run:
    st.header("🚀 Run Monitoring Check")
    # ... (your full existing Run Monitoring code here – unchanged)

with tab_history:
    st.header("📜 History & Archives")
    # ... (your full existing History code here – unchanged)

# Sidebar
st.sidebar.markdown("---")
st.sidebar.header("Account")
if st.sidebar.button("🚪 Logout"):
    st.session_state["authenticated"] = False
    st.rerun()

st.sidebar.info("Full Zotero bidirectional sync for targets and archives!")
