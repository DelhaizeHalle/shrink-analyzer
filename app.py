import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from supabase import create_client

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
        .range(0, 1000)
        .execute().data or []
    )

    df_products = pd.DataFrame(
        supabase.table("shrink_data")
        .select("*")
        .eq("user_id", user_id)
        .range(0, 10000)
        .execute().data or []
    )

    return df_weeks, df_products

df_weeks, df_products = load_data(user_id)

# =====================
# TITEL
# =====================

st.title("📊 Weekly Shrink Analyzer")
st.markdown("### 🏬 Inzicht in shrink en verbeteracties per week")

# =====================
# GEEN DATA CHECK
# =====================

if df_weeks.empty:
    st.warning("Geen data in 'weeks' tabel")
    st.stop()

# =====================
# DATA VOORBEREIDING
# =====================

df_weeks["shrink"] = pd.to_numeric(df_weeks["shrink"], errors="coerce")
df_weeks["percent"] = pd.to_numeric(df_weeks["percent"], errors="coerce")

df_weeks = df_weeks.dropna(subset=["shrink"])

# =====================
# KPI
# =====================

total_shrink = df_weeks["shrink"].sum()

dept = df_weeks.groupby("afdeling")["shrink"].sum().sort_values(ascending=False)

col1, col2 = st.columns(2)

with col1:
    st.metric("💸 Totale shrink (€)", f"€{total_shrink:.2f}")

with col2:
    st.metric("🏬 Aantal afdelingen", len(dept))

# =====================
# OVERZICHT
# =====================

st.subheader("🏬 Shrink per afdeling")
st.write(dept)

top_dept = dept.idxmax()
st.error(f"🔴 Grootste probleem: {top_dept}")

# =====================
# % CHECK
# =====================

if df_weeks["percent"].notna().any():
    top_percent = df_weeks.loc[df_weeks["percent"].idxmax()]
    st.warning(
        f"⚠️ Hoogste shrink %: {top_percent['afdeling']} ({top_percent['percent']:.2%})"
    )

# =====================
# INSIGHTS
# =====================

st.subheader("🧠 Slimme inzichten")

top3 = dept.head(3)
st.write("🔝 Top 3 probleemafdelingen:")
st.write(top3)

top_share = (top3.sum() / total_shrink) * 100
st.write(f"📊 Top 3 veroorzaakt {top_share:.1f}% van totale shrink")

if top_share > 60:
    st.warning("⚠️ Focus op top 3 afdelingen")
else:
    st.info("📉 Verlies is verspreid")

# =====================
# AI ANALYSE
# =====================

st.subheader("🤖 Slimme AI analyse")

avg_shrink = dept.mean()

for afdeling in dept.index:

    waarde = dept[afdeling]
    df_afdeling = df_weeks[df_weeks["afdeling"] == afdeling]
    perc = df_afdeling["percent"].mean()

    trend_msg = ""

    if df_weeks["week"].nunique() >= 2:
        trend = df_weeks.groupby(["week", "afdeling"])["shrink"].sum().reset_index()
        pivot = trend.pivot(index="week", columns="afdeling", values="shrink").sort_index()

        if afdeling in pivot.columns:
            last = pivot.iloc[-1][afdeling]
            prev = pivot.iloc[-2][afdeling]

            if last > prev * 1.2:
                trend_msg = "📈 stijgend"
            elif last < prev * 0.8:
                trend_msg = "📉 dalend"

    if waarde > avg_shrink * 1.5:
        if perc > 0.05:
            st.error(f"🔴 {afdeling}: Hoog € én hoog % {trend_msg}")
        else:
            st.error(f"🔴 {afdeling}: Hoog verlies {trend_msg}")

    elif perc > 0.05:
        st.warning(f"⚠️ {afdeling}: Hoog % {trend_msg}")

    elif trend_msg == "📈 stijgend":
        st.warning(f"📈 {afdeling}: stijgend")

    else:
        st.success(f"✅ {afdeling}: OK")

# =====================
# GRAFIEK
# =====================

st.subheader("📊 Grafiek")

fig, ax = plt.subplots()
dept.head(10).plot(kind='bar', ax=ax)

ax.set_title("Top 10 Shrink per afdeling (€)")
plt.xticks(rotation=45)

st.pyplot(fig)

# =====================
# TREND
# =====================

st.subheader("📈 Trend analyse per week")

if df_weeks["week"].nunique() < 2:
    st.info("Voeg meerdere weken toe")
else:
    trend = df_weeks.groupby(["week", "afdeling"])["shrink"].sum().reset_index()
    pivot = trend.pivot(index="week", columns="afdeling", values="shrink").sort_index()

    st.line_chart(pivot)

    last = pivot.iloc[-1]
    prev = pivot.iloc[-2]

    st.subheader("📊 Verandering t.o.v. vorige week")

    for afdeling in pivot.columns:
        diff = last[afdeling] - prev[afdeling]

        if diff > 0:
            st.error(f"🔴 {afdeling}: +€{diff:.2f}")
        elif diff < 0:
            st.success(f"✅ {afdeling}: €{diff:.2f}")
