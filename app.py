import streamlit as st
import pandas as pd

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

    # =====================
    # DATA INLADEN
    # =====================

    df = pd.read_excel(uploaded_file, sheet_name="Afdeling")
    df_p = pd.read_excel(uploaded_file, sheet_name="Producten")

    # =====================
    # CLEANING PRODUCT DATA
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

    with col1:
        st.metric("💸 Totale shrink (€)", f"€{total_shrink:.2f}")

    with col2:
        st.metric("🏬 Aantal afdelingen", len(dept))

    st.write(dept)

    top_dept = dept.idxmax()
    st.error(f"🔴 Grootste probleem: {top_dept}")

    # =====================
    # 📅 WEEK VERGELIJKING (COMPACT)
    # =====================

    st.subheader("📅 Week vergelijking (afdelingen)")

    if "Week" in df.columns and df["Week"].nunique() >= 2:

        week_data = df.groupby(["Week", "Afdeling"])["ID Shrink €"].sum().reset_index()
        pivot = week_data.pivot(index="Week", columns="Afdeling", values="ID Shrink €").sort_index()

        last = pivot.iloc[-1]
        prev = pivot.iloc[-2]

        afdelingen = list(pivot.columns)

        for i in range(0, len(afdelingen), 2):
            cols = st.columns(2)
            for j in range(2):
                if i + j < len(afdelingen):
                    afdeling = afdelingen[i + j]
                    verschil = last[afdeling] - prev[afdeling]

                    with cols[j]:
                        if verschil > 0:
                            st.error(f"{afdeling}: +€{verschil:.2f}")
                        elif verschil < 0:
                            st.success(f"{afdeling}: €{verschil:.2f}")
                        else:
                            st.info(f"{afdeling}: geen verandering")

    # =====================
    # 📊 PRODUCT OVERZICHT MET PERIODE
    # =====================

    st.subheader("📊 Product overzicht (per periode)")

    periode_type = st.selectbox("Kies periode type", ["Jaar", "Maand", "Week"])

    if periode_type == "Jaar":
        periode_value = st.selectbox("Kies jaar", sorted(df_p["jaar"].dropna().unique()))
        df_filtered = df_p[df_p["jaar"] == periode_value]

    elif periode_type == "Maand":
        periode_value = st.selectbox("Kies maand", sorted(df_p["maand"].dropna().unique()))
        df_filtered = df_p[df_p["maand"] == periode_value]

    else:
        periode_value = st.selectbox("Kies week", sorted(df_p["week"].dropna().unique()))
        df_filtered = df_p[df_p["week"] == periode_value]

    if not df_filtered.empty:

        product_summary = (
            df_filtered.groupby(["benaming", "categorie"])
            .agg(
                Frequentie=("benaming", "count"),
                Stuks_verlies=("stuks", "sum")
            )
            .sort_values(by="Stuks_verlies", ascending=False)
        )

        st.dataframe(product_summary)

        # 🔥 Meest uitgescande product
        top_product = product_summary.index[0]
        product_name = top_product[0]
        hope = top_product[1]

        st.subheader("🔴 Meest uitgescande product in gekozen periode")

        st.write(f"**{product_name} (Hope {hope})**")

        # Redenen (kolom C)
        product_data = df_filtered[df_filtered["benaming"] == product_name]
        redenen = product_data.groupby("reden")["stuks"].sum().sort_values(ascending=False)

        st.write("📌 Redenen:")
        st.write(redenen)

    else:
        st.info("Geen data voor gekozen periode")

    # =====================
    # 📦 PRODUCT ANALYSE (COMPACT)
    # =====================

    st.subheader("📦 Product analyse")

    top_products = df_p.groupby(["benaming", "categorie"])["stuks"].sum().sort_values(ascending=False)
    top10 = top_products.head(10)

    for (product, hope) in top10.index:

        product_data = df_p[df_p["benaming"] == product]
        totaal = product_data["stuks"].sum()

        with st.expander(f"🔎 {product} (Hope {hope}) — {int(totaal)} stuks"):

            redenen = product_data.groupby("reden")["stuks"].sum().sort_values(ascending=False)

            st.write("📌 Redenen:")
            st.write(redenen)

    # =====================
    # 🔥 COMBINED INSIGHT
    # =====================

    st.subheader("🔥 Gecombineerde inzichten")

    st.warning(f"""
    🔴 Grootste afdeling probleem: {top_dept}

    👉 Gebruik periodefilter hierboven om productproblemen gerichter te analyseren.
    """)
