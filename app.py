import streamlit as st
import pandas as pd
import plotly.express as px
from supabase import create_client
import datetime

# =====================
# CONFIG
# =====================

SUPABASE_URL = "https://adivczeimpamlhgaxthw.supabase.co"
SUPABASE_KEY = "sb_publishable_YB09KMt3LV8ol4ieLdGk-Q_acNlGllI"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

AFDELINGEN = [
    "DIEPVRIES","VOEDING","PARFUMERIE","DROGISTERIJ",
    "FRUIT EN GROENTEN","ZUIVEL","VERS VLEES","GEVOGELTE",
    "CHARCUTERIE","VIS EN SAURISSERIE","SELF-TRAITEUR",
    "BAKKERIJ","TRAITEUR","DRANKEN"
]

# =====================
# LOGIN
# =====================

def login(email, password):
    try:
        return supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
    except:
        return None

if "user" not in st.session_state:
    st.session_state["user"] = None

st.sidebar.title("🔐 Login")

email = st.sidebar.text_input("Email")
password = st.sidebar.text_input("Wachtwoord", type="password")

if st.sidebar.button("Login"):
    res = login(email, password)
    if res and res.user:
        st.session_state["user"] = res.user
        st.success("✅ Ingelogd")
        st.rerun()
    else:
        st.error("❌ Login mislukt")

if not st.session_state["user"]:
    st.stop()

user_id = st.session_state["user"].id

# =====================
# DATA
# =====================

df_db = pd.DataFrame(
    supabase.table("weeks").select("*").eq("user_id", user_id).execute().data or []
)

df_products = pd.DataFrame(
    supabase.table("shrink_data").select("*").eq("user_id", user_id).execute().data or []
)

# 🔥 BELANGRIJKE FIX (dashboard)
if not df_products.empty:
    df_products["reden"] = df_products["reden"].astype(str).str.strip()

    st.write("UNIEKE REDENEN IN DASHBOARD:")
    st.write(df_products["reden"].unique())
    st.write("Aantal:", df_products["reden"].nunique())

# =====================
# MENU
# =====================

menu = st.sidebar.radio("Menu", [
    "📊 Dashboard",
    "➕ Data invoeren",
    "📤 Upload producten"
])

# =====================
# DASHBOARD
# =====================

if menu == "📊 Dashboard":

    st.title("📊 Shrink Dashboard")

    # ===== FILTERS SHRINK =====
    st.subheader("📊 Shrink filters")

    col1, col2 = st.columns(2)

    with col1:
        jaar = st.multiselect("Jaar", sorted(df_db["jaar"].dropna().unique())) if not df_db.empty else []
        maand = st.multiselect("Maand", sorted(df_db["maand"].dropna().unique())) if not df_db.empty else []

    with col2:
        week = st.multiselect("Week", sorted(df_db["week"].dropna().unique())) if not df_db.empty else []
        afdeling = st.multiselect("Afdeling", sorted(df_db["afdeling"].dropna().unique())) if not df_db.empty else []

    df_filtered = df_db.copy()

    if not df_db.empty:
        if jaar:
            df_filtered = df_filtered[df_filtered["jaar"].isin(jaar)]
        if maand:
            df_filtered = df_filtered[df_filtered["maand"].isin(maand)]
        if week:
            df_filtered = df_filtered[df_filtered["week"].isin(week)]
        if afdeling:
            df_filtered = df_filtered[df_filtered["afdeling"].isin(afdeling)]

    # ===== GRAFIEK =====
    if not df_filtered.empty:

        periode = st.selectbox("Periode", ["Week", "Maand", "Jaar"])
        col_map = {"Week": "week", "Maand": "maand", "Jaar": "jaar"}

        chart = df_filtered.groupby([col_map[periode], "afdeling"])["shrink"].sum().reset_index()
        st.plotly_chart(px.line(chart, x=col_map[periode], y="shrink", color="afdeling"), use_container_width=True)

        # ===== WEEK VERGELIJKING =====
        st.subheader("📅 Week vergelijking")

        pivot = df_filtered.groupby(["week", "afdeling"])["shrink"].sum().unstack().fillna(0)

        if len(pivot) >= 2:
            last = pivot.iloc[-1]
            prev = pivot.iloc[-2]

            for a in pivot.columns:
                diff = last[a] - prev[a]

                if diff > 0:
                    st.error(f"{a}: +€{diff:.2f}")
                else:
                    st.success(f"{a}: €{diff:.2f}")

    # ===== PRODUCTEN =====
    st.subheader("📦 Product filters")

    if not df_products.empty and "jaar" in df_products.columns:

        col1, col2 = st.columns(2)

        with col1:
            jaar_p = st.multiselect("Jaar (producten)", sorted(df_products["jaar"].dropna().unique()))
            maand_p = st.multiselect("Maand", sorted(df_products["maand"].dropna().unique()))

        with col2:
            week_p = st.multiselect("Week", sorted(df_products["week"].dropna().unique()))
            reden_p = st.multiselect("Reden", sorted(df_products["reden"].dropna().unique()))

        df_p = df_products.copy()

        # 🔥 FIX FILTERS (BELANGRIJK)
        if jaar_p:
            df_p = df_p[df_p["jaar"].isin(jaar_p)]

        if maand_p:
            df_p = df_p[df_p["maand"].isin(maand_p)]

        if week_p:
            df_p = df_p[df_p["week"].isin(week_p)]

        if reden_p:
            df_p = df_p[df_p["reden"].isin(reden_p)]

        if not df_p.empty:

            st.subheader("📦 Top producten")
            top = df_p.groupby("product")["stuks"].sum().sort_values(ascending=False).head(10)
            st.plotly_chart(px.bar(top), use_container_width=True)

            st.subheader("📌 Redenen")
            red = df_p.groupby("reden")["stuks"].sum().sort_values(ascending=False)
            st.plotly_chart(px.bar(red), use_container_width=True)

            # ALERTS
            st.subheader("🚨 Alerts")
            st.error(f"Top product: {top.idxmax()}")
            st.warning(f"Top reden: {red.idxmax()}")

            # AI
            st.subheader("🧠 AI inzichten")

            if not df_filtered.empty and len(pivot) >= 3:
                trend = pivot.diff().iloc[-3:]
                slecht = trend.sum().idxmax()
                goed = trend.sum().idxmin()

                st.error(f"{slecht} verslechtert 3 weken")
                st.success(f"{goed} verbetert 3 weken")

    else:
        st.info("Upload eerst product data")

