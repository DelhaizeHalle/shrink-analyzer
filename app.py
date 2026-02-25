import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from supabase import create_client
import datetime

st.set_page_config(layout="wide")

# =====================
# CONFIG
# =====================

SUPABASE_URL = "https://adivczeimpamlhgaxthw.supabase.co"
SUPABASE_KEY = "sb_publishable_YB09KMt3LV8ol4ieLdGk-Q_acNlGllI"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

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

if not st.session_state["user"]:
    st.stop()

user_id = str(st.session_state["user"].id)

# =====================
# DATA LOAD (PAGINATION)
# =====================

@st.cache_data(ttl=60)
def load_data(user_id):

    def fetch_all(table_name):
        all_data = []
        batch_size = 1000
        start = 0

        while True:
            res = (
                supabase.table(table_name)
                .select("*")
                .eq("user_id", user_id)
                .range(start, start + batch_size - 1)
                .execute()
            )

            data = res.data

            if not data:
                break

            all_data.extend(data)

            if len(data) < batch_size:
                break

            start += batch_size

        return pd.DataFrame(all_data)

    return fetch_all("weeks"), fetch_all("shrink_data")

df_weeks, df_products = load_data(user_id)

# =====================
# MENU
# =====================

menu = st.sidebar.radio("Menu", [
    "📊 Dashboard",
    "➕ Data invoeren",
    "📤 Upload",
    "📦 Product analyse (PRO)"
])

# =====================
# PRO DASHBOARD
# =====================

if menu == "📦 Product analyse (PRO)":

    st.title("📦 Shrink Intelligence Dashboard")

    if df_products.empty:
        st.warning("Geen data")
        st.stop()

    df = df_products.copy()

    # =====================
    # FILTERS
    # =====================

    col1, col2 = st.columns(2)

    with col1:
        reden_opties = sorted(df["reden"].dropna().unique())
        selected_redenen = st.multiselect(
            "🎯 Reden",
            opties := reden_opties,
            default=opties
        )

    with col2:
        df["datum"] = pd.to_datetime(df["datum"])
        min_date = df["datum"].min()
        max_date = df["datum"].max()

        date_range = st.date_input(
            "📅 Periode",
            [min_date, max_date]
        )

    # filters toepassen
    df = df[df["reden"].isin(selected_redenen)]

    df = df[
        (df["datum"] >= pd.to_datetime(date_range[0])) &
        (df["datum"] <= pd.to_datetime(date_range[1]))
    ]

    df["stuks"] = pd.to_numeric(df["stuks"], errors="coerce").fillna(0)
    df["euro"] = pd.to_numeric(df["euro"], errors="coerce").fillna(0)

    # =====================
    # KPI
    # =====================

    total_euro = df["euro"].sum()
    total_stuks = df["stuks"].sum()
    unique_products = df["product"].nunique()

    col1, col2, col3 = st.columns(3)

    col1.metric("💸 Totale verlies (€)", f"€{total_euro:.2f}")
    col2.metric("📦 Aantal stuks", int(total_stuks))
    col3.metric("🛒 Unieke producten", unique_products)

    # =====================
    # VERLIES PER REDEN
    # =====================

    st.subheader("📊 Verlies per reden")

    verlies_per_reden = (
        df.groupby("reden")["euro"]
        .sum()
        .sort_values(ascending=False)
    )

    st.bar_chart(verlies_per_reden)

    if not verlies_per_reden.empty:
        top_reason = verlies_per_reden.idxmax()
        top_value = verlies_per_reden.max()

        st.metric("🔥 Grootste verlies reden", top_reason, f"€{top_value:.2f}")

    # =====================
    # TREND PER WEEK
    # =====================

    st.subheader("📈 Trend per week")

    df["week"] = df["datum"].dt.isocalendar().week

    trend = df.groupby("week")["euro"].sum()

    st.line_chart(trend)

    # =====================
    # TOP PRODUCTEN
    # =====================

    st.subheader("🏆 Top producten")

    top_products = (
        df.groupby("product")
        .agg({"stuks": "sum", "euro": "sum"})
        .sort_values("euro", ascending=False)
        .head(20)
    )

    st.dataframe(top_products)

    # =====================
    # DATA
    # =====================

    st.subheader("📋 Data")

    st.dataframe(df.head(200))

# =====================
# UPLOAD (zelfde als eerder)
# =====================

elif menu == "📤 Upload":

    st.title("Upload Excel")

    file = st.file_uploader("Upload Excel", type=["xlsx"])

    if file:

        df = pd.read_excel(file)
        df.columns = df.columns.str.strip()

        df = df.rename(columns={
            "Datum": "datum",
            "Benaming": "product",
            "Reden / Winkel": "reden",
            "Hoeveelheid": "stuks",
            "Totale prijs": "euro"
        })

        df["datum"] = pd.to_datetime(df["datum"], errors="coerce")
        df = df[df["datum"].notna()]

        df["week"] = df["datum"].dt.isocalendar().week.astype(int)
        df["jaar"] = df["datum"].dt.year.astype(int)
        df["maand"] = df["datum"].dt.month.astype(int)

        df["stuks"] = pd.to_numeric(df["stuks"], errors="coerce").fillna(0)
        df["euro"] = pd.to_numeric(df["euro"], errors="coerce").fillna(0)

        df["product"] = df["product"].astype(str).str.upper().str.strip()

        df = df[[
            "datum", "week", "jaar", "maand",
            "product", "reden", "stuks", "euro"
        ]]

        df["user_id"] = user_id
        df["categorie"] = "ONBEKEND"

        data = df.to_dict(orient="records")

        for i in range(0, len(data), 500):
            supabase.table("shrink_data").insert(data[i:i+500]).execute()

        st.success("Upload klaar")
