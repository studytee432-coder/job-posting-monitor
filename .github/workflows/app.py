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
import re  # For extracting visa evidence text

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
ARCHIVES_DIR = BASE_DIR / 'Archives'
INPUT_FILE = BASE_DIR / 'targets.xlsx'
OUTPUT_FILE = BASE_DIR / 'results.xlsx'

for dir_path in [LATEST_SNAPSHOT_DIR, OLD_SNAPSHOT_DIR, SCREENSHOTS_DIR, ARCHIVES_DIR]:
    dir_path.mkdir(exist_ok=True)

# Load targets (with Zotero Key column)
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

    st.markdown("### Quick Tips")
    with st.expander("How to get started"):
        st.write("""
        - Sync targets bidirectionally with Zotero in **Manage Targets**.
        - Run checks in **Run Monitoring** – detects Visa Sponsorship!
        - View archives in **History & Archives** with Zotero links or screenshots.
        """)

with tab_targets:
    st.header("🎯 Manage Monitoring Targets")
    st.markdown("Add, edit, or delete targets. Use Zotero for centralized management (optional).")

    # ── Load targets & PREVENT null/type issues ───────────────────────────────
    columns = ['Company Name', 'URL', 'Role', 'Zotero Key']

    if INPUT_FILE.exists():
        df_targets = pd.read_excel(INPUT_FILE)
    else:
        df_targets = pd.DataFrame(columns=columns)

    # Force all expected columns to exist
    for col in columns:
        if col not in df_targets.columns:
            df_targets[col] = ""

    # CRITICAL: Convert everything to string + replace nulls → ""
    df_targets = df_targets.astype(str).replace(['nan', 'NaN', 'None'], '', regex=True).fillna("")

    # ── Zotero integration (unchanged part) ────────────────────────────────────
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
            selected_collection = st.selectbox("Select Zotero Collection", collection_names)
            if selected_collection != "All Items":
                selected_collection_id = next((c['key'] for c in collections if c['data']['name'] == selected_collection), None)
        except Exception as e:
            st.warning(f"Zotero connection failed: {str(e)}\nCheck secrets.")

    # Sync from Zotero (your existing logic - should now be safe)
    if use_zotero and zot and st.button("🔄 Sync from Zotero (webpage items only)"):
        # ... your sync code here (no change needed) ...
        pass  # ← keep your sync implementation

    # ── SAFE Data Editor ───────────────────────────────────────────────────────
    column_config_safe = {
        "Company Name": st.column_config.TextColumn(
            "Company Name",
            required=True,
            help="Company or organization name"
        ),
        "URL": st.column_config.LinkColumn(
            "Career/Job URL",
            required=True,
            help="Full URL to monitor (career page recommended)"
        ),
        "Role": st.column_config.TextColumn(
            "Role/Keyword",
            required=True,
            help="Position or keyword you're interested in"
        ),
        "Zotero Key": st.column_config.TextColumn(
            "Zotero Key",
            disabled=True,
            help="Internal Zotero item identifier (auto-filled)"
        ),
    }

    try:
        edited_targets = st.data_editor(
            df_targets,
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            column_config=column_config_safe,
            key="targets_editor"  # helps with session state stability
        )
    except Exception as e:
        st.error("Data editor crashed → showing fallback table.\n"
                 "This usually happens due to invalid data types/nulls.\n"
                 f"Error: {str(e)}")
        st.dataframe(df_targets, use_container_width=True)
        edited_targets = df_targets  # fallback

    # Save logic
    col_save, col_info = st.columns([1, 3])
    with col_save:
        if st.button("💾 Save Targets & Sync to Zotero", type="primary", use_container_width=True):
            if edited_targets.duplicated(subset=['Company Name', 'Role']).any():
                st.error("Duplicate Company + Role combinations found.")
            elif edited_targets[['Company Name', 'URL', 'Role']].eq("").any(axis=1).any():
                st.error("Required fields (Company, URL, Role) cannot be empty.")
            else:
                # Your Zotero push logic here (unchanged)
                # ...
                edited_targets.to_excel(INPUT_FILE, index=False)
                st.success("Targets saved successfully!")
                st.rerun()

    with col_info:
        st.info("Zotero Key is read-only. Sync only affects webpage items.")

