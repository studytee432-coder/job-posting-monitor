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

# Authentication
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
st.markdown("Track job pages with full bidirectional Zotero integration for targets and archives.")

# Directories
BASE_DIR = Path(__file__).parent
LATEST_SNAPSHOT_DIR = BASE_DIR / 'Latest_Snapshot'
OLD_SNAPSHOT_DIR = BASE_DIR / 'Old_Snapshot'
SCREENSHOTS_DIR = BASE_DIR / 'Screenshots'
INPUT_FILE = BASE_DIR / 'targets.xlsx'
OUTPUT_FILE = BASE_DIR / 'results.xlsx'

for dir_path in [LATEST_SNAPSHOT_DIR, OLD_SNAPSHOT_DIR, SCREENSHOTS_DIR]:
    dir_path.mkdir(exist_ok=True)

# Load targets with Zotero Key column
columns = ['Company Name', 'URL', 'Role', 'Zotero Key']
if INPUT_FILE.exists():
    df_targets = pd.read_excel(INPUT_FILE)
    for col in columns:
        if col not in df_targets.columns:
            df_targets[col] = None
else:
    df_targets = pd.DataFrame(columns=columns)

# Tabs
tab_overview, tab_targets, tab_run, tab_history = st.tabs([
    "📊 Overview", 
    "🎯 Manage Targets", 
    "🚀 Run Monitoring", 
    "📜 History & Archives"
])

with tab_overview:
    st.header("Dashboard Overview")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Targets Monitored", len(df_targets))
    with col2:
        if OUTPUT_FILE.exists():
            history_df = pd.read_excel(OUTPUT_FILE)
            changes = len(history_df[history_df['Status'].str.contains("Change|First", na=False)])
            st.metric("Changes Detected", changes)
        else:
            st.metric("Changes Detected", 0)
    with col3:
        if OUTPUT_FILE.exists():
            last_run = pd.read_excel(OUTPUT_FILE)['Date'].max()
            st.metric("Last Run", last_run if pd.notna(last_run) else "Never")
        else:
            st.metric("Last Run", "Never")

    with st.expander("Quick Tips"):
        st.write("""
        - Enable Zotero integration and select a collection.
        - Sync targets from Zotero (pulls only webpage items).
        - Save & Sync pushes changes/additions back to Zotero.
        - Run monitoring to detect changes and archive snapshots.
        """)

with tab_targets:
    st.header("🎯 Manage Monitoring Targets")
    st.markdown("Add/edit/delete targets. Use Zotero for centralized, persistent management.")

    use_zotero = st.checkbox("Enable Zotero Integration (setup in secrets)", value=True)
    zot = None
    selected_collection_id = None
    collections = []

    if use_zotero:
        try:
            zot = zotero.Zotero(
                st.secrets["zotero"]["library_id"],
                st.secrets["zotero"]["library_type"],
                st.secrets["zotero"]["api_key"]
            )
            collections = zot.collections()
            collection_names = ["All Items"] + [c['data']['name'] for c in collections]
            selected_collection = st.selectbox("Select Zotero Collection", collection_names)
            if selected_collection != "All Items":
                selected_collection_id = next((c['key'] for c in collections if c['data']['name'] == selected_collection), None)
        except Exception as e:
            st.error(f"Zotero connection failed: {str(e)}\nCheck your secrets (api_key, library_id, library_type).")
            use_zotero = False

    if use_zotero and zot:
        if st.button("🔄 Sync from Zotero (webpage items only)"):
            try:
                if selected_collection_id:
                    items = zot.everything(zot.collection_items(selected_collection_id, itemtype="webpage"))
                else:
                    items = zot.everything(zot.items(itemtype="webpage"))

                synced_targets = []
                for item in items:
                    data = item['data']
                    company = data.get('title', 'Unknown')
                    url = data.get('url', '')
                    role = data.get('extra', '')
                    key = item['key']
                    if url:
                        synced_targets.append({
                            'Company Name': company,
                            'URL': url,
                            'Role': role,
                            'Zotero Key': key
                        })

                if synced_targets:
                    df_synced = pd.DataFrame(synced_targets)
                    # Merge: update existing by Zotero Key, add new
                    if not df_targets.empty:
                        df_targets = df_targets.set_index('Zotero Key', drop=False)
                        df_synced = df_synced.set_index('Zotero Key')
                        df_targets.update(df_synced)
                        df_targets = pd.concat([df_targets, df_synced[~df_synced.index.isin(df_targets.index)]])
                        df_targets = df_targets.reset_index(drop=True)
                    else:
                        df_targets = df_synced
                    df_targets.to_excel(INPUT_FILE, index=False)
                    st.success(f"Synced {len(synced_targets)} webpage items from Zotero!")
                    st.rerun()
                else:
                    st.info("No webpage items found in the selected scope.")
            except Exception as e:
                st.error(f"Sync from Zotero failed: {str(e)}")

    edited_targets = st.data_editor(
        df_targets,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "Company Name": st.column_config.TextColumn("Company Name", required=True),
            "URL": st.column_config.LinkColumn("Career/Job URL", required=True),
            "Role": st.column_config.TextColumn("Role/Keyword", required=True),
            "Zotero Key": st.column_config.TextColumn("Zotero Key", disabled=True),
        }
    )

    col_save, col_info = st.columns([1, 3])
    with col_save:
        if st.button("💾 Save Targets & Sync to Zotero", type="primary", use_container_width=True):
            if edited_targets.duplicated(subset=['Company Name', 'Role']).any():
                st.error("Duplicate Company + Role combinations found.")
            elif edited_targets[['Company Name', 'URL', 'Role']].isnull().any().any():
                st.error("Required fields (Company, URL, Role) cannot be empty.")
            else:
                if use_zotero and zot:
                    try:
                        for idx, row in edited_targets.iterrows():
                            item_key = row.get('Zotero Key')
                            template = zot.item_template('webpage')
                            template['title'] = row['Company Name']
                            template['url'] = row['URL']
                            template['extra'] = row['Role']
                            if selected_collection_id:
                                template['collections'] = [selected_collection_id]
                            if pd.notna(item_key):
                                # Update existing item
                                item = zot.item(item_key)
                                item['data'].update({
                                    'title': template['title'],
                                    'url': template['url'],
                                    'extra': template['extra']
                                })
                                zot.update_item(item)
                            else:
                                # Create new
                                new_items = zot.create_items([template])
                                new_key = new_items['successful']['0']['key']
                                edited_targets.at[idx, 'Zotero Key'] = new_key
                        st.success("Targets saved and synced to Zotero!")
                    except Exception as e:
                        st.warning(f"Zotero push failed: {str(e)} — local save still performed.")
                edited_targets.to_excel(INPUT_FILE, index=False)
                st.success("Targets saved locally!")
                st.rerun()
    with col_info:
        st.info("Zotero sync pulls only **webpage** items. Save pushes updates/adds to selected collection.")

# ... (The rest of the code for tab_run and tab_history remains the same as in your previous version.
# If you want me to include the full remaining code, let me know — but the main fix was in the Sync from Zotero block.)

st.sidebar.markdown("---")
st.sidebar.header("Account")
if st.sidebar.button("🚪 Logout"):
    st.session_state["authenticated"] = False
    st.rerun()

st.sidebar.info("Full bidirectional Zotero sync enabled! Targets = webpage items only.")
