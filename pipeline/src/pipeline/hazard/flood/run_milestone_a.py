"""Milestone A Runner: End-to-End Steps 1–4 for Barpeta, Assam.

Executes:
  - Step 1: Define Barpeta AOI boundary & save GeoJSON.
  - Step 2: Query Microsoft Planetary Computer STAC for Sentinel-1 RTC scenes.
  - Step 3: Stream and window-clip VV backscatter COG raster.
  - Step 4: Convert to dB, threshold, and export binary water mask GeoTIFF & preview PNG.
"""

import sys
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np

WORKSPACE_ROOT = Path(__file__).resolve().parents[4]

from pipeline.hazard.flood.aoi import save_barpeta_boundary, get_barpeta_bounds_projected
from pipeline.hazard.flood.stac import query_sentinel1_rtc, extract_scene_metadata
from pipeline.hazard.flood.water_mask import (
    stream_and_clip_raster,
    linear_to_db,
    detect_water,
    save_raster_geotiff,
    DEFAULT_VV_WATER_THRESHOLD_DB,
)


def main():
    print("=" * 70)
    print("SETU-DRR: Flood Susceptibility Pipeline - Milestone A (Steps 1-4)")
    print("Pilot: Barpeta (Brahmaputra Floodplain, Assam)")
    print("=" * 70)

    # -------------------------------------------------------------
    # Step 1: Define and save AOI boundary
    # -------------------------------------------------------------
    print("\n[Step 1] Initializing Barpeta AOI boundary...")
    boundary_path = WORKSPACE_ROOT / "data" / "raw" / "boundaries" / "barpeta.geojson"
    save_barpeta_boundary(boundary_path)
    print(f"  [+] Saved AOI boundary to: {boundary_path}")

    # -------------------------------------------------------------
    # Step 2: Query Sentinel-1 RTC scenes
    # -------------------------------------------------------------
    print("\n[Step 2] Querying Sentinel-1 RTC STAC catalog (Planetary Computer)...")
    scenes = query_sentinel1_rtc(datetime_range="2022-11-01/2022-11-30")
    print(f"  [+] Found {len(scenes)} scenes in November 2022 window.")

    if not scenes:
        raise RuntimeError("No Sentinel-1 RTC scenes found for the specified query.")

    selected_item = scenes[0]
    meta = extract_scene_metadata(selected_item)
    print(f"  [+] Selected Scene: {meta['id']}")
    print(f"    Date: {meta['datetime']}")
    print(f"    VV Asset URL: {meta['vv_href'][:80]}...")

    # -------------------------------------------------------------
    # Step 3: Stream and Clip VV Backscatter Raster
    # -------------------------------------------------------------
    print("\n[Step 3] Streaming & window-clipping VV raster directly from cloud...")
    raw_vv, transform, crs, nodata_val = stream_and_clip_raster(meta["vv_href"])
    print(f"  [+] Clipped Shape: {raw_vv.shape[0]} rows x {raw_vv.shape[1]} cols")
    print(f"  [+] Coordinate Reference System: {crs}")
    print(f"  [+] Pixel Resolution: {abs(transform.a):.1f}m x {abs(transform.e):.1f}m")

    # Convert linear power to dB
    vv_db, valid_mask = linear_to_db(raw_vv, nodata_val=nodata_val)
    valid_count = np.sum(valid_mask)
    print(f"  [+] Valid pixel observations: {valid_count:,} / {raw_vv.size:,} ({valid_count / raw_vv.size * 100:.1f}%)")

    # -------------------------------------------------------------
    # Step 4: Generate Water Mask
    # -------------------------------------------------------------
    print("\n[Step 4] Computing SAR binary water mask...")
    threshold_db = DEFAULT_VV_WATER_THRESHOLD_DB
    print(f"  [+] Applying VV backscatter threshold: < {threshold_db} dB")

    water_mask = detect_water(vv_db, valid_mask, threshold_db=threshold_db)

    water_pixels = np.sum(water_mask == 1)
    land_pixels = np.sum(water_mask == 0)
    invalid_pixels = np.sum(water_mask == 255)

    pixel_area_km2 = (abs(transform.a) * abs(transform.e)) / 1e6
    water_area_km2 = water_pixels * pixel_area_km2
    land_area_km2 = land_pixels * pixel_area_km2

    print(f"  [+] Water / Inundated pixels: {water_pixels:,} ({water_area_km2:.2f} km2)")
    print(f"  [+] Land / Non-water pixels:   {land_pixels:,} ({land_area_km2:.2f} km2)")
    print(f"  [+] Invalid / Out-of-swath:    {invalid_pixels:,}")

    # Save output GeoTIFF
    out_dir = WORKSPACE_ROOT / "data" / "interim" / "water_masks"
    geotiff_path = out_dir / f"{meta['id']}_water_mask.tif"
    save_raster_geotiff(geotiff_path, water_mask, transform, crs)
    print(f"  [+] Exported Water Mask GeoTIFF to: {geotiff_path}")

    # Generate visual validation preview PNG
    preview_png_path = out_dir / f"{meta['id']}_preview.png"
    generate_preview(vv_db, water_mask, meta["id"], meta["datetime"], preview_png_path)
    print(f"  [+] Exported Verification Preview PNG to: {preview_png_path}")

    print("\n" + "=" * 70)
    print("Milestone A completed successfully!")
    print("=" * 70)


