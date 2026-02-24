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
# DATA LOAD
# =====================

@st.cache_data
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
    "📤 Upload producten"
])

# =====================
# DASHBOARD
# =====================

if menu == "📊 Dashboard":

    st.title("📊 Shrink Dashboard")

    if df_db.empty:
        st.warning("⚠️ Geen data gevonden")
        st.stop()

    # ===== FILTER BAR =====
    st.markdown("### 🎛️ Filters")

    col1, col2, col3, col4, col5 = st.columns(5)

    jaar_opties = sorted(df_db["jaar"].unique())
    maand_opties = sorted(df_db["maand"].unique())
    week_opties = sorted(df_db["week"].unique())

    today = datetime.datetime.now()

    with col1:
        jaar = st.selectbox(
            "Jaar",
            jaar_opties,
            index=jaar_opties.index(today.year) if today.year in jaar_opties else 0
        )

    with col2:
        maand = st.selectbox(
            "Maand",
            maand_opties,
            index=maand_opties.index(today.month) if today.month in maand_opties else 0
        )

    with col3:
        week = st.multiselect("Week", week_opties)

    with col4:
        afdeling = st.multiselect("Afdeling", sorted(df_db["afdeling"].unique()))

    with col5:
        if st.button("🔄 Reset"):
            st.cache_data.clear()
            st.rerun()

    # ===== FILTER LOGIC =====
    df_filtered = df_db.copy()

    df_filtered = df_filtered[df_filtered["jaar"] == jaar]
    df_filtered = df_filtered[df_filtered["maand"] == maand]

    if week:
        df_filtered = df_filtered[df_filtered["week"].isin(week)]

    if afdeling:
        df_filtered = df_filtered[df_filtered["afdeling"].isin(afdeling)]

    # ===== KPI =====
    col1, col2, col3 = st.columns(3)

    col1.metric("Totale Shrink", f"€{df_filtered['shrink'].sum():,.2f}")
    col2.metric("Totale Sales", f"€{df_filtered['sales'].sum():,.2f}")
    col3.metric("Gemiddeld %", f"{df_filtered['percent'].mean():.2f}%")

    # ===== GRAFIEK =====
    st.subheader("📈 Trend")

    chart = df_filtered.groupby(["week", "afdeling"])["shrink"].sum().reset_index()

    st.plotly_chart(
        px.line(chart, x="week", y="shrink", color="afdeling"),
        use_container_width=True
    )

    # ===== PRODUCT ANALYSE =====
    st.subheader("📦 Product analyse")

    if not df_products.empty:

        df_p = df_products.copy()
        df_p = df_p[df_p["jaar"] == jaar]
        df_p = df_p[df_p["maand"] == maand]

        reden_filter = st.multiselect("Filter reden", sorted(df_p["reden"].unique()))

        if reden_filter:
            df_p = df_p[df_p["reden"].isin(reden_filter)]

        top = df_p.groupby("product")["stuks"].sum().sort_values(ascending=False).head(10)
        red = df_p.groupby("reden")["stuks"].sum().sort_values(ascending=False)

        col1, col2 = st.columns(2)

        col1.plotly_chart(px.bar(top, title="Top producten"), use_container_width=True)
        col2.plotly_chart(px.bar(red, title="Redenen"), use_container_width=True)

        # Insights
        st.subheader("🧠 Insights")

        if not top.empty:
            st.success(f"Top verlies: {top.idxmax()}")

        if not red.empty:
            st.warning(f"Belangrijkste reden: {red.idxmax()}")

    else:
        st.info("Upload eerst product data")

# =====================
# DATA INVOER
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
