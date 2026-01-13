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

# ── Page Config ────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Job Posting Monitor", page_icon="🔍", layout="wide")

# ── Authentication ─────────────────────────────────────────────────────────────
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
    return True

if not check_password():
    st.stop()

# ── Main Title ─────────────────────────────────────────────────────────────────
st.title("🔍 Automated Job Posting Monitor")
st.markdown("Welcome, Ritika! Track job pages in Dublin with full Zotero integration.")

# ── Directories ────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
LATEST_SNAPSHOT_DIR = BASE_DIR / 'Latest_Snapshot'
OLD_SNAPSHOT_DIR = BASE_DIR / 'Old_Snapshot'
SCREENSHOTS_DIR = BASE_DIR / 'Screenshots'
ARCHIVES_DIR = BASE_DIR / 'Archives'
INPUT_FILE = BASE_DIR / 'targets.xlsx'
OUTPUT_FILE = BASE_DIR / 'results.xlsx'

for d in [LATEST_SNAPSHOT_DIR, OLD_SNAPSHOT_DIR, SCREENSHOTS_DIR, ARCHIVES_DIR]:
    d.mkdir(exist_ok=True)

# ── Load Targets with null/type safety ─────────────────────────────────────────
columns = ['Company Name', 'URL', 'Role', 'Zotero Key']
if INPUT_FILE.exists():
    df_targets = pd.read_excel(INPUT_FILE)
else:
    df_targets = pd.DataFrame(columns=columns)

# Critical fix: everything to string + nulls → ""
df_targets = df_targets.astype(str).replace(['nan', 'NaN', 'None', 'null'], '', regex=True).fillna("")

# Tabs
tab_overview, tab_targets, tab_run, tab_history = st.tabs([
    "📊 Overview",
    "🎯 Manage Targets",
    "🚀 Run Monitoring",
    "📜 History & Archives"
])

# ── Overview Tab ───────────────────────────────────────────────────────────────
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

    # ── All Monitored Websites & Visa Sponsorship Status ───────────────────────
    st.markdown("### All Monitored Websites & Visa Sponsorship Evidence")

    if OUTPUT_FILE.exists():
        history = pd.read_excel(OUTPUT_FILE)

        # Get most recent record per unique target
        latest = history.sort_values('Date', ascending=False)\
                        .drop_duplicates(subset=['Company Name', 'URL', 'Role'], keep='first')

        # Merge — prioritize original clean URL from targets
        overview_df = df_targets[['Company Name', 'URL', 'Role']].copy()
        overview_df = overview_df.merge(
            latest[['Company Name', 'URL', 'Role', 'Visa Sponsorship', 'Visa Evidence', 'Date']],
            on=['Company Name', 'URL', 'Role'],
            how='left'
        )

        overview_df['Visa Sponsorship'] = overview_df['Visa Sponsorship'].fillna('Not checked yet')
        overview_df['Visa Evidence'] = overview_df['Visa Evidence'].fillna('—')
        overview_df['Date'] = overview_df['Date'].fillna('—')

        # Final columns: Company → URL → Visa Status → Evidence → Last Checked
        overview_df = overview_df[['Company Name', 'URL', 'Visa Sponsorship', 'Visa Evidence', 'Date']]
        overview_df = overview_df.rename(columns={'Date': 'Last Checked'})

        # High-contrast, readable styling
        def highlight_visa(val):
            if val == 'Yes':
                return 'background-color: #28a745; color: white; font-weight: bold;'
            elif val == 'No':
                return 'background-color: #dc3545; color: white;'
            elif val == 'Not checked yet':
                return 'background-color: #ffc107; color: black;'
            return ''

        st.dataframe(
            overview_df.style.map(highlight_visa, subset=['Visa Sponsorship'])
                             .set_properties(**{
                                 'text-align': 'left',
                                 'white-space': 'normal',
                                 'word-break': 'break-word',
                                 'padding': '8px'
                             })
                             .set_table_styles([
                                 {'selector': 'th', 'props': [('font-weight', 'bold'), ('text-align', 'center')]},
                             ]),
            use_container_width=True,
            column_config={
                "URL": st.column_config.LinkColumn("URL"),
                "Visa Sponsorship": st.column_config.Column(width="medium"),
                "Visa Evidence": st.column_config.Column(width="large"),
                "Last Checked": st.column_config.Column(width="medium")
            }
        )

        if overview_df['Visa Sponsorship'].eq('Yes').any():
            st.success("Some positions currently appear to offer Visa Sponsorship!")
        else:
            st.info("No confirmed Visa Sponsorship found in the latest checks.")
    else:
        st.info("No monitoring data yet. Run a check in the 'Run Monitoring' tab.")

# ── Manage Targets Tab ─────────────────────────────────────────────────────────
with tab_targets:
    st.header("🎯 Manage Monitoring Targets")

    # Use session state for persistence after sync
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
            st.warning(f"Zotero connection failed: {str(e)}")

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

    edited_targets = st.data_editor(
        df_targets,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "Company Name": st.column_config.TextColumn("Company Name", required=True),
            "URL": st.column_config.LinkColumn("Career/Job URL", required=True),
            "Role": st.column_config.TextColumn("Role/Keyword", required=True),
            "Zotero Key": st.column_config.TextColumn("Zotero Key", disabled=False),  # editable
        }
    )

    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("💾 Save Targets", type="primary", use_container_width=True):
            edited_targets.to_excel(INPUT_FILE, index=False)
            st.session_state['df_targets'] = edited_targets
            st.success("Targets saved!")
            st.rerun()
    with col2:
        st.info("Zotero Key is editable. Sync pulls only webpage items.")

