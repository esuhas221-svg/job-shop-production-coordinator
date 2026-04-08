import streamlit as st
import sqlite3
import pandas as pd
import json
from pathlib import Path

st.set_page_config(layout="wide")
st.title("🏭 Smart Job Shop Production Coordinator (Direct DB)")

DB_PATH = Path(__file__).parent.parent / "data" / "jobshop.db"
DATA_DIR = Path(__file__).parent.parent / "data"

@st.cache_data(ttl=5)
def get_orders():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM orders ORDER BY id DESC", conn)
    conn.close()
    return df

@st.cache_data(ttl=5)
def get_inventory():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM inventory", conn)
    conn.close()
    return df

def get_calendar():
    f = DATA_DIR / "calendar.json"
    if f.exists():
        return pd.DataFrame(json.loads(f.read_text()))
    return pd.DataFrame()

def get_tasks():
    f = DATA_DIR / "tasks.json"
    if f.exists():
        return pd.DataFrame(json.loads(f.read_text()))
    return pd.DataFrame()

def get_notes():
    f = DATA_DIR / "notes.json"
    if f.exists():
        return pd.DataFrame(json.loads(f.read_text()))
    return pd.DataFrame()

st.subheader("📊 Database Status")
orders_df = get_orders()
inv_df = get_inventory()
col1, col2 = st.columns(2)
col1.metric("Total Orders", len(orders_df))
col2.metric("Inventory Items", len(inv_df))

c1, c2, c3 = st.columns(3)
with c1:
    st.subheader("📅 Calendar")
    cal = get_calendar()
    if not cal.empty:
        st.dataframe(cal[["title","start","end"]])
    else:
        st.info("No calendar events")
with c2:
    st.subheader("✅ Tasks")
    tasks = get_tasks()
    if not tasks.empty:
        st.dataframe(tasks[["title","priority","status","due_date"]])
    else:
        st.info("No tasks")
with c3:
    st.subheader("📝 Notes")
    notes = get_notes()
    if not notes.empty:
        for _, n in notes.tail(5).iterrows():
            st.write(f"- {n['content'][:80]}...")
    else:
        st.info("No notes")

st.subheader("🗄️ Database Tables")
tab1, tab2 = st.tabs(["Orders", "Inventory"])
with tab1:
    if not orders_df.empty:
        st.dataframe(orders_df)
    else:
        st.info("No orders found")
with tab2:
    if not inv_df.empty:
        st.dataframe(inv_df)
    else:
        st.info("No inventory found")
