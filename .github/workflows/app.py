import streamlit as st
import os
import shutil
import datetime
import requests
import pandas as pd
from pathlib import Path
import hmac
from screenshotone import Client, TakeOptions

# Page config - wide layout for better use of space
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
    st.stop()  # Stop execution until authenticated

# Main App
st.title("🔍 Automated Job Posting Monitor")
st.markdown("""
Welcome to your personal job monitoring dashboard!  
Track changes on company career pages and get visual alerts (screenshots) when new postings appear.
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

# Use tabs for main sections
tab_overview, tab_targets, tab_run, tab_history = st.tabs([
    "📊 Overview", 
    "🎯 Manage Targets", 
    "🚀 Run Monitoring", 
    "📜 History & Screenshots"
])

with tab_overview:
    st.header("Dashboard Overview")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Targets Being Monitored", len(df_targets))
    with col2:
        if OUTPUT_FILE.exists():
            history_df = pd.read_excel(OUTPUT_FILE)
            changes = len(history_df[history_df['Status'].str.contains("Change|First", na=False)])
            st.metric("Total Changes Detected", changes)
        else:
            st.metric("Total Changes Detected", 0)
    with col3:
        if OUTPUT_FILE.exists():
            last_run = pd.read_excel(OUTPUT_FILE)['Date'].max()
            st.metric("Last Run", last_run if pd.notna(last_run) else "Never")
        else:
            st.metric("Last Run", "Never")

    st.markdown("### Quick Tips")
    with st.expander("How to use this app effectively"):
        st.write("""
        - Add company career pages (not single-job links) in **Manage Targets**.
        - Click **Run Monitoring** daily or whenever you want to check.
        - View changes with screenshots in **History & Screenshots**.
        - Screenshots are taken automatically on changes (optional).
        """)

with tab_targets:
    st.header("🎯 Manage Monitoring Targets")
    st.markdown("Add, edit, or delete job pages you want to track. Use company career pages for best results.")

    edited_targets = st.data_editor(
        df_targets,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "Company Name": st.column_config.TextColumn("Company Name", required=True),
            "URL": st.column_config.LinkColumn("Career Page URL", required=True),
            "Role": st.column_config.TextColumn("Role/Keyword", required=True),
        }
    )

    col_save, col_info = st.columns([1, 3])
    with col_save:
        if st.button("💾 Save Targets", type="primary", use_container_width=True):
            if edited_targets.duplicated(subset=['Company Name', 'Role']).any():
                st.error("Duplicate Company + Role combinations found. Each must be unique.")
            elif edited_targets.isnull().values.any():
                st.error("All fields are required.")
            else:
                edited_targets.to_excel(INPUT_FILE, index=False)
                st.success("Targets saved successfully!")
                st.rerun()
    with col_info:
        st.info("Tip: Use direct company career URLs (e.g., google.com/careers) to avoid blocking.")

with tab_run:
    st.header("🚀 Run Monitoring Check")
    st.markdown("Click below to scan all targets for changes. This may take a minute.")

    take_screenshots = st.checkbox("📸 Take screenshots on changes/first run (uses free API credits)", value=True)

    if st.button("🔄 Run Monitoring Now", type="primary", use_container_width=True):
        if len(edited_targets) == 0:
            st.warning("No targets added yet. Go to **Manage Targets** first.")
        else:
            with st.spinner("Fetching pages and comparing..."):
                current_date = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                results = []
                screenshot_client = None
                if take_screenshots:
                    try:
                        screenshot_client = Client(st.secrets["screenshotone"]["access_key"], st.secrets["screenshotone"]["secret_key"])
                    except Exception:
                        st.warning("Screenshot API keys missing. Screenshots disabled.")

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
                        with open(new_path, 'w', encoding='utf-8') as f:
                            f.write(response.text)
                    except Exception as e:
                        results.append({'Company Name': company, 'URL': url, 'Role': role, 'Date': current_date, 'Status': f"Error: {e}", 'Screenshot': None})
                        continue

                    if not old_path.exists():
                        has_changed = True
                        status = "First snapshot taken"
                    else:
                        with open(old_path, 'r', encoding='utf-8') as old_f, open(new_path, 'r', encoding='utf-8') as new_f:
                            has_changed = old_f.read() != new_f.read()
                        status = "Change detected! 🚨" if has_changed else "No change"

                    screenshot_path = None
                    if has_changed and take_screenshots and screenshot_client:
                        try:
                            options = TakeOptions.url(url).full_page(True).block_cookie_banners(True)
                            image = screenshot_client.take(options)
                            screenshot_filename = f"{current_date.replace(':', '-')}_{company}_{role}.png"
                            screenshot_path = SCREENSHOTS_DIR / screenshot_filename
                            with open(screenshot_path, 'wb') as f:
                                f.write(image.read())
                            status += " (Screenshot captured)"
                        except Exception as e:
                            st.warning(f"Screenshot failed for {company}: {e}")

                    results.append({'Company Name': company, 'URL': url, 'Role': role, 'Date': current_date, 'Status': status, 'Screenshot': str(screenshot_path) if screenshot_path else None})

                # Save results
                results_df = pd.DataFrame(results)
                if OUTPUT_FILE.exists():
                    existing = pd.read_excel(OUTPUT_FILE)
                    full_df = pd.concat([existing, results_df], ignore_index=True)
                else:
                    full_df = results_df
                full_df.to_excel(OUTPUT_FILE, index=False)

                # Move snapshots
                shutil.rmtree(OLD_SNAPSHOT_DIR)
                shutil.copytree(LATEST_SNAPSHOT_DIR, OLD_SNAPSHOT_DIR)
                shutil.rmtree(LATEST_SNAPSHOT_DIR)
                LATEST_SNAPSHOT_DIR.mkdir()

                st.success("Monitoring complete!")
                st.subheader("Latest Run Results")
                st.dataframe(results_df, use_container_width=True)

with tab_history:
    st.header("📜 Monitoring History")
    if OUTPUT_FILE.exists() and not pd.read_excel(OUTPUT_FILE).empty:
        history_df = pd.read_excel(OUTPUT_FILE)

        st.subheader("Edit / Clean History")
        st.markdown("You can delete old rows or edit entries here.")
        edited_history = st.data_editor(
            history_df.sort_values('Date', ascending=False),
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Screenshot": st.column_config.ImageColumn("Screenshot Preview", width="medium"),
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

        st.markdown("### Screenshots of Changes")
        change_rows = filtered[filtered['Status'].str.contains("Change|First", na=False)]
        if not change_rows.empty:
            for _, row in change_rows.iterrows():
                if pd.notna(row['Screenshot']) and os.path.exists(row['Screenshot']):
                    st.image(row['Screenshot'], caption=f"{row['Company Name']} - {row['Role']} ({row['Date']})", use_column_width=True)
        else:
            st.info("No changes with screenshots yet.")

        csv = filtered.to_csv(index=False).encode()
        st.download_button("📥 Download Filtered History (CSV)", csv, "job_monitor_history.csv")
    else:
        st.info("No history yet. Add targets and run monitoring first.")

# Sidebar footer
st.sidebar.markdown("---")
st.sidebar.header("Account")
if st.sidebar.button("🚪 Logout"):
    st.session_state["authenticated"] = False
    st.rerun()

st.sidebar.info("App runs in the cloud – check anytime from any device!")
