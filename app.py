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
def load_products(user_id):
    return pd.DataFrame(
        supabase.table("shrink_data")
        .select("*")
        .eq("user_id", user_id)
        .range(0, 10000)
        .execute().data or []
    )

df_products = load_products(user_id)

# =====================
# MENU
# =====================

menu = st.sidebar.radio("Menu", [
    "📊 Dashboard",
    "📤 Upload"
])

# =====================
# DASHBOARD
# =====================

if menu == "📊 Dashboard":

    st.title("📊 Shrink Dashboard")

    if df_products.empty:
        st.warning("Geen data")
        st.stop()

    # 🔥 EXACT zoals je oude app
    total = df_products["stuks"].sum()

    st.metric("Totale shrink (stuks)", int(total))

    st.subheader("📦 Redenen")
    redenen = df_products["reden"].value_counts()
    st.write(redenen)

    st.subheader("📊 Grafiek")
    st.plotly_chart(px.bar(redenen))

    # 🔥 debug
    st.subheader("🐞 Debug")
    st.write("Aantal records:", len(df_products))

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

            # 🔥 BELANGRIJK: oude data verwijderen
            supabase.table("shrink_data").delete().eq("user_id", user_id).execute()

            df["user_id"] = user_id
            df["categorie"] = "ONBEKEND"

            data = df[[
                "user_id","datum","week","jaar","maand",
                "product","categorie","reden","stuks"
            ]].to_dict("records")

            supabase.table("shrink_data").insert(data).execute()

            st.success("✅ Upload succesvol")

            st.cache_data.clear()
            st.rerun()
