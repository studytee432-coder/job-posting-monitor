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

# ── Authentication (unchanged) ─────────────────────────────────────────────────
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
st.markdown("Welcome, Ritika! Track job pages in Dublin with full Zotero integration.")

# Directories
BASE_DIR = Path(__file__).parent
LATEST_SNAPSHOT_DIR = BASE_DIR / 'Latest_Snapshot'
OLD_SNAPSHOT_DIR = BASE_DIR / 'Old_Snapshot'
SCREENSHOTS_DIR = BASE_DIR / 'Screenshots'
ARCHIVES_DIR = BASE_DIR / 'Archives'
INPUT_FILE = BASE_DIR / 'targets.xlsx'
OUTPUT_FILE = BASE_DIR / 'results.xlsx'

for d in [LATEST_SNAPSHOT_DIR, OLD_SNAPSHOT_DIR, SCREENSHOTS_DIR, ARCHIVES_DIR]:
    d.mkdir(exist_ok=True)

# Load targets safely
columns = ['Company Name', 'URL', 'Role', 'Zotero Key']
if INPUT_FILE.exists():
    df_targets = pd.read_excel(INPUT_FILE)
else:
    df_targets = pd.DataFrame(columns=columns)

df_targets = df_targets.astype(str).fillna("")

# Tabs
tab_overview, tab_targets, tab_run, tab_history = st.tabs([
    "📊 Overview", "🎯 Manage Targets", "🚀 Run Monitoring", "📜 History & Archives"
])

# Overview (unchanged)
with tab_overview:
    st.header("📊 Dashboard Overview")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Targets Monitored", len(df_targets))
    with col2:
        changes = 0
        if OUTPUT_FILE.exists():
            history = pd.read_excel(OUTPUT_FILE)
            changes = len(history[history['Status'].str.contains("Change|First", na=False)])
        st.metric("Changes Detected", changes)
    with col3:
        last = "Never"
        if OUTPUT_FILE.exists():
            last = pd.read_excel(OUTPUT_FILE)['Date'].max() or "Never"
        st.metric("Last Run", last)

# Targets tab (with session state for persistence)
with tab_targets:
    st.header("🎯 Manage Monitoring Targets")

    # Session state for targets
    if 'df_targets' not in st.session_state:
        st.session_state['df_targets'] = df_targets

    df_targets = st.session_state['df_targets']

    use_zotero = st.checkbox("Enable Zotero Integration", value=True)
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
                selected_collection_id = next((c['key'] for c in collections if c['data']['name'] == selected), None)
        except Exception as e:
            st.warning(f"Zotero failed: {str(e)}")

    if use_zotero and zot and st.button("🔄 Sync from Zotero"):
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
                df_new = pd.DataFrame(synced).astype(str).fillna("")
                if not df_targets.empty:
                    df_targets = df_targets.merge(df_new, on='Zotero Key', how='outer', suffixes=('', '_new'))
                    for c in ['Company Name', 'URL', 'Role']:
                        df_targets[c] = df_targets[f'{c}_new'].combine_first(df_targets[c])
                        df_targets.drop(f'{c}_new', axis=1, inplace=True, errors='ignore')
                else:
                    df_targets = df_new

                df_targets.to_excel(INPUT_FILE, index=False)
                st.session_state['df_targets'] = df_targets
                st.success(f"Synced {len(synced)} targets!")
                st.rerun()
            else:
                st.info("No webpage items found.")
        except Exception as e:
            st.error(f"Sync failed: {str(e)}")

    edited = st.data_editor(
        df_targets,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "Company Name": st.column_config.TextColumn("Company Name", required=True),
            "URL": st.column_config.LinkColumn("Career/Job URL", required=True),
            "Role": st.column_config.TextColumn("Role/Keyword", required=True),
            "Zotero Key": st.column_config.TextColumn("Zotero Key", disabled=False),
        }
    )

    if st.button("💾 Save Targets", type="primary"):
        edited.to_excel(INPUT_FILE, index=False)
        st.session_state['df_targets'] = edited
        st.success("Saved!")
        st.rerun()

