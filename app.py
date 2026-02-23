import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

# Titel
st.title("📊 Weekly Shrink Analyzer")
st.markdown("### 🏬 Inzicht in shrink en verbeteracties")

# Upload
uploaded_file = st.file_uploader("Upload je shrink bestand (Excel)", type=["xlsx"])

if uploaded_file is not None:

    # 📊 AFDELING DATA
    df = pd.read_excel(uploaded_file, sheet_name="Afdeling")

    # 📦 PRODUCT DATA
    df_p = pd.read_excel(uploaded_file, sheet_name="Producten")

    # 🔧 CLEANING PRODUCT DATA
    df_p["datum"] = pd.to_datetime(df_p["datum"], errors="coerce")
    df_p["stuks"] = pd.to_numeric(df_p["stuks"], errors="coerce")

    # 🔥 AUTOMATISCHE WEEK (BELANGRIJK)
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

    # Grootste probleem
    top_dept = dept.idxmax()
    st.error(f"🔴 Grootste probleem: {top_dept}")

    # =====================
    # 🧠 AFDELING AI
    # =====================

    st.subheader("🧠 Afdeling AI analyse")

    avg_shrink = dept.mean()

    for afdeling in dept.index:
        waarde = dept[afdeling]

        if waarde > avg_shrink * 1.5:
            st.error(f"🔴 {afdeling}: Hoog verlies → focus hier")
        else:
            st.success(f"✅ {afdeling}: Onder controle")

    # =====================
    # 📦 PRODUCT ANALYSE
    # =====================

    st.subheader("📦 Product analyse")

    # Top producten
    top_products = df_p.groupby("benaming")["stuks"].sum().sort_values(ascending=False)

    top10 = top_products.head(10)
    st.write(top10)

    top_product = top_products.idxmax()
    top_value = top_products.max()

    st.error(f"🔴 Grootste probleemproduct: {top_product} ({int(top_value)} stuks)")

    # =====================
    # 🤖 PRODUCT AI
    # =====================

    st.subheader("🤖 Product AI analyse")

    reason_product = df_p.groupby(["benaming", "reden"])["stuks"].sum().reset_index()

    for product in top10.index:

        product_data = reason_product[reason_product["benaming"] == product]

        if not product_data.empty:
            top_reason = product_data.sort_values(by="stuks", ascending=False).iloc[0]

            reden = str(top_reason["reden"]).lower()
            hoeveelheid = top_reason["stuks"]

            if "derving" in reden:
                st.error(f"🍎 {product}: Derving ({int(hoeveelheid)}) → houdbaarheid/rotatie probleem")

            elif "beschadigd" in reden:
                st.warning(f"📦 {product}: Beschadiging ({int(hoeveelheid)}) → handling probleem")

            elif "diefstal" in reden:
                st.error(f"🚨 {product}: Mogelijke diefstal ({int(hoeveelheid)})")

            else:
                st.info(f"🔍 {product}: Hoofdreden = {top_reason['reden']} ({int(hoeveelheid)})")

    # =====================
    # 📈 TREND ANALYSE PRODUCTEN
    # =====================

    st.subheader("📈 Trend analyse (producten per week)")

    if df_p["week"].nunique() >= 2:

        trend = df_p.groupby(["week"])["stuks"].sum()
        st.line_chart(trend)

        last_week = trend.iloc[-1]
        prev_week = trend.iloc[-2]

        diff = last_week - prev_week

        if diff > 0:
            st.error(f"🔴 Stijging van {int(diff)} stuks t.o.v. vorige week")
        else:
            st.success(f"✅ Daling van {int(abs(diff))} stuks")

    else:
        st.info("ℹ️ Voeg meerdere weken toe voor trend analyse")

    # =====================
    # 🔗 COMBINED AI (MAGIE)
    # =====================

    st.subheader("🔥 Gecombineerde AI inzichten")

    st.warning(f"""
    🔍 Grootste afdeling probleem: {top_dept}

    📦 Grootste product probleem: {top_product}

    👉 Focus op deze combinatie voor maximale impact
    """)
