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
    except Exception as e:
        st.error(f"Login fout: {e}")
        return None

if "user" not in st.session_state:
    st.session_state["user"] = None

st.sidebar.title("🔐 Login")

email = st.sidebar.text_input("Email")
password = st.sidebar.text_input("Wachtwoord", type="password")

if st.sidebar.button("Login"):
    if email and password:
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

    # =====================
    # 🔝 SHRINK FILTERS
    # =====================

    st.subheader("📊 Shrink filters")

    col1, col2 = st.columns(2)

    with col1:
        jaar_filter = st.multiselect("Jaar", sorted(df_db["jaar"].dropna().unique()))
        maand_filter = st.multiselect("Maand", sorted(df_db["maand"].dropna().unique()))

    with col2:
        week_filter = st.multiselect("Week", sorted(df_db["week"].dropna().unique()))
        afdeling_filter = st.multiselect("Afdeling", sorted(df_db["afdeling"].dropna().unique()))

    df_db_filtered = df_db.copy()

    if jaar_filter:
        df_db_filtered = df_db_filtered[df_db_filtered["jaar"].isin(jaar_filter)]

    if maand_filter:
        df_db_filtered = df_db_filtered[df_db_filtered["maand"].isin(maand_filter)]

    if week_filter:
        df_db_filtered = df_db_filtered[df_db_filtered["week"].isin(week_filter)]

    if afdeling_filter:
        df_db_filtered = df_db_filtered[df_db_filtered["afdeling"].isin(afdeling_filter)]

    # =====================
    # 📈 GRAFIEK
    # =====================

    periode = st.selectbox("Periode", ["Week", "Maand", "Jaar"])
    col_map = {"Week": "week", "Maand": "maand", "Jaar": "jaar"}
    group_col = col_map[periode]

    chart = df_db_filtered.groupby([group_col, "afdeling"])["shrink"].sum().reset_index()

    fig = px.line(chart, x=group_col, y="shrink", color="afdeling")
    st.plotly_chart(fig, use_container_width=True)

    # =====================
    # 📅 WEEK VERGELIJKING
    # =====================

    st.subheader("📅 Week vergelijking")

    week_data = df_db_filtered.groupby(["week", "afdeling"])["shrink"].sum().reset_index()
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
    # 📦 PRODUCT FILTERS
    # =====================

    st.subheader("📦 Product filters")

    col1, col2 = st.columns(2)

    with col1:
        jaar_p = st.multiselect("Jaar (producten)", sorted(df_products["jaar"].dropna().unique()))
        maand_p = st.multiselect("Maand (producten)", sorted(df_products["maand"].dropna().unique()))

    with col2:
        week_p = st.multiselect("Week (producten)", sorted(df_products["week"].dropna().unique()))
        reden_p = st.multiselect("Reden", sorted(df_products["reden"].dropna().unique()))

    df_products_filtered = df_products.copy()

    if jaar_p:
        df_products_filtered = df_products_filtered[df_products_filtered["jaar"].isin(jaar_p)]

    if maand_p:
        df_products_filtered = df_products_filtered[df_products_filtered["maand"].isin(maand_p)]

    if week_p:
        df_products_filtered = df_products_filtered[df_products_filtered["week"].isin(week_p)]

    if reden_p:
        df_products_filtered = df_products_filtered[df_products_filtered["reden"].isin(reden_p)]

    # =====================
    # 📊 PRODUCT GRAFIEKEN
    # =====================

    if not df_products_filtered.empty:

        st.subheader("📦 Top producten")

        top_products = (
            df_products_filtered.groupby("product")["stuks"]
            .sum()
            .sort_values(ascending=False)
            .head(10)
        )

        st.plotly_chart(px.bar(top_products), use_container_width=True)

        st.subheader("📌 Redenen")

        redenen_chart = (
            df_products_filtered.groupby("reden")["stuks"]
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
# 📤 UPLOAD
# =====================

elif menu == "📤 Upload producten":

    st.title("📤 Upload producten")

    file = st.file_uploader("Upload Excel", type=["xlsx"])

    if file:

        df = pd.read_excel(file)
        df.columns = df.columns.str.strip()

        # Kolommen opschonen
df.columns = df.columns.str.strip()

# 🔍 DEBUG (tijdelijk laten staan)
st.write("Kolommen:", df.columns)

# Automatische mapping (veel beter)
for col in df.columns:

    if "datum" in col.lower():
        df.rename(columns={col: "datum"}, inplace=True)

    if "benaming" in col.lower():
        df.rename(columns={col: "product"}, inplace=True)

    if "reden" in col.lower():
        df.rename(columns={col: "reden"}, inplace=True)

    if "hoeveel" in col.lower() or "stuks" in col.lower():
        df.rename(columns={col: "stuks"}, inplace=True)

    if "hope" in col.lower() or "categorie" in col.lower():
        df.rename(columns={col: "categorie"}, inplace=True)

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

