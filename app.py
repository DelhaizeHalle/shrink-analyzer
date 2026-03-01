import streamlit as st
import pandas as pd
from supabase import create_client
import datetime
def format_date_series(series):
    return pd.to_datetime(series, errors="coerce").dt.strftime("%d/%m/%Y")

st.set_page_config(layout="wide")

# =====================
# CONFIG
# =====================

SUPABASE_URL = "https://adivczeimpamlhgaxthw.supabase.co"
SUPABASE_KEY = "sb_publishable_YB09KMt3LV8ol4ieLdGk-Q_acNlGllI"

# 🔥 GEDEELDE STORE
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

    if df_weeks.empty:
        st.warning("Geen data")
        st.stop()

    df = df_weeks.copy()

    df["shrink"] = pd.to_numeric(df["shrink"], errors="coerce").fillna(0)
    df["sales"] = pd.to_numeric(df["sales"], errors="coerce").fillna(0)

    # FILTER AFDELING
    st.subheader("🎯 Filter afdeling")

    afdeling_opties = sorted(df["afdeling"].dropna().unique())

    col1, col2 = st.columns([1, 3])

    with col1:
        select_all = st.checkbox("Alles", value=True)

    with col2:
        if select_all:
            selected_afdeling = afdeling_opties
        else:
            selected_afdeling = st.multiselect("Selecteer afdeling(en)", afdeling_opties)

    df = df[df["afdeling"].isin(selected_afdeling)]

    # KPI
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

    # PER AFDELING
    st.subheader("🏬 Shrink per afdeling")

    dept = df.groupby("afdeling")[["shrink", "sales"]].sum()
    dept["shrink_pct"] = (dept["shrink"] / dept["sales"] * 100).fillna(0)

    st.dataframe(dept.sort_values("shrink", ascending=False))

    # TREND
    st.subheader("📈 Trend per week")

    weekly = df.groupby(["jaar", "week"]).agg({
        "shrink": "sum",
        "sales": "sum"
    }).reset_index()

    weekly["label"] = weekly["jaar"].astype(str) + "-W" + weekly["week"].astype(str)
    weekly = weekly.set_index("label")

    st.line_chart(weekly[["shrink", "sales"]])

    # VERGELIJKING
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

    col1, col2 = st.columns([1, 3])

    with col1:
        select_all_reden = st.checkbox("Alles", value=True, key="reden_all")

    with col2:
        reden_opties = sorted(df["reden"].dropna().unique())

        if select_all_reden:
            selected_redenen = reden_opties
        else:
            selected_redenen = st.multiselect("🎯 Reden", reden_opties)

    min_date = df["datum"].min()
    max_date = df["datum"].max()

    date_range = st.date_input("", [min_date, max_date])

    if len(date_range) == 2:
        start = date_range[0].strftime("%d/%m/%Y")
        end = date_range[1].strftime("%d/%m/%Y")
        st.write(f"📅 Periode: {start} → {end}")

    df = df[df["reden"].isin(selected_redenen)]

    df = df[
        (df["datum"] >= pd.to_datetime(date_range[0])) &
        (df["datum"] <= pd.to_datetime(date_range[1]))
    ]

    # =====================
    # ♻️ TOO GOOD TO GO LOGICA
    # =====================

    tg2g = df_products.copy()
    tg2g["datum"] = pd.to_datetime(tg2g["datum"])

    # Filter op datum
    tg2g = tg2g[
        (tg2g["datum"] >= pd.to_datetime(date_range[0])) &
        (tg2g["datum"] <= pd.to_datetime(date_range[1]))
    ]

    # Enkel Too Good To Go
    tg2g = tg2g[tg2g["reden"].str.lower().str.strip() == "verlies andere"]

    # Aantal pakketten
    aantal_pakketten = tg2g["stuks"].sum()

    # Recuperatie (€5 per pakket)
    recup = aantal_pakketten * 5

    # Bruto en netto
    bruto = df["euro"].sum()
    netto = bruto - recup

    # KPI's
    colA, colB, colC = st.columns(3)

    colA.metric("💸 Bruto verlies", f"€{bruto:.2f}")

    colB.metric(
        "♻️ Recuperatie (Too Good To Go)",
        f"€{recup:.2f}",
        f"{int(aantal_pakketten)} pakketten"
    )

    colC.metric("💰 Netto verlies", f"€{netto:.2f}")
    st.divider()

    col1, col2, col3 = st.columns(3)

    col1.metric("📦 Totaal stuks", int(df["stuks"].sum()))
    col2.metric("🛒 Aantal producten", df["product"].nunique())
    col3.metric(
        "📊 Gemiddeld verlies / product",
        f"€{(bruto / df['product'].nunique()):.2f}" if df["product"].nunique() > 0 else "€0"
    )

    st.divider()

    # =====================
    # 📊 VERLIES PER REDEN
    # =====================

    st.subheader("📊 Verlies per reden")
    st.bar_chart(df.groupby("reden")["euro"].sum())

    # =====================
    # 📈 TREND PER WEEK
    # =====================

    st.subheader("📈 Trend per week")
    df["week"] = df["datum"].dt.isocalendar().week
    st.line_chart(df.groupby("week")["euro"].sum())

    # =====================
    # 📉 VERLIES PER PRODUCT
    # =====================

    st.subheader("💸 Grootste verlies per product")

    top_products = (
        df.groupby("product")
        .agg({"stuks": "sum", "euro": "sum"})
        .sort_values("euro", ascending=False)
        .head(20)
    )

    st.dataframe(top_products)

    # =====================
    # 🔍 DETAIL DATA
    # =====================

    st.subheader("🔍 Detail data")

    df_display = df.copy()
    df_display["datum"] = format_date_series(df_display["datum"])

    st.dataframe(df_display.head(200))
