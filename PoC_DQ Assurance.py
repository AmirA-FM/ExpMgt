import streamlit as st
import pandas as pd
import requests
import time
from geopy.distance import geodesic

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
def geocode_address(address, city, postal_code=None):
    base_url = "https://api.geoapify.com/v1/geocode/search"
    # Build the query string with postal code if available
    query = f"{address}, {city}, Germany"
    if postal_code and not pd.isna(postal_code):
        query = f"{address}, {postal_code} {city}, Germany"
    params = {
        "text": query,
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

    # Unique ID Validation
    st.subheader("Policy Count Validation")
    if 'Unique ID' in df.columns:
        total_policies = len(df)
        unique_locations = df['Unique ID'].nunique()
        st.write(f"**Number of Policies = {total_policies}**")
        st.write(f"**Thereof Number of Unique Locations = {unique_locations}**")
        if total_policies > unique_locations:
            st.warning(f"Found {total_policies - unique_locations} duplicate Unique ID(s). Consider reviewing for data integrity.")
    else:
        st.error("Error: 'Unique ID' column not found in the uploaded CSV.")

    # Data Completeness Validation
    st.subheader("Data Completeness Validation")
    columns_to_check = ['Sum Insured', 'Deductible', 'Mapped LoB', 'Construction Type', 'Occupancy', 'Year Built', 'Number of Stories', 'Basement']
    total_rows = len(df)
    
    for column in columns_to_check:
        if column in df.columns:
            empty_count = df[column].isna().sum()
            reported_ratio = (1 - empty_count / total_rows) * 100
            st.write(f"**{column} reported: {reported_ratio:.2f}%**")
            if empty_count > 0:
                st.warning(f"Found {empty_count} empty {column} values.")
        else:
            st.error(f"Error: '{column}' column not found in the uploaded CSV.")



#--------------------------
    # GAUGES - Data Completeness Validation with Gauge Visualizations
    import plotly.graph_objects as go
    
    st.subheader("Data Completeness Validation")
    columns_to_check = ['Sum Insured', 'Deductible', 'Mapped LoB', 'Construction Type', 'Occupancy', 'Year Built', 'Number of Stories', 'Basement']
    total_rows = len(df)
    
    # Create a 2-column layout for gauges
    cols = st.columns(2)
    col_idx = 0
    
    for column in columns_to_check:
        if column in df.columns:
            empty_count = df[column].isna().sum()
            reported_ratio = (1 - empty_count / total_rows) * 100
            
            # Create Plotly gauge chart
            fig = go.Figure(go.Indicator(
                mode="gauge+number",
                value=reported_ratio,
                title={'text': f"{column} Reported", 'font': {'size': 16}},
                gauge={
                    'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': "black"},
                    'bar': {'color': "#1f77b4"},
                    'steps': [
                        {'range': [0, 50], 'color': "#ff4d4d"},
                        {'range': [50, 80], 'color': "#ffeb3b"},
                        {'range': [80, 100], 'color': "#4caf50"}
                    ],
                    'threshold': {
                        'line': {'color': "black", 'width': 4},
                        'thickness': 0.75,
                        'value': 100
                    }
                }
            ))
            fig.update_layout(height=200, margin=dict(l=10, r=10, t=50, b=10))
            
            # Display gauge in the appropriate column
            with cols[col_idx]:
                st.plotly_chart(fig, use_container_width=True)
                if empty_count > 0:
                    st.warning(f"Found {empty_count} empty {column} values.")
            
            # Alternate between columns
            col_idx = (col_idx + 1) % 2
        else:
            st.error(f"Error: '{column}' column not found in the uploaded CSV.")
    
   #--------------------------------------- 
    if "Address" in df.columns and "City" in df.columns:
        if "Latitude" not in df.columns:
            df["Latitude"] = None
        if "Longitude" not in df.columns:
            df["Longitude"] = None
        if "Geocoding Confidence" not in df.columns:
            df["Geocoding Confidence"] = None

        # Add new columns for API results
        df["API_Latitude"] = None
        df["API_Longitude"] = None
        df["API_Confidence"] = None
        df["Use_API_Coordinates"] = False

        for i, row in df.iterrows():
            # Always geocode the address
            api_lat, api_lon, api_conf = geocode_address(
        row["Address"], row["City"], row.get("Postal Code")
    )
            df.at[i, "API_Latitude"] = api_lat
            df.at[i, "API_Longitude"] = api_lon
            df.at[i, "API_Confidence"] = api_conf

            # Decide which coordinates to use
            orig_conf = row.get("Geocoding Confidence")
            if pd.isna(row["Latitude"]) or pd.isna(row["Longitude"]):
                # No original coordinates, use API
                df.at[i, "Use_API_Coordinates"] = True
            elif api_conf is not None and (orig_conf is None or api_conf > orig_conf):
                # API is more confident
                df.at[i, "Use_API_Coordinates"] = True
            else:
                # Keep original
                df.at[i, "Use_API_Coordinates"] = False

            # Optionally, update Latitude/Longitude if using API (uncomment if you want this)
            # if df.at[i, "Use_API_Coordinates"]:
            #     df.at[i, "Latitude"] = api_lat
            #     df.at[i, "Longitude"] = api_lon
            #     df.at[i, "Geocoding Confidence"] = api_conf

            time.sleep(1)

        # Data quality checks (use original or API coordinates as needed)
        dq_flags = []
        for i, row in df.iterrows():
            # Optionally, validate using the selected coordinates
            # if row["Use_API_Coordinates"]:
            #     row["Latitude"] = row["API_Latitude"]
            #     row["Longitude"] = row["API_Longitude"]
            #     row["Geocoding Confidence"] = row["API_Confidence"]
            flags = validate_row(row)
            dq_flags.append(flags)

        dq_df = pd.DataFrame(dq_flags)
        result_df = pd.concat([df, dq_df], axis=1)

        st.success("✅ Processing complete!")
        st.dataframe(result_df)

        # After processing and displaying the main dataframe/results
        # Add this after st.dataframe(result_df) and before the download button

        if st.button("🔍 Run Coordinate Distance Check"):
            # Calculate distance between original and API coordinates
            df["Coord_Diff_km"] = None
            for i, row in df.iterrows():
                if pd.notna(row["Latitude"]) and pd.notna(row["Longitude"]) and \
                   pd.notna(row["API_Latitude"]) and pd.notna(row["API_Longitude"]):
                    orig_coords = (row["Latitude"], row["Longitude"])
                    api_coords = (row["API_Latitude"], row["API_Longitude"])
                    df.at[i, "Coord_Diff_km"] = geodesic(orig_coords, api_coords).km
                else:
                    df.at[i, "Coord_Diff_km"] = None

            # Flag large discrepancies (e.g., >1km)
            df["DQ: Large Coordinate Discrepancy"] = df["Coord_Diff_km"].apply(lambda x: x is not None and x > 1)

            # Simple report
            total_checked = df["Coord_Diff_km"].notna().sum()
            large_discrepancies = df["DQ: Large Coordinate Discrepancy"].sum()
            st.info(
                f"Coordinate distance check complete: {total_checked} rows checked. "
                f"{large_discrepancies} rows have a coordinate difference greater than 1 km."
            )
            if large_discrepancies > 0:
                st.warning("Some records have significant coordinate discrepancies. Please review them.")

                # Show details for rows with large discrepancies
                st.write("### Rows with >1km coordinate difference")
                st.dataframe(
                    df[df["DQ: Large Coordinate Discrepancy"]][
                        [
                            "Unique ID", "Address", "City", "Postal Code",
                            "Latitude", "Longitude", "API_Latitude", "API_Longitude",
                            "Geocoding Confidence", "API_Confidence", "Coord_Diff_km"
                        ]
                        if "Unique ID" in df.columns else
                        [
                            "Address", "City", "Postal Code",
                            "Latitude", "Longitude", "API_Latitude", "API_Longitude",
                            "Geocoding Confidence", "API_Confidence", "Coord_Diff_km"
                        ]       )
                    ]
                )        csv = result_df.to_csv(index=False).encode("utf-8")





        st.error("❌ The uploaded file must contain 'Address' and 'City' columns.")    else:        st.download_button("📥 Download Validated CSV", csv, "geocoded_validated.csv", "text/csv")        csv = result_df.to_csv(index=False).encode("utf-8")        st.download_button("📥 Download Validated CSV", csv, "geocoded_validated.csv", "text/csv")
    else:
        st.error("❌ The uploaded file must contain 'Address' and 'City' columns.")
