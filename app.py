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
    supabase.table("weeks").select("*").execute().data or []
)

df_products = pd.DataFrame(
    supabase.table("shrink_data").select("*").execute().data or []
)

# 🔥 CLEAN DATABASE DATA
if not df_products.empty:
    df_products.columns = df_products.columns.str.strip().str.lower()
    df_products["reden"] = df_products["reden"].astype(str).str.strip().str.upper()

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

    if not df_products.empty:

        col1, col2 = st.columns(2)

        with col1:
            jaar_p = st.multiselect("Jaar", sorted(df_products["jaar"].dropna().unique()),
                                   default=sorted(df_products["jaar"].dropna().unique()))
            maand_p = st.multiselect("Maand", sorted(df_products["maand"].dropna().unique()),
                                    default=sorted(df_products["maand"].dropna().unique()))

        with col2:
            week_p = st.multiselect("Week", sorted(df_products["week"].dropna().unique()),
                                   default=sorted(df_products["week"].dropna().unique()))
            reden_p = st.multiselect("Reden", sorted(df_products["reden"].dropna().unique()),
                                    default=sorted(df_products["reden"].dropna().unique()))

        df_p = df_products.copy()

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

    else:
        st.warning("⚠️ Geen data gevonden")

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
# UPLOAD
# =====================

elif menu == "📤 Upload producten":

    st.title("📤 Upload producten")

    file = st.file_uploader("Upload Excel", type=["xlsx"])

    if file:

        df = pd.read_excel(file)

        # 🔥 FIX KOLOMNAMEN
        df.columns = df.columns.str.strip().str.lower()

        st.write("📊 KOLOMMEN:", df.columns)

        df = df.rename(columns={
            "datum": "datum",
            "benaming": "product",
            "reden / winkel": "reden",
            "reden/winkel": "reden",
            "reden": "reden",
            "hoeveelheid": "stuks",
            "hope": "categorie"
        })

        # 🔥 CLEAN REDEN
        df["reden"] = df["reden"].astype(str).str.strip().str.upper()
        df["reden"] = df["reden"].str.replace(r'^\d+\s*', '', regex=True)

        # 🔥 DATUM FIX
        df["datum"] = pd.to_datetime(df["datum"], dayfirst=True, errors="coerce")
        df = df.dropna(subset=["datum"])

        df["week"] = df["datum"].dt.isocalendar().week.astype(int)
        df["jaar"] = df["datum"].dt.year.astype(int)
        df["maand"] = df["datum"].dt.month.astype(int)

        # 🔥 DEBUG
        st.write("UNIEKE REDENEN:", df["reden"].unique())

        if st.button("Uploaden"):

            data = []

            for _, row in df.iterrows():
                data.append({
                    "user_id": user_id,
                    "datum": str(row["datum"]),
                    "week": int(row["week"]),
                    "jaar": int(row["jaar"]),
                    "maand": int(row["maand"]),
                    "product": row["product"],
                    "categorie": str(row["categorie"]),
                    "reden": str(row["reden"]),
                    "stuks": float(row["stuks"])
                })

            supabase.table("shrink_data").insert(data).execute()

            st.success(f"✅ {len(data)} producten opgeslagen!")

