    import datetime
import html
from io import BytesIO

import numpy as np
import pandas as pd
import streamlit as st
from openai import OpenAI
from supabase import create_client

# =====================
# CONFIG
# =====================

DEBUG = False
st.set_page_config(layout="wide")

STORE_ID = "delhaize_halle"
BATCH = 1000
CACHE_TTL = 600  # seconden; data wordt sowieso gewist na eigen wijzigingen

WAARDE_PAKKET = 20
WINST_PER_PAKKET = 3.29
PAKKET_REDEN = "38 VERLIES - ANDERE"

AFDELINGEN = [
    "DIEPVRIES", "VOEDING", "PARFUMERIE", "DROGISTERIJ", "FRUIT EN GROENTEN",
    "ZUIVEL", "VERS VLEES", "GEVOGELTE", "CHARCUTERIE", "VIS EN SAURISSERIE",
    "SELF-TRAITEUR", "BAKKERIJ", "TRAITEUR", "DRANKEN",
]


def get_supabase():
    # Eén client per browsersessie: niet bij elke rerun opnieuw aanmaken, maar ook
    # niet delen tussen gebruikers (de client bewaart de login-sessie).
    if "supabase" not in st.session_state:
        st.session_state["supabase"] = create_client(
            st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"]
        )
    return st.session_state["supabase"]


@st.cache_resource
def get_openai():
    return OpenAI(api_key=st.secrets["OPENAI_API_KEY"])


# =====================
# HELPERS
# =====================

def format_euro(value):
    try:
        if value is None:
            return "€0,00"
        return f"€{float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return "€0,00"


def format_pct(value):
    try:
        return f"{float(value):.2f}%".replace(".", ",")
    except (TypeError, ValueError):
        return "0,00%"


def format_date_series(series):
    return pd.to_datetime(series, errors="coerce").dt.strftime("%d/%m/%Y")


def to_num(series):
    return pd.to_numeric(series, errors="coerce").fillna(0)


def safe_pct(teller, noemer):
    return (teller / noemer * 100).replace([np.inf, -np.inf], 0).fillna(0)


def normalize_hope(series):
    """'5410', 5410 en 5410.0 worden allemaal '5410'."""
    out = series.fillna("").astype(str).str.strip()
    num = pd.to_numeric(series, errors="coerce")
    mask = num.notna()
    out[mask] = num[mask].astype("int64").astype(str)
    return out


def add_winkelweek(df):
    """Winkelweek loopt van donderdag t.e.m. woensdag."""
    shift = df["datum"] - pd.Timedelta(days=3)
    iso = shift.dt.isocalendar()
    df["winkelweek"] = iso.week.astype("Int64")
    df["winkeljaar"] = iso.year.astype("Int64")
    # Donderdag waarop de winkelweek start: uniek over jaren heen, dus correct sorteerbaar
    df["week_start"] = shift.dt.normalize() - pd.to_timedelta(shift.dt.weekday, unit="D") + pd.Timedelta(days=3)
    return df


def flash(msg):
    st.session_state["flash"] = msg


def show_flash():
    msg = st.session_state.pop("flash", None)
    if msg:
        st.success(msg)


def euro_stuks_top(df, by, n=10):
    return (
        df.groupby(by)
        .agg(euro=("euro", "sum"), stuks=("stuks", "sum"))
        .reset_index()
        .sort_values("euro", ascending=False)
        .head(n)
    )


# =====================
# DATA LOAD
# =====================

def fetch_all(table, columns="*"):
    sb = get_supabase()
    rows, start = [], 0
    while True:
        data = (
            sb.table(table)
            .select(columns)
            .eq("store_id", STORE_ID)
            .range(start, start + BATCH - 1)
            .execute()
            .data
        )
        rows.extend(data or [])
        if not data or len(data) < BATCH:
            break
        start += BATCH
    return pd.DataFrame(rows)


@st.cache_data(ttl=CACHE_TTL)
def load_weeks():
    df = fetch_all("weeks")
    if df.empty:
        return df
    for col in ["shrink", "sales"]:
        df[col] = to_num(df[col])
    for col in ["jaar", "week"]:
        df[col] = to_num(df[col]).astype(int)
    return df


@st.cache_data(ttl=CACHE_TTL)
def load_shrink_data():
    df = fetch_all("shrink_data")
    if df.empty:
        return df
    df["datum"] = pd.to_datetime(df["datum"], errors="coerce")
    df["euro"] = to_num(df["euro"])
    df["stuks"] = to_num(df["stuks"])
    df["hope"] = normalize_hope(df["hope"])
    df["reden"] = df["reden"].fillna("Onbekend").astype(str)
    df["product"] = df["product"].fillna("").astype(str)
    df = add_winkelweek(df)
    # Oude rijen zonder week-kolom: val terug op de berekende winkelweek
    week = pd.to_numeric(df["week"], errors="coerce") if "week" in df else pd.Series(np.nan, index=df.index)
    df["week"] = week.fillna(df["winkelweek"].astype(float)).fillna(0).astype(int)
    return df.drop(columns=["afdeling"], errors="ignore")  # afdeling komt live uit de mapping


