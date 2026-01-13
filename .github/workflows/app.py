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
st.markdown("""
Welcome! Track job pages with full Zotero integration for targets and archives.
""")

# Directories
BASE_DIR = Path(__file__).parent
LATEST_SNAPSHOT_DIR = BASE_DIR / 'Latest_Snapshot'
OLD_SNAPSHOT_DIR = BASE_DIR / 'Old_Snapshot'
SCREENSHOTS_DIR = BASE_DIR / 'Screenshots'
INPUT_FILE = BASE_DIR / 'targets.xlsx'
OUTPUT_FILE = BASE_DIR / 'results.xlsx'

for dir_path in [LATEST_SNAPSHOT_DIR, OLD_SNAPSHOT_DIR, SCREENSHOTS_DIR]:
    dir_path.mkdir(exist_ok=True)

# Load targets (now with Zotero Key column)
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

    st.markdown("### Quick Tips")
    with st.expander("How to get started"):
        st.write("""
        - Sync targets bidirectionally with Zotero in **Manage Targets**.
        - Run checks in **Run Monitoring** – detects Visa Sponsorship!
        - View archives in **History** with Zotero links or screenshots.
        """)

with tab_targets:
    st.header("🎯 Manage Monitoring Targets")
    st.markdown("Add/edit/delete targets with full bidirectional Zotero sync.")

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
            collection_names = ["All Collections"] + [c['data']['name'] for c in collections]
            selected_collection = st.selectbox("Select Zotero Collection", collection_names)
            if selected_collection != "All Collections":
                selected_collection_id = next((c['key'] for c in collections if c['data']['name'] == selected_collection), None)
        except Exception as e:
            st.warning(f"Zotero connection failed: {e}. Check secrets.")

    if use_zotero and zot:
        if st.button("🔄 Sync from Zotero"):
            try:
                if selected_collection_id:
                    items = zot.everything(zot.collection_items(selected_collection_id))
                else:
                    items = zot.everything(zot.items(itemType='webpage'))
                synced_targets = []
                for item in items:
                    if item['meta']['itemType'] == 'webpage':
                        company = item['data'].get('title', 'Unknown')
                        url = item['data'].get('url', '')
                        role = item['data'].get('extra', '')  # Use extra for role
                        key = item['key']
                        if url:
                            synced_targets.append({'Company Name': company, 'URL': url, 'Role': role, 'Zotero Key': key})
                if synced_targets:
                    df_synced = pd.DataFrame(synced_targets)
                    # Merge with existing, update if key matches
                    if not df_targets.empty:
                        df_targets = df_targets.merge(df_synced, on='Zotero Key', how='outer', suffixes=('', '_new'))
                        for col in ['Company Name', 'URL', 'Role']:
                            df_targets[col] = df_targets[col + '_new'].combine_first(df_targets[col])
                            df_targets.drop(col + '_new', axis=1, inplace=True)
                    else:
                        df_targets = df_synced
                    df_targets.to_excel(INPUT_FILE, index=False)
                    st.success(f"Synced {len(synced_targets)} targets from Zotero!")
                    st.rerun()
                else:
                    st.info("No webpage items found.")
            except Exception as e:
                st.error(f"Sync failed: {e}")

    edited_targets = st.data_editor(
        df_targets,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "Company Name": st.column_config.TextColumn(required=True),
            "URL": st.column_config.LinkColumn(required=True),
            "Role": st.column_config.TextColumn(required=True),
            "Zotero Key": st.column_config.TextColumn(disabled=True),  # Read-only
        }
    )

    col_save, col_info = st.columns([1, 3])
    with col_save:
        if st.button("💾 Save Targets & Sync to Zotero", type="primary", use_container_width=True):
            if edited_targets.duplicated(subset=['Company Name', 'Role']).any():
                st.error("Duplicates found.")
            elif edited_targets.isnull().any().any() and 'Zotero Key' not in edited_targets.columns[edited_targets.isnull().any()]:
                st.error("Fill required fields.")
            else:
                if use_zotero and zot and selected_collection_id:
                    try:
                        for idx, row in edited_targets.iterrows():
                            item_key = row.get('Zotero Key')
                            template = zot.item_template('webpage')
                            template['title'] = row['Company Name']
                            template['url'] = row['URL']
                            template['extra'] = row['Role']
                            if selected_collection_id:
                                template['collections'] = [selected_collection_id]
                            if item_key:
                                # Update
                                item = zot.item(item_key)
                                item['data']['title'] = template['title']
                                item['data']['url'] = template['url']
                                item['data']['extra'] = template['extra']
                                zot.update_item(item)
                            else:
                                # Create
                                new_item = zot.create_items([template])
                                new_key = new_item['successful']['0']['key']
                                edited_targets.at[idx, 'Zotero Key'] = new_key
                        st.success("Synced to Zotero!")
                    except Exception as e:
                        st.warning(f"Zotero sync failed: {e}")
                edited_targets.to_excel(INPUT_FILE, index=False)
                st.success("Targets saved!")
                st.rerun()
    with col_info:
        st.info("Zotero sync: Pulls all webpage items; pushes updates/adds to selected collection.")