# =====================
# DATA INVOEREN
# =====================

elif menu == "➕ Data invoeren":

    st.title("➕ Weeks invoer")

    if not df_weeks.empty:
        latest = df_weeks.sort_values(["jaar", "week"], ascending=False).iloc[0]
        default_jaar = int(latest["jaar"])
        default_week = int(latest["week"])
        default_maand = int(latest.get("maand", 1))
    else:
        today = datetime.datetime.now()
        default_jaar = today.year
        default_week = today.isocalendar()[1]
        default_maand = today.month

    jaar = st.number_input("Jaar", value=default_jaar)
    maand = st.number_input("Maand", value=default_maand)
    week = st.number_input("Week", value=default_week)

    # DROPDOWN AFDELING
    if not df_weeks.empty:
        afdeling_opties = sorted(df_weeks["afdeling"].dropna().unique().tolist())
    else:
        afdeling_opties = []

    afdeling_opties_met_nieuw = afdeling_opties + ["➕ Nieuwe afdeling"]

    gekozen = st.selectbox("Afdeling", afdeling_opties_met_nieuw)

    if gekozen == "➕ Nieuwe afdeling":
        afdeling = st.text_input("Nieuwe afdeling")
    else:
        afdeling = gekozen

    shrink = st.number_input("Shrink €")
    sales = st.number_input("Sales €")

    if st.button("Opslaan"):

        supabase.table("weeks").insert({
            "store_id": store_id,
            "jaar": int(jaar),
            "maand": int(maand),
            "week": int(week),
            "afdeling": afdeling,
            "shrink": float(shrink),
            "sales": float(sales)
        }).execute()

        st.success("Opgeslagen")
        st.cache_data.clear()
        st.rerun()

# =====================
# UPLOAD
# =====================

elif menu == "📤 Upload":

    import numpy as np

    st.title("Upload Excel")

    file = st.file_uploader("Upload Excel", type=["xlsx"])

    if file:

        # =====================
        # INLEZEN
        # =====================
        df = pd.read_excel(file)
        df.columns = df.columns.str.strip()

        # =====================
        # KOLOMMEN MAPPING
        # =====================
        df = df.rename(columns={
            "Datum": "datum",
            "Benaming": "product",
            "Reden / Winkel": "reden",
            "Hoeveelheid": "stuks",
            "Totale prijs": "euro"
        })

        # =====================
        # VALIDATIE KOLOMMEN
        # =====================
        required_cols = ["datum", "product", "reden", "stuks", "euro"]

        missing = [col for col in required_cols if col not in df.columns]

        if missing:
            st.error(f"❌ Ontbrekende kolommen: {missing}")
            st.stop()

        # =====================
        # DATA CLEANING
        # =====================
        df["datum"] = pd.to_datetime(df["datum"], errors="coerce")
        df = df[df["datum"].notna()]

        df["week"] = df["datum"].dt.isocalendar().week.astype(int)
        df["jaar"] = df["datum"].dt.year.astype(int)
        df["maand"] = df["datum"].dt.month.astype(int)

        df["stuks"] = pd.to_numeric(df["stuks"], errors="coerce").fillna(0)
        df["euro"] = pd.to_numeric(df["euro"], errors="coerce").fillna(0)

        df["product"] = df["product"].astype(str).str.upper().str.strip()
        df["reden"] = df["reden"].astype(str).str.strip()

        df = df[["datum","week","jaar","maand","product","reden","stuks","euro"]]

        df["store_id"] = store_id
        df["categorie"] = "ONBEKEND"

        # =====================
        # 🔥 CRUCIALE FIXES
        # =====================
        df = df.replace({np.nan: None})

        # datum → string (anders crash)
        df["datum"] = df["datum"].astype(str)

        # alles JSON-safe maken
        df = df.astype(object)

        # =====================
        # PREVIEW (SUPER HANDIG)
        # =====================
        st.subheader("Preview")
        st.dataframe(df.head(20))

        # =====================
        # UPLOAD BUTTON
        # =====================
        if st.button("🚀 Bevestig upload"):

            data = df.to_dict(orient="records")

            if not data:
                st.warning("Geen geldige data om te uploaden")
                st.stop()

            try:
                for i in range(0, len(data), 500):
                    supabase.table("shrink_data").insert(data[i:i+500]).execute()

                st.success(f"✅ Upload klaar ({len(data)} rijen)")

                st.cache_data.clear()

            except Exception as e:
                st.error(f"❌ Upload fout: {e}")
















