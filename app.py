import streamlit as st
import pandas as pd
from supabase import create_client

# =====================
# SUPABASE CONFIG
# =====================

SUPABASE_URL = "https://adivczeimpamlhgaxthw.supabase.co"
SUPABASE_KEY = "sb_publishable_YB09KMt3LV8ol4ieLdGk-Q_acN1GI1I"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# =====================
# LOGIN FUNCTIE
# =====================

def login(email, password):
    try:
        res = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        return res
    except Exception as e:
        st.error(f"Login fout: {e}")
        return None

# =====================
# SESSION
# =====================

if "user" not in st.session_state:
    st.session_state["user"] = None

# =====================
# SIDEBAR LOGIN
# =====================

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

# STOP als niet ingelogd
if not st.session_state["user"]:
    st.warning("Log eerst in")
    st.stop()

user_id = st.session_state["user"].id

# =====================
# TITEL
# =====================

st.title("📊 Shrink Analyzer Pro")
st.markdown("### 🏬 Afdeling + Product + AI inzichten")

# =====================
# UPLOAD
# =====================

uploaded_file = st.file_uploader("Upload je shrink bestand (Excel)", type=["xlsx"])

if uploaded_file is not None:

    df = pd.read_excel(uploaded_file, sheet_name="Afdeling")
    df_p = pd.read_excel(uploaded_file, sheet_name="Producten")

    # =====================
    # CLEANING
    # =====================

    df_p["datum"] = pd.to_datetime(df_p["datum"], errors="coerce")
    df_p["stuks"] = pd.to_numeric(df_p["stuks"], errors="coerce")

    df_p["week"] = df_p["datum"].dt.isocalendar().week
    df_p["jaar"] = df_p["datum"].dt.year
    df_p["maand"] = df_p["datum"].dt.month

    # =====================
    # 📊 AFDELING ANALYSE
    # =====================

    st.subheader("🏬 Afdeling analyse")

    total_shrink = df["ID Shrink €"].sum()
    dept = df.groupby("Afdeling")["ID Shrink €"].sum().sort_values(ascending=False)

    col1, col2 = st.columns(2)
    col1.metric("💸 Totale shrink (€)", f"€{total_shrink:.2f}")
    col2.metric("🏬 Aantal afdelingen", len(dept))

    st.write(dept)

    top_dept = dept.idxmax()
    st.error(f"🔴 Grootste probleem: {top_dept}")

    # =====================
    # 💾 OPSLAAN NAAR SUPABASE (FIXED)
    # =====================

    if st.button("💾 Opslaan in database"):

        for _, row in df.iterrows():

            # veilige week
            try:
                week = int(row.get("Week"))
            except:
                week = 0

            # veilige sales
            try:
                sales = float(row["ID Shrink €"])
            except:
                sales = 0

            supabase.table("weeks").insert({
                "user_id": user_id,
                "week": week,
                "jaar": 2024,
                "sales": sales
            }).execute()

        st.success("✅ Data opgeslagen!")

    # =====================
    # 📅 WEEK VERGELIJKING
    # =====================

    st.subheader("📅 Week vergelijking")

    if "Week" in df.columns and df["Week"].nunique() >= 2:

        week_data = df.groupby(["Week", "Afdeling"])["ID Shrink €"].sum().reset_index()
        pivot = week_data.pivot(index="Week", columns="Afdeling", values="ID Shrink €").sort_index()

        last = pivot.iloc[-1]
        prev = pivot.iloc[-2]

        for afdeling in pivot.columns:
            verschil = last[afdeling] - prev[afdeling]

            if verschil > 0:
                st.error(f"{afdeling}: +€{verschil:.2f}")
            else:
                st.success(f"{afdeling}: €{verschil:.2f}")

    # =====================
    # 🔍 ZOEKEN
    # =====================

    st.subheader("🔍 Zoeken")

    search = st.text_input("Zoek product of reden")

    if search:
        results = df_p[
            df_p["benaming"].str.contains(search, case=False, na=False) |
            df_p["reden"].str.contains(search, case=False, na=False)
        ]
        st.dataframe(results)

    # =====================
    # 📦 PRODUCT ANALYSE
    # =====================

    st.subheader("📦 Product analyse")

    top_products = df_p.groupby(["benaming", "categorie"])["stuks"].sum().sort_values(ascending=False).head(10)

    for (product, cat), value in top_products.items():

        with st.expander(f"{product} ({cat}) - {int(value)} stuks"):

            data = df_p[df_p["benaming"] == product]
            redenen = data.groupby("reden")["stuks"].sum()

            st.write(redenen)

    # =====================
    # 🔥 INSIGHT
    # =====================

    st.subheader("🔥 Inzichten")

    st.warning(f"""
    🔴 Grootste probleem afdeling: {top_dept}
    """)

# =====================
# 📥 DATA UIT SUPABASE LADEN
# =====================

st.subheader("☁️ Jouw opgeslagen data")

data = supabase.table("weeks").select("*").eq("user_id", user_id).execute()

if data.data:
    df_db = pd.DataFrame(data.data)
    st.dataframe(df_db)
else:
    st.info("Nog geen opgeslagen data")
