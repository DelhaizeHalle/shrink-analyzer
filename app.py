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
        return None
    except Exception as e:
        st.error(f"Login error: {e}")
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
# DATA LOAD (CACHE)
# =====================

@st.cache_data(ttl=60)
def load_data(user_id):
    weeks = supabase.table("weeks").select("*").eq("user_id", user_id).execute().data
    products = supabase.table("shrink_data").select("*").eq("user_id", user_id).execute().data
    return pd.DataFrame(weeks or []), pd.DataFrame(products or [])

df_db, df_products = load_data(user_id)

# =====================
# CLEAN DATA
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
# REDEN CLEANING (ALLEEN BIJ UPLOAD)
# =====================

def clean_reden(series):
    s = series.astype(str)
    s = s.str.replace(r'^\d+\s*', '', regex=True)
    s = s.str.upper().str.strip()
    s = s.str.replace(r'\s+', ' ', regex=True)
    return s

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
        st.warning("⚠️ Geen data")
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

    # KPI
    c1, c2, c3 = st.columns(3)
    c1.metric("Shrink", f"€{df_f['shrink'].sum():,.2f}")
    c2.metric("Sales", f"€{df_f['sales'].sum():,.2f}")
    c3.metric("%", f"{df_f['percent'].mean():.2f}")

    chart = df_f.groupby(["week","afdeling"])["shrink"].sum().reset_index()
    st.plotly_chart(px.line(chart, x="week", y="shrink", color="afdeling"), use_container_width=True)

    # =====================
    # PRODUCT ANALYSE
    # =====================

    if not df_products.empty:

        st.subheader("📦 Product filters")

        df_p = df_products.copy()

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            categorie_filter = st.multiselect("Categorie", sorted(df_p["categorie"].dropna().unique()))

        with col2:
            reden_filter = st.multiselect("Reden", sorted(df_p["reden"].dropna().unique()))

        with col3:
            week_filter = st.multiselect("Week", sorted(df_p["week"].dropna().unique()))

        with col4:
            product_filter = st.multiselect("Product", sorted(df_p["product"].dropna().unique())[:50])

        if categorie_filter:
            df_p = df_p[df_p["categorie"].isin(categorie_filter)]

        if reden_filter:
            df_p = df_p[df_p["reden"].isin(reden_filter)]

        if week_filter:
            df_p = df_p[df_p["week"].isin(week_filter)]

        if product_filter:
            df_p = df_p[df_p["product"].isin(product_filter)]

        st.subheader("📊 Analyse")

        top = df_p.groupby("product")["stuks"].sum().sort_values(ascending=False).head(10)
        red = df_p.groupby("reden")["stuks"].sum().sort_values(ascending=False)

        col1, col2 = st.columns(2)
        col1.plotly_chart(px.bar(top, title="Top producten"), use_container_width=True)
        col2.plotly_chart(px.bar(red, title="Redenen"), use_container_width=True)

# =====================
# DATA INPUT
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
            "jaar": int(jaar),
            "maand": int(maand),
            "week": int(week),
            "afdeling": afdeling,
            "shrink": float(shrink),
            "sales": float(sales),
            "percent": float(percent)
        }).execute()

        st.success("✅ Opgeslagen")
        st.cache_data.clear()

# =====================
# UPLOAD (ROBUST FIX)
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

        df["categorie"] = "ONBEKEND"

        df["datum"] = pd.to_datetime(df["datum"], errors="coerce")
        df = df.dropna(subset=["datum"])

        iso = df["datum"].dt.isocalendar()
        df["jaar"] = iso.year.astype(int)
        df["week"] = iso.week.astype(int)
        df["maand"] = df["datum"].dt.month.astype(int)

        df["reden"] = clean_reden(df["reden"])

        st.write("🔍 Controle redenen (Excel):")
        st.write(df["reden"].value_counts())

        if st.button("Uploaden"):

            df_clean = df.copy()
             # datum verplicht
            df_clean = df_clean[df_clean["datum"].notna()]
            # reden fix
            df_clean["reden"] = df_clean["reden"].fillna("ONBEKEND")
            df_clean["reden"] = df_clean["reden"].astype(str).str.strip()
            df_clean = df_clean[df_clean["reden"] != ""]

            # types
            df_clean["datum"] = df_clean["datum"].astype(str)
            df_clean["week"] = df_clean["week"].astype(int)
            df_clean["jaar"] = df_clean["jaar"].astype(int)
            df_clean["maand"] = df_clean["maand"].astype(int)
            df_clean["product"] = df_clean["product"].astype(str)
            df_clean["stuks"] = df_clean["stuks"].fillna(0).astype(float)

            df_upload = df_clean[[
                "datum",
                "week",
                "jaar",
                "maand",
                "product",
                "reden",
                "stuks"
            ]].copy()
     
            df_upload["categorie"] = "ONBEKEND"
            df_upload["user_id"] = user_id

            st.write("🚀 Upload check:")
            st.write(df_upload["reden"].value_counts())

            data = df_upload.to_dict("records")

            chunk_size = 500

            for i in range(0, len(data), chunk_size):
                chunk = data[i:i+chunk_size]
                supabase.table("shrink_data").insert(chunk).execute()

            st.success(f"✅ {len(data)} records opgeslagen")
            st.cache_data.clear()

# =====================
# DEBUG
# =====================

elif menu == "🐞 Debug":

    st.title("🐞 Debug")

    st.write("User ID:", user_id)

    if not df_products.empty:
        st.write("Redenen:")
        st.write(df_products["reden"].value_counts())

        st.write("Categorieën:")
        st.write(df_products["categorie"].value_counts())





