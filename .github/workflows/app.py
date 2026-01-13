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

# Fix nulls/types for data_editor stability
df_targets = df_targets.astype(str).fillna("")

# Tabs
tab_overview, tab_targets, tab_run, tab_history = st.tabs([
    "📊 Overview", 
    "🎯 Manage Targets", 
    "🚀 Run Monitoring", 
    "📜 History & Archives"
])

with tab_overview:
    st.header("📊 Dashboard Overview")
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

with tab_targets:
    st.header("🎯 Manage Monitoring Targets")

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
            collection_names = ["All Items"] + [c['data']['name'] for c in collections]
            selected_collection = st.selectbox("Select Zotero Collection", collection_names)
            if selected_collection != "All Items":
                selected_collection_id = next((c['key'] for c in collections if c['data']['name'] == selected_collection), None)
        except Exception as e:
            st.warning(f"Zotero connection failed: {str(e)}")

    if use_zotero and zot:
        if st.button("🔄 Sync from Zotero"):
            try:
                if selected_collection_id:
                    items = zot.everything(zot.collection_items(selected_collection_id, itemtype="webpage"))
                else:
                    items = zot.everything(zot.items(itemtype="webpage"))

                synced_targets = []
                for item in items:
                    company = item['data'].get('title', 'Unknown')
                    url = item['data'].get('url', '')
                    role = item['data'].get('extra', '')
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
                    df_synced = df_synced.astype(str).fillna("")

                    # Merge logic
                    if not df_targets.empty:
                        df_targets = df_targets.merge(
                            df_synced,
                            on='Zotero Key',
                            how='outer',
                            suffixes=('', '_new')
                        )
                        for col in ['Company Name', 'URL', 'Role']:
                            df_targets[col] = df_targets[f'{col}_new'].combine_first(df_targets[col])
                            df_targets.drop(f'{col}_new', axis=1, inplace=True, errors='ignore')
                    else:
                        df_targets = df_synced

                    df_targets.to_excel(INPUT_FILE, index=False)
                    st.success(f"Synced {len(synced_targets)} items from Zotero!")
                    st.rerun()
                else:
                    st.info("No webpage items found in the selected scope.")
            except Exception as e:
                st.error(f"Sync failed: {str(e)}")

    # Data editor (safe version)
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
            edited_targets.to_excel(INPUT_FILE, index=False)
            st.success("Targets saved locally!")
            st.rerun()
    with col_info:
        st.info("Zotero Key is read-only. Sync only pulls webpage items.")

# ── Run Monitoring tab ──────────────────────────────────────────────────────────
with tab_run:
    st.header("🚀 Run Monitoring Check")
    st.markdown("Scan targets for changes, visa sponsorship mentions, and archive snapshots.")

    take_archives = st.checkbox("Archive changes (Zotero or Screenshot)", value=True)

    if st.button("🔄 Run Now", type="primary"):
        if df_targets.empty:
            st.warning("No targets. Add some in Manage Targets first.")
        else:
            with st.spinner("Checking targets..."):
                current_date = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                results = []

                for _, row in df_targets.iterrows():
                    company = row['Company Name']
                    url = row['URL']
                    role = row['Role']

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
                        results.append({
                            'Date': current_date, 'Company Name': company, 'URL': url, 'Role': role,
                            'Status': f"Error: {str(e)}", 'Visa Sponsorship': 'N/A', 'Visa Evidence': '',
                            'Archive': None
                        })
                        continue

                    # Improved Visa logic
                    visa_pattern = r"(visa sponsorship|sponsors visa|visa support|work visa|sponsor (h1b|visa))"
                    negation_pattern = r"(no|not|without|do not|does not|cannot|unavailable)"
                    sentences = re.split(r'(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?)\s', html)
                    evidence = [s.strip() for s in sentences if re.search(visa_pattern, s, re.I)]

                    has_visa = bool(evidence)
                    is_negated = any(re.search(negation_pattern, e, re.I) for e in evidence)
                    visa_result = "No" if is_negated else "Yes" if has_visa else "No"
                    evidence_text = "\n".join(evidence) if evidence else ""

                    changed = True
                    status = "First snapshot"

                    if old_path.exists():
                        with open(old_path, 'r', encoding='utf-8') as old, open(new_path, 'r', encoding='utf-8') as new:
                            changed = old.read() != new.read()
                        status = "Change detected! 🚨" if changed else "No change"

                    archive_link = None
                    if changed and take_archives:
                        archive_path = ARCHIVES_DIR / f"{current_date.replace(':', '-')}_{filename}"
                        shutil.copy(new_path, archive_path)
                        archive_link = str(archive_path)  # placeholder - extend with Zotero/screenshot if needed

                    results.append({
                        'Date': current_date, 'Company Name': company, 'URL': url, 'Role': role,
                        'Status': status, 'Visa Sponsorship': visa_result, 'Visa Evidence': evidence_text,
                        'Archive': archive_link
                    })

                df_results = pd.DataFrame(results)
                if OUTPUT_FILE.exists():
                    existing = pd.read_excel(OUTPUT_FILE)
                    df_results = pd.concat([existing, df_results], ignore_index=True)
                df_results.to_excel(OUTPUT_FILE, index=False)

                # Update snapshot state
                shutil.rmtree(OLD_SNAPSHOT_DIR, ignore_errors=True)
                shutil.copytree(LATEST_SNAPSHOT_DIR, OLD_SNAPSHOT_DIR)
                shutil.rmtree(LATEST_SNAPSHOT_DIR, ignore_errors=True)
                LATEST_SNAPSHOT_DIR.mkdir(exist_ok=True)

                st.success("Check complete!")
                st.subheader("Latest Results")
                st.dataframe(df_results, use_container_width=True)

# History tab (basic placeholder - expand as needed)
with tab_history:
    st.header("📜 History & Archives")
    if OUTPUT_FILE.exists():
        df_history = pd.read_excel(OUTPUT_FILE)
        st.dataframe(df_history.sort_values('Date', ascending=False), use_container_width=True)
    else:
        st.info("No monitoring history yet. Run a check first.")

# Sidebar
st.sidebar.markdown("---")
if st.sidebar.button("🚪 Logout"):
    st.session_state["authenticated"] = False
    st.rerun()