def generate_preview(vv_db: np.ndarray, water_mask: np.ndarray, scene_id: str, scene_date: str, out_path: Path):
    """Generate side-by-side plot of SAR backscatter (dB) and binary water mask."""
    fig, axes = plt.subplots(1, 2, figsize=(16, 8), dpi=150)

    # Panel 1: SAR VV Backscatter (dB)
    vv_display = np.ma.masked_invalid(vv_db)
    im1 = axes[0].imshow(vv_display, cmap="gray", vmin=-25, vmax=-5)
    axes[0].set_title(f"Sentinel-1 RTC VV Backscatter (dB)\n{scene_date[:10]}", fontsize=12, fontweight="bold")
    axes[0].axis("off")
    cbar1 = plt.colorbar(im1, ax=axes[0], fraction=0.046, pad=0.04)
    cbar1.set_label("Backscatter (dB)", fontsize=10)

    # Panel 2: Water Mask
    # Colormap: 0=lightgreen (land), 1=deep skyblue (water), 2=dark slate (nodata)
    cmap_mask = mcolors.ListedColormap(["#d1e7dd", "#0d6efd", "#212529"])
    norm = mcolors.BoundaryNorm([-0.5, 0.5, 1.5, 2.5], cmap_mask.N)

    # Remap 255 to 2 for discrete indexing in colormap
    disp_mask = np.zeros_like(water_mask, dtype=np.uint8)
    disp_mask[water_mask == 0] = 0
    disp_mask[water_mask == 1] = 1
    disp_mask[water_mask == 255] = 2

    im2 = axes[1].imshow(disp_mask, cmap=cmap_mask, norm=norm)
    axes[1].set_title("Detected Surface Water Mask\n(Blue: Water, Green: Land, Dark: Nodata)", fontsize=12, fontweight="bold")
    axes[1].axis("off")

    cbar2 = plt.colorbar(im2, ax=axes[1], ticks=[0, 1, 2], fraction=0.046, pad=0.04)
    cbar2.ax.set_yticklabels(["Land (0)", "Water (1)", "Nodata (255)"], fontsize=10)

    plt.suptitle(f"Barpeta (Brahmaputra Floodplain) — Scene: {scene_id[:35]}...", fontsize=14, y=0.98)
    plt.tight_layout()
    plt.savefig(out_path, bbox_inches="tight")
    plt.close()


if __name__ == "__main__":
    main()
