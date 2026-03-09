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

@st.cache_data(ttl=300)
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

# =====================
# MENU
# =====================

menu = st.sidebar.radio("Menu", [
    "📊 Dashboard",
    "📦 Product analyse (PRO)",
    "➕ Data invoeren",
    "📤 Upload",
    "⚙️ Afdeling beheer"
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

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("💸 Totale shrink", f"€{total_shrink:.2f}")
    col2.metric("🛒 Totale sales", f"€{total_sales:.2f}")
    col3.metric("📊 Shrink %", f"{shrink_pct:.2f}%")
    col4.metric("📉 vs vorige week", f"€{current:.2f}", f"{delta:.2f}", delta_color="inverse")

    # 📈 Trend
    st.subheader("📈 Trend per week")

    weekly = df.groupby(["jaar", "week"]).agg({
        "shrink": "sum",
        "sales": "sum"
    }).reset_index()

    weekly["label"] = weekly["jaar"].astype(str) + "-W" + weekly["week"].astype(str)
    weekly = weekly.set_index("label")

    st.line_chart(weekly[["shrink", "sales"]])

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

    # =====================
    # TOTAAL VERLIES PER HOPE
    # =====================

    df_totals = (
        df_shrink
        .groupby(["hope", "product"])["euro"]
        .sum()
        .reset_index()
        .sort_values("euro", ascending=False)
    )

    # =====================
    # MAPPING OPHALEN
    # =====================

    mapping_res = (
        supabase.table("product_afdelingen")
        .select("hope")
        .execute()
    )

    df_mapping = pd.DataFrame(mapping_res.data)

    # =====================
    # ENKEL NIET-GEMAPTE HOPE'S
    # =====================

    if not df_mapping.empty:
        df_onbekend = df_totals[~df_totals["hope"].isin(df_mapping["hope"])]
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

    # Multi-select met productnaam erbij
    selected_hopes = st.multiselect(
        "Selecteer HOPE's",
        df_onbekend["hope"],
        format_func=lambda x: f"{x} - {df_onbekend[df_onbekend['hope']==x]['product'].values[0]}"
    )

    # Afdelingen (zoals je nu gebruikt)
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

            data = [
                {"hope": hope, "afdeling": nieuwe_afdeling}
                for hope in selected_hopes
            ]

            supabase.table("product_afdelingen").upsert(data).execute()

            st.success(f"✅ {len(selected_hopes)} producten toegewezen")
            st.rerun()
            st.divider()

    st.divider()
    st.subheader("🔁 Bestaande afdeling wijzigen")

    # Mapping ophalen
    mapping_full = supabase.table("product_afdelingen").select("*").execute()
    df_mapping_full = pd.DataFrame(mapping_full.data)

    if df_mapping_full.empty:
        st.info("Nog geen bestaande mappings.")
    else:

        # Productnamen ophalen uit shrink_data
        product_res = (
            supabase.table("shrink_data")
            .select("hope, product")
            .execute()
        )

        df_products_lookup = pd.DataFrame(product_res.data)
        # Zorg dat hope altijd string is
        df_products_lookup["hope"] = df_products_lookup["hope"].astype(str)
        df_mapping_full["hope"] = df_mapping_full["hope"].astype(str)

        df_products_lookup = (
            df_products_lookup
            .sort_values("hope")
            .drop_duplicates(subset=["hope"])
        )

        # Merge mapping + productnaam
        df_combined = df_mapping_full.merge(
            df_products_lookup,
            on="hope",
            how="left"
        )

        df_combined = df_combined.sort_values("hope")

        # Maak label voor dropdown
        df_combined["label"] = (
            df_combined["hope"].astype(str) + " - " +
            df_combined["product"].fillna("Onbekend")
        )

        selected_label = st.selectbox(
            "Kies HOPE om te wijzigen",
            df_combined["label"]
        )

        # Extract HOPE terug uit label
        selected_existing_hope = selected_label.split(" - ")[0]

        huidige_afdeling = df_combined[
            df_combined["hope"] == selected_existing_hope
        ]["afdeling"].values[0]

        st.write(f"Huidige afdeling: **{huidige_afdeling}**")

        nieuwe_afdeling_wijzig = st.selectbox(
            "Nieuwe afdeling",
            afdelingen,
            key="wijzig_afdeling"
        )

        if st.button("🔄 Wijzig afdeling"):
            supabase.table("product_afdelingen").upsert({
                "hope": selected_existing_hope,
                "afdeling": nieuwe_afdeling_wijzig
            }).execute()

            st.success("✅ Afdeling gewijzigd")
            st.rerun()
    st.divider()
    st.subheader("📂 Overzicht per afdeling")

    # Mapping opnieuw ophalen (zeker van laatste versie)
    mapping_full = supabase.table("product_afdelingen").select("*").execute()
    df_mapping_full = pd.DataFrame(mapping_full.data)

    if df_mapping_full.empty:
        st.info("Nog geen producten gelinkt.")
    else:

        # Zorg dat hope string is
        df_mapping_full["hope"] = df_mapping_full["hope"].astype(str)
        df_shrink["hope"] = df_shrink["hope"].astype(str)

        # Totaal verlies per hope
         df_totals_all = (
             df_shrink
            .groupby(["hope", "product"])["euro"]
            .sum()
            .reset_index()
        )

        # Merge mapping + verlies
        df_overzicht = df_mapping_full.merge(
            df_totals_all,
            on="hope",
            how="left"
        )

        df_overzicht["euro"] = df_overzicht["euro"].fillna(0)

        # Afdeling kiezen
        afdelingen_beschikbaar = sorted(df_overzicht["afdeling"].unique())

        gekozen_afdeling = st.selectbox(
            "Kies afdeling om te bekijken",
            afdelingen_beschikbaar,
            key="overzicht_afdeling"
        )

        df_afdeling = (
            df_overzicht[df_overzicht["afdeling"] == gekozen_afdeling]
            .sort_values("euro", ascending=False)
        )

        st.write(f"**Aantal producten:** {len(df_afdeling)}")
        st.write(f"**Totaal verlies:** €{df_afdeling['euro'].sum():.2f}")

        st.dataframe(
            df_afdeling[["hope", "product", "euro"]],
            use_container_width=True
        )
# =====================
# PRODUCT ANALYSE
# =====================

elif menu == "📦 Product analyse (PRO)":

    st.title("📦 Shrink Intelligence Dashboard")

    df = df_products.copy()

    # =====================
    # AFSLAG ANALYSE (SNELLE VERSIE - GEEN LOOPS)
    # =====================

    df["datum"] = pd.to_datetime(df["datum"])

    # 1️⃣ Groepeer per HOPE + datum
    grouped = (
        df.groupby(["hope", "datum", "reden"])["euro"]
        .sum()
        .reset_index()
    )

    # 2️⃣ Split per type
    afslag = grouped[grouped["reden"].str.contains("AFSLAG", case=False, na=False)]
    verval = grouped[grouped["reden"].str.contains("VERVAL", case=False, na=False)]
    tgtg = grouped[grouped["reden"] == "38 VERLIES - ANDERE"]

    # 3️⃣ Merge op HOPE + datum (zelfde dag)
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

    # 4️⃣ Nulls vervangen door 0
    merged["euro_verval"] = merged["euro_verval"].fillna(0)
    merged["euro_tgtg"] = merged["euro_tgtg"].fillna(0)

    # 5️⃣ Totalen berekenen
    afslag_euro = merged["euro_afslag"].sum()
    verval_euro = merged["euro_verval"].sum()
    tgtg_euro = merged["euro_tgtg"].sum()

    effectief_verkocht = afslag_euro - verval_euro - tgtg_euro

    if afslag_euro > 0:
        afslag_eff = (effectief_verkocht / afslag_euro) * 100
    else:
        afslag_eff = 0

    # =====================
    # FILTER AFDELING
    # =====================

    st.subheader("🏬 Afdeling")

    afdeling_opties = sorted(df["afdeling"].dropna().unique())

    select_all_afdeling = st.checkbox("Alles afdelingen", value=True, key="prod_afdeling")

    if select_all_afdeling:
        selected_afdelingen = afdeling_opties
    else:
        selected_afdelingen = st.multiselect(
            "Kies afdeling(en)",
            afdeling_opties
        )

    if not selected_afdelingen:
        selected_afdelingen = afdeling_opties

    df = df[df["afdeling"].isin(selected_afdelingen)]


    if df.empty:
        st.warning("Geen data")
        st.stop()

    df["reden"] = df["reden"].fillna("Onbekend")
    df["datum"] = pd.to_datetime(df["datum"], errors="coerce")
    df = df[df["datum"].notna()]

    df["stuks"] = pd.to_numeric(df["stuks"], errors="coerce").fillna(0)
    df["euro"] = pd.to_numeric(df["euro"], errors="coerce").fillna(0)

    # =====================
    # FILTER REDEN
    # =====================

    st.subheader("🎯 Reden")

    # haal unieke redenen op
    reden_opties = sorted(df["reden"].dropna().unique())

    # checkbox "Alles"
    select_all_reden = st.checkbox("Alles", value=True)

    # selectie logica
    if select_all_reden:
        selected_redenen = reden_opties
    else:
        selected_redenen = st.multiselect(
            "Kies reden(en)",
            reden_opties
        )

    # ✅ safety: als niets gekozen → automatisch alles
    if not selected_redenen:
        selected_redenen = reden_opties

    # filter toepassen
    df = df[df["reden"].isin(selected_redenen)]

    # 📅 datum filter
    min_date = df["datum"].min()
    max_date = df["datum"].max()

    date_range = st.date_input("📅 Periode", [min_date, max_date])

    df = df[
        (df["datum"] >= pd.to_datetime(date_range[0])) &
        (df["datum"] <= pd.to_datetime(date_range[1]))
    ]

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
    df["week"] = df["datum"].dt.isocalendar().week
    st.line_chart(df.groupby("week")["euro"].sum())

    # 🏆 producten
    st.subheader("💸 Grootste verlies per product")

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
    
    top_products = (
        df.groupby(["product", "hope"])
        .agg({
            "stuks": "sum",
            "euro": "sum"
        })
        .reset_index()
        .sort_values("euro", ascending=False)
        .head(20)
    )

    st.dataframe(top_products, use_container_width=True, hide_index=True)

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
    # 🔍 ZOEK OP HOPE
    # =====================

    st.subheader("🔍 Zoek product (HOPE)")

    search_hope = st.text_input("Geef HOPE nummer")

    if search_hope:

        df["hope"] = df["hope"].astype(str)

        result = df[df["hope"] == search_hope]

        if result.empty:
            st.warning("Geen product gevonden")
        else:
            st.success(f"{len(result)} records gevonden")

            # KPI's
            col1, col2 = st.columns(2)

            col1.metric("📦 Totaal stuks", int(result["stuks"].sum()))
            col2.metric("💸 Totaal verlies (€)", f"€{result['euro'].sum():.2f}")

            # product naam
            st.write("**Product:**", result["product"].iloc[0])

            # redenen
            st.subheader("📊 Verlies per reden")
            reden_df = result.groupby("reden")["euro"].sum().sort_values(ascending=False)
            st.bar_chart(reden_df)

            # per datum
            st.subheader("📅 Verlies over tijd")
            result["datum"] = pd.to_datetime(result["datum"])
            tijd_df = result.groupby("datum")["euro"].sum()
            st.line_chart(tijd_df)

            # detail tabel
            st.subheader("📋 Detail")
            st.dataframe(result.sort_values("datum", ascending=False), hide_index=True)
    

    
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

        df["week"] = df["datum"].dt.isocalendar().week.astype(int)
        df["jaar"] = df["datum"].dt.year.astype(int)
        df["maand"] = df["datum"].dt.month.astype(int)

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

        mapping_res = supabase.table("product_afdelingen").select("*").execute()
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



















































