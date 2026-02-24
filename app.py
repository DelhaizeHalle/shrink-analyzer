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

df_products = pd.DataFrame(
    supabase.table("shrink_data").select("*").eq("user_id", user_id).execute().data or []
)

menu = st.sidebar.radio("Menu", ["📊 Dashboard", "📤 Upload producten"])

# =====================
# DASHBOARD
# =====================

if menu == "📊 Dashboard":

    st.title("📊 Dashboard")

    if not df_products.empty:

        st.subheader("📦 Redenen overzicht")

        st.write("Unieke redenen in database:")
        st.write(df_products["reden"].unique())

        redenen_chart = df_products.groupby("reden")["stuks"].sum().sort_values(ascending=False)
        st.bar_chart(redenen_chart)

    else:
        st.warning("Geen data")

# =====================
# UPLOAD
# =====================

elif menu == "📤 Upload producten":

    st.title("📤 Upload producten")

    file = st.file_uploader("Upload Excel", type=["xlsx"])

    if file:

        df = pd.read_excel(file)
        df.columns = df.columns.str.strip()

        st.write("Kolommen:", df.columns)

        # 🔥 HARDCODE MAPPING (JOUW FILE)
        df = df.rename(columns={
            "Datum": "datum",
            "Benaming": "product",
            "Reden / Winkel": "reden",
            "Hoeveelheid": "stuks",
            "Hope": "categorie"
        })

        # 🔥 DEBUG ALLES
        st.write("UNIEKE WAARDEN PER KOLOM:")
        for col in df.columns:
            st.write(col, "→", df[col].dropna().unique()[:5])

        # 🔥 CLEAN REDEN
        df["reden"] = df["reden"].astype(str).str.strip()
        df["reden"] = df["reden"].str.replace(r'^\d+\s*', '', regex=True)

        # 🔥 DEBUG REDEN
        st.write("Unieke redenen NA cleaning:")
        st.write(df["reden"].unique())
        st.write("Aantal unieke redenen:", df["reden"].nunique())

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

            res = supabase.table("shrink_data").insert(data).execute()

            st.success(f"✅ {len(data)} producten opgeslagen!")
            st.write("Upload response:", res)