with tab_run:
    st.header("🚀 Run Monitoring Check")
    st.markdown("Scan targets for changes, visa sponsorship, and archive if enabled.")

    take_archives = st.checkbox("📸 Archive Changes (Zotero or Screenshot)", value=True)

    if st.button("🔄 Run Now", type="primary", use_container_width=True):
        if len(df_targets) == 0:
            st.warning("No targets added yet. Go to Manage Targets first.")
        else:
            with st.spinner("Monitoring in progress..."):
                current_date = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                results = []
                screenshot_client = None
                zot = None  # Initialize zot here if needed
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

                for _, row in df_targets.iterrows():
                    company = row['Company Name']
                    url = row['URL']
                    role = row['Role']

                    filename = f"{company.replace(' ', '_').replace('/', '-')}_{role.replace(' ', '_').replace('/', '-')}.html"
                    new_path = LATEST_SNAPSHOT_DIR / filename
                    old_path = OLD_SNAPSHOT_DIR / filename
                    archive_path = ARCHIVES_DIR / f"{current_date.replace(':', '-')}_{filename}"

                    try:
                        response = requests.get(url, timeout=20, headers={'User-Agent': 'Mozilla/5.0'})
                        response.raise_for_status()
                        html_content = response.text
                        with open(new_path, 'w', encoding='utf-8') as f:
                            f.write(html_content)
                    except Exception as e:
                        results.append({
                            'Company Name': company, 'URL': url, 'Role': role, 'Date': current_date,
                            'Status': f"Error: {e}", 'Visa Sponsorship': 'N/A', 'Visa Evidence': '', 'Archive': None
                        })
                        continue

                    # Visa Sponsorship Check with Evidence
                    visa_keywords = ["visa sponsorship", "sponsors visa", "visa support", "work visa", "sponsor h1b", "sponsor visa"]
                    visa_evidence = []
                    for keyword in visa_keywords:
                        matches = re.findall(r'[^.]*?\b' + re.escape(keyword) + r'\b[^.]*\.', html_content, re.IGNORECASE | re.DOTALL)
                        visa_evidence.extend(matches)
                    visa_mention = bool(visa_evidence)
                    visa_status = "Yes" if visa_mention else "No"
                    visa_evidence_str = "\n".join(set(visa_evidence))  # Unique snippets

                    if not old_path.exists():
                        has_changed = True
                        status = "First snapshot taken"
                    else:
                        with open(old_path, 'r', encoding='utf-8') as old_f, open(new_path, 'r', encoding='utf-8') as new_f:
                            has_changed = old_f.read() != new_f.read()
                        status = "Change detected! 🚨" if has_changed else "No change"

                    archive_link = None
                    if has_changed and take_archives:
                        shutil.copy(new_path, archive_path)
                        if zot:
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
                                st.warning(f"Screenshot failed for {company}: {e}")

                    results.append({
                        'Company Name': company, 'URL': url, 'Role': role, 'Date': current_date,
                        'Status': status, 'Visa Sponsorship': visa_status, 'Visa Evidence': visa_evidence_str, 'Archive': archive_link
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

                st.success("Monitoring complete!")
                st.subheader("Latest Run Results")
                st.dataframe(results_df, use_container_width=True)

with tab_history:
    st.header("📜 Monitoring History & Archives")
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
            st.success("History updated!")
            st.rerun()

        st.markdown("---")
        st.subheader("Filter & View History")
        col1, col2 = st.columns(2)
        with col1:
            company_filter = st.multiselect("Filter by Company", ["All"] + sorted(history_df['Company Name'].unique()))
        with col2:
            status_filter = st.multiselect("Filter by Status", ["All"] + sorted(history_df['Status'].unique()))

        filtered = history_df
        if "All" not in company_filter and company_filter:
            filtered = filtered[filtered['Company Name'].isin(company_filter)]
        if "All" not in status_filter and status_filter:
            filtered = filtered[filtered['Status'].isin(status_filter)]

        st.dataframe(filtered.sort_values('Date', ascending=False), use_container_width=True)

        st.markdown("### Visa Sponsorship Section")
        visa_yes = filtered[filtered['Visa Sponsorship'] == "Yes"]
        if not visa_yes.empty:
            st.dataframe(visa_yes, use_container_width=True)
        else:
            st.info("No entries with Visa Sponsorship detected.")

        st.markdown("### Visa Evidence Details")
        for _, row in filtered.iterrows():
            if row['Visa Sponsorship'] == "Yes" and row['Visa Evidence']:
                with st.expander(f"Evidence for {row['Company Name']} - {row['Role']} ({row['Date']})"):
                    st.text(row['Visa Evidence'])

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
            st.info("No changes with archives yet.")

        csv = filtered.to_csv(index=False).encode()
        st.download_button("📥 Download CSV", csv, "history.csv")
    else:
        st.info("No history yet. Add targets and run monitoring.")

# Sidebar
st.sidebar.markdown("---")
st.sidebar.header("Account")
if st.sidebar.button("🚪 Logout"):
    st.session_state["authenticated"] = False
    st.rerun()

st.sidebar.info("Full Zotero bidirectional sync for targets and archives!")
