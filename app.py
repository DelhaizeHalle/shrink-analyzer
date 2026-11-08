import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import html
import json
import re
import time
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus
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