# ── Run Monitoring Tab ─────────────────────────────────────────────────────────
with tab_run:
    st.header("🚀 Run Monitoring Check")
    st.markdown("Scans all targets. You should see progress for each target below.")

    take_archives = st.checkbox("Archive changes (Zotero or Screenshot)", value=True)

    if st.button("🔄 Run Now", type="primary", use_container_width=True):
        if df_targets.empty:
            st.warning("No targets added. Go to Manage Targets first.")
        else:
            with st.spinner("Checking targets..."):
                current_date = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                results = []
                error_count = 0

                st.write("Starting scan...")

                for idx, row in df_targets.iterrows():
                    company = row['Company Name']
                    url = row['URL'].strip()
                    role = row['Role']

                    st.write(f"→ Checking {company} – {role} ({url[:60]}...)")

                    filename = f"{company}_{role}".replace(' ', '_').replace('/', '-') + ".html"
                    new_path = LATEST_SNAPSHOT_DIR / filename
                    old_path = OLD_SNAPSHOT_DIR / filename

                    html = None
                    try:
                        headers = {
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                            'Accept-Language': 'en-US,en;q=0.5',
                        }
                        r = requests.get(url, timeout=20, headers=headers, allow_redirects=True)
                        r.raise_for_status()
                        html = r.text
                        with open(new_path, 'w', encoding='utf-8') as f:
                            f.write(html)
                        st.success(f"  ✓ Page fetched (status {r.status_code})")
                    except Exception as e:
                        error_count += 1
                        status_msg = f"Fetch error: {str(e)}"
                        st.error(f"  ✗ {status_msg}")
                        results.append({
                            'Date': current_date,
                            'Company Name': company,
                            'URL': url,
                            'Role': role,
                            'Status': status_msg,
                            'Visa Sponsorship': 'N/A',
                            'Visa Evidence': '',
                            'Archive': None
                        })
                        continue

                    # Visa check
                    visa_status = "No"
                    evidence_text = ""
                    if html:
                        visa_keywords = ["visa sponsorship", "sponsors visa", "visa support", "work visa", "sponsor h1b"]
                        evidence = [s.strip() for s in re.split(r'\.\s*', html) if any(kw.lower() in s.lower() for kw in visa_keywords)]
                        visa_status = "Yes" if evidence else "No"
                        evidence_text = "\n".join(evidence)[:500] + "..." if len("\n".join(evidence)) > 500 else "\n".join(evidence)

                    changed = True
                    status = "First snapshot"

                    if old_path.exists():
                        try:
                            with open(old_path, 'r', encoding='utf-8') as old, open(new_path, 'r', encoding='utf-8') as new:
                                changed = old.read() != new.read()
                            status = "Change detected! 🚨" if changed else "No change"
                        except:
                            status = "Change detection failed"

                    archive_link = None
                    if changed and take_archives:
                        archive_path = ARCHIVES_DIR / f"{current_date.replace(':', '-')}_{filename}"
                        shutil.copy(new_path, archive_path)
                        archive_link = str(archive_path)

                    results.append({
                        'Date': current_date,
                        'Company Name': company,
                        'URL': url,
                        'Role': role,
                        'Status': status,
                        'Visa Sponsorship': visa_status,
                        'Visa Evidence': evidence_text,
                        'Archive': archive_link
                    })

                st.markdown(f"**Scan Summary:** {len(results) - error_count} successful | {error_count} failed")

                if results:
                    df_results = pd.DataFrame(results)
                    if OUTPUT_FILE.exists():
                        existing = pd.read_excel(OUTPUT_FILE)
                        df_results = pd.concat([existing, df_results], ignore_index=True)
                    df_results.to_excel(OUTPUT_FILE, index=False)

                    shutil.rmtree(OLD_SNAPSHOT_DIR, ignore_errors=True)
                    shutil.copytree(LATEST_SNAPSHOT_DIR, OLD_SNAPSHOT_DIR, dirs_exist_ok=True)
                    shutil.rmtree(LATEST_SNAPSHOT_DIR, ignore_errors=True)
                    LATEST_SNAPSHOT_DIR.mkdir(exist_ok=True)

                    st.session_state['latest_results'] = df_results

                    st.success("Monitoring complete!")

                    # ── NEW: Table showing only NEW / CHANGED unique instances ──────
                    st.subheader("New / Changed Information (Unique Instances Only)")
                    changed_df = df_results[df_results['Status'].str.contains("Change|First", na=False)]
                    if not changed_df.empty:
                        # Remove duplicates within this run (unique by Company + URL + Role)
                        changed_unique = changed_df.drop_duplicates(subset=['Company Name', 'URL', 'Role'])
                        st.dataframe(changed_unique, use_container_width=True)
                    else:
                        st.info("No new or changed pages detected in this run.")

                    # Full results (for reference)
                    st.subheader("Full Scan Results")
                    st.dataframe(df_results, use_container_width=True)
                else:
                    st.error("No results generated – check URLs and network.")
# ── History & Archives Tab ─────────────────────────────────────────────────────
with tab_history:
    st.header("📜 History & Archives")
    if OUTPUT_FILE.exists():
        df_history = pd.read_excel(OUTPUT_FILE)
        st.dataframe(df_history.sort_values('Date', ascending=False), use_container_width=True)
    else:
        st.info("No history yet. Run monitoring first.")

# ── Sidebar ────────────────────────────────────────────────────────────────────
st.sidebar.markdown("---")
if st.sidebar.button("🚪 Logout"):
    st.session_state["authenticated"] = False
    st.rerun()

st.sidebar.info("Your personal job posting monitor – updated January 13, 2026")
