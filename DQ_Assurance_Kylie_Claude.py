import streamlit as st
import pandas as pd
import requests
import time
from geopy.distance import geodesic
import plotly.graph_objects as go
import json
import anthropic

# -----------------------------
# Config
# -----------------------------
GERMANY_LAT_RANGE = (47.27, 55.06)
GERMANY_LON_RANGE = (5.87, 15.04)
CONFIDENCE_THRESHOLD = 0.8

# -----------------------------
# Claude Setup
# -----------------------------
claude_api_key = st.sidebar.text_input("🔑 Enter Claude API Key", type="password")
client = None
if claude_api_key and claude_api_key.strip() != "":
    client = anthropic.Anthropic(api_key=claude_api_key)


def get_building_attributes_from_ai(address, postal, client):
    prompt = f"""
    You are an insurance data assistant.
    Given an address and postal code in Germany, return estimated building characteristics.

    Input:
    Address: {address}
    Postal: {postal}

    Output strictly in JSON only. 
    Keys: ConstructionType, Occupancy, Stories, YearBuilt.
    """
    resp = client.messages.create(
        model="claude-opus-4-1-20250805",
        max_tokens=300,
        temperature=0,
        messages=[{"role": "user", "content": prompt}]
    )

    raw_text = resp.content[0].text.strip()

    # clean if code fences are present
    if raw_text.startswith("```"):
        raw_text = raw_text.strip("`")
        raw_text = raw_text.replace("json\n", "").replace("\n```", "")

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        return {"error": "Invalid JSON", "raw_output": raw_text}


# -----------------------------
# Geocoding Functions (unchanged)
# -----------------------------
def geocode_address(address, city, api_key, postal_code=None):
    base_url = "https://api.geoapify.com/v1/geocode/search"
    query = f"{address}, {city}, Germany"
    if postal_code and not pd.isna(postal_code):
        query = f"{address}, {postal_code} {city}, Germany"
    params = {"text": query, "apiKey": api_key, "limit": 1, "lang": "de"}
    response = requests.get(base_url, params=params)
    if response.status_code == 200:
        data = response.json()
        if data["features"]:
            feature = data["features"][0]
            lat = feature["geometry"]["coordinates"][1]
            lon = feature["geometry"]["coordinates"][0]
            confidence = feature["properties"].get("rank", {}).get("confidence", None)
            return lat, lon, confidence
    return None, None, None

def reverse_geocode(lat, lon, api_key):
    url = f"https://api.geoapify.com/v1/geocode/reverse?lat={lat}&lon={lon}&apiKey={api_key}&lang=de"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if data["features"]:
            props = data["features"][0]["properties"]
            return props.get("city", ""), props.get("postcode", "")
    return "", ""

# -----------------------------
# Data Quality Checks
# -----------------------------
def validate_row(row, api_key):
    flags = {
        "DQ: Missing Coordinates": False,
        "DQ: Invalid Coordinates": False,
        "DQ: Low Confidence": False,
        "DQ: Reverse Geocode Mismatch": False,
        "DQ: City/Postal Mismatch": False,
        "DQ: Incomplete Address": False
    }

    if pd.isna(row["Latitude"]) or pd.isna(row["Longitude"]):
        flags["DQ: Missing Coordinates"] = True
    else:
        if not (GERMANY_LAT_RANGE[0] <= row["Latitude"] <= GERMANY_LAT_RANGE[1]) or \
           not (GERMANY_LON_RANGE[0] <= row["Longitude"] <= GERMANY_LON_RANGE[1]):
            flags["DQ: Invalid Coordinates"] = True
        else:
            rev_city, rev_postal = reverse_geocode(row["Latitude"], row["Longitude"], api_key)
            if rev_city and isinstance(row["City"], str) and rev_city.lower() != row["City"].lower():
                flags["DQ: Reverse Geocode Mismatch"] = True
            if rev_postal and row.get("Postal Code") and str(rev_postal) != str(row["Postal Code"]):
                flags["DQ: City/Postal Mismatch"] = True

    if row.get("Geocoding Confidence") is not None and row["Geocoding Confidence"] < CONFIDENCE_THRESHOLD:
        flags["DQ: Low Confidence"] = True

    if isinstance(row["Address"], str):
        if len(row["Address"].split()) < 2:
            flags["DQ: Incomplete Address"] = True
    else:
        flags["DQ: Incomplete Address"] = True

    return flags

