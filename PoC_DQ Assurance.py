
import streamlit as st
import pandas as pd
import requests
import time

# -----------------------------
# Configuration
# -----------------------------
API_KEY = "56175b1bf61f4499a63abe45efdcd86f"
GERMANY_LAT_RANGE = (47.27, 55.06)
GERMANY_LON_RANGE = (5.87, 15.04)
CONFIDENCE_THRESHOLD = 0.8

# -----------------------------
# Geocoding Functions
# -----------------------------
def geocode_address(address, city):
    base_url = "https://api.geoapify.com/v1/geocode/search"
    params = {
        "text": f"{address}, {city}, Germany",
        "apiKey": API_KEY,
        "limit": 1,
        "lang": "de"
    }
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

def reverse_geocode(lat, lon):
    url = f"https://api.geoapify.com/v1/geocode/reverse?lat={lat}&lon={lon}&apiKey={API_KEY}&lang=de"
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
def validate_row(row):
    flags = {
        "DQ: Missing Coordinates": False,
        "DQ: Invalid Coordinates": False,
        "DQ: Low Confidence": False,
        "DQ: Reverse Geocode Mismatch": False,
        "DQ: City/Postal Mismatch": False,
        "DQ: Incomplete Address": False
    }

    # Check missing coordinates
    if pd.isna(row["Latitude"]) or pd.isna(row["Longitude"]):
        flags["DQ: Missing Coordinates"] = True
    else:
        # Check coordinate range

        if not (GERMANY_LAT_RANGE[0] <= row["Latitude"] <= GERMANY_LAT_RANGE[1]) or \
           not (GERMANY_LON_RANGE[0] <= row["Longitude"] <= GERMANY_LON_RANGE[1]):
            flags["DQ: Invalid Coordinates"] = True
        else:
            # Reverse geocode and compare city
            rev_city, rev_postal = reverse_geocode(row["Latitude"], row["Longitude"])
            if rev_city and isinstance(row["City"], str) and rev_city.lower() != row["City"].lower():
                flags["DQ: Reverse Geocode Mismatch"] = True
            if rev_postal and row.get("Postal Code") and str(rev_postal) != str(row["Postal Code"]):
                flags["DQ: City/Postal Mismatch"] = True
        
            

    # Check confidence
    if row.get("Geocoding Confidence") is not None and row["Geocoding Confidence"] < CONFIDENCE_THRESHOLD:
        flags["DQ: Low Confidence"] = True
    # The score indicates the reliability of the match e.g. if lower than 100% say 70%, it is e.g. due to misspellings, alternative street names, or partial matching.


    # Check address completeness
    if isinstance(row["Address"], str):
        if len(row["Address"].split()) < 2:
            flags["DQ: Incomplete Address"] = True
    else:
        flags["DQ: Incomplete Address"] = True

    return flags

# -----------------------------
# Streamlit UI
# -----------------------------
st.title("📍 Geocoding & Data Quality Validator (Germany)")
st.write("Upload a CSV file with addresses and cities. The app will geocode missing coordinates and validate geospatial data quality.")

uploaded_file = st.file_uploader("📄 Upload your CSV file", type=["csv"])

if uploaded_file:
    df = pd.read_csv(uploaded_file)
    df.columns = df.columns.str.strip()

    if "Address" in df.columns and "City" in df.columns:
        if "Latitude" not in df.columns:
            df["Latitude"] = None
        if "Longitude" not in df.columns:
            df["Longitude"] = None
        if "Geocoding Confidence" not in df.columns:
            df["Geocoding Confidence"] = None

        # Geocode missing coordinates
        for i, row in df.iterrows():
            if pd.isna(row["Latitude"]) or pd.isna(row["Longitude"]):
                lat, lon, conf = geocode_address(row["Address"], row["City"])
                df.at[i, "Latitude"] = lat
                df.at[i, "Longitude"] = lon
                df.at[i, "Geocoding Confidence"] = conf
                time.sleep(1)

        # Data quality checks
        dq_flags = []
        for i, row in df.iterrows():
            flags = validate_row(row)
            dq_flags.append(flags)

        dq_df = pd.DataFrame(dq_flags)
        result_df = pd.concat([df, dq_df], axis=1)

        st.success("✅ Processing complete!")
        st.dataframe(result_df)

        csv = result_df.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Download Validated CSV", csv, "geocoded_validated.csv", "text/csv")
    else:
        st.error("❌ The uploaded file must contain 'Address' and 'City' columns.")
