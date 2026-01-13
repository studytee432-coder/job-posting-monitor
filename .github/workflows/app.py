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
    st.markdown("Add, edit or delete targets. Zotero integration is optional.")

    # ── Load and FIX the dataframe to prevent editor crash ───────────────────────
    columns = ['Company Name', 'URL', 'Role', 'Zotero Key']

    if INPUT_FILE.exists():
        df_targets = pd.read_excel(INPUT_FILE)
    else:
        df_targets = pd.DataFrame(columns=columns)

    # Guarantee all columns exist
    for col in columns:
        if col not in df_targets.columns:
            df_targets[col] = ""

    # The magic fix: everything → string + NaN/None → ""
    df_targets = df_targets.astype(str).replace(['nan', 'NaN', 'None', 'null'], '', regex=True).fillna("")

    # ── Zotero connection & sync (your existing logic - kept minimal) ───────────
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
            selected = st.selectbox("Select Collection", names)
            if selected != "All Items":
                selected_collection_id = next((c['key'] for c in collections if c['data']['name'] == selected), None)
        except Exception as e:
            st.warning(f"Zotero connection failed: {str(e)}")
            use_zotero = False

    if use_zotero and zot and st.button("🔄 Sync from Zotero"):
        # Your sync logic here...
        # (keep your existing code – just make sure synced df also gets astype(str).fillna(""))
        pass

    # ── Safe & robust data editor ───────────────────────────────────────────────
    column_config = {
        "Company Name": st.column_config.TextColumn("Company Name", required=True),
        "URL": st.column_config.LinkColumn("Career/Job URL", required=True),
        "Role": st.column_config.TextColumn("Role/Keyword", required=True),
        # Safest way for read-only key column
        "Zotero Key": st.column_config.TextColumn("Zotero Key", disabled=True),
    }

    try:
        edited_targets = st.data_editor(
            df_targets,
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            column_config=column_config,
            key="targets_editor_safe"  # helps avoid stale state issues
        )
    except Exception as e:
        st.error(
            "⚠️ Data editor failed (probably bad data types).\n"
            "Showing raw table as fallback. You can still edit below.\n\n"
            f"Error: {str(e)}"
        )
        st.dataframe(df_targets, use_container_width=True)
        # Fallback: use simple input for saving
        edited_targets = df_targets.copy()  # or implement manual editing if needed

    # ── Save section ────────────────────────────────────────────────────────────
    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("💾 Save Targets", type="primary", use_container_width=True):
            # Optional: your Zotero push logic here...
            edited_targets.to_excel(INPUT_FILE, index=False)
            st.success("Targets saved!")
            st.rerun()

    with col2:
        st.info("Zotero Key is read-only. Null values are now handled automatically.")

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

                    # Improved Visa Sponsorship Check with Evidence and Negation Detection
                    visa_keywords = r"(visa sponsorship|sponsors visa|visa support|work visa|sponsor h1b|sponsor visa)"
                    negation_keywords = r"(no|not|without|unable|do not|does not|cannot|unavailable)"

                    # Find sentences with visa keywords
                    sentences = re.split(r'(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?)\s', html_content)
                    visa_evidence = []
                    for sentence in sentences:
                        if re.search(visa_keywords, sentence, re.IGNORECASE):
                            visa_evidence.append(sentence.strip())
                    
                    # Determine status with negation check
                    visa_mention = bool(visa_evidence)
                    if visa_mention:
                        negation_found = any(re.search(negation_keywords, ev, re.IGNORECASE) for ev in visa_evidence)
                        visa_status = "No" if negation_found else "Yes"
                    else:
                        visa_status = "No"

                    visa_evidence_str = "\n".join(visa_evidence) if visa_evidence else ""

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
               
