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
        res = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        return res
    except Exception as e:
        st.error(f"Login fout: {e}")
        return None


if "user" not in st.session_state:
    st.session_state["user"] = None

st.sidebar.title("🔐 Login")

email = st.sidebar.text_input("Email")
password = st.sidebar.text_input("Wachtwoord", type="password")

if st.sidebar.button("Login"):

    if not email or not password:
        st.warning("Vul email en wachtwoord in")

    else:
        res = login(email, password)

        if res and res.user:
            st.session_state["user"] = res.user
            st.success("✅ Ingelogd")
            st.rerun()  # 🔥 BELANGRIJK

        else:
            st.error("❌ Login mislukt")


# STOP als niet ingelogd
if not st.session_state["user"]:
    st.info("Log eerst in")
    st.stop()

# =====================
# DATA
# =====================

df_db = pd.DataFrame(
    supabase.table("weeks").select("*").eq("user_id", user_id).execute().data or []
)

df_products = pd.DataFrame(
    supabase.table("shrink_data").select("*").eq("user_id", user_id).execute().data or []
)

# =====================
# MENU
# =====================

menu = st.sidebar.radio("Menu", [
    "📊 Dashboard",
    "➕ Data invoeren",
    "📤 Upload producten"
])

# =====================
# 📊 DASHBOARD
# =====================

if menu == "📊 Dashboard":

    st.title("📊 Shrink Dashboard")

    if df_db.empty:
        st.warning("Geen data")
        st.stop()

    # =====================
    # 🔍 POWER FILTERS
    # =====================

    st.subheader("🔍 Filters")

    col1, col2 = st.columns(2)

    with col1:
        jaren = sorted(df_products["jaar"].dropna().unique()) if not df_products.empty else []
        jaar_filter = st.multiselect("Jaar", jaren)

        maanden = sorted(df_products["maand"].dropna().unique()) if not df_products.empty else []
        maand_filter = st.multiselect("Maand", maanden)

    with col2:
        weken = sorted(df_products["week"].dropna().unique()) if not df_products.empty else []
        week_filter = st.multiselect("Week", weken)

        redenen = sorted(df_products["reden"].dropna().unique()) if not df_products.empty else []
        reden_filter = st.multiselect("Reden", redenen)

    afdeling_filter = st.multiselect(
        "Afdeling",
        sorted(df_db["afdeling"].dropna().unique())
    )

    # =====================
    # FILTER LOGICA
    # =====================

    df_filtered = df_products.copy()

    if jaar_filter:
        df_filtered = df_filtered[df_filtered["jaar"].isin(jaar_filter)]

    if maand_filter:
        df_filtered = df_filtered[df_filtered["maand"].isin(maand_filter)]

    if week_filter:
        df_filtered = df_filtered[df_filtered["week"].isin(week_filter)]

    if reden_filter:
        df_filtered = df_filtered[df_filtered["reden"].isin(reden_filter)]

    # =====================
    # 📊 GRAFIEK AFDELING
    # =====================

    periode = st.selectbox("Periode", ["Week", "Maand", "Jaar"])
    col_map = {"Week": "week", "Maand": "maand", "Jaar": "jaar"}
    group_col = col_map[periode]

    chart = df_db.groupby([group_col, "afdeling"])["shrink"].sum().reset_index()

    if afdeling_filter:
        chart = chart[chart["afdeling"].isin(afdeling_filter)]

    fig = px.line(chart, x=group_col, y="shrink", color="afdeling")
    st.plotly_chart(fig, use_container_width=True)

    # =====================
    # 📅 WEEK VERGELIJKING
    # =====================

    st.subheader("📅 Week vergelijking (€)")

    week_data = df_db.groupby(["week", "afdeling"])["shrink"].sum().reset_index()
    pivot = week_data.pivot(index="week", columns="afdeling", values="shrink").fillna(0)

    if len(pivot) >= 2:
        last = pivot.iloc[-1]
        prev = pivot.iloc[-2]

        for afdeling in pivot.columns:
            diff = last[afdeling] - prev[afdeling]
            if diff > 0:
                st.error(f"{afdeling}: +€{diff:.2f}")
            else:
                st.success(f"{afdeling}: €{diff:.2f}")

    # =====================
    # 📦 PRODUCT ANALYSE
    # =====================

    if not df_filtered.empty:

        st.subheader("📦 Top producten")

        top_products = (
            df_filtered.groupby("product")["stuks"]
            .sum()
            .sort_values(ascending=False)
            .head(10)
        )

        st.plotly_chart(px.bar(top_products), use_container_width=True)

        st.subheader("📌 Redenen")

        redenen_chart = (
            df_filtered.groupby("reden")["stuks"]
            .sum()
            .sort_values(ascending=False)
        )

        st.plotly_chart(px.bar(redenen_chart), use_container_width=True)

# =====================
# ➕ INPUT
# =====================

elif menu == "➕ Data invoeren":

    st.title("➕ Data invoeren")

    today = datetime.datetime.now()

    if "week" not in st.session_state:
        st.session_state.week = today.isocalendar()[1]
        st.session_state.maand = today.month
        st.session_state.jaar = today.year
        st.session_state.afdeling = AFDELINGEN[0]
        st.session_state.shrink = 0.0
        st.session_state.sales = 0.0
        st.session_state.percent = 0.0

    with st.form("input"):

        jaar = st.number_input("Jaar", key="jaar")
        maand = st.number_input("Maand", key="maand")
        week = st.number_input("Week", key="week")

        afdeling = st.selectbox("Afdeling", AFDELINGEN, key="afdeling")

        shrink = st.number_input("Shrink €", key="shrink")
        sales = st.number_input("Sales €", key="sales")
        percent = st.number_input("Shrink %", key="percent")

        submit = st.form_submit_button("Opslaan")

        if submit:

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

            st.session_state.week += 1
            st.session_state.shrink = 0.0
            st.session_state.sales = 0.0
            st.session_state.percent = 0.0

# =====================
# 📤 UPLOAD
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
            "Totale prijs": "prijs",
            "Hope": "categorie"
        })

        df["datum"] = pd.to_datetime(df["datum"], errors="coerce")

        df["week"] = df["datum"].dt.isocalendar().week
        df["jaar"] = df["datum"].dt.year
        df["maand"] = df["datum"].dt.month

        if st.button("Uploaden"):

            data = []

            for _, row in df.iterrows():

                try:
                    stuks = float(row.get("stuks", 0))
                except:
                    stuks = 0

                data.append({
                    "user_id": user_id,
                    "datum": str(row.get("datum")),
                    "week": int(row.get("week", 0)),
                    "jaar": int(row.get("jaar", 0)),
                    "maand": int(row.get("maand", 0)),
                    "product": row.get("product"),
                    "categorie": str(row.get("categorie")),
                    "reden": row.get("reden"),
                    "stuks": stuks
                })

            supabase.table("shrink_data").insert(data).execute()

            st.success(f"✅ {len(data)} producten opgeslagen!")



