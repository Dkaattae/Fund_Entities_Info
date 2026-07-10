import streamlit as st

pages = [
    st.Page("pages/1_Recently_Formed_Funds.py", title="Recently Formed Funds"),
    st.Page("pages/2_Service_Provider_Changes.py", title="Service Provider Changes"),
    st.Page("pages/3_Fund_Formation_by_Quarter.py", title="Fund Formation by Quarter"),
    st.Page("pages/4_First_Round_Fundraise.py", title="First Round Fundraise"),
    st.Page("pages/5_Fund_Closures.py", title="Fund Closures"),
    st.Page("pages/6_Nothing_Fund_Tracker.py", title="Nothing Fund Tracker"),
    st.Page("pages/7_Newly_Registered_State_RIAs.py", title="Newly Registered State RIAs"),
    st.Page("pages/8_Service_Provider_Directory.py", title="Service Provider Directory"),
    st.Page("pages/9_Auditor_Watch.py", title="Auditor Watch"),
    st.Page("pages/10_Missing_ERA_Filings.py", title="Missing ERA Filings"),
]

pg = st.navigation(pages)
pg.run()
