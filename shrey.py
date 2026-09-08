import os
from dotenv import load_dotenv
from pystac_client import Client
import planetary_computer

# 1. Load environment variables from the .env file
load_dotenv()

def main():
    print("Connecting to Microsoft Planetary Computer STAC API...")
    
    # 2. Connect with automatic token signing
    # If PC_SDK_SUBSCRIPTION_KEY is in your environment, it will automatically use it here.
    catalog = Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )

    # 3. Define the Barpeta Bounding Box [Min Lon, Min Lat, Max Lon, Max Lat]
    # Barpeta district along the Brahmaputra River floodplain in Assam
    barpeta_bbox = [90.70, 26.05, 91.45, 26.75]

    # 4. Query the Sentinel-1 RTC collection for the monsoon window
    print("Querying Sentinel-1 RTC scenes for Barpeta (Brahmaputra Floodplain)...")
    search = catalog.search(
        collections=["sentinel-1-rtc"],
        bbox=barpeta_bbox,
        datetime="2023-06-01/2023-09-30", 
    )

    items = list(search.items())
    print(f"Success! Found {len(items)} Sentinel-1 RTC scenes for Barpeta.")

    # 5. Print the signed URLs for the first 3 scenes
    for item in items[:3]:
        print(f"\n--- Scene ID: {item.id} ---")
        print(f"Date: {item.datetime}")
        print(f"VV Asset URL: {item.assets['vv'].href}")
        
        # If you wanted to download or open the raster, you would pass this exact href 
        # directly into rioxarray.open_rasterio() in the next step of your pipeline.

if __name__ == "__main__":
    main()