# -----------------------------
# Streamlit Layout
# -----------------------------
st.set_page_config(page_title="Exposure Management – Data Quality Dashboard", layout="wide")
st.title("📊 Exposure Management – Data Quality Dashboard")

with st.sidebar:
    st.header("Configuration")
    api_key = st.text_input("🔑 Enter Geoapify API Key", type="password")

uploaded_file = st.file_uploader("📄 Upload your CSV file", type=["csv"])

if uploaded_file:
    df = pd.read_csv(uploaded_file)
    df.columns = df.columns.str.strip()

    qtab, completeness_tab, geotab, discrepancy_tab, export_tab, building_tab = st.tabs([
        "Policy Count Validation", "Data Completeness", "Geocoding & Flags", "Coordinate Discrepancies", "Export", "Building Validation"
    ])

    # ---------------- Tab 1 ----------------
    with qtab:
        st.subheader("Policy Count Validation")
        if 'Unique ID' in df.columns:
            total_policies = len(df)
            unique_locations = df['Unique ID'].nunique()
            st.write(f"**Number of Policies = {total_policies}**")
            st.write(f"**Thereof Number of Unique Locations = {unique_locations}**")
            if total_policies > unique_locations:
                st.warning(f"Found {total_policies - unique_locations} duplicate Unique ID(s).")
        else:
            st.error("Error: 'Unique ID' column not found.")

    # ---------------- Tab 2 ----------------
    with completeness_tab:
        st.subheader("Data Completeness Validation")
        columns_to_check = ['Sum Insured', 'Deductible', 'Mapped LoB', 'Construction Type', 'Occupancy', 'Year Built', 'Number of Stories', 'Basement']
        total_rows = len(df)

        cols = st.columns(2)
        col_idx = 0

        for column in columns_to_check:
            if column in df.columns:
                empty_count = df[column].isna().sum()
                reported_ratio = (1 - empty_count / total_rows) * 100
                fig = go.Figure(go.Indicator(
                    mode="gauge+number",
                    value=reported_ratio,
                    title={'text': f"{column} Reported", 'font': {'size': 16}},
                    gauge={
                        'axis': {'range': [0, 100]},
                        'bar': {'color': "#1f77b4"},
                        'steps': [
                            {'range': [0, 50], 'color': "#ff4d4d"},
                            {'range': [50, 80], 'color': "#ffeb3b"},
                            {'range': [80, 100], 'color': "#4caf50"}
                        ],
                        'threshold': {'line': {'color': "black", 'width': 4}, 'value': 100}
                    }
                ))
                fig.update_layout(height=200, margin=dict(l=10, r=10, t=50, b=10))
                with cols[col_idx]:
                    st.plotly_chart(fig, use_container_width=True)
                    if empty_count > 0:
                        st.warning(f"Found {empty_count} empty {column} values.")
                col_idx = (col_idx + 1) % 2
            else:
                st.error(f"Error: '{column}' column not found in the uploaded CSV.")

    # ---------------- Tab 3 ----------------
    with geotab:
        st.subheader("Geocoding & Flags")

        if "Address" in df.columns and "City" in df.columns:
            # Sidebar controls
            max_rows = st.sidebar.number_input("🔢 Limit rows for geocoding (0 = all)", 
                                            min_value=0, max_value=len(df), value=0, step=100)

            if api_key:
                # Ensure required cols exist
                for col in ["Latitude", "Longitude", "Geocoding Confidence"]:
                    if col not in df.columns:
                        df[col] = None

                # Add API results columns
                df["API_Latitude"] = None
                df["API_Longitude"] = None
                df["API_Confidence"] = None
                df["Use_API_Coordinates"] = False

                # --- Cached geocode call ---
                @st.cache_data(show_spinner=False)
                def cached_geocode(address, city, postal, api_key):
                    return geocode_address(address, city, api_key, postal)

                # --- Progress bar setup ---
                n_rows = len(df) if max_rows == 0 else min(max_rows, len(df))
                progress = st.progress(0)
                status = st.empty()

                for i, row in df.head(n_rows).iterrows():
                    api_lat, api_lon, api_conf = cached_geocode(row["Address"], row["City"], row.get("Postal Code"), api_key)
                    df.at[i, "API_Latitude"] = api_lat
                    df.at[i, "API_Longitude"] = api_lon
                    df.at[i, "API_Confidence"] = api_conf

                    orig_conf = row.get("Geocoding Confidence")
                    if pd.isna(row["Latitude"]) or pd.isna(row["Longitude"]):
                        df.at[i, "Use_API_Coordinates"] = True
                    elif api_conf is not None and (orig_conf is None or api_conf > orig_conf):
                        df.at[i, "Use_API_Coordinates"] = True

                    progress.progress((i+1)/n_rows)
                    status.text(f"Processed {i+1}/{n_rows} rows...")

                progress.empty()
                status.success(f"✅ Finished geocoding {n_rows} rows.")

                # --- Run validation checks ---
                dq_flags = [validate_row(row, api_key) for _, row in df.head(n_rows).iterrows()]
                dq_df = pd.DataFrame(dq_flags)
                result_df = pd.concat([df.head(n_rows), dq_df], axis=1)

                # --- Show summary counts ---
                st.write("### Data Quality Summary")
                summary = dq_df.sum().reset_index()
                summary.columns = ["Check", "Count"]
                st.table(summary)

                st.write("### Detailed Results")
                st.dataframe(result_df)

            else:
                st.warning("⚠️ Please enter your Geoapify API key in the sidebar to run geocoding.")
        else:
            st.error("❌ The uploaded file must contain 'Address' and 'City' columns.")


    # ---------------- Tab 4 ----------------
    with discrepancy_tab:
        st.subheader("Coordinate Discrepancy Check")
        if st.button("🔍 Run Coordinate Distance Check"):
            df["Coord_Diff_km"] = None
            for i, row in df.iterrows():
                if pd.notna(row["Latitude"]) and pd.notna(row["Longitude"]) and \
                   pd.notna(row["API_Latitude"]) and pd.notna(row["API_Longitude"]):
                    orig_coords = (row["Latitude"], row["Longitude"])
                    api_coords = (row["API_Latitude"], row["API_Longitude"])
                    df.at[i, "Coord_Diff_km"] = geodesic(orig_coords, api_coords).km
                else:
                    df.at[i, "Coord_Diff_km"] = None

            df["DQ: Large Coordinate Discrepancy"] = df["Coord_Diff_km"].apply(lambda x: x is not None and x > 1)
            total_checked = df["Coord_Diff_km"].notna().sum()
            large_discrepancies = df["DQ: Large Coordinate Discrepancy"].sum()
            st.info(f"Checked {total_checked} rows. {large_discrepancies} rows have >1km discrepancy.")
            if large_discrepancies > 0:
                st.write("### Rows with >1km coordinate difference")
                cols_to_show = [
                    "Unique ID", "Address", "City", "Postal Code", "Latitude", "Longitude",
                    "API_Latitude", "API_Longitude", "Geocoding Confidence", "API_Confidence", "Coord_Diff_km"
                ]
                st.dataframe(df[df["DQ: Large Coordinate Discrepancy"]][cols_to_show])


    # ---------------- Tab 5 ----------------
    with export_tab:
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Download Validated CSV", csv, "validated.csv", "text/csv")

    # ---------------- Tab 6 ----------------
    with building_tab:
        st.subheader("🏠 Building Characteristics via GenAI Only")
        addr = st.text_input("Enter address (e.g. Schillerstrasse 8)")
        postal = st.text_input("Enter postal code (e.g. 70839)")
        if st.button("🔍 Get Building Attributes"):
            if addr and postal and client:
                attrs = get_building_attributes_from_ai(addr, postal, client)
                st.write("### AI Estimated Building Attributes")
                st.json(attrs)
            else:
                st.warning("Provide address + postal code and Claude API key.")