@st.cache_data(ttl=CACHE_TTL)
def load_mapping():
    df = fetch_all("product_afdelingen")
    if df.empty:
        return pd.DataFrame(columns=["hope", "afdeling"])
    df["hope"] = normalize_hope(df["hope"])
    return df[["hope", "afdeling"]].drop_duplicates("hope", keep="last")


@st.cache_data(ttl=CACHE_TTL)
def load_demo_promos():
    return fetch_all("demo_promos")


def with_afdeling(df):
    df = df.drop(columns=["afdeling"], errors="ignore").merge(load_mapping(), on="hope", how="left")
    df["afdeling"] = df["afdeling"].fillna("ONBEKEND")
    return df


# =====================
# PDF RAPPORT
# =====================

def generate_pdf(df, afdeling, total_loss, total_sales, shrink_pct):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()

    kpi_table = Table([
        ["Verlies", format_euro(total_loss)],
        ["Sales", format_euro(total_sales)],
        ["Shrink %", format_pct(shrink_pct)],
    ])
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.whitesmoke),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
    ]))

    def top_table(data):
        left = euro_stuks_top(data, ["product", "hope"])
        right = euro_stuks_top(data, "reden")
        rows = [["#", "Product", "€", "Stuks", "#", "Categorie", "€", "Stuks"]]
        for i in range(max(len(left), len(right))):
            row = []
            for part, label in ((left, "product"), (right, "reden")):
                if i < len(part):
                    r = part.iloc[i]
                    row += [i + 1, str(r[label])[:25], format_euro(r["euro"]), int(r["stuks"])]
                else:
                    row += ["", "", "", ""]
            rows.append(row)
        table = Table(rows, colWidths=[20, 190, 45, 30, 20, 190, 45, 30])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.black),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("LINEBEFORE", (4, 0), (4, -1), 0.5, colors.grey),
        ]))
        return table

    df = df.dropna(subset=["datum"])
    laatste = df["week_start"].max()
    df_week = df[df["week_start"] == laatste]

    doc.build([
        Paragraph(f"Rapport - {afdeling}", styles["Title"]), Spacer(1, 20),
        kpi_table, Spacer(1, 20),
        Paragraph(f"Week {df_week['winkelweek'].iloc[0]}", styles["Heading1"]), Spacer(1, 10),
        top_table(df_week), Spacer(1, 20),
        Paragraph("Historiek", styles["Heading1"]), Spacer(1, 10),
        top_table(df),
    ])
    buffer.seek(0)
    return buffer


# =====================
# LOGIN
# =====================

def login(email, password):
    try:
        res = get_supabase().auth.sign_in_with_password({"email": email, "password": password})
        return res.session.user if res.session else None
    except Exception:
        return None


