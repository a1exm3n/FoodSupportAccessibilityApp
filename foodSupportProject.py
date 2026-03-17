import streamlit as st
import pandas as pd
import re
import requests

# Start with the page config

# =====
# Page Config
# =====
st.set_page_config(
    page_title="Food Support Accessibility Research",
    layout="wide",
)

# =====
# Constants for Convenience
# =====
file_path = "dataset_ae1.csv"
postcodes_api = "https://api.postcodes.io/postcodes" # use it for lan/lon based on postcode

# =====
# Helper Function
# Postcode Cleaning
# =====
def clean_postcode(postcode: str) -> str | None:
    """
    Used to clean and standardize UK-format postcodes
    Gets rid of extra spaces, helps with the upper/lower case
    Cleans from artifact characters
    """

    # Handle nan cases
    if pd.isna(postcode):
        return None

    postcode = str(postcode).upper().strip()

    #Only keep letterrs and digits
    postcode = re.sub(r"[^A-Z0-9]", "", postcode)

    # Insert the standard space before the three last chars
    if len(postcode) >= 5:
        postcode = postcode[:-3] + " " + postcode[-3:]

    return postcode if postcode else None

# =====
# Helper Function
# Coordinates Finding
# =====
@st.cache_data(show_spinner=False) #if the input file does not change this function will not rerun, saving time
def fetch_postcodes(postcodes: list[str]) -> dict:
    """
    takes a list of postcodes
    returns a dict of postcodes with lan and lon
    """
    unique_postcodes = [
        pc for pc in pd.Series(postcodes)
        .dropna()
        .unique()
        .tolist()
        if pc
    ]

    if not unique_postcodes:
        return {}

    payload = {"postcodes": unique_postcodes}

    try:
        response = requests.post(
            postcodes_api,
            json=payload,
            timeout=10
        )

        response.raise_for_status()
        data = response.json()

    except requests.RequestException as e:
        st.error(f"Postcode lookup failed: {e}")
        return {}

    lookup = {}

    for item in data.get("result", []):
        query = item.get("query")
        result = item.get("result")

        if result:
            lookup[query] = {
                "latitude": result.get("latitude"),
                "longitude": result.get("longitude"),
            }
        else:
            lookup[query] = {
                "latitude": None,
                "longitude": None,
            }

    return lookup

# =====
# Data Loading
# =====
@st.cache_data(show_spinner=False) # if the input file does not change this function will not rerun, saving time
def load_data(file_path: str) -> pd.DataFrame:
    """
    Loads the df and assigns coordinates
    """
    df = pd.read_csv(file_path, encoding="cp1252")

    # clean postcodes
    df["postcode"] = df["postcode"].apply(clean_postcode)

    # lookup coordinates for all postcodes
    lookup = fetch_postcodes(df["postcode"].tolist())

    # assign lat from the created dic
    df["latitude"] = df["postcode"].map(
        lambda postcode: lookup.get(postcode, {}).get("latitude")
    )

    # assign lon from the created dic
    df["longitude"] = df["postcode"].map(
        lambda postcode: lookup.get(postcode, {}).get("longitude")
    )

    return df

# =====
# Main App
# =====
st.title("Food Support Accessibility Research")
st.write("Version 1. df loading and postcode based coordinates")

df = load_data(file_path)

st.subheader("Coordinates quality check")

col1, col2, col3 = st.columns(3)
col1.metric("total rows", len(df))
col2.metric("rows with lat", df["latitude"].notna().sum())
col3.metric("rows with lon", df["longitude"].notna().sum())

# Show dataset

st.subheader("Dataset preview")
st.dataframe(df, use_container_width=True)

#Check missing lat/lon
st.subheader("Rows with no coordinates")

missing = df[df["latitude"].isna() | df["longitude"].isna()]
st.dataframe(missing, use_container_width=True)
