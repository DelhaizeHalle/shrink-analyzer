import streamlit as st
import pandas as pd
from supabase import create_client
import datetime
import numpy as np
import matplotlib.pyplot as plt
from openai import OpenAI

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4

# =====================
# CONFIG
# =====================

DEBUG = False
st.set_page_config(layout="wide")

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

store_id = "delhaize_halle"
WINST_PER_PAKKET = 3.29
PAKKET_REDEN = "38 VERLIES - ANDERE"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# =====================
# HELPERS
# =====================

def format_date_series(series):
    return pd.to_datetime(series, errors="coerce").dt.strftime("%d/%m/%Y")


def get_color(value, type="euro"):
    if type == "pct":
        if value > 4:
            return colors.red
        elif value > 2:
            return colors.orange
        else:
            return colors.green
    else:
        if value > 300:
            return colors.red
        elif value > 100:
            return colors.orange
        else:
            return colors.green

def generate_pdf(df, afdeling, total_loss, total_sales, shrink_pct):

    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
    from reportlab.lib.styles import getSampleStyleSheet
    from io import BytesIO
    import matplotlib.pyplot as plt
    import tempfile
    import pandas as pd

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    # =====================
    # TITEL
    # =====================
    elements.append(Paragraph(f"Rapport - {afdeling}", styles["Title"]))
    elements.append(Spacer(1, 20))

    # =====================
    # KPI
    # =====================
    elements.append(Paragraph(f"Verlies: €{total_loss:.2f}", styles["Normal"]))
    elements.append(Paragraph(f"Sales: €{total_sales:.2f}", styles["Normal"]))
    elements.append(Paragraph(f"Shrink %: {shrink_pct:.2f}%", styles["Normal"]))
    elements.append(Spacer(1, 20))

    # =====================
    # DATA CLEAN
    # =====================
    df["datum"] = pd.to_datetime(df["datum"], errors="coerce")

    df["datum_shift"] = df["datum"] - pd.Timedelta(days=3)
    df["week"] = df["datum_shift"].dt.isocalendar().week

    df["euro"] = pd.to_numeric(df["euro"], errors="coerce").fillna(0)
    df["stuks"] = pd.to_numeric(df["stuks"], errors="coerce").fillna(0)

    # =====================
    # 🔥 TOP 10 ALL TIME
    # =====================
    top_all = (
        df.groupby(["product", "hope"])
        .agg({"euro": "sum", "stuks": "sum"})
        .reset_index()
        .sort_values("euro", ascending=False)
        .head(10)
    )

    elements.append(Paragraph("Top 10 verlies (ALL TIME)", styles["Heading2"]))
    elements.append(Spacer(1, 10))

    for _, row in top_all.iterrows():
        elements.append(
            Paragraph(
                f"{row['product']} | €{row['euro']:.2f} | {int(row['stuks'])} stuks",
                styles["Normal"]
            )
        )

    elements.append(Spacer(1, 20))

    # =====================
    # 📅 LAATSTE WEEK
    # =====================
    laatste_week = df["week"].max()

    df_last = df[df["week"] == laatste_week]

    top_week = (
        df_last.groupby(["product", "hope"])
        .agg({"euro": "sum", "stuks": "sum"})
        .reset_index()
        .sort_values("euro", ascending=False)
        .head(10)
    )

    elements.append(Paragraph(f"Top 10 verlies (Week {laatste_week})", styles["Heading2"]))
    elements.append(Spacer(1, 10))

    for _, row in top_week.iterrows():
        elements.append(
            Paragraph(
                f"{row['product']} | €{row['euro']:.2f} | {int(row['stuks'])} stuks",
                styles["Normal"]
            )
        )

    elements.append(Spacer(1, 20))

    # =====================
    # 📦 PER CATEGORIE
    # =====================
    if "reden" in df.columns:

        categorie = (
            df.groupby("reden")
            .agg({"euro": "sum", "stuks": "sum"})
            .reset_index()
            .sort_values("euro", ascending=False)
        )

        elements.append(Paragraph("Verlies per categorie", styles["Heading2"]))
        elements.append(Spacer(1, 10))

        for _, row in categorie.iterrows():
            elements.append(
                Paragraph(
                    f"{row['reden']} | €{row['euro']:.2f} | {int(row['stuks'])} stuks",
                    styles["Normal"]
                )
            )

        elements.append(Spacer(1, 20))

        # =====================
        # 🥧 PIE CHART
        # =====================
        cat_top = categorie.head(5)

        plt.figure()
        plt.pie(
            cat_top["euro"],
            labels=cat_top["reden"],
            autopct="%1.1f%%"
        )
        plt.title("Verdeling verlies")

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
        plt.savefig(tmp.name, bbox_inches="tight")
        plt.close()

        elements.append(Paragraph("Verdeling verlies per categorie", styles["Heading2"]))
        elements.append(Spacer(1, 10))
        elements.append(Image(tmp.name, width=400, height=300))

    # =====================
    # BUILD
    # =====================
    doc.build(elements)
    buffer.seek(0)

    return buffer

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