def render_branding():
    _, col, _ = st.sidebar.columns([1, 2, 1])
    with col:
        st.image("assets/logo_300x300.png", width=180)
    st.sidebar.markdown(
        """
        <div style="text-align:center; margin-top:-10px; margin-bottom:20px;">
            <div style="font-size:18px; font-weight:700;">SHRINK ANALYZER</div>
            <div style="font-size:12px; color:#777;">DELHAIZE HALLE</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


st.session_state.setdefault("user", None)
render_branding()

if not st.session_state["user"]:
    st.sidebar.markdown("### 🔐 Aanmelden")
    with st.sidebar.form("login"):
        email = st.text_input("Email")
        password = st.text_input("Wachtwoord", type="password")
        submitted = st.form_submit_button("Login")
    if submitted:
        user = login(email, password)
        if user:
            st.session_state["user"] = user
            st.rerun()
        st.sidebar.error("❌ Login mislukt")
    st.stop()

# =====================
# GEBRUIKER
# =====================

st.sidebar.markdown(
    f"""<div style="background-color:#f5f6f8;border-radius:10px;padding:12px;margin-bottom:8px;border:1px solid #e1e3e6;">
<div style="font-weight:600;font-size:14px;margin-bottom:3px;">👤 Ingelogd</div>
<div style="font-size:12px;color:#666;word-break:break-word;">{html.escape(st.session_state["user"].email)}</div>
<div style="font-size:11px;color:#16803c;margin-top:6px;">● Online</div>
</div>""",
    unsafe_allow_html=True,
)

if st.sidebar.button("🚪 Uitloggen", use_container_width=True):
    try:
        get_supabase().auth.sign_out()
    except Exception:
        pass
    st.session_state["user"] = None
    st.rerun()

# =====================
# MENU
# =====================

st.markdown(
    """
    <style>
    [data-testid="stSidebar"] [data-testid="stRadio"] label {
        padding: 9px 10px !important;
        border-radius: 8px !important;
        margin-bottom: 3px !important;
        transition: 0.15s;
    }
    [data-testid="stSidebar"] [data-testid="stRadio"] input[type="radio"],
    [data-testid="stSidebar"] [data-testid="stRadio"] label > div:first-child,
    [data-testid="stSidebar"] [data-testid="stRadio"] label > div > div:first-child {
        display: none !important;
    }
    [data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {
        background-color: #ffe5e5 !important;
        font-weight: 600 !important;
    }
    [data-testid="stSidebar"] [data-testid="stRadio"] label p {
        margin: 0 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.sidebar.markdown("### NAVIGATIE")
menu = st.sidebar.radio(
    "Navigatie",
    [
        "📊 Dashboard",
        "📦 Product analyse (PRO)",
        "📑 Rapport",
        "➕ Data invoeren",
        "📤 Upload",
        "⚙️ Afdeling beheer",
        "🧊 Demo promoties",
    ],
    label_visibility="collapsed",
)

show_flash()

# =====================
# DASHBOARD
# =====================

if menu == "📊 Dashboard":

    st.title("📊 Wekelijks Shrink Overzicht")

    df = load_weeks()
    if df.empty:
        st.warning("Geen data")
        st.stop()

    st.subheader("🎯 Afdeling")
    afdeling_opties = sorted(df["afdeling"].dropna().unique())

    col1, col2 = st.columns([1, 3])
    with col1:
        select_all = st.checkbox("Alles", value=True, key="afd_all")
    with col2:
        selected = afdeling_opties if select_all else st.multiselect("Kies afdeling(en)", afdeling_opties)

    df = df[df["afdeling"].isin(selected or afdeling_opties)].copy()
    if df.empty:
        st.warning("Geen data")
        st.stop()

    # jaar + week als één sleutel: werkt ook over de jaarwissel heen
    df["periode"] = df["jaar"] * 100 + df["week"]
    perioden = sorted(df["periode"].unique())
    latest = perioden[-1]
    previous = perioden[-2] if len(perioden) > 1 else None

    total_shrink = df["shrink"].sum()
    total_sales = df["sales"].sum()
    shrink_pct = total_shrink / total_sales * 100 if total_sales > 0 else 0

    current_week = df[df["periode"] == latest]
    previous_week = df[df["periode"] == previous]
    current = current_week["shrink"].sum()
    delta = current - previous_week["shrink"].sum()

    col1, col2, col3, col4 = st.columns([1.2, 1.2, 0.8, 1])
    col1.metric("💸 Totale shrink", format_euro(total_shrink))
    col2.metric("🛒 Totale sales", format_euro(total_sales))
    col3.metric("📊 Shrink %", format_pct(shrink_pct))
    col4.metric(
        "📉 vs vorige week",
        format_euro(current),
        f"-{format_euro(abs(delta))}" if delta < 0 else f"+{format_euro(delta)}",
        delta_color="inverse",
    )

    
    # ---------- Jaarvergelijking per winkelweek ----------
    weekly = (
        df.groupby(["jaar", "week"], as_index=False)[["shrink", "sales"]]
        .sum()
        .sort_values(["jaar", "week"])
    )

    weekly["shrink_pct"] = safe_pct(
        weekly["shrink"], weekly["sales"]
    )

    # Beschikbare jaren automatisch ophalen
    jaar_opties = sorted(
        weekly["jaar"].dropna().astype(int).unique().tolist()
    )

    standaard_jaren = jaar_opties[-2:]

    st.subheader("📅 Jaarvergelijking")
    st.caption("Selecteer de jaren die je wilt vergelijken")

    geselecteerde_jaren = st.pills(
        "Jaren",
        options=jaar_opties,
        default=standaard_jaren,
        selection_mode="multi",
        label_visibility="collapsed",
        key="dashboard_jaren",
    )

    weekly_compare = weekly[
        weekly["jaar"].isin(geselecteerde_jaren)
    ].copy()

    if weekly_compare.empty:
        st.info("Selecteer minstens één jaar om de grafieken te bekijken.")
    else:
        # Weeknummer én startdatum van de winkelweek behouden
    week_datums = (
        df[["jaar", "week"]]
        .drop_duplicates()
        .merge(
            weekly_compare[["jaar", "week"]].drop_duplicates(),
            on=["jaar", "week"],
            how="inner",
        )
    )

    # Donderdag als startdatum van de winkelweek berekenen
    week_datums["datum"] = pd.to_datetime(
        week_datums["jaar"].astype(str) + "-01-04"
    )
    week_datums["datum"] = (
        week_datums["datum"]
        - pd.to_timedelta(week_datums["datum"].dt.weekday, unit="D")
        + pd.Timedelta(days=3)
        + pd.to_timedelta((week_datums["week"] - 1) * 7, unit="D")
    )

    shrink_chart = weekly_compare.pivot_table(
        index="week",
        columns="jaar",
        values="shrink",
        aggfunc="sum",
    ).sort_index()

    # Weeknummer en datum samen als label tonen
    shrink_chart.index = [
        f"W{int(w):02d} ({week_datums.loc[week_datums['week'] == w, 'datum'].min():%d/%m})"
        for w in shrink_chart.index
    ]
        sales_chart = weekly_compare.pivot_table(
            index="week",
            columns="jaar",
            values="sales",
            aggfunc="sum",
        ).sort_index()

        pct_chart = weekly_compare.pivot_table(
            index="week",
            columns="jaar",
            values="shrink_pct",
            aggfunc="mean",
        ).sort_index()

        # Jaarlabels duidelijk tonen in de legenda
        shrink_chart.columns = shrink_chart.columns.astype(str)
        sales_chart.columns = sales_chart.columns.astype(str)
        pct_chart.columns = pct_chart.columns.astype(str)

        st.subheader("📉 Shrink per week")
        st.line_chart(shrink_chart, x_label="Winkelweek", y_label="Shrink (€)")

        with st.expander("📈 Sales per week"):
            st.line_chart(sales_chart, x_label="Winkelweek", y_label="Sales (€)")

        with st.expander("📊 Shrink % per week"):
            st.line_chart(pct_chart, x_label="Winkelweek", y_label="Shrink (%)")


    st.subheader("⚖️ Verschil vs vorige week per afdeling")

    def per_afdeling(data, prefix):
        return data.groupby("afdeling")[["shrink", "sales"]].sum().add_prefix(prefix)

    compare = (
        per_afdeling(current_week, "current_")
        .join(per_afdeling(previous_week, "previous_"), how="outer")
        .fillna(0)
        .join(per_afdeling(df, "total_"), how="left")
    )
    compare["verschil"] = compare["current_shrink"] - compare["previous_shrink"]
    compare["shrink % (week)"] = safe_pct(compare["current_shrink"], compare["current_sales"])
    compare["shrink % (historiek)"] = safe_pct(compare["total_shrink"], compare["total_sales"])

    st.dataframe(
        compare.sort_values("shrink % (historiek)", ascending=False).round(2),
        use_container_width=True,
    )

# =====================
# AFDELING BEHEER
# =====================

elif menu == "⚙️ Afdeling beheer":

    st.title("⚙️ HOPE → Afdeling beheer")

    df_shrink = load_shrink_data()
    if df_shrink.empty:
        st.warning("Geen data gevonden")
        st.stop()

    df_mapping = load_mapping()
    df_totals = (
        df_shrink.groupby(["hope", "product"], as_index=False)["euro"].sum()
        .sort_values("euro", ascending=False)
    )
    df_onbekend = df_totals[~df_totals["hope"].isin(df_mapping["hope"])]

    if DEBUG:
        st.write("Aantal mapping records:", len(df_mapping))
        st.write("Voorbeeld mapping HOPE:", df_mapping["hope"].head(10).tolist())
        st.write("Voorbeeld totals HOPE:", df_totals["hope"].head(10).tolist())

    if df_onbekend.empty:
        st.success("✅ Alle producten hebben een afdeling toegewezen!")
        st.stop()

    st.metric("🔎 Onbekende producten", len(df_onbekend))
    st.dataframe(df_onbekend.head(100), use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("✏️ Afdelingen toewijzen (meerdere tegelijk)")

    zoekterm = st.text_input("Zoek op HOPE of productnaam")
    df_filter = df_onbekend
    if zoekterm:
        df_filter = df_filter[
            df_filter["hope"].str.contains(zoekterm, case=False, na=False, regex=False)
            | df_filter["product"].str.contains(zoekterm, case=False, na=False, regex=False)
        ]
    st.caption(f"{len(df_filter)} resultaten gevonden")

    labels = df_onbekend.drop_duplicates("hope").set_index("hope")["product"].to_dict()
    gefilterde_hopes = df_filter["hope"].drop_duplicates().tolist()

    def selecteer_alles():
        st.session_state["selected_hopes"] = gefilterde_hopes

    st.button("Selecteer alle gefilterde resultaten", on_click=selecteer_alles)

    # Huidige selectie altijd in de opties houden, anders crasht de widget na een nieuwe zoekterm.
    # Waarden die niet meer bestaan (bv. intussen gemapt) eruit halen vóór de widget getekend wordt.
    reeds_gekozen = [h for h in st.session_state.get("selected_hopes", []) if h in labels]
    st.session_state["selected_hopes"] = reeds_gekozen
    opties = list(dict.fromkeys(reeds_gekozen + gefilterde_hopes))

    selected_hopes = st.multiselect(
        "Selecteer HOPE's",
        opties,
        key="selected_hopes",
        format_func=lambda h: f"{h} - {labels.get(h, '')}",
    )

    if selected_hopes:
        nieuwe_afdeling = st.selectbox("Nieuwe afdeling", AFDELINGEN)

        if st.button("💾 Opslaan voor selectie"):
            data = [
                {"store_id": STORE_ID, "hope": hope, "afdeling": nieuwe_afdeling}
                for hope in set(selected_hopes)
            ]
            try:
                get_supabase().table("product_afdelingen").upsert(
                    data, on_conflict="store_id,hope"
                ).execute()
                load_mapping.clear()
                del st.session_state["selected_hopes"]
                flash(f"✅ {len(data)} producten toegewezen aan {nieuwe_afdeling}")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Fout bij opslaan: {e}")

# =====================
# PRODUCT ANALYSE
# =====================

elif menu == "📦 Product analyse (PRO)":

    st.title("📦 Shrink Intelligence Dashboard")

    df = load_shrink_data()
    if df.empty:
        st.warning("Geen data")
        st.stop()

    df = with_afdeling(df.dropna(subset=["datum"]))

    # ---------- Filters rij 1 ----------
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🏬 Afdeling")
        afdeling_keuze = st.selectbox(
            "Kies afdeling",
            ["Alles"] + sorted(df["afdeling"].unique()),
            label_visibility="collapsed",
        )
    if afdeling_keuze != "Alles":
        df = df[df["afdeling"] == afdeling_keuze]
    if df.empty:
        st.warning("Geen data voor deze selectie")
        st.stop()

    with col2:
        st.subheader("🎯 Reden")
        reden_opties = sorted(df["reden"].unique())
        if st.checkbox("Alle redenen", value=True, key="alle_redenen"):
            geselecteerde_redenen = reden_opties
        else:
            geselecteerde_redenen = st.multiselect(
                "Kies reden(en)", reden_opties, label_visibility="collapsed"
            ) or reden_opties

    # ---------- Filters rij 2 ----------
    col3, col4 = st.columns(2)
    filter_mode = st.radio("Filtermodus", ["Winkelweek", "Jaar", "Vrije datums"], horizontal=True)

    with col3:
        if filter_mode == "Jaar":
            st.subheader("📆 Jaar")

            jaren = sorted(
                df["winkeljaar"].dropna().astype(int).unique(),
                reverse=True
            )

            col_jaar, col_week = st.columns(2)

            with col_jaar:
                gekozen_jaar = st.selectbox(
                    "Jaar",
                    jaren,
                    index=0,  # meest recente jaar
                )
            df_jaar = df[df["winkeljaar"] == gekozen_jaar]

            # Winkelweken met data in dit jaar
            weken_jaar = (
                df_jaar.drop_duplicates("week_start")
                .sort_values("week_start")
                .set_index("week_start")["winkelweek"]
            )
            with col_week:
                gekozen_week = st.selectbox(
                    "Week",
                    [None] + weken_jaar.index.tolist(),
                    format_func=lambda d: "Alle weken" if d is None else f"Week {weken_jaar[d]}",
                    key=f"week_in_jaar_{gekozen_jaar}",  # reset naar 'Alle weken' bij ander jaar
                )

            if gekozen_week is None:
                df = df_jaar
                st.caption(f"01/01/{gekozen_jaar} → 31/12/{gekozen_jaar}")
            else:
                # Volledige winkelweek (do → wo), ook als die over de jaarwissel loopt
                df = df[df["week_start"] == gekozen_week]
                st.caption(
                    f"{gekozen_week:%d/%m/%Y} → {gekozen_week + pd.Timedelta(days=6):%d/%m/%Y}"
                )
        elif filter_mode == "Winkelweek":
            st.subheader("📅 Winkelweek")
            weken = (
                df.drop_duplicates("week_start")
                .sort_values("week_start")
                .set_index("week_start")["winkelweek"]
            )
            if weken.empty:
                st.warning("Geen data voor deze selectie")
                st.stop()
            gekozen_start = st.selectbox(
                "Kies week",
                weken.index.tolist(),
                index=len(weken) - 1,
                format_func=lambda d: (
                    f"Week {weken[d]} ({d:%d/%m/%Y} → {d + pd.Timedelta(days=6):%d/%m/%Y})"
                ),
                label_visibility="collapsed",
            )
            df = df[df["week_start"] == gekozen_start]
        else:
            st.subheader("🗓️ Vrije datums")
            date_range = st.date_input(
                "Kies periode",
                [df["datum"].min().date(), df["datum"].max().date()],
                label_visibility="collapsed",
            )
            if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
                # Einddatum volledig meenemen, ook als datum een tijdstip bevat
                van = pd.Timestamp(date_range[0])
                tot = pd.Timestamp(date_range[1]) + pd.Timedelta(days=1)
                df = df[(df["datum"] >= van) & (df["datum"] < tot)]

    with col4:
        st.subheader("🔍 Zoek HOPE")
        search_hope = st.text_input("Geef HOPE nummer", label_visibility="collapsed").strip()
    if search_hope:
        df = df[df["hope"] == search_hope]

    # ---------- Afslag analyse (alle redenen binnen de gekozen periode/afdeling) ----------
    # Per product per dag: afslag, verval en TGTG naast elkaar. Verval/TGTG telt enkel mee
    # op dagen waarop dat product ook afgeslagen werd. (Elke dag één keer, ook als er
    # meerdere afslag-redenen zijn.)
    is_afslag = df["reden"].str.contains("AFSLAG", case=False, na=False)
    per_dag = (
        df.assign(
            afslag=df["euro"].where(is_afslag, 0),
            verval=df["euro"].where(df["reden"].str.contains("VERVAL", case=False, na=False), 0),
            tgtg=df["euro"].where(df["reden"] == PAKKET_REDEN, 0),
            heeft_afslag=is_afslag,
        )
        .groupby(["hope", "datum"])[["afslag", "verval", "tgtg", "heeft_afslag"]]
        .agg({"afslag": "sum", "verval": "sum", "tgtg": "sum", "heeft_afslag": "any"})
    )
    per_dag = per_dag[per_dag["heeft_afslag"]]

    afslag_euro = per_dag["afslag"].sum()
    verval_euro = per_dag["verval"].sum()
    tgtg_euro = per_dag["tgtg"].sum()
    effectief_verkocht = afslag_euro - verval_euro - tgtg_euro
    afslag_eff = effectief_verkocht / afslag_euro * 100 if afslag_euro > 0 else 0

    # ---------- Reden-filter pas nu toepassen ----------
    df = df[df["reden"].isin(geselecteerde_redenen)]

    # ---------- KPI's ----------
    verlies_andere = df.loc[df["reden"] == PAKKET_REDEN, "euro"].sum()
    pakketten = verlies_andere / WAARDE_PAKKET
    recup = pakketten * WINST_PER_PAKKET
    bruto = df["euro"].sum()
    netto = bruto - recup

    col1, col2, col3 = st.columns(3)
    col1.metric("💸 Bruto verlies", format_euro(bruto))
    col2.metric("♻️ Too Good to Go", format_euro(recup), f"{int(pakketten)} pakketten")
    col3.metric("💰 Netto verlies", format_euro(netto))

    col4, col5, col6, col7 = st.columns(4)
    col4.metric("📦 Afslag totaal", format_euro(afslag_euro))
    col5.metric("📛 Afslag vuilbak", format_euro(verval_euro))
    col6.metric("♻️ Afslag TGTG", format_euro(tgtg_euro))
    col7.metric("📉 Afslag efficiëntie", format_pct(afslag_eff))

    st.divider()

    st.subheader("📊 Verlies per reden")
    st.bar_chart(df.groupby("reden")["euro"].sum())

    st.subheader("📈 Trend per week")
    trend = df.groupby("week_start")["euro"].sum().sort_index()
    st.line_chart(trend)

    st.subheader("📦 Artikels per afdeling")
    st.bar_chart(df.groupby("afdeling")["product"].nunique().sort_values(ascending=False))

    st.subheader("🏆 Top producten binnen geselecteerde afdeling(en)")
    top_products = (
        df.groupby(["afdeling", "product", "hope"], as_index=False)[["stuks", "euro"]].sum()
        .sort_values(["afdeling", "euro"], ascending=[True, False])
    )
    st.dataframe(top_products, use_container_width=True, hide_index=True)

    # ---------- AI ----------
    st.subheader("🧠 AI inzichten")
    if st.button("Genereer AI inzichten"):
        summary = df.groupby("reden")["euro"].sum().nlargest(5)
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
            with st.spinner("AI analyseert..."):
                response = get_openai().responses.create(model="gpt-4o-mini", input=prompt)
            st.success("AI Analyse:")
            st.write(response.output_text)
        except Exception as e:
            st.error(f"AI fout: {e}")

    df_display = df.head(200).drop(columns=["week_start"]).copy()
    df_display["datum"] = format_date_series(df_display["datum"])
    st.dataframe(df_display, hide_index=True)

# =====================
# UPLOAD
# =====================

elif menu == "📤 Upload":

    st.title("📤 Upload shrink_data (Excel)")

    file = st.file_uploader("📎 Kies Excel bestand", type=["xlsx"])

    if file is not None:

        df = pd.read_excel(file)
        df.columns = df.columns.str.strip()

        st.subheader("👀 Preview")
        st.dataframe(df.head(20))

        kolommen = {
            "Datum": "datum",
            "Benaming": "product",
            "Reden / Winkel": "reden",
            "Hoeveelheid": "stuks",
            "Totale prijs": "euro",
            "Hope": "hope",
        }
        ontbrekend = [k for k in kolommen if k not in df.columns]
        if ontbrekend:
            st.error(f"❌ Ontbrekende kolommen: {', '.join(ontbrekend)}")
            st.stop()

        df = df.rename(columns=kolommen)
        df["datum"] = pd.to_datetime(df["datum"], errors="coerce")
        df = df[df["datum"].notna()].copy()

        if df.empty:
            st.error("❌ Geen geldige data")
            st.stop()
        if len(df) > 10000:
            st.error("❌ Max 10.000 records per upload")
            st.stop()

        iso = (df["datum"] - pd.Timedelta(days=3)).dt.isocalendar()
        df["week"] = iso.week.astype(int)
        df["jaar"] = iso.year.astype(int)
        df["maand"] = df["datum"].dt.month
        df["stuks"] = to_num(df["stuks"])
        df["euro"] = to_num(df["euro"])
        df["product"] = df["product"].astype(str).str.upper().str.strip()
        df["reden"] = df["reden"].astype(str).str.strip()
        df["hope"] = to_num(df["hope"]).astype(int).astype(str)

        df = with_afdeling(df)

        df = df[["datum", "week", "jaar", "maand", "afdeling", "product", "hope", "reden", "stuks", "euro"]]
        df["store_id"] = STORE_ID
        df["categorie"] = "ONBEKEND"
        df["datum"] = df["datum"].dt.strftime("%Y-%m-%d")
        # NaN → None (JSON-null); astype(object) zodat ook float-kolommen None kunnen bevatten
        df = df.astype(object).where(df.notna(), None)

        col1, col2, col3 = st.columns(3)
        col1.metric("📦 Rijen", len(df))
        col2.metric("💸 Totaal €", format_euro(df["euro"].sum()))
        col3.metric("🛒 Producten", df["product"].nunique())

        if st.button("🚀 Upload naar database"):
            data = df.to_dict(orient="records")
            sb = get_supabase()
            try:
                with st.spinner("Uploaden..."):
                    for i in range(0, len(data), 500):
                        sb.table("shrink_data").insert(data[i:i + 500]).execute()
                load_shrink_data.clear()
                flash(f"✅ {len(data)} records geüpload")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Er ging iets mis bij upload: {e}")

# =====================
# DATA INVOEREN
# =====================

elif menu == "➕ Data invoeren":

    st.title("➕ Weeks invoer")

    today = datetime.date.today()

    with st.form("weeks_invoer"):
        jaar = st.number_input("Jaar", value=today.year, step=1)
        maand = st.number_input("Maand", value=today.month, min_value=1, max_value=12, step=1)
        week = st.number_input("Week", value=today.isocalendar().week, min_value=1, max_value=53, step=1)
        afdeling = st.selectbox("Afdeling", AFDELINGEN)
        shrink = st.number_input("Shrink €")
        sales = st.number_input("Sales €")
        opslaan = st.form_submit_button("💾 Opslaan")

    if opslaan:
        try:
            get_supabase().table("weeks").insert({
                "store_id": STORE_ID,
                "jaar": int(jaar),
                "maand": int(maand),
                "week": int(week),
                "afdeling": afdeling,
                "shrink": float(shrink),
                "sales": float(sales),
            }).execute()
            load_weeks.clear()
            st.success(f"✅ Opgeslagen voor {afdeling}")
        except Exception as e:
            st.error(f"❌ Fout bij opslaan: {e}")

# =====================
# DEMO PROMOTIES
# =====================

elif menu == "🧊 Demo promoties":

    st.title("🧊 Demo promoties")

    df = load_shrink_data()
    if df.empty:
        st.warning("Geen shrink data beschikbaar")
        st.stop()

    producten = df.drop_duplicates("hope").set_index("hope")["product"].to_dict()

    col1, col2 = st.columns(2)
    with col1:
        demo_nr = st.selectbox("Demo", [1, 2, 3, 4, 5])
    with col2:
        week = st.number_input("Week", min_value=1, max_value=53)

    selected_hope = st.selectbox(
        "Product",
        list(producten),
        format_func=lambda h: f"{h} - {producten[h]}",
    )
    promo_type = st.selectbox("Promo type", [
        "GEEN", "1+1", "2+1", "3+1", "4+1",
        "2e -50%", "2e -20%", "2e -40%", "2e -70%", "3 voor €5",
    ])
    sales = st.number_input("Sales (€)", min_value=0.0)

    total_shrink = df.loc[(df["hope"] == selected_hope) & (df["week"] == week), "euro"].sum()
    st.metric("💸 Shrink deze week", format_euro(total_shrink))

    if st.button("💾 Opslaan"):
        today = datetime.date.today()
        try:
            get_supabase().table("demo_promos").insert({
                "datum": str(today),
                "week": int(week),
                "jaar": today.year,
                "demo_nr": demo_nr,
                "hope": selected_hope,
                "product": producten[selected_hope],
                "promo_type": promo_type,
                "sales_euro": float(sales),
                "store_id": STORE_ID,
            }).execute()
            load_demo_promos.clear()
            flash("✅ Opgeslagen")
            st.rerun()
        except Exception as e:
            st.error(f"❌ Fout: {e}")

    st.divider()
    st.subheader("🔍 Analyse per product")

    df_demo = load_demo_promos()
    if df_demo.empty:
        st.info("Nog geen demo data")
        st.stop()

    df_demo = df_demo.copy()
    df_demo["hope"] = normalize_hope(df_demo["hope"])
    df_demo["week"] = to_num(df_demo["week"]).astype(int)
    df_demo["product"] = df_demo["product"].fillna("").astype(str)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        search_hope = st.text_input("🔍 Zoek HOPE")
    with col2:
        search_product = st.text_input("🔍 Zoek product")
    with col3:
        demo_filter = st.selectbox("Demo", ["Alles", 1, 2, 3, 4, 5], key="demo_filter")
    with col4:
        week_filter = st.selectbox("📅 Week", ["Alles"] + sorted(df_demo["week"].dropna().unique()))

    mask = pd.Series(True, index=df_demo.index)
    if search_hope:
        mask &= df_demo["hope"].str.contains(search_hope, case=False, na=False, regex=False)
    if search_product:
        mask &= df_demo["product"].str.contains(search_product, case=False, na=False, regex=False)
    if demo_filter != "Alles":
        mask &= df_demo["demo_nr"] == demo_filter
    if week_filter != "Alles":
        mask &= df_demo["week"].eq(week_filter).fillna(False).astype(bool)
    df_filtered = df_demo[mask]

    if df_filtered.empty:
        st.warning("Geen resultaten gevonden")
        st.stop()

    shrink_per_week = df.groupby(["hope", "week"], as_index=False)["euro"].sum()
    df_merge = df_filtered.merge(shrink_per_week, on=["hope", "week"], how="left")
    df_merge["euro"] = df_merge["euro"].fillna(0)
    df_merge["sales_euro"] = to_num(df_merge["sales_euro"])

    col1, col2 = st.columns(2)
    col1.metric("💰 Sales", format_euro(df_merge["sales_euro"].sum()))
    col2.metric("💸 Shrink", format_euro(df_merge["euro"].sum()))

    st.dataframe(
        df_merge[["hope", "product", "demo_nr", "week", "promo_type", "sales_euro", "euro"]],
        use_container_width=True,
        hide_index=True,
    )
    st.bar_chart(df_merge.groupby("demo_nr")[["sales_euro", "euro"]].sum())

    st.subheader("🏆 Top 10 best verkochte producten")
    st.dataframe(
        df_merge.groupby(["product", "hope"], as_index=False)[["sales_euro", "euro"]].sum()
        .nlargest(10, "sales_euro"),
        use_container_width=True,
        hide_index=True,
    )

# =====================
# RAPPORT
# =====================

elif menu == "📑 Rapport":

    st.title("🔥 Top 20 terugkerende producten")
    st.write(
        "Producten die in de laatste 4 weken regelmatig terugkomen "
        "en samen minstens het ingestelde verlies hebben."
    )

    col1, col2 = st.columns(2)
    with col1:
        min_weken = st.number_input("Minimum aantal weken", min_value=1, max_value=4, value=3, step=1)
    with col2:
        min_verlies = st.number_input("Minimum totaal verlies (€)", min_value=0.0, value=20.0, step=5.0)

    df = load_shrink_data()
    if df.empty:
        st.warning("Geen productdata beschikbaar.")
        st.stop()

    df = df.dropna(subset=["datum"])

    # Laatste 4 winkelweken op kalender (ook correct rond de jaarwissel)
    laatste_start = df["week_start"].max()
    eerste_start = laatste_start - pd.Timedelta(weeks=3)
    df_4 = df[df["week_start"] >= eerste_start]

    if df_4.empty:
        st.warning("Geen data gevonden voor de laatste 4 weken.")
        st.stop()

    top = (
        df_4.groupby(["hope", "product"], dropna=False)
        .agg(weken=("week_start", "nunique"), totaal_verlies=("euro", "sum"))
        .reset_index()
    )
    top["gemiddeld_verlies"] = top["totaal_verlies"] / top["weken"]

    # Trend: laatste 2 weken vs 2 weken daarvoor
    if df_4["week_start"].nunique() >= 4:
        recent = df_4["week_start"] > laatste_start - pd.Timedelta(weeks=2)
        nieuw = top["hope"].map(df_4[recent].groupby("hope")["euro"].sum()).fillna(0)
        oud = top["hope"].map(df_4[~recent].groupby("hope")["euro"].sum()).fillna(0)
        top["trend"] = np.select([nieuw > oud * 1.10, nieuw < oud * 0.90], ["↑", "↓"], "→")
    else:
        top["trend"] = "→"

    top = top[(top["weken"] >= min_weken) & (top["totaal_verlies"] >= min_verlies)]
    top = with_afdeling(top).nlargest(20, "totaal_verlies")

    st.divider()
    st.subheader("🔥 Top 20 — laatste 4 weken")
    st.caption(
        f"{eerste_start:%d/%m/%Y} → {laatste_start + pd.Timedelta(days=6):%d/%m/%Y} · "
        f"minstens {min_weken}/4 weken aanwezig en minstens {format_euro(min_verlies)} totaal verlies"
    )

    if top.empty:
        st.info("Er zijn geen producten die aan deze voorwaarden voldoen.")
        st.stop()

    top.insert(0, "#", range(1, len(top) + 1))
    top = top.rename(columns={
        "hope": "HOPE",
        "product": "Product",
        "afdeling": "Afdeling",
        "weken": "Weken",
        "totaal_verlies": "Totaal verlies",
        "gemiddeld_verlies": "Gemiddeld verlies",
        "trend": "Trend",
    }).round({"Totaal verlies": 2, "Gemiddeld verlies": 2})

    st.dataframe(
        top[["#", "Product", "HOPE", "Afdeling", "Weken", "Totaal verlies", "Gemiddeld verlies", "Trend"]],
        use_container_width=True,
        hide_index=True,
    )

    rijen = top.drop_duplicates("HOPE").set_index("HOPE")
    gekozen_hope = st.selectbox(
        "🔎 Bekijk productdetail",
        [None] + rijen.index.tolist(),
        format_func=lambda h: "Kies een product..." if h is None else f"{rijen.at[h, 'Product']} ({h})",
    )

    if gekozen_hope is not None:
        rij = rijen.loc[gekozen_hope]
        st.divider()
        st.subheader(f"📦 {rij['Product']}")

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("💸 Totaal verlies", format_euro(rij["Totaal verlies"]))
        col2.metric("📊 Gemiddeld / week", format_euro(rij["Gemiddeld verlies"]))
        col3.metric("📅 Weken", f"{int(rij['Weken'])}/4")
        col4.metric("📈 Trend", rij["Trend"])

        st.write(f"**HOPE:** {gekozen_hope}")
        st.write(f"**Afdeling:** {rij['Afdeling']}")
