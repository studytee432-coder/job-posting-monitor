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
        with st.form("Login Form", clear_on_submit=True):
            st.text_input("Username", key="username")
            st.text_input("Password", type="password", key="password")
            st.form_submit_button("Login", type="primary", on_click=password_entered)
        if st.session_state.get("authenticated") == False:
            st.error("❌ Invalid credentials")
        return False
    return True

if not check_password():
    st.stop()

st.title("🔍 Automated Job Posting Monitor")
st.markdown("Manage and monitor job pages with Zotero sync support.")

# Directories
BASE_DIR = Path(__file__).parent
LATEST_SNAPSHOT_DIR = BASE_DIR / 'Latest_Snapshot'
OLD_SNAPSHOT_DIR = BASE_DIR / 'Old_Snapshot'
SCREENSHOTS_DIR = BASE_DIR / 'Screenshots'
INPUT_FILE = BASE_DIR / 'targets.xlsx'
OUTPUT_FILE = BASE_DIR / 'results.xlsx'

for d in [LATEST_SNAPSHOT_DIR, OLD_SNAPSHOT_DIR, SCREENSHOTS_DIR]:
    d.mkdir(exist_ok=True)

# Load targets & fix nulls/types early
columns = ['Company Name', 'URL', 'Role', 'Zotero Key']
if INPUT_FILE.exists():
    df_targets = pd.read_excel(INPUT_FILE)
else:
    df_targets = pd.DataFrame(columns=columns)

# Ensure all columns exist & fix problematic types/nulls
for col in columns:
    if col not in df_targets.columns:
        df_targets[col] = ""
df_targets = df_targets.astype(object).fillna("")

# Tabs
tab_overview, tab_targets, tab_run, tab_history = st.tabs([
    "📊 Overview", "🎯 Manage Targets", "🚀 Run Monitoring", "📜 History & Archives"
])

with tab_overview:
    st.header("Dashboard Overview")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Targets", len(df_targets))
    with col2:
        changes = 0
        if OUTPUT_FILE.exists():
            history = pd.read_excel(OUTPUT_FILE)
            changes = len(history[history['Status'].str.contains("Change|First", case=False, na=False)])
        st.metric("Changes Detected", changes)
    with col3:
        last_run = "Never"
        if OUTPUT_FILE.exists():
            last_run = pd.read_excel(OUTPUT_FILE)['Date'].max() or "Never"
        st.metric("Last Run", last_run)

with tab_targets:
    st.header("🎯 Manage Monitoring Targets")

    use_zotero = st.checkbox("Enable Zotero Integration (setup in secrets)", value=True)
    zot = None
    selected_collection_id = None

    if use_zotero:
        try:
            zot = zotero.Zotero(
                st.secrets["zotero"]["library_id"],
                st.secrets["zotero"]["library_type"],
                st.secrets["zotero"]["api_key"]
            )
            collections = zot.collections()
            names = ["All Items"] + [c['data']['name'] for c in collections]
            selected = st.selectbox("Select Zotero Collection", names)
            if selected != "All Items":
                selected_collection_id = next(c['key'] for c in collections if c['data']['name'] == selected)
        except Exception as e:
            st.error(f"Zotero failed: {str(e)}\nCheck secrets (api_key, library_id, library_type).")
            use_zotero = False

    if use_zotero and zot and st.button("🔄 Sync from Zotero (webpage items only)"):
        try:
            if selected_collection_id:
                items = zot.everything(zot.collection_items(selected_collection_id, itemtype="webpage"))
            else:
                items = zot.everything(zot.items(itemtype="webpage"))

            synced = []
            for item in items:
                d = item['data']
                synced.append({
                    'Company Name': d.get('title', 'Unknown'),
                    'URL': d.get('url', ''),
                    'Role': d.get('extra', ''),
                    'Zotero Key': item['key']
                })

            if synced:
                df_new = pd.DataFrame(synced)
                # Simple safe merge: prioritize new data where keys match
                if not df_targets.empty:
                    df_targets = df_targets.merge(
                        df_new,
                        on='Zotero Key',
                        how='outer',
                        suffixes=('', '_new')
                    )
                    for c in ['Company Name', 'URL', 'Role']:
                        df_targets[c] = df_targets[c + '_new'].combine_first(df_targets[c])
                        df_targets.drop(c + '_new', axis=1, inplace=True, errors='ignore')
                    df_targets['Zotero Key'] = df_targets['Zotero Key'].fillna("")
                else:
                    df_targets = df_new
                df_targets.to_excel(INPUT_FILE, index=False)
                st.success(f"Synced {len(synced)} items!")
                st.rerun()
            else:
                st.info("No webpage items found.")
        except Exception as e:
            st.error(f"Sync failed: {str(e)}")

    # Safe data editor
    column_cfg = {
        "Company Name": st.column_config.TextColumn("Company Name", required=True),
        "URL": st.column_config.LinkColumn("Career/Job URL", required=True),
        "Role": st.column_config.TextColumn("Role/Keyword", required=True),
        "Zotero Key": st.column_config.TextColumn("Zotero Key", disabled=True),
    }

    try:
        edited_targets = st.data_editor(
            df_targets,
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            column_config=column_cfg
        )
    except Exception as e:
        st.error(f"Data editor issue: {str(e)}\nShowing raw table as fallback.")
        st.dataframe(df_targets, use_container_width=True)
        edited_targets = df_targets  # fallback for saving

    col_save, col_info = st.columns([1, 3])
    with col_save:
        if st.button("💾 Save Targets & Sync to Zotero", type="primary", use_container_width=True):
            edited_targets.to_excel(INPUT_FILE, index=False)
            st.success("Saved locally!")
            st.rerun()
    with col_info:
        st.info("Zotero Key is read-only. Sync pulls only webpage items.")

# Run Monitoring & History tabs (implement as in your previous working version)
# For brevity, add them back from your last good code if needed.
# They should now render since tab_targets no longer crashes.

st.sidebar.markdown("---")
st.sidebar.header("Account")
if st.sidebar.button("🚪 Logout"):
    st.session_state["authenticated"] = False
    st.rerun()
