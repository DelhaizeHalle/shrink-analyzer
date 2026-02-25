import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
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
    try:f
        res = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        if res.session:
            return res.session.user
    except Exception as e:
        st.error(e)
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

    df_weeks = pd.DataFrame(
        supabase.table("weeks")
        .select("*")
        .eq("user_id", user_id)
        .execute().data or []
    )

    df_products = pd.DataFrame(
        supabase.table("shrink_data")
        .select("*")
        .eq("user_id", user_id)
        .execute().data or []
    )

    return df_weeks, df_products

df_weeks, df_products = load_data(user_id)


# =====================
# MENU
# =====================

menu = st.sidebar.radio("Menu", [
    "📊 Dashboard",
    "➕ Data invoeren (weeks)",
    "📤 Upload producten",
    "📦 Product data bekijken"
])

# =====================
# DASHBOARD
# =====================

if menu == "📊 Dashboard":

    st.title("📊 Weekly Shrink Analyzer")

    if df_weeks.empty:
        st.warning("Geen data in weeks")
        st.stop()

    df_weeks["shrink"] = pd.to_numeric(df_weeks["shrink"], errors="coerce").fillna(0)

    total_shrink = df_weeks["shrink"].sum()

    dept = df_weeks.groupby("afdeling")["shrink"].sum().sort_values(ascending=False)

    col1, col2 = st.columns(2)
    col1.metric("💸 Totale shrink (€)", f"€{total_shrink:.2f}")
    col2.metric("🏬 Aantal afdelingen", len(dept))

    st.subheader("🏬 Shrink per afdeling")
    st.dataframe(dept)

    fig, ax = plt.subplots()
    dept.head(10).plot(kind='bar', ax=ax)
    plt.xticks(rotation=45)
    st.pyplot(fig)

    # 🔥 Top verlies per week
    st.subheader("🔥 Top verlies per week")

    weekly_loss = (
        df_weeks
        .groupby(["jaar", "week"])["shrink"]
        .sum()
        .reset_index()
    )

    weekly_loss["label"] = (
        weekly_loss["jaar"].astype(str) + "-W" +
        weekly_loss["week"].astype(str)
    )

    weekly_loss = weekly_loss.sort_values("shrink", ascending=False)

    st.dataframe(weekly_loss.head(10))

    fig2, ax2 = plt.subplots()
    weekly_loss.head(10).set_index("label")["shrink"].plot(kind="bar", ax=ax2)
    plt.xticks(rotation=45)
    st.pyplot(fig2)

# =====================
# DATA INVOEREN
# =====================

elif menu == "➕ Data invoeren (weeks)":

    st.title("➕ Weeks data invoeren")

    today = datetime.datetime.now()

    jaar = st.number_input("Jaar", value=today.year)
    maand = st.number_input("Maand", value=today.month)
    week = st.number_input("Week", value=today.isocalendar()[1])

    afdeling = st.text_input("Afdeling")

    shrink = st.number_input("Shrink €")
    sales = st.number_input("Sales €")
    percent = st.number_input("Shrink %")

    if st.button("Opslaan"):

        try:
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
            st.rerun()

        except Exception as e:
            st.error(e)

# =====================
# UPLOAD PRODUCTEN
# =====================

elif menu == "📤 Upload producten":

    st.title("📤 Upload Excel")

    file = st.file_uploader("Upload Excel", type=["xlsx"])

    if file:

        df = pd.read_excel(file)
        df.columns = df.columns.str.strip()

        df = df.rename(columns={
            "Datum": "datum",
            "Benaming": "product",
            "Reden / Winkel": "reden",
            "Hoeveelheid": "stuks",
            "Totale prijs": "euro"
        })

        cols_to_drop = ["%", "Source.Name", "Type wijziging", "EAN", "Hope", 
                        "Wijzigbaar", "Zenden", "Prijs", "Nw. Prijs", 
                        "Groothandelsprijs", "Totale groothandels"]

        df = df.drop(columns=[col for col in cols_to_drop if col in df.columns])

        df["datum"] = pd.to_datetime(df["datum"], errors="coerce")
        df = df[df["datum"].notna()]

        df["week"] = df["datum"].dt.isocalendar().week.astype(int)
        df["jaar"] = df["datum"].dt.year.astype(int)
        df["maand"] = df["datum"].dt.month.astype(int)

        df["stuks"] = pd.to_numeric(df["stuks"], errors="coerce").fillna(0)
        df["euro"] = pd.to_numeric(df["euro"], errors="coerce").fillna(0)

        df["product"] = df["product"].astype(str).str.upper().str.strip()

        df["reden"] = (
            df["reden"]
            .astype(str)
            .str.replace(r'^\d+\s*', '', regex=True)
            .str.upper()
            .str.strip()
        )

        df = df[[
            "datum",
            "week",
            "jaar",
            "maand",
            "product",
            "reden",
            "stuks",
            "euro"
        ]]

        st.dataframe(df.head())

        if st.button("Uploaden"):

            df["user_id"] = str(user_id)
            df["categorie"] = "ONBEKEND"

            def clean_value(x):
                if pd.isna(x):
                    return None
                if isinstance(x, (pd.Timestamp, datetime.date, datetime.datetime)):
                    return x.strftime("%Y-%m-%d")
                return x

            data = []
            for _, row in df.iterrows():
                record = {col: clean_value(row[col]) for col in df.columns}
                data.append(record)

            batch_size = 500
            for i in range(0, len(data), batch_size):
                batch = data[i:i+batch_size]
                try:
                    supabase.table("shrink_data").insert(batch).execute()
                except Exception as e:
                    st.error(e)
                    st.stop()

            st.success("✅ Upload klaar")
            st.cache_data.clear()
            st.rerun()

# =====================
# PRODUCT DATA
# =====================

elif menu == "📦 Product data bekijken":

    st.title("📦 Product data")

    if df_products.empty:
        st.warning("Geen product data")
        st.stop()

    # =====================
    # 🔥 FILTER OP PAGINA
    # =====================

    st.subheader("🎯 Filter op reden")

    reden_opties = sorted(df_products["reden"].dropna().unique())

    selected_redenen = st.multiselect(
        "Selecteer reden(en)",
        options=reden_opties,
        default=reden_opties
    )

    df_filtered = df_products[df_products["reden"].isin(selected_redenen)]

    # =====================
    # DATA CLEAN
    # =====================

    df_filtered["stuks"] = pd.to_numeric(df_filtered["stuks"], errors="coerce").fillna(0)
    df_filtered["euro"] = pd.to_numeric(df_filtered.get("euro", 0), errors="coerce").fillna(0)

    st.write("Aantal records:", len(df_filtered))

    # =====================
    # REDENEN
    # =====================

    st.subheader("Redenen (gefilterd)")
    st.dataframe(df_filtered["reden"].value_counts())

    # =====================
    # TOP PRODUCTEN
    # =====================

    top_products = (
        df_filtered
        .groupby("product")
        .agg({
            "stuks": "sum",
            "euro": "sum"
        })
    )

    st.subheader("Top 20 op €")
    st.dataframe(top_products.sort_values("euro", ascending=False).head(20))

    st.subheader("Top 20 op stuks")
    st.dataframe(top_products.sort_values("stuks", ascending=False).head(20))

    # =====================
    # DATA TABLE
    # =====================

    st.subheader("Data (gefilterd)")
    st.dataframe(df_filtered.head(100))


