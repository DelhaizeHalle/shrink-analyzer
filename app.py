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

# 🔥 BELANGRIJK: altijd string!
user_id = str(st.session_state["user"].id)

# =====================
# DATA LOAD (CACHE)
# =====================

@st.cache_data
def load_data(user_id):
    weeks = supabase.table("weeks").select("*").eq("user_id", user_id).execute().data
    products = supabase.table("shrink_data").select("*").eq("user_id", user_id).execute().data
    
    df_w = pd.DataFrame(weeks or [])
    df_p = pd.DataFrame(products or [])
    
    return df_w, df_p

df_db, df_products = load_data(user_id)

# =====================
# CLEAN DATA
# =====================

def clean_df(df):
    if df.empty:
        return df
    
    for col in ["jaar", "maand", "week"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    
    return df

df_db = clean_df(df_db)
df_products = clean_df(df_products)

if not df_products.empty:
    df_products["reden"] = df_products["reden"].astype(str).str.strip().str.upper()

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
        st.warning("⚠️ Geen data gevonden")
        st.stop()

    # ===== FILTERS =====
    st.subheader("📊 Filters")

    jaar_opties = sorted(df_db["jaar"].unique())
    maand_opties = sorted(df_db["maand"].unique())
    week_opties = sorted(df_db["week"].unique())

    col1, col2 = st.columns(2)

    with col1:
        jaar = st.multiselect("Jaar", jaar_opties, default=jaar_opties)
        maand = st.multiselect("Maand", maand_opties, default=maand_opties)

    with col2:
        week = st.multiselect("Week", week_opties, default=week_opties)
        afdeling = st.multiselect("Afdeling", sorted(df_db["afdeling"].unique()))

    df_filtered = df_db.copy()

    if jaar:
        df_filtered = df_filtered[df_filtered["jaar"].isin(jaar)]
    if maand:
        df_filtered = df_filtered[df_filtered["maand"].isin(maand)]
    if week:
        df_filtered = df_filtered[df_filtered["week"].isin(week)]
    if afdeling:
        df_filtered = df_filtered[df_filtered["afdeling"].isin(afdeling)]

    # ===== GRAFIEK =====
    periode = st.selectbox("Periode", ["Week", "Maand", "Jaar"])
    col_map = {"Week": "week", "Maand": "maand", "Jaar": "jaar"}

    chart = df_filtered.groupby([col_map[periode], "afdeling"])["shrink"].sum().reset_index()

    st.plotly_chart(
        px.line(chart, x=col_map[periode], y="shrink", color="afdeling"),
        use_container_width=True
    )

    # ===== VERGELIJKING =====
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

    # =====================
    # PRODUCT ANALYSE
    # =====================

    st.subheader("📦 Product analyse")

    if not df_products.empty:

        df_p = df_products.copy()

        top = df_p.groupby("product")["stuks"].sum().sort_values(ascending=False).head(10)
        red = df_p.groupby("reden")["stuks"].sum().sort_values(ascending=False)

        st.plotly_chart(px.bar(top, title="Top producten"), use_container_width=True)
        st.plotly_chart(px.bar(red, title="Redenen"), use_container_width=True)

        # 🔥 AI INSIGHTS
        st.subheader("🧠 AI Insights")

        st.info(f"""
        📌 Grootste verlies: {top.idxmax()}
        
        ⚠️ Hoofdreden: {red.idxmax()}
        
        👉 Actie:
        - Controleer stock van dit product
        - Analyseer reden (personeel / verval)
        - Focus op top 3 producten
        """)

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
            "jaar": int(jaar),
            "week": int(week),
            "maand": int(maand),
            "afdeling": afdeling,
            "shrink": float(shrink),
            "sales": float(sales),
            "percent": float(percent)
        }).execute()

        st.success("✅ Opgeslagen")
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
            "Hoeveelheid": "stuks",
            "Hope": "categorie"
        })

        df["datum"] = pd.to_datetime(df["datum"], errors="coerce")
        df = df.dropna(subset=["datum", "product"])

        iso = df["datum"].dt.isocalendar()

        df["jaar"] = iso.year.astype(int)
        df["week"] = iso.week.astype(int)
        df["maand"] = df["datum"].dt.month.astype(int)

        df["reden"] = df["reden"].astype(str).str.strip().str.upper()

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
                    "categorie": str(row.get("categorie")),
                    "reden": row["reden"],
                    "stuks": float(row.get("stuks", 0))
                })

            supabase.table("shrink_data").insert(data).execute()

            st.success(f"✅ {len(data)} producten opgeslagen!")
            st.cache_data.clear()

# =====================
# DEBUG
# =====================

elif menu == "🐞 Debug":

    st.title("🐞 Debug")

    st.write("USER ID:", user_id)

    st.subheader("Weeks data")
    st.write(df_db)

    st.subheader("Products data")
    st.write(df_products)