with tab_run:
    st.header("🚀 Run Monitoring Check")
    st.markdown("Scan for changes, Visa mentions, and archive to Zotero if enabled.")

    take_archives = st.checkbox("📸 Archive Changes (Zotero or Screenshot)", value=True)

    if st.button("🔄 Run Now", type="primary", use_container_width=True):
        if len(edited_targets) == 0:
            st.warning("Add targets first.")
        else:
            with st.spinner("Running..."):
                current_date = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                results = []
                screenshot_client = None
                if take_archives:
                    try:
                        screenshot_client = Client(st.secrets["screenshotone"]["access_key"], st.secrets["screenshotone"]["secret_key"])
                    except:
                        pass
                    if use_zotero and zot:
                        pass  # zot already initialized

                for _, row in edited_targets.iterrows():
                    company = row['Company Name']
                    url = row['URL']
                    role = row['Role']

                    filename = f"{company.replace(' ', '_').replace('/', '-')}_{role.replace(' ', '_').replace('/', '-')}.html"
                    new_path = LATEST_SNAPSHOT_DIR / filename
                    old_path = OLD_SNAPSHOT_DIR / filename

                    try:
                        response = requests.get(url, timeout=20, headers={'User-Agent': 'Mozilla/5.0'})
                        response.raise_for_status()
                        html_content = response.text
                        with open(new_path, 'w', encoding='utf-8') as f:
                            f.write(html_content)
                    except Exception as e:
                        results.append({
                            'Company Name': company, 'URL': url, 'Role': role, 'Date': current_date,
                            'Status': f"Error: {e}", 'Visa Sponsorship': 'N/A', 'Archive': None
                        })
                        continue

                    visa_keywords = ["visa sponsorship", "sponsors visa", "visa support", "work visa", "sponsor h1b", "sponsor visa"]
                    visa_mention = any(keyword.lower() in html_content.lower() for keyword in visa_keywords)
                    visa_status = "Yes" if visa_mention else "No"

                    if not old_path.exists():
                        has_changed = True
                        status = "First snapshot taken"
                    else:
                        with open(old_path, 'r', encoding='utf-8') as old_f, open(new_path, 'r', encoding='utf-8') as new_f:
                            has_changed = old_f.read() != new_f.read()
                        status = "Change detected! 🚨" if has_changed else "No change"

                    archive_link = None
                    if has_changed and take_archives:
                        archive_filename = f"{current_date.replace(':', '-')}_{company}_{role}.html"
                        archive_path = BASE_DIR / 'Archives' / archive_filename
                        archive_path.parent.mkdir(exist_ok=True)
                        shutil.copy(new_path, archive_path)
                        if use_zotero and zot:
                            try:
                                item = zot.item_template('webpage')
                                item['title'] = f"Archive: {company} - {role} ({current_date})"
                                item['url'] = url
                                item['extra'] = f"Role: {role}; Visa: {visa_status}"
                                if selected_collection_id:
                                    item['collections'] = [selected_collection_id]
                                new_item = zot.create_items([item])
                                item_key = new_item['successful']['0']['key']
                                zot.attachment_simple([str(archive_path)], item_key)
                                archive_link = f"https://www.zotero.org/{st.secrets['zotero']['library_type']}s/{st.secrets['zotero']['library_id']}/items/{item_key}"
                                status += " (Archived to Zotero)"
                            except Exception as e:
                                st.warning(f"Zotero archive failed: {e}")
                        elif screenshot_client:
                            try:
                                options = TakeOptions.url(url).full_page(True).block_cookie_banners(True)
                                image = screenshot_client.take(options)
                                screenshot_filename = f"{current_date.replace(':', '-')}_{company}_{role}.png"
                                screenshot_path = SCREENSHOTS_DIR / screenshot_filename
                                with open(screenshot_path, 'wb') as f:
                                    f.write(image.read())
                                archive_link = str(screenshot_path)
                                status += " (Screenshot captured)"
                            except Exception as e:
                                st.warning(f"Screenshot failed: {e}")

                    results.append({
                        'Company Name': company, 'URL': url, 'Role': role, 'Date': current_date,
                        'Status': status, 'Visa Sponsorship': visa_status, 'Archive': archive_link
                    })

                results_df = pd.DataFrame(results)
                if OUTPUT_FILE.exists():
                    existing = pd.read_excel(OUTPUT_FILE)
                    full_df = pd.concat([existing, results_df], ignore_index=True)
                else:
                    full_df = results_df
                full_df.to_excel(OUTPUT_FILE, index=False)

                shutil.rmtree(OLD_SNAPSHOT_DIR, ignore_errors=True)
                shutil.copytree(LATEST_SNAPSHOT_DIR, OLD_SNAPSHOT_DIR)
                shutil.rmtree(LATEST_SNAPSHOT_DIR)
                LATEST_SNAPSHOT_DIR.mkdir(exist_ok=True)

                st.success("Complete!")
                st.subheader("Latest Results")
                st.dataframe(results_df, use_container_width=True)

