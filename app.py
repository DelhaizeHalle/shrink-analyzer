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


# 👉 NIET ingelogd
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


# 👉 WEL ingelogd
st.sidebar.success("✅ Ingelogd")
st.sidebar.markdown(f"👤 {st.session_state['user'].email}")

if st.sidebar.button("🚪 Logout"):
    st.session_state["user"] = None
    st.rerun()

# =====================
# DATA LOAD
# =====================

@st.cache_data(ttl=60)
def load_data():

    def fetch_all(table):

        all_data = []
        start = 0
        batch = 1000

        while True:

            res = (
                supabase.table(table)
                .select("*")
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

    return fetch_all("weeks"), fetch_all("shrink_data")


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

    # =====================
    # AFDELING FILTER
    # =====================

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

    df["shrink"] = pd.to_numeric(df["shrink"], errors="coerce").fillna(0)
    df["sales"] = pd.to_numeric(df["sales"], errors="coerce").fillna(0)

    # =====================
    # KPI HUIDIGE WEEK
    # =====================

    latest_week = df["week"].max()

    current_week = df[df["week"] == latest_week]

    week_shrink = current_week["shrink"].sum()
    week_sales = current_week["sales"].sum()

    shrink_pct = (week_shrink / week_sales * 100) if week_sales > 0 else 0

    col1,col2,col3 = st.columns(3)

    col1.metric(
        "💸 Shrink (huidige week)",
        f"€{week_shrink:,.2f}"
    )

    col2.metric(
        "🛒 Verkoop (huidige week)",
        f"€{week_sales:,.2f}"
    )

    col3.metric(
        "📊 Shrink %",
        f"{shrink_pct:.2f}%"
    )

    # =====================
    # TREND
    # =====================

    st.subheader("📈 Trend per week")

    weekly = df.groupby(["jaar","week"]).agg({
        "shrink":"sum",
        "sales":"sum"
    }).reset_index()

    weekly["label"] = weekly["jaar"].astype(str) + "-W" + weekly["week"].astype(str)
    weekly = weekly.set_index("label")

    st.line_chart(weekly[["shrink","sales"]])

# =====================
# PRODUCT ANALYSE
# =====================

elif menu == "📦 Product analyse (PRO)":

    st.title("📦 Shrink Intelligence Dashboard")

    df = df_products.copy()

    if df.empty:
        st.warning("Geen data")
        st.stop()

    df["reden"] = df["reden"].fillna("Onbekend")
    df["datum"] = pd.to_datetime(df["datum"], errors="coerce")

    df = df[df["datum"].notna()]

    df["stuks"] = pd.to_numeric(df["stuks"], errors="coerce").fillna(0)
    df["euro"] = pd.to_numeric(df["euro"], errors="coerce").fillna(0)

    # =====================
    # REDEN FILTER
    # =====================

    st.subheader("🎯 Reden")

    reden_opties = sorted(df["reden"].unique())

    select_all = st.checkbox("Alles", value=True)

    if select_all:
        selected = reden_opties
    else:
        selected = st.multiselect("Kies reden", reden_opties)

    if not selected:
        selected = reden_opties

    df = df[df["reden"].isin(selected)]

    # =====================
    # DATUM FILTER
    # =====================

    min_date = df["datum"].min()
    max_date = df["datum"].max()

    date_range = st.date_input("📅 Periode", [min_date, max_date])

    df = df[
        (df["datum"] >= pd.to_datetime(date_range[0])) &
        (df["datum"] <= pd.to_datetime(date_range[1]))
    ]

    # =====================
    # HOPE ZOEK
    # =====================

    st.subheader("🔎 Zoek product (HOPE)")

    search_hope = st.text_input("Geef HOPE nummer")

    if search_hope:

        result = df[df["hope"].astype(str) == search_hope]

        if result.empty:
            st.warning("Geen product gevonden")

        else:

            st.success(f"{len(result)} records gevonden")

            col1,col2 = st.columns(2)

            col1.metric("📦 Totaal stuks", int(result["stuks"].sum()))
            col2.metric("💸 Totaal verlies", f"€{result['euro'].sum():.2f}")

            st.write("**Product:**", result["product"].iloc[0])

            st.subheader("📊 Verlies per reden")
            st.bar_chart(result.groupby("reden")["euro"].sum())

            st.subheader("📅 Verlies over tijd")
            st.line_chart(result.groupby("datum")["euro"].sum())

            st.dataframe(result.sort_values("datum", ascending=False))

    # =====================
    # TG2G
    # =====================

    tg2g = df[df["reden"].str.contains("ANDEREN", case=False)]

    pakketten = tg2g["stuks"].sum()

    tg2g_opbrengst = pakketten * 3.29

    bruto = df["euro"].sum()

    netto = bruto - tg2g_opbrengst

    col1,col2,col3 = st.columns(3)

    col1.metric("💸 Bruto verlies", f"€{bruto:.2f}")

    col2.metric(
        "📦 Too Good To Go",
        f"€{tg2g_opbrengst:.2f}",
        f"{int(pakketten)} pakketten"
    )

    col3.metric("💰 Netto verlies", f"€{netto:.2f}")

# =====================
# DATA INVOEREN
# =====================

elif menu == "➕ Data invoeren":

    st.title("➕ Weeks invoer")

    today = datetime.datetime.now()

    jaar = st.number_input("Jaar", value=today.year)
    maand = st.number_input("Maand", value=today.month)
    week = st.number_input("Week", value=today.isocalendar()[1])

    afdeling = st.text_input("Afdeling")

    shrink = st.number_input("Shrink €")
    sales = st.number_input("Sales €")

    if st.button("💾 Opslaan"):

        supabase.table("weeks").insert({
            "store_id":store_id,
            "jaar":int(jaar),
            "maand":int(maand),
            "week":int(week),
            "afdeling":afdeling,
            "shrink":float(shrink),
            "sales":float(sales)
        }).execute()

        st.success("✅ Opgeslagen")

        st.cache_data.clear()
