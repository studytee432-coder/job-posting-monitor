import streamlit as st
import pandas as pd

st.set_page_config(page_title="Job Posting Monitor", layout="wide")

# --- SIDEBAR NAVIGATION ---
st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to", ["Project Dashboard", "Project Proposal", "Run Logs"])

if page == "Project Dashboard":
    st.title("🎯 Job Posting Monitor")
    st.write("View the latest status of monitored company career pages.")
    
    # Example table display
    try:
        df = pd.read_excel("output.xls")
        st.dataframe(df, use_container_width=True)
    except:
        st.info("No output data found. Run the scraper to generate results.")

elif page == "Project Proposal":
    st.title("📄 Project Proposal")
    st.subheader("Automated Job Posting Monitoring Script")

    # Organize content into Tabs for easy navigation
    tab1, tab2, tab3, tab4 = st.tabs([
        "🚀 Overview & Vision", 
        "📋 Business Case & Objectives", 
        "⚙️ Technical Solution", 
        "✨ Enhancements & Conclusion"
    ])

    with tab1:
        st.header("1.0 Project Overview and Vision")
        st.write("""
        In today's fast-paced environment, the ability to automate repetitive tasks is a strategic advantage. 
        This script replaces manual workflows with a reliable, efficient, and fully automated system to monitor 
        multiple web pages for key changes in job postings.
        """)

    with tab2:
        st.header("2.0 Problem Statement")
        st.info("Manual checking is tedious, resource-intensive, and susceptible to mistakes like missed updates.")
        
        st.header("3.0 Core Project Objectives")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("### 🔍 Analysis")
            st.write("- Automated Web Page Analysis\n- Snapshot-Based Detection")
        with col2:
            st.markdown("### 📊 Reporting")
            st.write("- Structured Excel Reporting\n- Systematic State Management")

    with tab3:
        st.header("4.0 Technical Solution & Process Flow")
        
        with st.expander("4.1 Input and Configuration", expanded=True):
            st.write("Managed via `Input.xls` containing: **Company Name, URL, and Role.**")
            
        with st.expander("4.2 Core Processing Logic"):
            st.steps([
                "Initialization (Folder Setup)",
                "URL Processing",
                "Snapshot Capture",
                "Change Detection (Comparison)",
                "Output Generation"
            ])

        with st.expander("4.3 Post-Execution Management"):
            st.write("Archives latest snapshots to the 'Old' folder to prepare for the next run.")

    with tab4:
        st.header("5.0 Optional Enhancements")
        st.success("**5.1 Automated Email Notification:** Delivery of reports directly to stakeholders.")
        st.success("**5.2 Scheduled Daily Execution:** Fully autonomous 'hands-off' operation.")
        
        st.header("6.0 Conclusion")
        st.write("This solution provides significant time savings and improved accuracy in job tracking.")

elif page == "Run Logs":
    st.title("📜 Execution Logs")
    st.write("Check the GitHub Action logs for detailed scraping history.")
    st.markdown("[View GitHub Actions](https://github.com/studytee432-coder/job-posting-monitor/actions)")
