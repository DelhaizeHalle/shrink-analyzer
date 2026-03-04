import streamlit as st
import pandas as pd
from supabase import create_client
import datetime
import numpy as np
from openai import OpenAI

# =====================
# CONFIG
# =====================

st.set_page_config(layout="wide")

SUPABASE_URL = "https://adivczeimpamlhgaxthw.supabase.co"
SUPABASE_KEY = "sb_publishable_YB09KMt3LV8ol4ieLdGk-Q_acNlGllI"

store_id = "delhaize_halle"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# =====================
# HELPERS
# =====================

def format_date_series(series):
    return pd.to_datetime(series, errors="coerce").dt.strftime("%d/%m/%Y")

# =====================
# LOGIN
# =====================

def login(email, password):
    try:
        res = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        if res.session:
            return res.session.user
    except:
        return None

if "user" not in st.session_state:
    st.session_state["user"] = None

if not st.session_state["user"]:

    st.sidebar.title("🔐 Login")

    email = st.sidebar.text_input("Email")
    password = st.sidebar.text_input("Wachtwoord", type="password")

    if st.sidebar.button("Login"):
        user = login(email, password)

        if user:
            st.session_state["user"] = user
            st.success("✅ Ingelogd")
            st.rerun()

        else:
            st.error("❌ Login mislukt")

    st.stop()

st.sidebar.success("✅ Ingelogd")
st.sidebar.markdown(f"👤 {st.session_state['user'].email}")

if st.sidebar.button("🚪 Logout"):
    st.session_state["user"] = None
    st.rerun()

# =====================
# DATA LOAD
# =====================

def fetch_all(table, columns):

    all_data = []
    start = 0
    batch = 1000

    while True:

        res = (
            supabase.table(table)
            .select(columns)
            .eq("store_id", store_id)
            .range(start, start + batch - 1)
            .execute()
        )

        data = res.data

        if not data:
            break

        all_data.extend(data)

        if len(data) < batch:
            break

        start += batch

    return pd.DataFrame(all_data)


@st.cache_data(ttl=60)
def load_data():

    weeks_cols = "jaar,week,maand,afdeling,shrink,sales"
    products_cols = "datum,product,hope,reden,stuks,euro"

    df_weeks = fetch_all("weeks", weeks_cols)
    df_products = fetch_all("shrink_data", products_cols)

    if not df_weeks.empty:
        df_weeks["shrink"] = pd.to_numeric(df_weeks["shrink"], errors="coerce").fillna(0)
        df_weeks["sales"] = pd.to_numeric(df_weeks["sales"], errors="coerce").fillna(0)

    if not df_products.empty:
        df_products["datum"] = pd.to_datetime(df_products["datum"], errors="coerce")
        df_products["stuks"] = pd.to_numeric(df_products["stuks"], errors="coerce").fillna(0)
        df_products["euro"] = pd.to_numeric(df_products["euro"], errors="coerce").fillna(0)
        df_products["reden"] = df_products["reden"].fillna("Onbekend")

    return df_weeks, df_products

df_weeks, df_products = load_data()

# =====================
# MENU
# =====================

menu = st.sidebar.radio("Menu", [
    "📊 Dashboard",
    "📦 Product analyse (PRO)",
    "➕ Data invoeren",
    "📤 Upload"
])

# =====================
# DASHBOARD
# =====================

