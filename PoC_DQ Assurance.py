import streamlit as st
import pandas as pd
from geopy.geocoders import Nominatim

def geocode_address(address):
    geolocator = Nominatim(user_agent="FM_GEOCODER")
    location = geolocator.geocode(address)
    if location:
        return location.latitude, location.longitude
    return None, None

st.title("Address Geocoder & Validator")

uploaded_file = st.file_uploader("Upload your CSV", type=["csv"])
if uploaded_file:
    df = pd.read_csv(uploaded_file)
    
    if 'latitude' not in df.columns or 'longitude' not in df.columns:
        df['latitude'], df['longitude'] = None, None

    for i, row in df.iterrows():
        if pd.isna(row['latitude']) or pd.isna(row['longitude']):
            lat, lon = geocode_address(row['Address'])
            df.at[i, 'latitude'] = lat
            df.at[i, 'longitude'] = lon

    st.write(df)
    st.download_button("Download Updated CSV", df.to_csv(index=False), "geocoded.csv")
