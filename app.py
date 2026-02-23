import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

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
    # CLEANING
    # =====================

    df_p["datum"] = pd.to_datetime(df_p["datum"], errors="coerce")
    df_p["stuks"] = pd.to_numeric(df_p["stuks"], errors="coerce")

    df_p["week"] = df_p["datum"].dt.isocalendar().week
    df_p["jaar"] = df_p["datum"].dt.year

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

        st.line_chart(pivot)

        last = pivot.iloc[-1]
        prev = pivot.iloc[-2]

        st.subheader("📊 Verandering t.o.v. vorige week")

        afdelingen = list(pivot.columns)

        # 🔥 2 kolommen layout
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

    else:
        st.info("ℹ️ Voeg meerdere weken toe in Afdeling sheet")

    # =====================
    # 🔁 FREQUENTIE + IMPACT
    # =====================

    st.subheader("📊 Product overzicht (frequentie + impact)")

    freq = df_p["benaming"].value_counts()
    impact = df_p.groupby("benaming")["stuks"].sum()

    combined = pd.DataFrame({
        "Frequentie": freq,
        "Stuks verlies": impact
    }).fillna(0)

    combined = combined.sort_values(by="Stuks verlies", ascending=False).head(10)

    st.dataframe(combined)

    st.bar_chart(combined["Stuks verlies"])

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

            hoofdreden = redenen.index[0]
            hoeveelheid = redenen.iloc[0]
            reden_lower = str(hoofdreden).lower()

            if "derving" in reden_lower:
                st.error(f"🍎 Derving ({int(hoeveelheid)}) → houdbaarheid probleem")

            elif "beschadigd" in reden_lower:
                st.warning(f"📦 Beschadiging ({int(hoeveelheid)}) → handling probleem")

            elif "diefstal" in reden_lower:
                st.error(f"🚨 Diefstal ({int(hoeveelheid)}) → controle nodig")

            elif "afschrijving" in reden_lower:
                st.warning(f"📉 Afschrijving → mogelijk overstock")

            else:
                st.info(f"🔍 Hoofdreden: {hoofdreden} ({int(hoeveelheid)})")

    # =====================
    # 📈 PRODUCT TRENDS
    # =====================

    st.subheader("📈 Product trends per week + reden")

    if df_p["week"].nunique() >= 2:

        selected_product = st.selectbox("Kies product", df_p["benaming"].unique())

        product_data = df_p[df_p["benaming"] == selected_product]

        trend = product_data.groupby(["week", "reden"])["stuks"].sum().reset_index()
        pivot = trend.pivot(index="week", columns="reden", values="stuks").fillna(0)

        st.line_chart(pivot)
        st.write(pivot)

    else:
        st.info("ℹ️ Voeg meerdere weken toe voor trends")

    # =====================
    # 🔥 COMBINED INSIGHT
    # =====================

    st.subheader("🔥 Gecombineerde inzichten")

    top_product = top10.index[0][0]

    st.warning(f"""
    🔴 Grootste afdeling probleem: {top_dept}

    📦 Grootste product probleem: {top_product}

    👉 Focus hier voor maximale impact
    """)
