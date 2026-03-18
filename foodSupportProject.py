import streamlit as st
import pandas as pd
import re
import requests
import folium
from streamlit_folium import st_folium
import xml.etree.ElementTree as ET
from datetime import time, timedelta
import altair as alt

# Start with the page config

# =====
# Page Config
# =====
st.set_page_config(
    page_title="Food Support Accessibility Research",
    layout="wide"
)

# =====
# Constants for Convenience
# =====
file_path = "dataset_ae1.csv"
postcodes_api = "https://api.postcodes.io/postcodes" # use it for lan/lon based on postcode
kml_boundaries = "2506.kml"

# =====
# Defaults for map postioning over east london
# =====
default_map_lat = 51.515
default_map_lon = -0.03
default_map_zoom = 12

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
# Helper Function
# Unique locations builder
# =====

def build_locations_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    This function builds a dataframe of unique locations
    As the dataset contains multiple row per location,
    This is essential for mapping
    """
    location_cols = [
        "name",
        "category",
        "type",
        "address",
        "postcode",
        "latitude",
        "longitude"
    ]

    locations_df = df[location_cols].drop_duplicates().dropna(subset=["latitude", "longitude"])

    return locations_df

# =====
# Helper Function
# Marker Color
# =====
def get_marker_color(category:str) -> str:
    """
    Divides markers on map in colors based on category
    """
    if category == "Food Bank":
        return "red"

    if category == "Food Support":
        return "green"

    return "blue"

# =====
# Helper Function
# Opening Day Sorting (to keep the filter convenient)
# =====
def sort_open_days(days: list[str]) -> list[str]:
    """
    Sort days ijn the week for better UX
    """
    days_order = {
        "Mon":1,
        "Tue":2,
        "Wed":3,
        "Thu":4,
        "Fri":5,
        "Sat":6,
        "Sun":7,
    }

    return sorted(days, key=lambda day: days_order[day])

# =====
# Helper Function
# Parcing the time from the dataset
# =====
def parse_time(time):
    """
    Converts a string to datetime object
    If time cannot be converted, returns None
    """
    parsed = pd.to_datetime(time, format="%H:%M", errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.time()

# =====
# Helper Function
# Load the borough boundaries from the KML file
# =====
@st.cache_data(show_spinner=False)
def load_boundary(filepath: str):
    """
    Loads the boundaries for Tower Hamlets borough from the KML file
    *KML stores as lon/lat, folium needs lat/lon
    """
    tree = ET.parse(filepath)
    root = tree.getroot()

    ns = {"kml": "http://www.opengis.net/kml/2.2"}
    coords_text = root.find(".//kml:coordinates", ns).text.strip()

    coords = []

    for point in coords_text.split():
        parts = point.split(",")
        lon = float(parts[0])
        lat = float(parts[1])
        coords.append((lat, lon))

    return coords


# =====
# Helper Function
# Create the Map
# =====
def map_creator(
        locations_df: pd.DataFrame,
        boundary_coords,
        show_boundary: bool
) -> folium.Map:
    """
    Creates a basic folium map and maps the coordinates
    """

    m = folium.Map(
        location=[default_map_lat, default_map_lon],
        zoom_start=default_map_zoom,
        tiles="OpenStreetMap"
    )

    # Draw borough boundaries on request
    if show_boundary and boundary_coords:
        folium.Polygon(
            locations=boundary_coords,
            color="purple",
            weight=2,
            fill=True,
            fill_opacity=0.05,
            tooltip="Tower Hamlets boundary"
        ).add_to(m)

    for index, row in locations_df.iterrows():
        # for each marker add a list of info
        popup = f"""
        <b>{row['name']}</b><br>
        Category: {row['category']}<br>
        Type: {row['type']}<br>
        Address: {row['address']}<br>
        Postcode: {row['postcode']}
        """

        color = get_marker_color(row["category"])

        folium.Marker(
            location=[row["latitude"], row["longitude"]],
            popup= folium.Popup(popup, max_width=250),
            tooltip=row["name"],
            icon=folium.Icon(color=color, icon ="info-sign")
        ).add_to(m)

    return m

# =====
# Helper Function
# Unique places (needed for later analysis)
# =====
def unique_places(df: pd.DataFrame) -> pd.DataFrame:
    """
    As the dataset contains multiple rows per locarion
    to represent different opening days, we need a function
    to extract only the unique ones
    """
    place_cols = [
        "name",
        "category",
        "type",
        "area",
        "address",
        "postcode",
    ]

    unique_places_df = df[place_cols].drop_duplicates()
    return unique_places_df

# =====
# Helper Function
# Area accessability summary
# =====
def area_accessibility(df: pd.DataFrame) -> pd.DataFrame:
    """
    This function returns the accessibility metrics such as:
    number of unique service locations in the area
    number of non-referral open-access services
    number of days with at least one service
    """

    #unique service locatiosn by area
    unique_services = (
        df[["area","name","address", "postcode"]].drop_duplicates()
        .groupby("area")
        .size()
        .reset_index(name="unique_services")
    )

    open_access = (
        df[df["referral_required"] == "NO"][["area","name","address", "postcode"]].drop_duplicates()
        .groupby("area")
        .size()
        .reset_index(name="open_access_services")
    )

    days = (
        df[["area","open_days"]].drop_duplicates()
        .groupby("area")
        .size()
        .reset_index(name="days")
    )

    #merge everything
    area_summary = unique_services.merge(open_access, on="area", how="left")
    area_summary = area_summary.merge(days, on="area", how="left")

    #fill nans
    area_summary["open_access_services"] = area_summary["open_access_services"].fillna(0)
    area_summary["days"] = area_summary["days"].fillna(0)

    #convert to int
    area_summary["open_access_services"] = area_summary["open_access_services"].astype(int)
    area_summary["days"] = area_summary["days"].astype(int)

    #scoring
    area_summary["accessibility_score"] = (
            2 * area_summary["unique_services"]
            + 1 * area_summary["open_access_services"]
            + 1 * area_summary["days"]
    )

    #sorting
    area_summary = area_summary.sort_values(
        by="accessibility_score",
        ascending=False
    ).reset_index(drop=True)

    return area_summary

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

    # Parse times for the filters
    df["open_time_obj"] = df["open_time"].apply(parse_time)
    df["close_time_obj"] = df["close_time"].apply(parse_time)

    return df

# =====
# Main App
# =====
st.title("Food Support Accessibility Research")
st.write("Version 4. Adding some stats")

df = load_data(file_path)

# Load boundary coordinates
borough_boundaries = load_boundary(kml_boundaries)

# Sidebar filters
st.sidebar.header("Filters")

category_options = ["All"] + sorted(df["category"].dropna().unique().tolist()) #display the options

selected_category = st.sidebar.selectbox(
    "Category",
    category_options
)

area_options = ["All"] + sorted(df["area"].dropna().unique().tolist())
selected_area = st.sidebar.selectbox(
    "Area",
    area_options
)

day_values = df["open_days"].dropna().unique().tolist()
sorted_day_values = sort_open_days(day_values)

day_options = ["All"] + sorted_day_values
selected_day = st.sidebar.selectbox(
    "Opening day",
    day_options
)

# Time sliders
st.sidebar.subheader("Opening time filters")

selected_open_time = st.sidebar.slider(
    "Minimum opening time",
    min_value=time(0, 0),
    max_value=time(23, 59),
    value=time(0, 0),
    step=timedelta(minutes=30)
)

selected_close_time = st.sidebar.slider(
    "Latest closing time",
    min_value=time(0, 0),
    max_value=time(23, 59),
    value=time(23, 59),
    step=timedelta(minutes=30)
)

show_boundary = st.sidebar.checkbox(
    "Show Tower Hamlets boundary",
    value=True
)

# Apply filters
filtered_df = df.copy()

if selected_category != "All":
    filtered_df = filtered_df[
        filtered_df["category"] == selected_category
    ]

if selected_area != "All":
    filtered_df = filtered_df[
        filtered_df["area"] == selected_area
    ]

# Apply day filter first
if selected_day != "All":
    filtered_df = filtered_df[
        filtered_df["open_days"] == selected_day
    ]

# Then apply time filters to the already filtered rows
filtered_df = filtered_df[
    (filtered_df["open_time_obj"].notna())
    &
    (filtered_df["close_time_obj"].notna())
    &
    (filtered_df["open_time_obj"] >= selected_open_time)
    &
    (filtered_df["close_time_obj"] <= selected_close_time)
]

# Create the df for mapping
locations_df = build_locations_df(filtered_df)

places_df = unique_places(filtered_df)
area_access_df = area_accessibility(filtered_df)

# tabs
tab_map, tab_data, tab_stats, tab_access = st.tabs(
    ["Map", "Filtered Data", "Statistics","Accessibility Analysis"]
)

with tab_map:
    st.subheader("Support Services Map")

    col1, col2,col3 = st.columns(3)

    col1.metric("Total rows", len(df))
    col2.metric("Filtered rows", len(filtered_df))
    col3.metric("Mapped locations", len(locations_df))

    places_map = map_creator(
        locations_df=locations_df,
        boundary_coords=borough_boundaries,
        show_boundary=show_boundary
    )

    st_folium(places_map, height=600, use_container_width=True)

with tab_data:
    st.subheader("Filtered Dataset")

    st.dataframe(filtered_df, use_container_width=True)

    st.subheader("Rows with no coords")

    missing = df[
        df["latitude"].isna() | df["longitude"].isna()
    ]

    st.dataframe(missing, use_container_width=True)

with tab_stats:
    st.subheader("Statistics")

    # Services by category
    st.write("Services by category")

    category_counts = (
        places_df
        .groupby("category")
        .size()
        .reset_index(name="count")
    )

    pie_category = alt.Chart(category_counts).mark_arc().encode(
        theta="count:Q",
        color="category:N",
        tooltip=["category", "count"]
    )

    st.altair_chart(pie_category, use_container_width=True)

    #Services by type
    st.write("Services by type")

    type_counts = (
        places_df
        .groupby("type")
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
    )

    chart_type = alt.Chart(type_counts).mark_bar().encode(
        x=alt.X("type:N", sort="-y", title="Service Type"),
        y=alt.Y("count:Q", title="Number of Services"),
        tooltip=["type", "count"]
    )

    st.altair_chart(chart_type, use_container_width=True)

    # Services by area
    st.write("Services by area")

    area_counts = (
        places_df
        .groupby("area")
        .size()
        .reset_index(name="count")
        .sort_values(by="count", ascending=False)
    )

    chart_area = alt.Chart(area_counts).mark_bar().encode(
        x = alt.X("area:N", sort="-y"),
        y="count:Q"
    )

    st.altair_chart(chart_area, use_container_width=True)

    st.write("Services by opening day")

    day_counts = (
        filtered_df
        .groupby("open_days")
        .size()
        .reset_index(name="count")
    )

    day_order_df = pd.DataFrame({
        "open_days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    })

    day_counts = day_order_df.merge(day_counts, on="open_days", how="left").fillna(0)
    day_counts["count"] = day_counts["count"].astype(int)

    chart_day = alt.Chart(day_counts).mark_bar().encode(
        x=alt.X(
            "open_days:N",
            sort=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
            title="Opening Day"
        ),
        y=alt.Y("count:Q", title="Number of Services"),
        tooltip=["open_days", "count"]
    )

    st.altair_chart(chart_day, use_container_width=True)

with tab_access:
    st.subheader("Accessibility Analysis")

    st.write(
        "This section ranks areas using a simple accessibility score based on "
        "the number of unique services, open-access services, and number of days covered."
    )

    if not area_access_df.empty:
        best_area = area_access_df.iloc[0]
        worst_area = area_access_df.iloc[-1]

        col1, col2, col3 = st.columns(3)

        col1.metric(
            "Best served area",
            best_area["area"]
        )

        col2.metric(
            "Highest accessibility score",
            int(best_area["accessibility_score"])
        )

        col3.metric(
            "Most underserved area",
            worst_area["area"]
        )

    #Accessability
    st.write("Accessibility score by area")

    chart_access = alt.Chart(area_access_df).mark_bar().encode(
        x=alt.X("area:N", sort="-y", title="Area"),
        y=alt.Y("accessibility_score:Q", title="Accessibility Score"),
        tooltip=[
            "area",
            "unique_services",
            "open_access_services",
            "days",
            "accessibility_score"
        ]
    )

    st.altair_chart(chart_access, use_container_width=True)

    st.write("Ranked area summary")


    st.dataframe(
        area_access_df,
        use_container_width=True
    )
