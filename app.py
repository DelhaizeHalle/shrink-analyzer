import streamlit as st
import pandas as pd
from supabase import create_client
import datetime
import numpy as np
from openai import OpenAI

# =====================
# CONFIG
# =====================

st.set_page_config(layout="wide")

SUPABASE_URL = "https://adivczeimpamlhgaxthw.supabase.co"
SUPABASE_KEY = "sb_publishable_YB09KMt3LV8ol4ieLdGk-Q_acNlGllI"

store_id = "delhaize_halle"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# =====================
# HELPERS
# =====================

def format_date_series(series):
    return pd.to_datetime(series, errors="coerce").dt.strftime("%d/%m/%Y")


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


if not st.session_state["user"]:

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

    st.stop()


st.sidebar.success("✅ Ingelogd")
st.sidebar.markdown(f"👤 {st.session_state['user'].email}")

if st.sidebar.button("🚪 Logout"):
    st.session_state["user"] = None
    st.rerun()

# =====================
# DATA LOAD
# =====================


def fetch_all(table, columns):

    all_data = []
    start = 0
    batch = 1000

    while True:

        res = (
            supabase.table(table)
            .select(columns)
            .eq("store_id", store_id)
            .range(start, start + batch - 1)
            .execute()
        )

        data = res.data

        if not data:
            break

        all_data.extend(data)

        if len(data) < batch:
            break

        start += batch

    return pd.DataFrame(all_data)


@st.cache_data(ttl=60)
def load_data():

    weeks_cols = "jaar,week,maand,afdeling,shrink,sales"
    products_cols = "datum,product,hope,reden,stuks,euro"

    df_weeks = fetch_all("weeks", weeks_cols)
    df_products = fetch_all("shrink_data", products_cols)

    if not df_weeks.empty:
        df_weeks["shrink"] = pd.to_numeric(df_weeks["shrink"], errors="coerce").fillna(0)
        df_weeks["sales"] = pd.to_numeric(df_weeks["sales"], errors="coerce").fillna(0)

    if not df_products.empty:
        df_products["datum"] = pd.to_datetime(df_products["datum"], errors="coerce")
        df_products["stuks"] = pd.to_numeric(df_products["stuks"], errors="coerce").fillna(0)
        df_products["euro"] = pd.to_numeric(df_products["euro"], errors="coerce").fillna(0)
        df_products["reden"] = df_products["reden"].fillna("Onbekend")

    return df_weeks, df_products


df_weeks, df_products = load_data()

# =====================
# MENU
# =====================

menu = st.sidebar.radio("Menu", [
    "📊 Dashboard",
    "📦 Product analyse (PRO)",
    "➕ Data invoeren",
    "📤 Upload"
])

# =====================
# DASHBOARD
# =====================

if menu == "📊 Dashboard":

    st.title("📊 Weekly Shrink Dashboard")

    df = df_weeks.copy()

    if df.empty:
        st.warning("Geen data")
        st.stop()

    # =====================
    # AFDELING FILTER
    # =====================

    st.subheader("🎯 Afdeling")

    afdeling_opties = sorted(df["afdeling"].dropna().unique())

    col1, col2 = st.columns([1,3])

    with col1:
        select_all = st.checkbox("Alles", value=True)

    with col2:

        if select_all:
            selected = afdeling_opties

        else:
            selected = st.multiselect("Kies afdeling", afdeling_opties)

    if not selected:
        selected = afdeling_opties

    df = df[df["afdeling"].isin(selected)]

    # =====================
    # KPI
    # =====================

    total_shrink = df["shrink"].sum()
    total_sales = df["sales"].sum()

    shrink_pct = (total_shrink / total_sales * 100) if total_sales > 0 else 0

    weeks_sorted = sorted(df["week"].unique())

    latest_week = weeks_sorted[-1]
    previous_week = weeks_sorted[-2] if len(weeks_sorted) > 1 else latest_week

    current = df[df["week"] == latest_week]["shrink"].sum()
    previous = df[df["week"] == previous_week]["shrink"].sum()

    delta = current - previous

    col1,col2,col3,col4 = st.columns(4)

    col1.metric("💸 Totale shrink", f"€{total_shrink:.2f}")
    col2.metric("🛒 Totale sales", f"€{total_sales:.2f}")
    col3.metric("📊 Shrink %", f"{shrink_pct:.2f}%")
    col4.metric("📉 vs vorige week", f"€{current:.2f}", f"{delta:.2f}", delta_color="inverse")

    # =====================
    # TREND
    # =====================

    st.subheader("📈 Trend per week")

    weekly = df.groupby(["jaar","week"]).agg({
        "shrink":"sum",
        "sales":"sum"
    }).reset_index()

    weekly["shrink_pct"] = weekly["shrink"] / weekly["sales"] * 100

    weekly["label"] = weekly["jaar"].astype(str) + "-W" + weekly["week"].astype(str)
    weekly = weekly.set_index("label")

    st.line_chart(weekly["shrink_pct"])

    # =====================
    # AFDELING VERGELIJKING
    # =====================

    st.subheader("⚖️ Verschil vs vorige week per afdeling")

    current_dept = df[df["week"] == latest_week].groupby("afdeling")["shrink"].sum()
    previous_dept = df[df["week"] == previous_week].groupby("afdeling")["shrink"].sum()

    compare = pd.DataFrame({
        "current":current_dept,
        "previous":previous_dept
    }).fillna(0)

    compare["verschil"] = compare["current"] - compare["previous"]

    st.dataframe(compare.sort_values("verschil", ascending=False))


