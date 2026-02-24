import streamlit as st
import pandas as pd
from supabase import create_client

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
        return supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
    except Exception as e:
        st.error(e)
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
        st.success("✅ Ingelogd!")
    else:
        st.error("❌ Login mislukt")

if not st.session_state["user"]:
    st.warning("Log eerst in")
    st.stop()

user_id = st.session_state["user"].id

# =====================
# MENU
# =====================

menu = st.sidebar.radio("Menu", [
    "📊 Dashboard",
    "➕ Data invoeren",
    "📤 Upload Excel"
])

# =====================
# DATA OPHALEN
# =====================

data = supabase.table("weeks").select("*").eq("user_id", user_id).execute()

df_db = pd.DataFrame(data.data) if data.data else pd.DataFrame()

# =====================
# 📊 DASHBOARD
# =====================

if menu == "📊 Dashboard":

    st.title("📊 Dashboard")

    if df_db.empty:
        st.info("Nog geen data")
    else:
        # filters
        jaar_filter = st.selectbox("Selecteer jaar", sorted(df_db["jaar"].dropna().unique()))
        df_filtered = df_db[df_db["jaar"] == jaar_filter]

        # metrics
        totaal_sales = df_filtered["sales"].sum()
        totaal_shrink = df_filtered["shrink"].sum()

        col1, col2 = st.columns(2)
        col1.metric("💰 Sales", f"€{totaal_sales:.2f}")
        col2.metric("📉 Shrink", f"€{totaal_shrink:.2f}")

        # grafiek per week
        st.subheader("📈 Sales per week")
        week_chart = df_filtered.groupby("week")["sales"].sum()
        st.line_chart(week_chart)

        # top afdelingen
        if "afdeling" in df_filtered.columns:
            st.subheader("🏬 Top afdelingen")
            top = df_filtered.groupby("afdeling")["shrink"].sum().sort_values(ascending=False)
            st.bar_chart(top)

# =====================
# ➕ DATA INVOEREN
# =====================

elif menu == "➕ Data invoeren":

    st.title("➕ Nieuwe data invoeren")

    with st.form("data_form"):

        jaar = st.number_input("Jaar", value=2026)
        week = st.number_input("Week", value=1)
        maand = st.number_input("Maand", value=1)

        afdeling = st.text_input("Afdeling")

        shrink = st.number_input("ID Shrink €", value=0.0)
        sales = st.number_input("Sales excl VAT", value=0.0)
        percent = st.number_input("ID Shrink %", value=0.0)

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

            st.success("✅ Data opgeslagen!")

# =====================
# 📤 UPLOAD EXCEL
# =====================

elif menu == "📤 Upload Excel":

    st.title("📤 Upload Excel")

    uploaded_file = st.file_uploader("Upload Excel", type=["xlsx"])

    if uploaded_file is not None:

        df = pd.read_excel(uploaded_file, sheet_name="Afdeling")

        if st.button("💾 Opslaan in database"):

            data_to_insert = []

            for _, row in df.iterrows():

                # veilige waardes
                week = int(row["Week"]) if pd.notna(row.get("Week")) else 0
                sales = float(row["ID Shrink €"]) if pd.notna(row.get("ID Shrink €")) else 0

                data_to_insert.append({
                    "user_id": user_id,
                    "week": week,
                    "jaar": 2024,
                    "sales": sales,
                    "shrink": sales  # indien nodig aanpassen
                })

            supabase.table("weeks").insert(data_to_insert).execute()

            st.success(f"✅ {len(data_to_insert)} rijen opgeslagen!")

# =====================
# 📥 DATA TABEL
# =====================

st.subheader("☁️ Jouw data")

if not df_db.empty:
    st.dataframe(df_db)
else:
    st.info("Nog geen data")

