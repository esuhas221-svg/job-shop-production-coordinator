import streamlit as st
import requests
import pandas as pd

API_URL = "http://localhost:8000"

st.set_page_config(layout="wide", page_title="Job Shop Production Coordinator")
st.title("🏭 Smart Job Shop Production Coordinator")

try:
    r = requests.get(f"{API_URL}/orders", timeout=2)
    st.sidebar.success("🟢 API Live")
except:
    st.sidebar.error("🔴 API Down - start backend first")

st.subheader("🤖 Agent Commander")
user_input = st.text_input("Enter natural language command:", placeholder="e.g., new order from ABC Corp: 50 units of part B-789 due by April 15")
if st.button("Execute"):
    if user_input:
        with st.spinner("Agents working..."):
            resp = requests.post(f"{API_URL}/agent/command", json={"text": user_input})
            if resp.status_code == 200:
                st.json(resp.json())
                st.success("Workflow executed")
            else:
                st.error(f"Error: {resp.text}")

col1, col2, col3 = st.columns(3)
with col1:
    st.subheader("📅 Calendar (MCP)")
    cal = requests.get(f"{API_URL}/calendar").json()
    if cal:
        st.dataframe(pd.DataFrame(cal)[["title","start","end"]])
    else:
        st.info("No calendar events")
with col2:
    st.subheader("✅ Task Manager (MCP)")
    tasks = requests.get(f"{API_URL}/tasks").json()
    if tasks:
        st.dataframe(pd.DataFrame(tasks)[["title","priority","status","due_date"]])
    else:
        st.info("No tasks")
with col3:
    st.subheader("📝 Notes (MCP)")
    notes = requests.get(f"{API_URL}/notes").json()
    if notes:
        for n in notes[-5:]:
            st.write(f"- {n['content'][:80]}...")
    else:
        st.info("No notes")

st.subheader("🗄️ Database Viewer")
tab1, tab2 = st.tabs(["Orders", "Inventory"])
with tab1:
    orders = requests.get(f"{API_URL}/orders").json()
    if orders:
        st.dataframe(pd.DataFrame(orders))
    else:
        st.info("No orders")
with tab2:
    inv = requests.get(f"{API_URL}/inventory").json()
    if inv:
        st.dataframe(pd.DataFrame(inv))
    else:
        st.info("No inventory")