with tab_history:
    st.header("📜 Monitoring History")
    if OUTPUT_FILE.exists() and not pd.read_excel(OUTPUT_FILE).empty:
        history_df = pd.read_excel(OUTPUT_FILE)

        st.subheader("Edit / Clean History")
        edited_history = st.data_editor(
            history_df.sort_values('Date', ascending=False),
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Archive": st.column_config.LinkColumn("Zotero/Archive Link") if use_zotero else st.column_config.ImageColumn("Screenshot Preview", width="medium"),
            }
        )

        if st.button("💾 Save Edited History", type="primary"):
            edited_history.to_excel(OUTPUT_FILE, index=False)
            st.success("Updated!")
            st.rerun()

        st.markdown("---")
        st.subheader("Filter & View")
        col1, col2 = st.columns(2)
        with col1:
            company_filter = st.multiselect("Filter Company", ["All"] + sorted(history_df['Company Name'].unique()))
        with col2:
            status_filter = st.multiselect("Filter Status", ["All"] + sorted(history_df['Status'].unique()))

        filtered = history_df
        if "All" not in company_filter and company_filter:
            filtered = filtered[filtered['Company Name'].isin(company_filter)]
        if "All" not in status_filter and status_filter:
            filtered = filtered[filtered['Status'].isin(status_filter)]

        st.dataframe(filtered.sort_values('Date', ascending=False), use_container_width=True)

        st.markdown("### Archives of Changes")
        change_rows = filtered[filtered['Status'].str.contains("Change|First", na=False)]
        if not change_rows.empty:
            for _, row in change_rows.iterrows():
                if pd.notna(row['Archive']):
                    if use_zotero:
                        st.link_button("View Archive in Zotero", row['Archive'])
                    else:
                        st.image(row['Archive'], caption=f"{row['Company Name']} - {row['Date']}", use_column_width=True)
        else:
            st.info("No archives yet.")

        csv = filtered.to_csv(index=False).encode()
        st.download_button("📥 Download CSV", csv, "history.csv")
    else:
        st.info("No history. Run monitoring.")

# Sidebar
st.sidebar.markdown("---")
st.sidebar.header("Account")
if st.sidebar.button("🚪 Logout"):
    st.session_state["authenticated"] = False
    st.rerun()

st.sidebar.info("Full Zotero bidirectional sync for targets and archives!")
