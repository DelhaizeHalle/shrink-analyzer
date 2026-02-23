import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

# Titel
st.title("📊 Weekly Shrink Analyzer")
st.markdown("### 🏬 Inzicht in shrink en verbeteracties per week")

# Upload
uploaded_file = st.file_uploader("Upload je Excel bestand", type=["xlsx"])

if uploaded_file is not None:
    df = pd.read_excel(uploaded_file)

    # 🔧 DATA CLEANING
    df["ID Shrink €"] = pd.to_numeric(df["ID Shrink €"], errors="coerce")
    df["ID Shrink %"] = pd.to_numeric(df["ID Shrink %"], errors="coerce")

    df = df.dropna(subset=["ID Shrink €"])

    # 📋 Data overzicht
    st.subheader("📋 Data overzicht")
    st.write(df.head())

    # 💸 Totale shrink
    total_shrink = df["ID Shrink €"].sum()

    # 🏬 Shrink per afdeling (BELANGRIJK eerst!)
    dept = df.groupby("Afdeling")["ID Shrink €"].sum().sort_values(ascending=False)

    # 🎯 KPI BLOKKEN (nu correct geplaatst)
    col1, col2 = st.columns(2)

    with col1:
        st.metric("💸 Totale shrink (€)", f"€{total_shrink:.2f}")

    with col2:
        st.metric("🏬 Aantal afdelingen", len(dept))

    # 📊 Shrink per afdeling
    st.subheader("🏬 Shrink per afdeling")
    st.write(dept)

    # 🔴 Grootste probleem
    top_dept = dept.idxmax()
    st.error(f"🔴 Grootste probleem: {top_dept}")

    # ⚠️ Hoogste %
    if df["ID Shrink %"].notna().any():
        top_percent = df.loc[df["ID Shrink %"].idxmax()]
        st.warning(f"⚠️ Hoogste shrink %: {top_percent['Afdeling']} ({top_percent['ID Shrink %']:.2%})")

    # 🧠 Slimme inzichten
    st.subheader("🧠 Slimme inzichten")

    top3 = dept.head(3)
    st.write("🔝 Top 3 probleemafdelingen:")
    st.write(top3)

    top_share = (top3.sum() / total_shrink) * 100
    st.write(f"📊 Top 3 veroorzaakt {top_share:.1f}% van totale shrink")

    if top_share > 60:
        st.warning("⚠️ Focus op top 3 afdelingen — grootste impact!")
    else:
        st.info("📉 Verlies is verspreid — bredere controle nodig")

    # 🎯 ACTIE AANBEVELINGEN
    st.subheader("🎯 Actie aanbevelingen")

    # Grootste impact
    main_problem = dept.idxmax()
    st.error(f"🔴 Focus op {main_problem} — grootste impact op shrink")

    # Hoog percentage
    if df["ID Shrink %"].notna().any():
        high_percent = df.loc[df["ID Shrink %"].idxmax()]
        if high_percent["ID Shrink %"] > 0.05:
            st.warning(f"⚠️ {high_percent['Afdeling']} heeft hoog shrink % → mogelijk procesfout")

    # 📊 Grafiek
    st.subheader("📊 Grafiek")

    fig, ax = plt.subplots()
    dept.head(10).plot(kind='bar', ax=ax)

    ax.set_title("Top 10 Shrink per afdeling (€)")
    ax.set_xlabel("Afdeling")
    ax.set_ylabel("Shrink (€)")

    plt.xticks(rotation=45)
    st.pyplot(fig)

    # 📅 TREND ANALYSE
    st.subheader("📈 Trend analyse per week")

    if "Week" in df.columns:
        unique_weeks = df["Week"].nunique()

        if unique_weeks < 2:
            st.info("ℹ️ Voeg meerdere weken toe om trends te zien")
        else:
            trend = df.groupby(["Week", "Afdeling"])["ID Shrink €"].sum().reset_index()

            pivot = trend.pivot(index="Week", columns="Afdeling", values="ID Shrink €")
            pivot = pivot.sort_index()

            st.line_chart(pivot)

            # Vergelijk laatste weken
            last = pivot.iloc[-1]
            prev = pivot.iloc[-2]

            st.subheader("📊 Verandering t.o.v. vorige week")

            for afdeling in pivot.columns:
                if afdeling in last and afdeling in prev:
                    verschil = last[afdeling] - prev[afdeling]

                    if verschil > 0:
                        st.error(f"🔴 {afdeling}: +€{verschil:.2f} (meer verlies)")
                    elif verschil < 0:
                        st.success(f"✅ {afdeling}: €{verschil:.2f} (verbetering)")