# =====================
# INPUT
# =====================

elif menu == "➕ Data invoeren":

    st.title("➕ Data invoeren")

    today = datetime.datetime.now()

    jaar = st.number_input("Jaar", value=today.year)
    maand = st.number_input("Maand", value=today.month)
    week = st.number_input("Week", value=today.isocalendar()[1])

    afdeling = st.selectbox("Afdeling", AFDELINGEN)

    shrink = st.number_input("Shrink €")
    sales = st.number_input("Sales €")
    percent = st.number_input("Shrink %")

    if st.button("Opslaan"):

        supabase.table("weeks").insert({
            "user_id": user_id,
            "jaar": jaar,
            "week": week,
            "maand": maand,
            "afdeling": afdeling,
            "shrink": shrink,
            "sales": sales,
            "percent": percent
        }).execute()

        st.success("✅ Opgeslagen")

# =====================
# UPLOAD PRODUCTEN
# =====================

elif menu == "📤 Upload producten":

    st.title("📤 Upload producten")

    file = st.file_uploader("Upload Excel", type=["xlsx"])

    if file:

        df = pd.read_excel(file)
        df.columns = df.columns.str.strip()

        df = df.rename(columns={
            "Datum": "datum",
            "Benaming": "product",
            "Reden / Winkel": "reden",
            "Hoeveelheid": "stuks",
            "Hope": "categorie"
        })

        # 🔥 CLEAN REDEN (WERKT 100%)
        df["reden"] = df["reden"].astype(str).str.strip()
        df["reden"] = df["reden"].str.replace(r'^\d+\s*', '', regex=True)

        df["datum"] = pd.to_datetime(df["datum"], errors="coerce")
        df["week"] = df["datum"].dt.isocalendar().week
        df["jaar"] = df["datum"].dt.year
        df["maand"] = df["datum"].dt.month

        if st.button("Uploaden"):

            data = []

            for _, row in df.iterrows():
                data.append({
                    "user_id": user_id,
                    "datum": str(row.get("datum")),
                    "week": int(row.get("week", 0)),
                    "jaar": int(row.get("jaar", 0)),
                    "maand": int(row.get("maand", 0)),
                    "product": row.get("product"),
                    "categorie": str(row.get("categorie")),
                    "reden": row.get("reden"),
                    "stuks": float(row.get("stuks", 0))
                })

            supabase.table("shrink_data").insert(data).execute()

            st.success(f"✅ {len(data)} producten opgeslagen!")

