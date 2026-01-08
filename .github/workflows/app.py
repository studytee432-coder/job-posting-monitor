import streamlit as st
import os
import shutil
import datetime
import requests
import pandas as pd
from pathlib import Path
import hmac
from screenshotone import Client, TakeOptions

# Page config
st.set_page_config(page_title="Job Posting Monitor", layout="wide")

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
        with st.form("Login"):
            st.text_input("Username", key="username")
            st.text_input("Password", type="password", key="password")
            st.form_submit_button("Login", on_click=password_entered)

        if st.session_state.get("authenticated") == False:
            st.error("Invalid username or password")
        return False
    else:
        return True

if check_password():
    st.title("Automated Job Posting Monitor")
    st.markdown("""
    Monitor job pages for changes. Now with screenshots on changes, and editable history!
    """)

    # Directories
    BASE_DIR = Path(__file__).parent
    LATEST_SNAPSHOT_DIR = BASE_DIR / 'Latest_Snapshot'
    OLD_SNAPSHOT_DIR = BASE_DIR / 'Old_Snapshot'
    SCREENSHOTS_DIR = BASE_DIR / 'Screenshots'
    INPUT_FILE = BASE_DIR / 'targets.xlsx'
    OUTPUT_FILE = BASE_DIR / 'results.xlsx'

    LATEST_SNAPSHOT_DIR.mkdir(exist_ok=True)
    OLD_SNAPSHOT_DIR.mkdir(exist_ok=True)
    SCREENSHOTS_DIR.mkdir(exist_ok=True)

    # Sidebar: Targets
    st.sidebar.header("Manage Targets")
    if INPUT_FILE.exists():
        df_targets = pd.read_excel(INPUT_FILE)
    else:
        df_targets = pd.DataFrame(columns=['Company Name', 'URL', 'Role'])

    edited_targets = st.data_editor(
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
        if edited_targets.duplicated(subset=['Company Name', 'Role']).any():
            st.error("Duplicates detected.")
        elif edited_targets.isnull().any().any():
            st.error("Fill all fields.")
        else:
            edited_targets.to_excel(INPUT_FILE, index=False)
            st.success("Saved!")
            st.rerun()

    # Run Monitoring
    st.header("Run Monitoring")
    take_screenshots = st.checkbox("Take screenshots on changes (uses API credits)", value=True)

    if st.button("Run Now", type="primary"):
        if not INPUT_FILE.exists() or len(edited_targets) == 0:
            st.warning("No targets.")
        else:
            with st.spinner("Running..."):
                current_date = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                results = []
                screenshot_client = None
                if take_screenshots:
                    try:
                        screenshot_client = Client(st.secrets["screenshotone"]["access_key"], st.secrets["screenshotone"]["secret_key"])
                    except:
                        st.warning("Screenshot API keys not set in secrets. Screenshots disabled.")

                for _, row in edited_targets.iterrows():
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
                    except Exception as e:
                        st.error(f"Error fetching {company} - {role}: {e}")
                        results.append({'Company Name': company, 'URL': url, 'Role': role, 'Date': current_date, 'Status': f"Error: {e}", 'Screenshot': None})
                        continue

                    if not old_path.exists():
                        has_changed = True
                        status = "First snapshot"
                    else:
                        with open(old_path, 'r', encoding='utf-8') as old_f, open(new_path, 'r', encoding='utf-8') as new_f:
                            has_changed = old_f.read() != new_f.read()
                        status = "Change detected!" if has_changed else "No change"

                    screenshot_path = None
                    if has_changed and take_screenshots and screenshot_client:
                        try:
                            options = TakeOptions.url(url).format("png").viewport_width(1280).viewport_height(1024).block_cookie_banners(True)
                            image = screenshot_client.take(options)
                            screenshot_filename = f"{company}_{role}_{current_date.replace(':', '-')}.png"
                            screenshot_path = str(SCREENSHOTS_DIR / screenshot_filename)
                            with open(screenshot_path, 'wb') as f:
                                shutil.copyfileobj(image, f)
                            status += " (Screenshot taken)"
                        except Exception as e:
                            st.warning(f"Screenshot failed for {company}: {e}")

                    results.append({'Company Name': company, 'URL': url, 'Role': role, 'Date': current_date, 'Status': status, 'Screenshot': screenshot_path})

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

                st.success("Complete!")
                st.subheader("Latest Results")
                st.dataframe(results_df)

    # History Management
    st.header("Monitoring History")
    if OUTPUT_FILE.exists():
        history_df = pd.read_excel(OUTPUT_FILE)
        if not history_df.empty:
            st.subheader("Edit History (Delete/Edit Rows)")
            edited_history = st.data_editor(
                history_df,
                num_rows="dynamic",
                use_container_width=True,
                hide_index=False,
                column_config={
                    "Screenshot": st.column_config.ImageColumn("Screenshot Preview", width="small"),
                }
            )

            if st.button("Save Edited History"):
                edited_history.to_excel(OUTPUT_FILE, index=False)
                st.success("History updated!")
                st.rerun()

            # Display with filters
            col1, col2 = st.columns(2)
            selected_company = st.multiselect("Filter Company", ["All"] + sorted(history_df['Company Name'].unique()))
            selected_status = st.multiselect("Filter Status", ["All"] + sorted(history_df['Status'].unique()))

            filtered_df = history_df
            if "All" not in selected_company and selected_company:
                filtered_df = filtered_df[filtered_df['Company Name'].isin(selected_company)]
            if "All" not in selected_status and selected_status:
                filtered_df = filtered_df[filtered_df['Status'].isin(selected_status)]

            st.dataframe(filtered_df.sort_values('Date', ascending=False))

            # Show screenshots
            for _, row in filtered_df.iterrows():
                if pd.notna(row.get('Screenshot')):
                    st.image(row['Screenshot'], caption=f"Screenshot for {row['Company Name']} - {row['Date']}")

            csv = filtered_df.to_csv(index=False).encode()
            st.download_button("Download CSV", csv, "history.csv")

        else:
            st.info("No history.")
    else:
        st.info("No history. Run monitoring.")

    st.markdown("""
    ### Notes
    - Screenshots via ScreenshotOne API (100 free/month). Add keys to secrets.toml:
      [screenshotone]
      access_key = "your_access_key"
      secret_key = "your_secret_key"
    - Sign up at screenshotone.com for keys.
    - History editable: delete/edit rows above and save.
    """)

    st.sidebar.header("Account")
    if st.sidebar.button("Logout"):
        st.session_state["authenticated"] = False
        st.rerun()