if menu == "📊 Dashboard":

    st.title("📊 Weekly Shrink Dashboard")

    df = df_weeks.copy()

    if df.empty:
        st.warning("Geen data")
        st.stop()

    st.subheader("🎯 Afdeling")

    afdeling_opties = sorted(df["afdeling"].dropna().unique())

    col1, col2 = st.columns([1,3])

    with col1:
        select_all = st.checkbox("Alles", value=True)

    with col2:
        if select_all:
            selected = afdeling_opties
        else:
            selected = st.multiselect("Kies afdeling", afdeling_opties)

    if not selected:
        selected = afdeling_opties

    df = df[df["afdeling"].isin(selected)]

    total_shrink = df["shrink"].sum()
    total_sales = df["sales"].sum()

    shrink_pct = (total_shrink / total_sales * 100) if total_sales > 0 else 0

    weeks_sorted = sorted(df["week"].unique())

    latest_week = weeks_sorted[-1]
    previous_week = weeks_sorted[-2] if len(weeks_sorted) > 1 else latest_week

    current = df[df["week"] == latest_week]["shrink"].sum()
    previous = df[df["week"] == previous_week]["shrink"].sum()

    delta = current - previous

    col1,col2,col3,col4 = st.columns(4)

    col1.metric("💸 Totale shrink", f"€{total_shrink:.2f}")
    col2.metric("🛒 Totale sales", f"€{total_sales:.2f}")
    col3.metric("📊 Shrink %", f"{shrink_pct:.2f}%")
    col4.metric("📉 vs vorige week", f"€{current:.2f}", f"{delta:.2f}", delta_color="inverse")

    st.subheader("📈 Trend per week")

    weekly = df.groupby(["jaar","week"]).agg({
        "shrink":"sum",
        "sales":"sum"
    }).reset_index()

    weekly["shrink_pct"] = weekly["shrink"] / weekly["sales"] * 100

    weekly["label"] = weekly["jaar"].astype(str) + "-W" + weekly["week"].astype(str)
    weekly = weekly.set_index("label")

    st.line_chart(weekly["shrink_pct"])

# =====================
# PRODUCT ANALYSE
# =====================

elif menu == "📦 Product analyse (PRO)":

    st.title("📦 Shrink Intelligence Dashboard")

    df = df_products.copy()

    if df.empty:
        st.warning("Geen data")
        st.stop()

    st.subheader("🎯 Reden")

    redenen = sorted(df["reden"].unique())

    select_all = st.checkbox("Alles", value=True)

    if select_all:
        selected = redenen
    else:
        selected = st.multiselect("Kies reden", redenen)

    if not selected:
        selected = redenen

    df = df[df["reden"].isin(selected)]

    min_date = df["datum"].min()
    max_date = df["datum"].max()

    date_range = st.date_input("📅 Periode", [min_date, max_date])

    df = df[
        (df["datum"] >= pd.to_datetime(date_range[0])) &
        (df["datum"] <= pd.to_datetime(date_range[1]))
    ]

    # =====================
    # TOO GOOD TO GO
    # =====================

    # start van volledige dataset
    tg2g = df_products.copy()

    # datum correct zetten
    tg2g["datum"] = pd.to_datetime(tg2g["datum"], errors="coerce")

    # periode filter toepassen
    tg2g = tg2g[
        (tg2g["datum"] >= pd.to_datetime(date_range[0])) &
        (tg2g["datum"] <= pd.to_datetime(date_range[1]))
    ]

    # filter enkel verlies - anderen
    tg2g = tg2g[
        tg2g["reden"]
        .astype(str)
        .str.lower()
        .str.contains("anderen", na=False)
    ]

    # aantal pakketten = aantal stuks
    pakketten = tg2g["stuks"].sum()

    # prijs per pakket
    tg2g_prijs = 3.29

    # opbrengst
    tg2g_opbrengst = pakketten * tg2g_prijs

    # bruto verlies (van gefilterde data)
    bruto = df["euro"].sum()

    # netto verlies
    netto = bruto - tg2g_opbrengst

    # TG2G efficiëntie
    totale_waarde = tg2g["euro"].sum()
    tg2g_eff = (totale_waarde / bruto * 100) if bruto > 0 else 0

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("💸 Bruto verlies", f"€{bruto:.2f}")

    col2.metric(
        "📦 Too Good To Go",
        f"€{tg2g_opbrengst:.2f}",
        f"{int(pakketten)} pakketten"
    )

    col3.metric("💰 Netto verlies", f"€{netto:.2f}")

    col4.metric(
        "📊 TG2G efficiëntie",
        f"{tg2g_eff:.1f}%"
    )

    st.divider()

    st.subheader("📊 Verlies per reden")
    st.bar_chart(df.groupby("reden")["euro"].sum())

    st.subheader("📈 Trend per week")
    df["week"] = df["datum"].dt.isocalendar().week
    st.line_chart(df.groupby("week")["euro"].sum())

    st.subheader("💸 Grootste verlies per product")

    top_products = (
        df.groupby(["product","hope"])
        .agg({
            "stuks":"sum",
            "euro":"sum"
        })
        .reset_index()
        .sort_values("euro", ascending=False)
        .head(20)
    )

    st.dataframe(top_products, use_container_width=True, hide_index=True)








