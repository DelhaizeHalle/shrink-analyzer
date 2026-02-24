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
    if res and res.session:
        st.session_state["user"] = res.user
        st.success("Ingelogd")

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

    if df_db.empty:
        st.warning("Geen data")
        st.stop()

    periode = st.selectbox("Periode", ["Week", "Maand", "Jaar"])
    col_map = {"Week": "week", "Maand": "maand", "Jaar": "jaar"}
    group_col = col_map[periode]

    chart = df_db.groupby([group_col, "afdeling"])["shrink"].sum().reset_index()

    fig = px.line(chart, x=group_col, y="shrink", color="afdeling", title="Shrink evolutie")
    st.plotly_chart(fig, use_container_width=True)

    # Week vergelijking
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

    # Alerts
    st.subheader("🚨 Alerts")
    top = df_db.groupby("afdeling")["shrink"].sum().sort_values(ascending=False).head(3)
    for afdeling, value in top.items():
        st.warning(f"{afdeling} hoge shrink: €{value:.2f}")

    # AI insights
    st.subheader("🧠 Insights")
    for afdeling in df_db["afdeling"].unique():
        temp = df_db[df_db["afdeling"] == afdeling].sort_values("week")
        if len(temp) >= 3:
            last3 = temp["shrink"].tail(3)
            if last3.is_monotonic_increasing:
                st.error(f"{afdeling} verslechtert 3 weken op rij")
            if last3.is_monotonic_decreasing:
                st.success(f"{afdeling} verbetert 3 weken op rij")

    # Product analyse
    if not df_products.empty:
        st.subheader("📦 Top producten")
        top_products = df_products.groupby("product")["stuks"].sum().sort_values(ascending=False).head(10)
        st.plotly_chart(px.bar(top_products), use_container_width=True)

        st.subheader("📌 Redenen")
        redenen = df_products.groupby("reden")["stuks"].sum().sort_values(ascending=False)
        st.plotly_chart(px.bar(redenen), use_container_width=True)

# =====================
# ➕ SLIMME INPUT
# =====================

elif menu == "➕ Data invoeren":

    st.title("➕ Data invoeren")

    today = datetime.datetime.now()

    # defaults
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

            st.success("✅ Opgeslagen!")

            # 🔥 AUTO VOLGENDE WEEK
            st.session_state.week += 1

            # reset velden
            st.session_state.shrink = 0.0
            st.session_state.sales = 0.0
            st.session_state.percent = 0.0

# =====================
# 📤 UPLOAD PRODUCTEN
# =====================

elif menu == "📤 Upload producten":

    st.title("📤 Upload producten")

    file = st.file_uploader("Upload Excel", type=["xlsx"])

    if file:

        df = pd.read_excel(file)

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

                stuks = 0 if pd.isna(row.get("stuks")) else float(row.get("stuks"))

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
