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
# CLEAN
# =====================

def clean_df(df):
    if df.empty:
        return df
    for col in ["jaar", "maand", "week"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    return df

df_db = clean_df(df_db)
df_products = clean_df(df_products)

# =====================
# MENU
# =====================

menu = st.sidebar.radio("Menu", [
    "📊 Dashboard",
    "➕ Data invoeren",
    "📤 Upload producten",
    "🐞 Debug"
])

# =====================
# DASHBOARD
# =====================

if menu == "📊 Dashboard":

    st.title("📊 Shrink Dashboard")

    if df_db.empty:
        st.warning("Geen data")
        st.stop()

    col1, col2, col3, col4 = st.columns(4)

    jaar = col1.selectbox("Jaar", sorted(df_db["jaar"].unique()))
    maand = col2.selectbox("Maand", sorted(df_db["maand"].unique()))
    week = col3.multiselect("Week", sorted(df_db["week"].unique()))
    afdeling = col4.multiselect("Afdeling", sorted(df_db["afdeling"].unique()))

    df_f = df_db[(df_db["jaar"] == jaar) & (df_db["maand"] == maand)]

    if week:
        df_f = df_f[df_f["week"].isin(week)]

    if afdeling:
        df_f = df_f[df_f["afdeling"].isin(afdeling)]

    st.metric("Shrink", f"€{df_f['shrink'].sum():,.2f}")

    chart = df_f.groupby(["week","afdeling"])["shrink"].sum().reset_index()
    st.plotly_chart(px.line(chart, x="week", y="shrink", color="afdeling"))

    # PRODUCTEN
    if not df_products.empty:

        st.subheader("📦 Product filters")

        col1, col2, col3, col4 = st.columns(4)

        categorie = col1.multiselect("Categorie", sorted(df_products["categorie"].dropna().unique()))
        reden = col2.multiselect("Reden", sorted(df_products["reden"].dropna().unique()))
        week_p = col3.multiselect("Week", sorted(df_products["week"].dropna().unique()))
        product = col4.multiselect("Product", sorted(df_products["product"].dropna().unique())[:50])

        df_p = df_products.copy()

        if categorie:
            df_p = df_p[df_p["categorie"].isin(categorie)]
        if reden:
            df_p = df_p[df_p["reden"].isin(reden)]
        if week_p:
            df_p = df_p[df_p["week"].isin(week_p)]
        if product:
            df_p = df_p[df_p["product"].isin(product)]

        st.write("Aantal rijen:", len(df_p))

        st.plotly_chart(px.bar(df_p.groupby("product")["stuks"].sum().sort_values(ascending=False).head(10)))
        st.plotly_chart(px.bar(df_p.groupby("reden")["stuks"].sum().sort_values(ascending=False)))

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
            "user_id": str(user_id),
            "jaar": int(jaar),
            "maand": int(maand),
            "week": int(week),
            "afdeling": afdeling,
            "shrink": float(shrink),
            "sales": float(sales),
            "percent": float(percent)
        }).execute()

        st.success("Opgeslagen")
        st.cache_data.clear()

# =====================
# UPLOAD
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
            "Hoeveelheid": "stuks"
        })

        df["datum"] = pd.to_datetime(df["datum"], errors="coerce")

        iso = df["datum"].dt.isocalendar()
        df["jaar"] = iso.year.astype(int)
        df["week"] = iso.week.astype(int)
        df["maand"] = df["datum"].dt.month.astype(int)

        df["reden"] = df["reden"].astype(str).str.upper().str.strip()

        st.write("Controle:", df["reden"].value_counts())

        if st.button("Uploaden"):

            df_clean = df[df["datum"].notna()].copy()

            df_clean["datum"] = df_clean["datum"].dt.date
            df_clean["stuks"] = df_clean["stuks"].fillna(0)

            df_upload = df_clean[[
                "datum","week","jaar","maand","product","reden","stuks"
            ]].copy()

            df_upload["categorie"] = "ONBEKEND"
            df_upload["user_id"] = str(user_id)

            clean_data = []

            for _, row in df_upload.iterrows():
                clean_data.append({
                    "user_id": str(user_id),
                    "datum": str(row["datum"]),
                    "week": int(row["week"]),
                    "jaar": int(row["jaar"]),
                    "maand": int(row["maand"]),
                    "product": str(row["product"]),
                    "categorie": "ONBEKEND",
                    "reden": str(row["reden"]),
                    "stuks": float(row["stuks"])
                })

            supabase.table("shrink_data").insert(clean_data).execute()

            st.success(f"{len(clean_data)} records opgeslagen")

            st.cache_data.clear()
            st.rerun()

# =====================
# DEBUG
# =====================

elif menu == "🐞 Debug":

    st.write("Aantal records:", len(df_products))

    if not df_products.empty:
        st.write(df_products["reden"].value_counts())
