import streamlit as st
import pandas as pd
from supabase import create_client
import datetime
import numpy as np

# =====================
# HELPERS
# =====================

def format_date_series(series):
    return pd.to_datetime(series, errors="coerce").dt.strftime("%d/%m/%Y")

# =====================
# CONFIG
# =====================

st.set_page_config(layout="wide")

SUPABASE_URL = "https://adivczeimpamlhgaxthw.supabase.co"
SUPABASE_KEY = "sb_publishable_YB09KMt3LV8ol4ieLdGk-Q_acNlGllI"

store_id = "delhaize_halle"

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

# =====================
# DATA LOAD
# =====================

@st.cache_data(ttl=60)
def load_data():

    def fetch_all(table_name):
        all_data = []
        batch_size = 1000
        start = 0

        while True:
            res = (
                supabase.table(table_name)
                .select("*")
                .eq("store_id", store_id)
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

    # =====================
    # 📅 DATUM FILTER
    # =====================

    if "datum" in df.columns:
        df["datum"] = pd.to_datetime(df["datum"], errors="coerce")
    else:
        df["datum"] = pd.to_datetime(
            df["jaar"].astype(str) + df["week"].astype(str) + '1',
            format='%G%V%u',
            errors="coerce"
        )

    df = df[df["datum"].notna()]

    min_date = df["datum"].min()
    max_date = df["datum"].max()

    today = datetime.date.today()

    safe_min = min_date if pd.notna(min_date) else today - datetime.timedelta(days=30)
    safe_max = max_date if pd.notna(max_date) else today

    date_range = st.date_input("📅 Periode", [safe_min, safe_max])

    df = df[
        (df["datum"] >= pd.to_datetime(date_range[0])) &
        (df["datum"] <= pd.to_datetime(date_range[1]))
    ]

    # =====================
    # KPI'S
    # =====================

    df["shrink"] = pd.to_numeric(df["shrink"], errors="coerce").fillna(0)
    df["sales"] = pd.to_numeric(df["sales"], errors="coerce").fillna(0)

    total_shrink = df["shrink"].sum()
    total_sales = df["sales"].sum()
    shrink_pct = (total_shrink / total_sales * 100) if total_sales > 0 else 0

    latest_week = df["week"].max()

    current = df[df["week"] == latest_week]["shrink"].sum()
    previous = df[df["week"] == latest_week - 1]["shrink"].sum()

    delta = current - previous

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("💸 Totale shrink", f"€{total_shrink:.2f}")
    col2.metric("🛒 Totale sales", f"€{total_sales:.2f}")
    col3.metric("📊 Shrink %", f"{shrink_pct:.2f}%")
    col4.metric("📉 vs vorige week", f"€{current:.2f}", f"{delta:.2f}", delta_color="inverse")

    # =====================
    # 📈 TREND PER WEEK
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
    # ⚖️ VERGELIJKING PER AFDELING
    # =====================

    st.subheader("⚖️ Verschil vs vorige week per afdeling")

    current_dept = df[df["week"] == latest_week].groupby("afdeling")["shrink"].sum()
    previous_dept = df[df["week"] == latest_week - 1].groupby("afdeling")["shrink"].sum()

    compare = pd.DataFrame({
        "current": current_dept,
        "previous": previous_dept
    }).fillna(0)

    compare["verschil"] = compare["current"] - compare["previous"]

    st.dataframe(compare.sort_values("verschil", ascending=False))
# =====================
# PRODUCT ANALYSE
# =====================

elif menu == "📦 Product analyse (PRO)":

    st.title("📦 Shrink Intelligence Dashboard")

    df = df_products.copy()
    # Fix lege reden
    df["reden"] = df["reden"].fillna("Onbekend")

    # =====================
    # 🔥 DATUM FIX (CRUCIAAL)
    # =====================

    df["datum"] = pd.to_datetime(df["datum"], errors="coerce")
    df = df[df["datum"].notna()]

    if df.empty:
        st.error("❌ Geen geldige data na datum filtering")
        st.stop()

    min_date = df["datum"].min()
    max_date = df["datum"].max()

    # extra safety
    if pd.isna(min_date) or pd.isna(max_date):
        st.error("❌ Datums niet correct")
        st.stop()

    # =====================
    # 🎯 FILTER REDEN
    # =====================

    col1, col2 = st.columns([1, 3])

    with col1:
        select_all_reden = st.checkbox("Alles", value=True)

    with col2:
        reden_opties = sorted(df["reden"].dropna().unique())

        if select_all_reden:
            selected_redenen = reden_opties
        else:
            selected_redenen = st.multiselect("🎯 Reden", reden_opties)

    # toepassen filter
    df = df[df["reden"].isin(selected_redenen)]

    df["datum"] = pd.to_datetime(df["datum"])
    df["stuks"] = pd.to_numeric(df["stuks"], errors="coerce").fillna(0)
    df["euro"] = pd.to_numeric(df["euro"], errors="coerce").fillna(0)

    df["datum"] = pd.to_datetime(df["datum"], errors="coerce")

    df = df[df["datum"].notna()]

    min_date = df["datum"].min()
    max_date = df["datum"].max()

    # veilige fallback datums
    today = datetime.date.today()

    safe_min = min_date if pd.notna(min_date) else today - datetime.timedelta(days=30)
    safe_max = max_date if pd.notna(max_date) else today

    date_range = st.date_input("📅 Periode", [safe_min, safe_max])

    df = df[
        (df["datum"] >= pd.to_datetime(date_range[0])) &
        (df["datum"] <= pd.to_datetime(date_range[1]))
    ]

    # =====================
    # TG2G
    # =====================

    tg2g = df[df["reden"].str.lower().str.contains("andere")]

    aantal_pakketten = tg2g["stuks"].sum()
    recup = aantal_pakketten * 5

    bruto = df["euro"].sum()
    netto = bruto - recup

    colA, colB, colC = st.columns(3)

    colA.metric("💸 Bruto verlies", f"€{bruto:.2f}")
    colB.metric("♻️ Recuperatie", f"€{recup:.2f}", f"{int(aantal_pakketten)} pakketten")
    colC.metric("💰 Netto verlies", f"€{netto:.2f}")

    st.divider()

    # =====================
    # GRAFIEKEN
    # =====================

    st.subheader("📊 Verlies per reden")
    st.bar_chart(df.groupby("reden")["euro"].sum())

    st.subheader("📈 Trend per week")
    df["week"] = df["datum"].dt.isocalendar().week
    st.line_chart(df.groupby("week")["euro"].sum())

    # =====================
    # PRODUCTEN
    # =====================

    st.subheader("💸 Grootste verlies per product")

    top_products = (
        df.groupby("product")
        .agg({"stuks": "sum", "euro": "sum"})
        .sort_values("euro", ascending=False)
        .head(20)
    )

    st.dataframe(top_products)

    if df["product"].nunique() > 50:
        st.error(f"🚨 Veel verschillende verliesproducten ({df['product'].nunique()})")
    elif df["product"].nunique() > 30:
        st.warning(f"⚠️ {df['product'].nunique()} verschillende verliesproducten")

    # =====================
    # INSIGHTS
    # =====================

    st.subheader("🧠 Automatische inzichten")

    if not top_products.empty:
        top = top_products.iloc[0]
        if top["euro"] > bruto * 0.2:
            st.warning(f"🚨 {top.name} veroorzaakt groot deel van verlies")

    if aantal_pakketten < 10:
        st.warning("♻️ Weinig TG2G pakketten")

    # =====================
    # DETAIL
    # =====================

    df_display = df.copy()
    df_display["datum"] = format_date_series(df_display["datum"])

    st.dataframe(df_display.head(200))











