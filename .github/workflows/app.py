import streamlit as st
import os
import shutil
import datetime
import requests
import pandas as pd
from pathlib import Path
import hmac

# Page config (must be first)
st.set_page_config(page_title="Job Posting Monitor", layout="wide")

# --- Authentication Function ---
def check_password():
    """Returns `True` if the user had the correct password."""

    def password_entered():
        """Checks whether a password entered by the user is correct."""
        if hmac.compare_digest(
            st.session_state["password"],
            st.secrets["auth"]["password"]
        ) and st.session_state["username"] == st.secrets["auth"]["username"]:
            st.session_state["authenticated"] = True
            del st.session_state["password"]  # Don't store password
        else:
            st.session_state["authenticated"] = False

    # First run or not authenticated
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if not st.session_state["authenticated"]:
        with st.form("Login"):
            st.text_input("Username", key="username")
            st.text_input("Password", type="password", key="password")
            st.form_submit_button("Login", on_click=password_entered)

        if st.session_state["authenticated"] == False:
            st.error("Invalid username or password")
        return False
    else:
        # Optional: Add a logout button in the sidebar later
        return True

# --- If authenticated, show the main app ---
if check_password():
    st.title("Automated Job Posting Monitor")
    st.markdown("""
    This app monitors company job pages for changes (potential new postings).  
    Add/edit targets below, run the monitor, and view results/history.
    """)

    # Define directories
    BASE_DIR = Path(__file__).parent
    LATEST_SNAPSHOT_DIR = BASE_DIR / 'Latest_Snapshot'
    OLD_SNAPSHOT_DIR = BASE_DIR / 'Old_Snapshot'
    INPUT_FILE = BASE_DIR / 'targets.xlsx'
    OUTPUT_FILE = BASE_DIR / 'results.xlsx'

    # Ensure directories exist
    LATEST_SNAPSHOT_DIR.mkdir(exist_ok=True)
    OLD_SNAPSHOT_DIR.mkdir(exist_ok=True)

    # Sidebar for managing targets
    st.sidebar.header("Manage Monitoring Targets")
    st.sidebar.markdown("Add, edit, or delete company job pages to monitor.")

    if INPUT_FILE.exists():
        df_targets = pd.read_excel(INPUT_FILE)
    else:
        df_targets = pd.DataFrame(columns=['Company Name', 'URL', 'Role'])

    edited_df = st.data_editor(
        df_targets,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "Company Name": st.column_config.TextColumn(required=True),
            "URL": st.column_config.LinkColumn(required=True),
            "Role": st.column_config.TextColumn(required=True),
        }
    )

    if st.button("Save Targets"):
        if edited_df.duplicated(subset=['Company Name', 'Role']).any():
            st.error("Duplicate Company Name + Role combinations detected. Each must be unique.")
        elif edited_df.isnull().any().any():
            st.error("All fields are required. Please fill in all rows.")
        else:
            edited_df.to_excel(INPUT_FILE, index=False)
            st.success("Targets saved successfully!")
            st.rerun()

    # Main area: Run monitoring
    st.header("Run Monitoring")
    if st.button("Run Monitoring Now", type="primary"):
        if not INPUT_FILE.exists() or len(edited_df) == 0:
            st.warning("No targets defined. Add some targets first.")
        else:
            with st.spinner("Monitoring in progress... This may take a while."):
                current_date = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                results = []

                for _, row in edited_df.iterrows():
                    company = row['Company Name']
                    url = row['URL']
                    role = row['Role']

                    filename = f"{company.replace(' ', '_').replace('/', '-')}_{role.replace(' ', '_').replace('/', '-')}.html"
                    new_path = LATEST_SNAPSHOT_DIR / filename
                    old_path = OLD_SNAPSHOT_DIR / filename

                    try:
                        response = requests.get(url, timeout=15)
                        response.raise_for_status()
                        with open(new_path, 'w', encoding='utf-8') as f:
                            f.write(response.text)
                        snapshot_success = True
                    except Exception as e:
                        st.error(f"Error fetching {company} - {role}: {e}")
                        results.append({
                            'Company Name': company,
                            'URL': url,
                            'Role': role,
                            'Date': current_date,
                            'Status': f"Error: {e}"
                        })
                        continue

                    if not old_path.exists():
                        has_changed = True
                        status = "First snapshot taken (treated as change)"
                    else:
                        with open(old_path, 'r', encoding='utf-8') as old_f, open(new_path, 'r', encoding='utf-8') as new_f:
                            has_changed = old_f.read() != new_f.read()
                        status = "New posting detected!" if has_changed else "No change"

                    results.append({
                        'Company Name': company,
                        'URL': url,
                        'Role': role,
                        'Date': current_date,
                        'Status': status
                    })

                results_df = pd.DataFrame(results)
                if OUTPUT_FILE.exists():
                    existing_df = pd.read_excel(OUTPUT_FILE)
                    full_df = pd.concat([existing_df, results_df], ignore_index=True)
                else:
                    full_df = results_df
                full_df.to_excel(OUTPUT_FILE, index=False)

                if OLD_SNAPSHOT_DIR.exists():
                    shutil.rmtree(OLD_SNAPSHOT_DIR)
                shutil.copytree(LATEST_SNAPSHOT_DIR, OLD_SNAPSHOT_DIR)
                shutil.rmtree(LATEST_SNAPSHOT_DIR)
                LATEST_SNAPSHOT_DIR.mkdir(exist_ok=True)

                st.success("Monitoring complete!")
                st.subheader("Latest Run Results")
                st.dataframe(results_df, use_container_width=True)

    # History
    st.header("Monitoring History")
    if OUTPUT_FILE.exists():
        history_df = pd.read_excel(OUTPUT_FILE)
        if not history_df.empty:
            col1, col2 = st.columns(2)
            with col1:
                selected_company = st.multiselect("Filter by Company", options=["All"] + sorted(history_df['Company Name'].unique()))
            with col2:
                selected_status = st.multiselect("Filter by Status", options=["All"] + sorted(history_df['Status'].unique()))

            filtered_df = history_df
            if "All" not in selected_company and selected_company:
                filtered_df = filtered_df[filtered_df['Company Name'].isin(selected_company)]
            if "All" not in selected_status and selected_status:
                filtered_df = filtered_df[filtered_df['Status'].isin(selected_status)]

            st.dataframe(filtered_df.sort_values(by='Date', ascending=False), use_container_width=True)

            csv = filtered_df.to_csv(index=False).encode()
            st.download_button("Download Full History as CSV", csv, "job_monitor_history.csv", "text/csv")
        else:
            st.info("No results yet.")
    else:
        st.info("No results yet. Add targets and run monitoring.")

    st.markdown("""
    ### Notes
    - Change detection is based on full HTML comparison.
    - Errors (e.g., network issues) are logged.
    - Everything runs in the cloud – no installation needed!
    """)

    # Optional logout (in sidebar)
    st.sidebar.header("Account")
    if st.sidebar.button("Logout"):
        st.session_state["authenticated"] = False
        st.rerun()

else:
    # This else is for when not authenticated – the login form is already shown in check_password()
    pass
