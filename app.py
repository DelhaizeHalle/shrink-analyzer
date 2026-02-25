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
    "📦 Product analyse (PRO)",
    "➕ Data invoeren",
    "📤 Upload"
])

# =====================
# DASHBOARD
# =====================

if menu == "📊 Dashboard":

    st.title("📊 Weekly Shrink Dashboard")

    if df_weeks.empty:
        st.warning("Geen data in weeks")
        st.stop()

    df = df_weeks.copy()

    df["shrink"] = pd.to_numeric(df["shrink"], errors="coerce").fillna(0)
    df["sales"] = pd.to_numeric(df["sales"], errors="coerce").fillna(0)

    # =====================
    # FILTER AFDELING (MET SELECT ALL)
    # =====================

    st.subheader("🎯 Filter afdeling")

    afdeling_opties = sorted(df["afdeling"].dropna().unique())

    col1, col2 = st.columns([1, 3])

    with col1:
        select_all = st.checkbox("Alles", value=True)

    with col2:
        if select_all:
            selected_afdeling = afdeling_opties
        else:
            selected_afdeling = st.multiselect(
                "Selecteer afdeling(en)",
                afdeling_opties
            )

    df = df[df["afdeling"].isin(selected_afdeling)]

    # =====================
    # KPI
    # =====================

    total_shrink = df["shrink"].sum()
    total_sales = df["sales"].sum()
    shrink_pct = (total_shrink / total_sales * 100) if total_sales > 0 else 0

    latest_week = df["week"].max()

    current_week = df[df["week"] == latest_week]
    previous_week = df[df["week"] == latest_week - 1]

    current_shrink = current_week["shrink"].sum()
    previous_shrink = previous_week["shrink"].sum()

    delta = current_shrink - previous_shrink

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("💸 Totale shrink", f"€{total_shrink:.2f}")
    col2.metric("🛒 Totale sales", f"€{total_sales:.2f}")
    col3.metric("📊 Shrink %", f"{shrink_pct:.2f}%")
    col4.metric("📉 vs vorige week", f"€{current_shrink:.2f}", f"{delta:.2f}")

    # =====================
    # PER AFDELING
    # =====================

    st.subheader("🏬 Shrink per afdeling")

    dept = df.groupby("afdeling")[["shrink", "sales"]].sum()
    dept["shrink_pct"] = (dept["shrink"] / dept["sales"] * 100).fillna(0)

    st.dataframe(dept.sort_values("shrink", ascending=False))

    # =====================
    # TREND
    # =====================

    st.subheader("📈 Trend per week")

    weekly = df.groupby(["jaar", "week"]).agg({
        "shrink": "sum",
        "sales": "sum"
    }).reset_index()

    weekly["label"] = weekly["jaar"].astype(str) + "-W" + weekly["week"].astype(str)
    weekly = weekly.set_index("label")

    st.line_chart(weekly[["shrink", "sales"]])

    # =====================
    # TOP WEKEN
    # =====================

    st.subheader("🔥 Top verlies weken")

    weekly["shrink_pct"] = (weekly["shrink"] / weekly["sales"] * 100).fillna(0)

    st.dataframe(
        weekly.sort_values("shrink", ascending=False)
        [["shrink", "sales", "shrink_pct"]]
        .head(10)
    )

    # =====================
    # VERGELIJKING PER AFDELING
    # =====================

    st.subheader("⚖️ Verschil vs vorige week per afdeling")

    current = df[df["week"] == latest_week].groupby("afdeling")["shrink"].sum()
    previous = df[df["week"] == latest_week - 1].groupby("afdeling")["shrink"].sum()

    compare = pd.DataFrame({
        "current": current,
        "previous": previous
    }).fillna(0)

    compare["verschil"] = compare["current"] - compare["previous"]

    st.dataframe(compare.sort_values("verschil", ascending=False))

# =====================
# PRODUCT ANALYSE
# =====================

elif menu == "📦 Product analyse (PRO)":

    st.title("📦 Shrink Intelligence Dashboard")

    if df_products.empty:
        st.warning("Geen data")
        st.stop()

    df = df_products.copy()

    df["datum"] = pd.to_datetime(df["datum"])
    df["stuks"] = pd.to_numeric(df["stuks"], errors="coerce").fillna(0)
    df["euro"] = pd.to_numeric(df["euro"], errors="coerce").fillna(0)

    col1, col2 = st.columns(2)

    with col1:
        reden_opties = sorted(df["reden"].dropna().unique())
        selected_redenen = st.multiselect("🎯 Reden", reden_opties, default=reden_opties)

    with col2:
        min_date = df["datum"].min()
        max_date = df["datum"].max()
        date_range = st.date_input("📅 Periode", [min_date, max_date])

    df = df[df["reden"].isin(selected_redenen)]

    df = df[
        (df["datum"] >= pd.to_datetime(date_range[0])) &
        (df["datum"] <= pd.to_datetime(date_range[1]))
    ]

    col1, col2, col3 = st.columns(3)
    col1.metric("💸 Verlies", f"€{df['euro'].sum():.2f}")
    col2.metric("📦 Stuks", int(df["stuks"].sum()))
    col3.metric("🛒 Producten", df["product"].nunique())

    st.subheader("📊 Verlies per reden")
    st.bar_chart(df.groupby("reden")["euro"].sum())

    st.subheader("📈 Trend per week")
    df["week"] = df["datum"].dt.isocalendar().week
    st.line_chart(df.groupby("week")["euro"].sum())

    st.subheader("🏆 Top producten")
    top_products = df.groupby("product").agg({"stuks": "sum", "euro": "sum"}).sort_values("euro", ascending=False).head(20)
    st.dataframe(top_products)

    st.dataframe(df.head(200))

# =====================
# DATA INVOEREN
# =====================

elif menu == "➕ Data invoeren":

    st.title("➕ Weeks invoer")

    jaar = st.number_input("Jaar", value=2025)
    week = st.number_input("Week", value=1)
    afdeling = st.text_input("Afdeling")
    shrink = st.number_input("Shrink €")
    sales = st.number_input("Sales €")

    if st.button("Opslaan"):
        supabase.table("weeks").insert({
            "user_id": user_id,
            "jaar": jaar,
            "week": week,
            "afdeling": afdeling,
            "shrink": shrink,
            "sales": sales
        }).execute()
        st.success("Opgeslagen")

# =====================
# UPLOAD
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

        df = df[["datum","week","jaar","maand","product","reden","stuks","euro"]]

        df["user_id"] = user_id
        df["categorie"] = "ONBEKEND"

        data = df.to_dict(orient="records")

        for i in range(0, len(data), 500):
            supabase.table("shrink_data").insert(data[i:i+500]).execute()

        st.success("Upload klaar")