# ── Run Monitoring ──────────────────────────────────────────────────────────────
with tab_run:
    st.header("🚀 Run Monitoring Check")

    take_archives = st.checkbox("Archive changes (Zotero/Screenshot)", value=True)

    if st.button("🔄 Run Now", type="primary"):
        if df_targets.empty:
            st.warning("No targets yet. Add some in Manage Targets.")
        else:
            with st.spinner("Checking all targets..."):
                current_date = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                results = []
                errors = []

                for idx, row in df_targets.iterrows():
                    company = row['Company Name']
                    url = row['URL']
                    role = row['Role']

                    st.write(f"→ Checking {company} – {role}...")

                    filename = f"{company}_{role}".replace(' ', '_').replace('/', '-') + ".html"
                    new_path = LATEST_SNAPSHOT_DIR / filename
                    old_path = OLD_SNAPSHOT_DIR / filename

                    try:
                        r = requests.get(url, timeout=20, headers={'User-Agent': 'Mozilla/5.0'})
                        r.raise_for_status()
                        html = r.text
                        with open(new_path, 'w', encoding='utf-8') as f:
                            f.write(html)
                    except Exception as e:
                        err_msg = f"Fetch failed for {company}: {str(e)}"
                        errors.append(err_msg)
                        results.append({
                            'Date': current_date, 'Company Name': company, 'URL': url, 'Role': role,
                            'Status': "Error", 'Visa Sponsorship': 'N/A', 'Visa Evidence': '',
                            'Archive': None
                        })
                        st.error(err_msg)
                        continue

                    # Visa logic (simplified for visibility)
                    visa_found = "visa sponsorship" in html.lower()
                    visa_status = "Yes" if visa_found else "No"

                    changed = True
                    status = "First run"

                    if old_path.exists():
                        with open(old_path, 'r', encoding='utf-8') as old, open(new_path, 'r', encoding='utf-8') as new:
                            changed = old.read() != new.read()
                        status = "Change detected!" if changed else "No change"

                    archive_link = None
                    if changed and take_archives:
                        archive_path = ARCHIVES_DIR / f"{current_date}_{filename}"
                        shutil.copy(new_path, archive_path)
                        archive_link = str(archive_path)

                    results.append({
                        'Date': current_date, 'Company Name': company, 'URL': url, 'Role': role,
                        'Status': status, 'Visa Sponsorship': visa_status, 'Visa Evidence': '',
                        'Archive': archive_link
                    })

                if results:
                    df_results = pd.DataFrame(results)
                    if OUTPUT_FILE.exists():
                        existing = pd.read_excel(OUTPUT_FILE)
                        df_results = pd.concat([existing, df_results], ignore_index=True)
                    df_results.to_excel(OUTPUT_FILE, index=False)

                    # Update snapshots
                    shutil.rmtree(OLD_SNAPSHOT_DIR, ignore_errors=True)
                    shutil.copytree(LATEST_SNAPSHOT_DIR, OLD_SNAPSHOT_DIR)
                    shutil.rmtree(LATEST_SNAPSHOT_DIR, ignore_errors=True)
                    LATEST_SNAPSHOT_DIR.mkdir(exist_ok=True)

                    # Save latest results in session state
                    st.session_state['latest_results'] = df_results

                    st.success("Check complete!")
                    if errors:
                        st.warning(f"{len(errors)} targets had errors.")
                else:
                    st.warning("No results generated – check if URLs are valid.")

    # Always show latest results if they exist
    if 'latest_results' in st.session_state:
        st.subheader("Latest Run Results")
        st.dataframe(st.session_state['latest_results'], use_container_width=True)
    elif OUTPUT_FILE.exists():
        st.subheader("Previous Results")
        st.dataframe(pd.read_excel(OUTPUT_FILE).sort_values('Date', ascending=False), use_container_width=True)
    else:
        st.info("Run monitoring to see results here.")

# History tab (simple)
with tab_history:
    st.header("📜 History & Archives")
    if OUTPUT_FILE.exists():
        df_history = pd.read_excel(OUTPUT_FILE)
        st.dataframe(df_history.sort_values('Date', ascending=False), use_container_width=True)
    else:
        st.info("No history yet. Run monitoring first.")

# Sidebar
st.sidebar.markdown("---")
if st.sidebar.button("🚪 Logout"):
    st.session_state["authenticated"] = False
    st.rerun()
