import streamlit as st
import pandas as pd
import plotly.express as px
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
# DATA LOAD
# =====================

@st.cache_data(ttl=60)
def load_data(user_id):

    df_db = pd.DataFrame(
        supabase.table("weeks")
        .select("*")
        .eq("user_id", user_id)
        .range(0, 1000)
        .execute().data or []
    )

    df_products = pd.DataFrame(
        supabase.table("shrink_data")
        .select("*")
        .eq("user_id", user_id)
        .range(0, 10000)
        .execute().data or []
    )

    return df_db, df_products

df_db, df_products = load_data(user_id)

# =====================
# MENU
# =====================

menu = st.sidebar.radio("Menu", [
    "📊 Dashboard",
    "📤 Upload",
    "🐞 Debug"
])

# =====================
# DASHBOARD
# =====================

if menu == "📊 Dashboard":

    st.title("📊 Shrink Dashboard")

    if df_products.empty:
        st.warning("Geen data")
        st.stop()

    st.metric("Totale stuks", int(df_products["stuks"].sum()))

    st.subheader("📦 Redenen")
    redenen = df_products["reden"].value_counts()
    st.write(redenen)

    st.plotly_chart(px.bar(redenen))

# =====================
# UPLOAD
# =====================

elif menu == "📤 Upload":

    st.title("📤 Upload Excel")

    file = st.file_uploader("Upload Excel", type=["xlsx"])

    if file:

        df = pd.read_excel(file)
        df.columns = df.columns.str.strip()

        df = df.rename(columns={
            "Datum": "datum",
            "Benaming": "product",
            "Reden / Winkel": "reden",
            "Hoeveelheid": "stuks"
        })

        df["datum"] = pd.to_datetime(df["datum"], errors="coerce")
        df = df[df["datum"].notna()]

        df["week"] = df["datum"].dt.isocalendar().week
        df["jaar"] = df["datum"].dt.year
        df["maand"] = df["datum"].dt.month

        df["reden"] = (
            df["reden"]
            .astype(str)
            .str.replace(r'^\d+\s*', '', regex=True)
            .str.upper()
            .str.strip()
        )

        df["stuks"] = pd.to_numeric(df["stuks"], errors="coerce").fillna(0)

        st.write("🔍 Controle redenen:")
        st.write(df["reden"].value_counts())

        if st.button("Uploaden"):

            df["user_id"] = user_id
            df["categorie"] = "ONBEKEND"

            data = []

            for _, row in df.iterrows():
                data.append({
                    "user_id": user_id,
                    "datum": row["datum"].strftime("%Y-%m-%d"),  # 🔥 FIX
                    "week": int(row["week"]),
                    "jaar": int(row["jaar"]),
                    "maand": int(row["maand"]),
                    "product": str(row["product"]),
                    "categorie": "ONBEKEND",
                    "reden": str(row["reden"]),
                    "stuks": float(row["stuks"])
                })

            response = supabase.table("shrink_data").insert(data).execute()

            st.write("Response:", response)

            st.success(f"✅ {len(data)} records opgeslagen")

            st.cache_data.clear()
            st.rerun()

# =====================
# DEBUG
# =====================

elif menu == "🐞 Debug":

    st.write("Aantal products:", len(df_products))

    if not df_products.empty:
        st.write(df_products.head())
        st.write(df_products["reden"].value_counts())