# =====================
# PRODUCT ANALYSE
# =====================

elif menu == "📦 Product analyse (PRO)":

    st.title("📦 Shrink Intelligence Dashboard")

    df = df_products.copy()

    if df.empty:
        st.warning("Geen data")
        st.stop()

    # =====================
    # REDEN FILTER
    # =====================

    st.subheader("🎯 Reden")

    redenen = sorted(df["reden"].unique())

    select_all = st.checkbox("Alles", value=True)

    if select_all:
        selected = redenen
    else:
        selected = st.multiselect("Kies reden", redenen)

    if not selected:
        selected = redenen

    df = df[df["reden"].isin(selected)]

    # =====================
    # DATUM FILTER
    # =====================

    min_date = df["datum"].min()
    max_date = df["datum"].max()

    date_range = st.date_input("📅 Periode", [min_date, max_date])

    df = df[
        (df["datum"] >= pd.to_datetime(date_range[0])) &
        (df["datum"] <= pd.to_datetime(date_range[1]))
    ]

    # =====================
    # KPI
    # =====================

    tg2g = df[df["reden"].str.lower().str.contains("andere")]

    pakketten = tg2g["stuks"].sum()
    recup = pakketten * 5

    bruto = df["euro"].sum()
    netto = bruto - recup

    col1,col2,col3 = st.columns(3)

    col1.metric("💸 Bruto verlies", f"€{bruto:.2f}")
    col2.metric("♻️ Recuperatie", f"€{recup:.2f}", f"{int(pakketten)} pakketten")
    col3.metric("💰 Netto verlies", f"€{netto:.2f}")

    st.divider()

    # =====================
    # GRAFIEKEN
    # =====================

    st.subheader("📊 Verlies per reden")
    st.bar_chart(df.groupby("reden")["euro"].sum())

    st.subheader("📈 Trend per week")
    df["week"] = df["datum"].dt.isocalendar().week
    st.line_chart(df.groupby("week")["euro"].sum())

    # =====================
    # TOP PRODUCTEN
    # =====================

    st.subheader("💸 Grootste verlies per product")

    top_products = (
        df.groupby(["product","hope"])
        .agg({
            "stuks":"sum",
            "euro":"sum"
        })
        .reset_index()
        .sort_values("euro", ascending=False)
        .head(20)
    )

    st.dataframe(top_products, use_container_width=True, hide_index=True)

    # =====================
    # HOPE ZOEK
    # =====================

    st.subheader("🔍 Zoek product (HOPE)")

    search_hope = st.text_input("Geef HOPE nummer")

    if search_hope:

        df["hope"] = df["hope"].astype(str)

        result = df[df["hope"].str.contains(search_hope, na=False)]

        if result.empty:

            st.warning("Geen product gevonden")

        else:

            st.success(f"{len(result)} records gevonden")

            col1,col2 = st.columns(2)

            col1.metric("📦 Totaal stuks", int(result["stuks"].sum()))
            col2.metric("💸 Totaal verlies", f"€{result['euro'].sum():.2f}")

            st.write("**Product:**", result["product"].iloc[0])

            st.subheader("📊 Verlies per reden")
            st.bar_chart(result.groupby("reden")["euro"].sum())

            st.subheader("📅 Verlies over tijd")
            st.line_chart(result.groupby("datum")["euro"].sum())

            st.subheader("📋 Detail")
            st.dataframe(result.sort_values("datum", ascending=False), hide_index=True)

    # =====================
    # AI INSIGHTS (LAATSTE MAAND)
    # =====================

    st.subheader("🧠 AI analyse (laatste maand)")

    if st.button("Genereer AI analyse"):

        if df.empty:
            st.warning("Geen data")
            st.stop()

        # =====================
        # FILTER LAATSTE MAAND
        # =====================

        latest_date = df["datum"].max()
        start_date = latest_date - pd.DateOffset(days=30)

        df_month = df[df["datum"] >= start_date]

        if df_month.empty:
            st.warning("Geen data voor laatste maand")
            st.stop()

    # =====================
    # WEEK TREND
    # =====================

        weekly_loss = df_month.groupby("week")["euro"].sum().sort_index()

        if len(weekly_loss) > 1:
            last_week = weekly_loss.iloc[-1]
            prev_week = weekly_loss.iloc[-2]
            change_pct = ((last_week - prev_week) / prev_week * 100) if prev_week > 0 else 0
        else:
            change_pct = 0

        # =====================
        # TOP PRODUCTEN
        # =====================

        top_products = (
            df_month.groupby("product")["euro"]
            .sum()
            .sort_values(ascending=False)
            .head(5)
        )

        # =====================
        # TOP REDENEN
        # =====================

        top_reasons = (
            df_month.groupby("reden")["euro"]
            .sum()
            .sort_values(ascending=False)
            .head(5)
        )

        # =====================
        # 80/20 VERLIES
        # =====================

        product_loss = (
            df_month.groupby("product")["euro"]
            .sum()
            .sort_values(ascending=False)
        )

        cum = product_loss.cumsum() / product_loss.sum()

        critical_products = product_loss[cum <= 0.8].head(10)

        # =====================
        # AI PROMPT
        # =====================

        prompt = f"""
    Je bent een retail shrink expert voor een supermarkt.

    Analyseer de shrink data van de laatste maand.

    Periode:
    {start_date.date()} tot {latest_date.date()}

    Week verandering:
    {change_pct:.1f} %

    Top verlies producten:
    {top_products}

    Top verlies redenen:
    {top_reasons}

    Producten die 80% van het verlies veroorzaken:
    {critical_products}

    Schrijf een analyse voor een winkelmanager met deze structuur:

    ⚠️ Grootste probleem
    📦 Belangrijkste producten
    🔍 Mogelijke oorzaken
    📊 Belangrijkste trend deze maand
    ✅ 3 concrete acties voor de winkel

    De analyse moet praktisch en kort zijn.
    """

        try:

            response = client.responses.create(
                model="gpt-4o-mini",
                input=prompt
            )

            ai_text = response.output[0].content[0].text

            st.success("AI Analyse laatste maand")

            st.write(ai_text)

        except Exception as e:

            st.error(f"AI fout: {e}")

    df_display = df.copy()
    df_display["datum"] = format_date_series(df_display["datum"])

    st.dataframe(df_display.head(200))


# =====================
# DATA INVOEREN
# =====================

elif menu == "➕ Data invoeren":

    st.title("➕ Weeks invoer")

    today = datetime.datetime.now()

    afdelingen = [
        "DIEPVRIES","VOEDING","PARFUMERIE","DROGISTERIJ",
        "FRUIT EN GROENTEN","ZUIVEL","VERS VLEES",
        "GEVOGELTE","CHARCUTERIE","VIS EN SAURISSERIE",
        "SELF-TRAITEUR","BAKKERIJ","TRAITEUR","DRANKEN"
    ]

    jaar = st.number_input("Jaar", value=today.year)
    maand = st.number_input("Maand", value=today.month)
    week = st.number_input("Week", value=today.isocalendar()[1])

    afdeling = st.selectbox("Afdeling", afdelingen)

    shrink = st.number_input("Shrink €")
    sales = st.number_input("Sales €")

    if st.button("💾 Opslaan"):

        supabase.table("weeks").insert({
            "store_id":store_id,
            "jaar":int(jaar),
            "maand":int(maand),
            "week":int(week),
            "afdeling":afdeling,
            "shrink":float(shrink),
            "sales":float(sales)
        }).execute()

        st.success("✅ Opgeslagen")

        st.cache_data.clear()