# session state
if "user" not in st.session_state:
    st.session_state["user"] = None

# 👉 NIET ingelogd → toon login
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

# 👉 WEL ingelogd → toon user + logout
st.sidebar.success("✅ Ingelogd")
st.sidebar.markdown(f"👤 {st.session_state['user'].email}")

if st.sidebar.button("🚪 Logout"):
    st.session_state["user"] = None
    st.rerun()

# =====================
# DATA LOAD
# =====================

@st.cache_data
def load_data():

    def fetch_all(table):
        all_data = []
        start = 0
        batch = 1000

        while True:
            res = (
                supabase.table(table)
                .select("*")
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

    return fetch_all("weeks"), fetch_all("shrink_data")

df_weeks, df_products = load_data()

@st.cache_data
def load_mapping():

    all_data = []
    start = 0
    batch = 1000

    while True:
        res = (
            supabase.table("product_afdelingen")
            .select("*")
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

    df_mapping = pd.DataFrame(all_data)

    if "hope" in df_mapping.columns:
        df_mapping["hope"] = df_mapping["hope"].astype(str).str.strip()

    return df_mapping

# =====================
# MENU
# =====================

menu = st.sidebar.radio("Menu", [
    "📊 Dashboard",
    "📦 Product analyse (PRO)",
    "➕ Data invoeren",
    "📤 Upload",
    "⚙️ Afdeling beheer",
    "🧊 Demo promoties",
    "📑 Rapport", 
])

# =====================
# DASHBOARD
# =====================

if menu == "📊 Dashboard":

    st.title("📊 Weekly Shrink Dashboard")

    df = df_weeks.copy()

    # =====================
    # FILTER AFDELING
    # =====================

    st.subheader("🎯 Afdeling")

    afdeling_opties = sorted(df["afdeling"].dropna().unique())

    col1, col2 = st.columns([1, 3])

    with col1:
        select_all_afdeling = st.checkbox("Alles", value=True, key="afd_all")

    with col2:
        if select_all_afdeling:
            selected_afdelingen = afdeling_opties
        else:
            selected_afdelingen = st.multiselect(
                "Kies afdeling(en)",
                afdeling_opties
            )

    # safety (zelfde als reden)
    if not selected_afdelingen:
        selected_afdelingen = afdeling_opties

    # filter toepassen
    df = df[df["afdeling"].isin(selected_afdelingen)]
    
    if df.empty:
        st.warning("Geen data")
        st.stop()

    df["shrink"] = pd.to_numeric(df["shrink"], errors="coerce").fillna(0)
    df["sales"] = pd.to_numeric(df["sales"], errors="coerce").fillna(0)

    total_shrink = df["shrink"].sum()
    total_sales = df["sales"].sum()
    shrink_pct = (total_shrink / total_sales * 100) if total_sales > 0 else 0

    latest_week = df["week"].max()

    current = df[df["week"] == latest_week]["shrink"].sum()
    previous = df[df["week"] == latest_week - 1]["shrink"].sum()

    delta = current - previous

    col1, col2, col3, col4 = st.columns([1.2, 1.2, 0.8, 1])

    col1.metric("💸 Totale shrink", f"€{total_shrink:.2f}")
    col2.metric("🛒 Totale sales", f"€{total_sales:.2f}")
    col3.metric("📊 Shrink %", f"{shrink_pct:.2f}%")
    col4.metric("📉 vs vorige week", f"€{current:.2f}", f"{delta:.2f}", delta_color="inverse")

  
    weekly = df.groupby(["jaar", "week"]).agg({
        "shrink": "sum",
        "sales": "sum"
    }).reset_index()

    # ✅ sortering (super belangrijk!)
    weekly = weekly.sort_values(["jaar", "week"])

    # =====================
    # 🔥 SHRINK % berekenen
    # =====================
    weekly["shrink_pct"] = (
        weekly["shrink"] / weekly["sales"] * 100
    ).replace([np.inf, -np.inf], 0).fillna(0)

    # =====================
    # 📉 SHRINK (BELANGRIJKSTE)
    # =====================
    st.subheader("📉 Shrink per week")
    st.line_chart(weekly.set_index("week")["shrink"])

    # =====================
    # 📈 SALES (CONTEXT)
    # =====================
    with st.expander("📈 Sales per week", expanded=False):
        st.line_chart(weekly.set_index("week")["sales"])

    # =====================
    # 📊 SHRINK %
    # =====================
    with st.expander("📊 Shrink % per week", expanded=False):
        st.line_chart(weekly.set_index("week")["shrink_pct"])

    # ⚖️ vergelijking
    st.subheader("⚖️ Verschil vs vorige week per afdeling")

    current_week = df[df["week"] == latest_week]
    previous_week = df[df["week"] == latest_week - 1]

    current_dept = current_week.groupby("afdeling").agg({
        "shrink": "sum",
        "sales": "sum"
    }).rename(columns={"shrink": "current_shrink", "sales": "current_sales"})

    previous_dept = previous_week.groupby("afdeling").agg({
        "shrink": "sum",
        "sales": "sum"
    }).rename(columns={"shrink": "previous_shrink", "sales": "previous_sales"})

    compare = current_dept.join(previous_dept, how="outer").fillna(0)

    # verschil in €
    compare["verschil"] = compare["current_shrink"] - compare["previous_shrink"]

    # percentage shrink huidig
    compare["shrink_%"] = (
        compare["current_shrink"] / compare["current_sales"] * 100
    ).replace([np.inf, -np.inf], 0).fillna(0)

    # afronden
    compare = compare.round(2)

    st.dataframe(compare.sort_values("verschil", ascending=False))

elif menu == "⚙️ Afdeling beheer":

    st.title("⚙️ HOPE → Afdeling beheer")

    # =====================
    # ALLE SHRINK DATA OPHALEN (in batches)
    # =====================

    def fetch_all_shrink():
        all_data = []
        start = 0
        batch = 1000

        while True:
            res = (
                supabase.table("shrink_data")
                .select("hope, product, euro")
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

    df_shrink = fetch_all_shrink()

    if df_shrink.empty:
        st.warning("Geen data gevonden")
        st.stop()
        
    # Zorg dat hope string is
    df_shrink["hope"] = df_shrink["hope"].astype(str).str.strip()

    # =====================
    # TOTAAL VERLIES PER HOPE
    # =====================

    df_totals = (
        df_shrink
        .groupby(["hope", "product"], as_index=False)["euro"]
        .sum()
        .sort_values("euro", ascending=False)
    )

    # =====================
    # MAPPING OPHALEN
    # =====================

    df_mapping = load_mapping()
    st.write("Aantal mapping records:", len(df_mapping))
    st.write("Voorbeeld mapping HOPE:", df_mapping["hope"].head())

    # =====================
    # ENKEL NIET-GEMAPTE
    # =====================

    if not df_mapping.empty:
         df_mapping = load_mapping()

         # 🔎 DEBUG START
         if DEBUG:
             st.write("Aantal mapping records:", len(df_mapping))
             st.write("Voorbeeld mapping HOPE:", df_mapping["hope"].head(10).tolist())
             st.write("Voorbeeld totals HOPE:", df_totals["hope"].head(10).tolist())
         # 🔎 DEBUG EINDE

         if not df_mapping.empty:
             df_onbekend = df_totals[
                 ~df_totals["hope"].astype(str).isin(df_mapping["hope"])
             ]
         else:
            df_onbekend = df_totals.copy()

    if df_onbekend.empty:
        st.success("✅ Alle producten hebben een afdeling toegewezen!")
        st.stop()

    st.metric("🔎 Onbekende producten", len(df_onbekend))

    # Toon top 20 onbekenden (gesorteerd op verlies)
    st.dataframe(df_onbekend.head(20), use_container_width=True)

    st.divider()
    st.subheader("✏️ Afdelingen toewijzen (meerdere tegelijk)")

    # Toon tabel met onbekenden
    st.dataframe(
        df_onbekend[["hope", "product", "euro"]].head(100),
        use_container_width=True
    )

    # 🔎 Zoekveld 
    zoekterm = st.text_input("Zoek op HOPE of productnaam")

    df_filter = df_onbekend.copy()
    st.write("Lengte df_filter:", len(df_filter))

    if zoekterm:
        df_filter = df_filter[
            df_filter["hope"].astype(str).str.contains(zoekterm, case=False, na=False)
        | df_filter["product"].str.contains(zoekterm, case=False, na=False)
        ]

    st.caption(f"{len(df_filter)} resultaten gevonden")

    # Multi-select met eigen key
    selected_hopes = st.multiselect(
        "Selecteer HOPE's",
        df_filter["hope"],
        key="selected_hopes",
        format_func=lambda x: f"{x} - {df_filter[df_filter['hope']==x]['product'].values[0]}"
    )

    # Selecteer alle knop
    if st.button("Selecteer alle gefilterde resultaten"):
        st.session_state["selected_hopes"] = df_filter["hope"].tolist()

    # Afdelingen
    afdelingen = [
        "DIEPVRIES",
        "VOEDING",
        "PARFUMERIE",
        "DROGISTERIJ",
        "FRUIT EN GROENTEN",
        "ZUIVEL",
        "VERS VLEES",
        "GEVOGELTE",
        "CHARCUTERIE",
        "VIS EN SAURISSERIE",
        "SELF-TRAITEUR",
        "BAKKERIJ",
        "TRAITEUR",
        "DRANKEN"
    ]

    if selected_hopes:

        nieuwe_afdeling = st.selectbox("Nieuwe afdeling", afdelingen)
        
        if st.button("💾 Opslaan voor selectie"):

            unique_hopes = list(set(selected_hopes))

            data = [
                {
                    "store_id": store_id,
                    "hope": str(hope),
                    "afdeling": nieuwe_afdeling
                }
                for hope in unique_hopes
            ]

            try:
                result = supabase.table("product_afdelingen") \
                    .upsert(data, on_conflict="store_id,hope") \
                    .execute()

                st.session_state["save_message"] = f"✅ {len(unique_hopes)} producten toegewezen"
                st.cache_data.clear()   # 🔥 wist ALLES
                st.rerun()

            except Exception as e:
                st.error(f"❌ Fout bij opslaan: {e}")
        # 👇 HIER komt de melding
        if "save_message" in st.session_state:
            st.success(st.session_state["save_message"])
            del st.session_state["save_message"]
    
    
# =====================
# PRODUCT ANALYSE
# =====================

elif menu == "📦 Product analyse (PRO)":

    st.title("📦 Shrink Intelligence Dashboard")

    df = df_products.copy()

    # =====================
    # 🔄 LIVE MAPPING MERGE
    # =====================

    # mapping ophalen
    df_mapping = load_mapping()

    df["hope"] = df["hope"].astype(str).str.strip()

    if "hope" in df_mapping.columns:
        df_mapping["hope"] = df_mapping["hope"].astype(str).str.strip()

    # verwijder oude afdeling uit shrink_data
    if "afdeling" in df.columns:
        df = df.drop(columns=["afdeling"])

    # merge met live mapping
    df = df.merge(
        df_mapping,
        on="hope",
        how="left"
    )

    df["afdeling"] = df["afdeling"].fillna("ONBEKEND")

    # =====================
    # AFSLAG ANALYSE (SNELLE VERSIE - GEEN LOOPS)
    # =====================

    df["datum"] = pd.to_datetime(df["datum"], errors="coerce")

    grouped = (
        df.groupby(["hope", "datum", "reden"])["euro"]
        .sum()
        .reset_index()
    )

    afslag = grouped[grouped["reden"].str.contains("AFSLAG", case=False, na=False)]
    verval = grouped[grouped["reden"].str.contains("VERVAL", case=False, na=False)]
    tgtg = grouped[grouped["reden"] == "38 VERLIES - ANDERE"]

    merged = afslag.merge(
        verval[["hope", "datum", "euro"]],
        on=["hope", "datum"],
        how="left",
        suffixes=("_afslag", "_verval")
    )

    merged = merged.merge(
        tgtg[["hope", "datum", "euro"]],
        on=["hope", "datum"],
        how="left"
    )

    merged = merged.rename(columns={"euro": "euro_tgtg"})

    merged["euro_verval"] = merged["euro_verval"].fillna(0)
    merged["euro_tgtg"] = merged["euro_tgtg"].fillna(0)

    afslag_euro = merged["euro_afslag"].sum()
    verval_euro = merged["euro_verval"].sum()
    tgtg_euro = merged["euro_tgtg"].sum()

    effectief_verkocht = afslag_euro - verval_euro - tgtg_euro

    if afslag_euro > 0:
        afslag_eff = (effectief_verkocht / afslag_euro) * 100
    else:
        afslag_eff = 0

    # =====================
    # CLEANING
    # =====================

    df["reden"] = df["reden"].fillna("Onbekend")
    df = df[df["datum"].notna()]
    df["stuks"] = pd.to_numeric(df["stuks"], errors="coerce").fillna(0)
    df["euro"] = pd.to_numeric(df["euro"], errors="coerce").fillna(0)

    # =====================
    # FILTER RIJ 1
    # =====================

    col1, col2 = st.columns(2)

    # 🏬 Afdeling
    with col1:
        st.subheader("🏬 Afdeling")

        afdeling_opties = sorted(df["afdeling"].dropna().unique())
        afdeling_keuze = st.selectbox(
            "Kies afdeling",
            ["Alles"] + afdeling_opties,
            label_visibility="collapsed"
        )

        if afdeling_keuze != "Alles":

            # mapping ophalen
            df_mapping = load_mapping()

            if not df_mapping.empty:
                afdeling_hopes = df_mapping[
                    df_mapping["afdeling"] == afdeling_keuze
                ]["hope"].unique()

            df = df[df["hope"].isin(afdeling_hopes)]
            
            # HOPE's van gekozen afdeling
            afdeling_hopes = df_mapping[
                df_mapping["afdeling"] == afdeling_keuze
            ]["hope"].unique()

            # filter shrink_data op die HOPE's
            df = df[df["hope"].isin(afdeling_hopes)]


    # 🎯 Reden
    with col2:
        st.subheader("🎯 Reden")

        reden_opties = sorted(df["reden"].dropna().unique())
        reden_keuze = st.selectbox(
            "Kies reden",
            ["Alles"] + reden_opties,
            label_visibility="collapsed"
        )

        if reden_keuze != "Alles":
            df = df[df["reden"] == reden_keuze]


    # =====================
    # FILTER RIJ 2
    # =====================

    col3, col4 = st.columns(2)

    # 📅 Periode
    with col3:
        st.subheader("📅 Periode")

        min_date = df["datum"].min()
        max_date = df["datum"].max()

        date_range = st.date_input(
            "Kies periode",
            [min_date, max_date],
            label_visibility="collapsed"
        )

        if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
            df = df[
                (df["datum"] >= pd.to_datetime(date_range[0])) &
                (df["datum"] <= pd.to_datetime(date_range[1]))
            ]


    # 🔍 Zoek HOPE
    with col4:
        st.subheader("🔍 Zoek HOPE")

        search_hope = st.text_input(
            "Geef HOPE nummer",
            label_visibility="collapsed"
        )

        if search_hope:
            df = df[df["hope"].astype(str) == search_hope]


# ♻️ Recuperatie pakketten (38 VERLIES - ANDERE)

    tg2g = df[df["reden"] == "38 VERLIES - ANDERE"]

    verlies_andere = tg2g["euro"].sum()

    waarde_pakket = 20
    winst_per_pakket = 3.29   # of 3.29 als dat correct is

    pakketten = verlies_andere / waarde_pakket
    recup = pakketten * winst_per_pakket

    bruto = df["euro"].sum()
    netto = bruto - recup
    recup_pct = (recup / bruto) * 100 if bruto > 0 else 0

    # =====================
    # KPI BLOK (3 + 2 layout)
    # =====================

    # Rij 1 (3 kolommen)
    col1, col2, col3 = st.columns(3)

    col1.metric("💸 Bruto verlies", f"€{bruto:.2f}")
    col2.metric("♻️ Too Good to Go", f"€{recup:.2f}", f"{int(pakketten)} pakketten")
    col3.metric("💰 Netto verlies", f"€{netto:.2f}")

    st.markdown("")

    # Rij 2 (4 kolommen)
    col4, col5, col6, col7 = st.columns(4)

    col4.metric("📦 Afslag totaal", f"€{afslag_euro:.2f}")
    col5.metric("📛 Afslag vuilbak", f"€{verval_euro:.2f}")
    col6.metric("♻️ Afslag TGTG", f"€{tgtg_euro:.2f}")
    col7.metric(
        "📉 Afslag efficiëntie",
        f"{afslag_eff:.1f}%",
        f"€{effectief_verkocht:.2f} effectief verkocht"
    )

    st.divider()

    # 📊 grafieken
    st.subheader("📊 Verlies per reden")
    st.bar_chart(df.groupby("reden")["euro"].sum())

    st.subheader("📈 Trend per week")

    df["datum"] = pd.to_datetime(df["datum"], errors="coerce")

    # 🔥 shift -3 dagen (donderdag start)
    df["datum_shift"] = df["datum"] - pd.Timedelta(days=3)

    df["week"] = df["datum_shift"].dt.isocalendar().week

    trend = df.groupby("week")["euro"].sum().sort_index()

    st.line_chart(trend)

    # optioneel opruimen
    df = df.drop(columns=["datum_shift"])


    # =====================
    # PRODUCTEN PER AFDELING
    # =====================

    st.subheader("📦 Artikels per afdeling")

    producten_per_afdeling = (
        df.groupby("afdeling")["product"]
        .nunique()
        .sort_values(ascending=False)
    )

    st.bar_chart(producten_per_afdeling)

    st.subheader("🏆 Top producten binnen geselecteerde afdeling(en)")

    top_products = (
        df.groupby(["afdeling", "product", "hope"])
        .agg({
            "stuks": "sum",
            "euro": "sum"
        })
        .reset_index()
        .sort_values(["afdeling", "euro"], ascending=[True, False])
    )

    st.dataframe(top_products, use_container_width=True)

    # =====================
    # AI INSIGHTS
    # =====================

    from openai import OpenAI
    import os

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    st.subheader("🧠 AI inzichten")

    if st.button("Genereer AI inzichten"):

        # beperk data (belangrijk voor snelheid)
        sample = df.sample(min(len(df), 50))

        summary = (
            sample.groupby("reden")["euro"]
            .sum()
            .sort_values(ascending=False)
            .head(5)
        )

        prompt = f"""
        Analyseer deze retail shrink data.

        Top verlies redenen:
        {summary.to_string()}

        Geef:
        - grootste probleem
        - belangrijkste oorzaak
        - 2 concrete acties voor de winkel
        """

        try:
            response = client.responses.create(
                model="gpt-4o-mini",
                input=prompt
            )

            ai_text = response.output[0].content[0].text

            st.success("AI Analyse:")
            st.write(ai_text)

        except Exception as e:
            st.error(f"AI fout: {e}")

    # 📋 detail
    df_display = df.copy()
    df_display["datum"] = format_date_series(df_display["datum"])

    st.dataframe(df_display.head(200))

# =====================
# 📤 UPLOAD (zelfde structuur)
# =====================

elif menu == "📤 Upload":

    st.title("📤 Upload shrink_data (Excel)")

    file = st.file_uploader("📎 Kies Excel bestand", type=["xlsx"])

    if file is not None:

        df = pd.read_excel(file)
        df.columns = df.columns.str.strip()

        st.subheader("👀 Preview")
        st.dataframe(df.head(20))

        # =====================
        # KOLOMMEN MAPPING
        # =====================

        df = df.rename(columns={
            "Datum": "datum",
            "Benaming": "product",
            "Reden / Winkel": "reden",
            "Hoeveelheid": "stuks",
            "Totale prijs": "euro",
            "Hope": "hope"
        })

        # =====================
        # CLEANING
        # =====================

        df["datum"] = pd.to_datetime(df["datum"], errors="coerce")
        df = df[df["datum"].notna()]

        if df.empty:
            st.error("❌ Geen geldige data")
            st.stop()

        df["datum_shift"] = df["datum"] - pd.Timedelta(days=3)

        df["week"] = df["datum_shift"].dt.isocalendar().week.astype(int)
        df["jaar"] = df["datum_shift"].dt.isocalendar().year.astype(int)
        df["maand"] = df["datum"].dt.month.astype(int)

        df = df.drop(columns=["datum_shift"])

        df["stuks"] = pd.to_numeric(df["stuks"], errors="coerce").fillna(0)
        df["euro"] = pd.to_numeric(df["euro"], errors="coerce").fillna(0)

        df["product"] = df["product"].astype(str).str.upper().str.strip()
        df["reden"] = df["reden"].astype(str).str.strip()

        # =====================
        # HOPE FIX (cruciaal)
        # =====================

        df["hope"] = (
            pd.to_numeric(df["hope"], errors="coerce")
            .fillna(0)
            .astype(int)
            .astype(str)
        )

        # =====================
        # AFDELING MAPPING
        # =====================

        mapping_res = (
            supabase.table("product_afdelingen")
            .select("*")
            .eq("store_id", store_id)
            .execute()
        )
        mapping_df = pd.DataFrame(mapping_res.data)

        if not mapping_df.empty:
            mapping_df["hope"] = mapping_df["hope"].astype(str)
            df = df.merge(mapping_df, on="hope", how="left")
        else:
            df["afdeling"] = None

        df["afdeling"] = df["afdeling"].fillna("ONBEKEND")

        # =====================
        # KOLOMMEN SELECTIE
        # =====================

        df = df[[
            "datum","week","jaar","maand",
            "afdeling",
            "product","hope","reden","stuks","euro"
        ]]

        df["store_id"] = store_id
        df["categorie"] = "ONBEKEND"

        df = df.replace({np.nan: None})
        df["datum"] = df["datum"].astype(str)

        # =====================
        # BEVEILIGING: max upload
        # =====================

        if len(df) > 10000:
            st.error("❌ Max 10.000 records per upload")
            st.stop()

        # =====================
        # KPI PREVIEW
        # =====================

        col1, col2, col3 = st.columns(3)

        col1.metric("📦 Rijen", len(df))
        col2.metric("💸 Totaal €", f"€{df['euro'].sum():.2f}")
        col3.metric("🛒 Producten", df["product"].nunique())

        # =====================
        # UPLOAD BUTTON
        # =====================

        if st.button("🚀 Upload naar database"):

            data = df.to_dict(orient="records")

            try:
                for i in range(0, len(data), 500):
                    supabase.table("shrink_data").insert(data[i:i+500]).execute()

                st.success(f"✅ {len(data)} records geüpload")

                st.cache_data.clear()
                st.rerun()

            except Exception:
                st.error("❌ Er ging iets mis bij upload")

# =====================
# DATA INVOEREN
# =====================

elif menu == "➕ Data invoeren":

    st.title("➕ Weeks invoer")

    today = datetime.datetime.now()

    afdelingen = [
        "DIEPVRIES",
        "VOEDING",
        "PARFUMERIE",
        "DROGISTERIJ",
        "FRUIT EN GROENTEN",
        "ZUIVEL",
        "VERS VLEES",
        "GEVOGELTE",
        "CHARCUTERIE",
        "VIS EN SAURISSERIE",
        "SELF-TRAITEUR",
        "BAKKERIJ",
        "TRAITEUR",
        "DRANKEN"
    ]

    jaar = st.number_input("Jaar", value=today.year)
    maand = st.number_input("Maand", value=today.month)
    week = st.number_input("Week", value=today.isocalendar()[1])

    afdeling = st.selectbox("Afdeling", afdelingen)

    shrink = st.number_input("Shrink €")
    sales = st.number_input("Sales €")

    if st.button("💾 Opslaan"):

        supabase.table("weeks").insert({
            "store_id": store_id,
            "jaar": int(jaar),
            "maand": int(maand),
            "week": int(week),
            "afdeling": afdeling,
            "shrink": float(shrink),
            "sales": float(sales)
        }).execute()

        st.success(f"✅ Opgeslagen voor {afdeling}")
        st.cache_data.clear()

elif menu == "🧊 Demo promoties":

    st.title("🧊 Demo promoties")

    df = df_products.copy()

    if df.empty:
        st.warning("Geen shrink data beschikbaar")
        st.stop()

    # =====================
    # UNIEKE PRODUCTEN
    # =====================
    df["hope"] = df["hope"].astype(str)
    df_unique = df[["hope", "product"]].drop_duplicates()

    # =====================
    # INPUT
    # =====================

    col1, col2 = st.columns(2)

    with col1:
        demo_nr = st.selectbox("Demo", [1,2,3,4,5])

    with col2:
        week = st.number_input("Week", min_value=1, max_value=52)

    selected_hope = st.selectbox(
        "Product",
        df_unique["hope"],
        format_func=lambda x: f"{x} - {df_unique[df_unique['hope']==x]['product'].values[0]}"
    )

    product_match = df_unique[df_unique["hope"] == selected_hope]

    if product_match.empty:
        st.error("Product niet gevonden")
        st.stop()

    product_name = product_match["product"].values[0]

    promo_type = st.selectbox("Promo type", [
        "GEEN",
        "1+1",
        "2+1",
        "3+1",
        "4+1",
        "2e -50%",
        "2e -20%",
        "2e -40%",
        "2e -70%",
    ])

    sales = st.number_input("Sales (€)", min_value=0.0)

    # =====================
    # 🔥 LIVE SHRINK
    # =====================

    shrink_check = df[
        (df["hope"] == selected_hope) &
        (df["week"] == week)
    ]

    total_shrink = shrink_check["euro"].sum()

    st.metric("💸 Shrink deze week", f"€{total_shrink:.2f}")

    # =====================
    # SAVE
    # =====================

    if st.button("💾 Opslaan"):

        data = {
            "datum": str(datetime.date.today()),
            "week": int(week),
            "jaar": datetime.date.today().year,
            "demo_nr": demo_nr,
            "hope": str(selected_hope),
            "product": product_name,
            "promo_type": promo_type,
            "sales_euro": float(sales),
            "store_id": store_id
        }

        try:
            supabase.table("demo_promos").insert(data).execute()
            st.success("✅ Opgeslagen")

            st.cache_data.clear()
            st.rerun()

        except Exception as e:
            st.error(f"❌ Fout: {e}")

    # =====================
    # 🔍 ANALYSE
    # =====================

    st.divider()
    st.subheader("🔍 Analyse per product")

    # =====================
    # DATA OPHALEN (MOET BOVEN FILTERS!)
    # =====================

    res = supabase.table("demo_promos").select("*").eq("store_id", store_id).execute()
    df_demo = pd.DataFrame(res.data)

    if df_demo.empty:
        st.info("Nog geen demo data")
        st.stop()

    # =====================
    # FILTERS
    # =====================

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        search_hope = st.text_input("🔍 Zoek HOPE")

    with col2:
        search_product = st.text_input("🔍 Zoek product")

    with col3:
        demo_filter = st.selectbox("Demo", ["Alles", 1, 2, 3, 4, 5])

    with col4:
        week_filter = st.selectbox(
            "📅 Week",
            ["Alles"] + sorted(df_demo["week"].dropna().unique())
        )

    # =====================
    # FILTER LOGIC
    # =====================

    df_filtered = df_demo.copy()

    if search_hope:
        df_filtered = df_filtered[
            df_filtered["hope"].astype(str).str.contains(search_hope, case=False, na=False)
        ]

    if search_product:
        df_filtered = df_filtered[
            df_filtered["product"].str.contains(search_product, case=False, na=False)
        ]

    if demo_filter != "Alles":
        df_filtered = df_filtered[df_filtered["demo_nr"] == demo_filter]

    if df_filtered.empty:
        st.warning("Geen resultaten gevonden")
        st.stop()

    # filter week
    if week_filter != "Alles":
        df_filtered = df_filtered[df_filtered["week"] == week_filter]

    # =====================
    # MERGE MET SHRINK
    # =====================

    df_shrink_grouped = (
        df.groupby(["hope", "week"])["euro"]
        .sum()
        .reset_index()
    )
    
    df_merge = df_filtered.merge(
        df_shrink_grouped,
        on=["hope", "week"],
        how="left"
    )

    df_merge["euro"] = pd.to_numeric(df_merge["euro"], errors="coerce").fillna(0)

    # =====================
    # KPI
    # =====================

    total_sales = df_merge["sales_euro"].sum()
    total_shrink = df_merge["euro"].sum()

    col1, col2 = st.columns(2)

    col1.metric("💰 Sales", f"€{total_sales:.2f}")
    col2.metric("💸 Shrink", f"€{total_shrink:.2f}")

    # =====================
    # TABEL
    # =====================

    st.dataframe(
        df_merge[[
            "hope",
            "product",
            "demo_nr",
            "week",
            "promo_type",
            "sales_euro",
            "euro"
        ]],
        use_container_width=True,
        hide_index=True
    )

    # =====================
    # GRAFIEK
    # =====================

    st.bar_chart(
        df_merge.groupby("demo_nr")[["sales_euro", "euro"]].sum()
    )

    # =====================
    # 🏆 TOP 10 PRODUCTEN
    # =====================

    st.subheader("🏆 Top 10 best verkochte producten")

    top_products = (
        df_merge.groupby(["product", "hope"])
        .agg({
            "sales_euro": "sum",
            "euro": "sum"
        })
        .reset_index()
        .sort_values("sales_euro", ascending=False)
        .head(10)
    )

    st.dataframe(top_products, use_container_width=True, hide_index=True)



elif menu == "📑 Rapport":

    st.title("📑 Rapport export")

    # =====================
    # DATA
    # =====================

    df = df_products.copy()

    if df.empty:
        st.warning("Geen data")
        st.stop()

    # =====================
    # MAPPING
    # =====================

    df_mapping = load_mapping()

    if not df_mapping.empty and "hope" in df.columns:

        df["hope"] = (
            pd.to_numeric(df["hope"], errors="coerce")
            .fillna(0)
            .astype(int)
            .astype(str)
        )

        df_mapping["hope"] = (
            pd.to_numeric(df_mapping["hope"], errors="coerce")
            .fillna(0)
            .astype(int)
            .astype(str)
        )

        df = df.merge(
            df_mapping,
            on="hope",
            how="left",
            suffixes=("", "_map")
        )

        if "afdeling_map" in df.columns:
            df["afdeling"] = df["afdeling_map"]

    df["afdeling"] = df["afdeling"].fillna("ONBEKEND")

    # =====================
    # SELECTOR
    # =====================

    afdeling = st.selectbox(
        "🏬 Kies afdeling",
        ["Alles"] + sorted(df["afdeling"].unique())
    )

    # =====================
    # FILTER
    # =====================

    if afdeling != "Alles":
        df_filtered = df[df["afdeling"] == afdeling]
    else:
        df_filtered = df.copy()

    # =====================
    # SALES DATA
    # =====================

    df_weeks_local = df_weeks.copy()

    if afdeling != "Alles":
        df_weeks_filtered = df_weeks_local[df_weeks_local["afdeling"] == afdeling]
    else:
        df_weeks_filtered = df_weeks_local.copy()

    df_weeks_filtered["sales"] = pd.to_numeric(df_weeks_filtered["sales"], errors="coerce").fillna(0)
    df_weeks_filtered["shrink"] = pd.to_numeric(df_weeks_filtered["shrink"], errors="coerce").fillna(0)

    # =====================
    # SAMENVATTING (KORT)
    # =====================

    total_loss = df_filtered["euro"].sum()
    total_sales = df_weeks_filtered["sales"].sum()

    shrink_pct = (total_loss / total_sales * 100) if total_sales > 0 else 0

    st.subheader(f"📊 Rapport - {afdeling}")

    col1, col2, col3 = st.columns(3)
    col1.metric("💸 Verlies", f"€{total_loss:.2f}")
    col2.metric("🛒 Sales", f"€{total_sales:.2f}")
    col3.metric("📊 Shrink %", f"{shrink_pct:.2f}%")

    # =====================
    # PDF EXPORT
    # =====================

    st.divider()

    if st.button("📄 Genereer PDF rapport"):

        pdf_file = generate_pdf(
            df_filtered,
            afdeling,
            total_loss,
            total_sales,
            shrink_pct
        )

        st.download_button(
            "⬇️ Download rapport",
            pdf_file,
            file_name=f"rapport_{afdeling}.pdf",
            mime="application/pdf"
        )
