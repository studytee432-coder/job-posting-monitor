import streamlit as st
import os
import shutil
import datetime
import requests
import pandas as pd
from pathlib import Path
import hmac
from screenshotone import Client, TakeOptions
from pyzotero import zotero  # New import for Zotero integration

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
Welcome, Ritika! Track job pages in Dublin and beyond. Now with Visa Sponsorship checks and optional Zotero integration for long-term data retention.
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

# Load targets
if INPUT_FILE.exists():
    df_targets = pd.read_excel(INPUT_FILE)
else:
    df_targets = pd.DataFrame(columns=['Company Name', 'URL', 'Role'])

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
        - Add career pages in **Manage Targets** (e.g., for Dublin jobs).
        - Run checks in **Run Monitoring** – now detects Visa Sponsorship!
        - View archives in **History** with screenshots or Zotero links.
        - For long-term retention, enable Zotero (setup in secrets).
        """)

with tab_targets:
    st.header("🎯 Manage Monitoring Targets")
    st.markdown("Add/edit/delete targets. Optionally sync from Zotero collection for centralized management.")

    # Zotero Sync Option
    use_zotero = st.checkbox("Use Zotero for Targets & Archives (enable in secrets)")
    if use_zotero:
        try:
            zot = zotero.Zotero(
                st.secrets["zotero"]["library_id"],
                st.secrets["zotero"]["library_type"],
                st.secrets["zotero"]["api_key"]
            )
            if st.button("🔄 Sync Targets from Zotero"):
                items = zot.collection_items(st.secrets["zotero"]["collection_id"])
                new_targets = []
                for item in items:
                    if item['meta']['itemType'] == 'webpage':
                        company = item['data'].get('title', 'Unknown')
                        url = item['data'].get('url', '')
                        role = item['data'].get('extra', '')  # Use extra for role
                        if url:
                            new_targets.append({'Company Name': company, 'URL': url, 'Role': role})
                if new_targets:
                    df_targets = pd.DataFrame(new_targets)
                    df_targets.to_excel(INPUT_FILE, index=False)
                    st.success(f"Synced {len(new_targets)} targets from Zotero!")
                    st.rerun()
                else:
                    st.info("No webpage items found in Zotero collection.")
        except Exception as e:
            st.warning(f"Zotero sync failed: {e}. Check secrets for api_key, library_id, library_type, collection_id.")

    edited_targets = st.data_editor(
        df_targets,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "Company Name": st.column_config.TextColumn("Company Name", required=True),
            "URL": st.column_config.LinkColumn("Career/Job URL", required=True),
            "Role": st.column_config.TextColumn("Role/Keyword", required=True),
        }
    )

    col_save, col_info = st.columns([1, 3])
    with col_save:
        if st.button("💾 Save Targets", type="primary", use_container_width=True):
            if edited_targets.duplicated(subset=['Company Name', 'Role']).any():
                st.error("Duplicates found.")
            elif edited_targets.isnull().values.any():
                st.error("Fill all fields.")
            else:
                edited_targets.to_excel(INPUT_FILE, index=False)
                st.success("Saved!")
                st.rerun()
    with col_info:
        st.info("Use company career URLs to avoid blocks. For Visa checks, pages must mention 'visa sponsorship' explicitly.")

with tab_run:
    st.header("🚀 Run Monitoring Check")
    st.markdown("Scan targets for changes. Adds 'Visa Sponsorship' column based on page content.")

    take_archives = st.checkbox("📸 Take Screenshot / Archive to Zotero on Changes", value=True)

    if st.button("🔄 Run Now", type="primary", use_container_width=True):
        if len(edited_targets) == 0:
            st.warning("Add targets first.")
        else:
            with st.spinner("Running..."):
                current_date = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                results = []
                screenshot_client = None
                zot = None
                if take_archives:
                    try:
                        screenshot_client = Client(st.secrets["screenshotone"]["access_key"], st.secrets["screenshotone"]["secret_key"])
                    except:
                        pass
                    if use_zotero:
                        try:
                            zot = zotero.Zotero(
                                st.secrets["zotero"]["library_id"],
                                st.secrets["zotero"]["library_type"],
                                st.secrets["zotero"]["api_key"]
                            )
                        except:
                            st.warning("Zotero setup incomplete.")

                for _, row in edited_targets.iterrows():
                    company = row['Company Name']
                    url = row['URL']
                    role = row['Role']

                    filename = f"{company.replace(' ', '_').replace('/', '-')}_{role.replace(' ', '_').replace('/', '-')}.html"
                    new_path = LATEST_SNAPSHOT_DIR / filename
                    old_path = OLD_SNAPSHOT_DIR / filename
                    archive_dir = BASE_DIR / 'Archives' / current_date.replace(':', '-')
                    archive_dir.mkdir(parents=True, exist_ok=True)
                    archive_path = archive_dir / filename

                    try:
                        response = requests.get(url, timeout=20, headers={'User-Agent': 'Mozilla/5.0'})
                        response.raise_for_status()
                        html_content = response.text
                        with open(new_path, 'w', encoding='utf-8') as f:
                            f.write(html_content)
                        # Archive copy for long-term retention
                        shutil.copy(new_path, archive_path)
                    except Exception as e:
                        results.append({
                            'Company Name': company, 'URL': url, 'Role': role, 'Date': current_date,
                            'Status': f"Error: {e}", 'Visa Sponsorship': 'N/A', 'Archive': None
                        })
                        continue

                    # Visa Sponsorship Check
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
                        if zot:
                            try:
                                item = zot.item_template('webpage')
                                item['title'] = f"{company} - {role} ({current_date})"
                                item['url'] = url
                                item['extra'] = role
                                new_item = zot.create_items([item])
                                item_key = new_item['successful']['0']['key']
                                # Attach HTML snapshot
                                zot.attachment_simple([str(archive_path)], item_key)
                                archive_link = f"https://www.zotero.org/{st.secrets['zotero']['library_type']}s/{st.secrets['zotero']['library_id']}/items/{item_key}"
                                status += " (Archived to Zotero)"
                            except Exception as e:
                                st.warning(f"Zotero archive failed for {company}: {e}")
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
                "Archive": st.column_config.ImageColumn("Archive Preview", width="medium") if not use_zotero else st.column_config.LinkColumn("Zotero Link"),
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
                        st.link_button("View in Zotero", row['Archive'])
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

st.sidebar.info("Cloud-based app with persistent data. Zotero integrates for long-term archives!")
