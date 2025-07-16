import streamlit as st
import pandas as pd
import requests
import time

# Streamlit UI
st.title("📍 Address Geocoder & Validator (Geoapify API)")
st.write("Upload a CSV file with addresses and cities. The app will geocode missing coordinates using the Geoapify API.")

# API key input
api_key = "56175b1bf61f4499a63abe45efdcd86f"  # Generate a new code if needed from https://myprojects.geoapify.com/api/RKShInVzmpM9LnXVasBf/keys

# File uploader
uploaded_file = st.file_uploader("📄 Upload your CSV file", type=["csv"])

# Geocoding function using Geoapify
def geocode_address(address, city, api_key):
    base_url = "https://api.geoapify.com/v1/geocode/search"
    params = {
        "text": f"{address}, {city}, Germany",
        "apiKey": api_key,
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

# Process the uploaded file
if uploaded_file and api_key:
    df = pd.read_csv(uploaded_file)

    # Normalize column names
    df.columns = df.columns.str.strip()

    # Ensure required columns exist
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
                lat, lon, conf = geocode_address(row["Address"], row["City"], api_key)
                df.at[i, "Latitude"] = lat
                df.at[i, "Longitude"] = lon
                df.at[i, "Geocoding Confidence"] = conf
                time.sleep(1)  # Respect Geoapify rate limit

        st.success("✅ Geocoding complete!")
        st.dataframe(df)

        # Download button
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Download Updated CSV", csv, "geocoded_output.csv", "text/csv")
    else:
        st.error("❌ The uploaded file must contain 'Address' and 'City' columns.")

