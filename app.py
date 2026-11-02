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
