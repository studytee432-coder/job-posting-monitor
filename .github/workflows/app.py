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

# ── Authentication ──────────────────────────────────────────────────────────────
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

# ── Main App ────────────────────────────────────────────────────────────────────
st.title("🔍 Automated Job Posting Monitor")
st.markdown("Track job pages with full bidirectional Zotero integration.")

# Directories
BASE_DIR = Path(__file__).parent
LATEST_SNAPSHOT_DIR = BASE_DIR / 'Latest_Snapshot'
OLD_SNAPSHOT_DIR = BASE_DIR / 'Old_Snapshot'
SCREENSHOTS_DIR = BASE_DIR / 'Screenshots'
INPUT_FILE = BASE_DIR / 'targets.xlsx'
OUTPUT_FILE = BASE_DIR / 'results.xlsx'

for d in [LATEST_SNAPSHOT_DIR, OLD_SNAPSHOT_DIR, SCREENSHOTS_DIR]:
    d.mkdir(exist_ok=True)

# ── Load & Prepare Targets ──────────────────────────────────────────────────────
columns = ['Company Name', 'URL', 'Role', 'Zotero Key']
if INPUT_FILE.exists():
    df_targets = pd.read_excel(INPUT_FILE)
else:
    df_targets = pd.DataFrame(columns=columns)

# Fix types & nulls that cause data_editor to crash
if 'Zotero Key' in df_targets.columns:
    df_targets['Zotero Key'] = df_targets['Zotero Key'].astype("object").fillna("")
else:
    df_targets['Zotero Key'] = ""

for col in ['Company Name', 'URL', 'Role']:
    if col in df_targets.columns:
        df_targets[col] = df_targets[col].astype("object").fillna("")

# ── Tabs ────────────────────────────────────────────────────────────────────────
tab_overview, tab_targets, tab_run, tab_history = st.tabs([
    "📊 Overview",
    "🎯 Manage Targets",
    "🚀 Run Monitoring",
    "📜 History & Archives"
])

# Overview tab (unchanged for brevity)
with tab_overview:
    st.header("Dashboard Overview")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Targets Monitored", len(df_targets))
    # ... (rest same as before)

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
            collection_names = ["All Items"] + [c['data']['name'] for c in collections]
            selected = st.selectbox("Select Zotero Collection", collection_names)
            if selected != "All Items":
                selected_collection_id = next((c['key'] for c in collections if c['data']['name'] == selected), None)
        except Exception as e:
            st.error(f"Zotero connection failed: {str(e)}")
            use_zotero = False

    # Sync from Zotero
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
                # Safe merge
                df_targets = pd.merge(
                    df_targets.drop(columns=['Zotero Key'], errors='ignore'),
                    df_new,
                    on=['Company Name', 'URL', 'Role'],
                    how='outer',
                    suffixes=('', '_zotero'),
                    indicator=True
                )
                df_targets['Zotero Key'] = df_targets['Zotero Key'].fillna(df_targets['Zotero Key_zotero'])
                df_targets = df_targets.drop(columns=['Zotero Key_zotero', '_merge'], errors='ignore')
                df_targets.to_excel(INPUT_FILE, index=False)
                st.success(f"Synced {len(synced)} items!")
                st.rerun()
            else:
                st.info("No webpage items found.")
        except Exception as e:
            st.error(f"Sync failed: {str(e)}")

    # Data Editor – safe config
    try:
        edited_targets = st.data_editor(
            df_targets,
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            column_config={
                "Company Name": st.column_config.TextColumn("Company Name", required=True),
                "URL": st.column_config.LinkColumn("Career/Job URL", required=True),
                "Role": st.column_config.TextColumn("Role/Keyword", required=True),
                "Zotero Key": st.column_config.ColumnConfig("Zotero Key", disabled=True),
            }
        )
    except Exception as e:
        st.error(f"Data editor failed: {str(e)}\nTry refreshing or clearing browser cache.")
        edited_targets = df_targets  # fallback

    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("💾 Save Targets & Sync to Zotero", type="primary", use_container_width=True):
            # ... (your save + push to Zotero logic here - unchanged)
            edited_targets.to_excel(INPUT_FILE, index=False)
            st.success("Targets saved!")
            st.rerun()
    with col2:
        st.info("Zotero Key is read-only. Sync only pulls webpage items.")

# Run & History tabs remain the same as in your previous working version

st.sidebar.markdown("---")
st.sidebar.header("Account")
if st.sidebar.button("🚪 Logout"):
    st.session_state["authenticated"] = False
    st.rerun()
