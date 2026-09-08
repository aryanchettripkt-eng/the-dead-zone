"""Milestone B Runner: End-to-End Steps 5–7 for Barpeta, Assam.

Executes:
  - Step 5: Ingest JRC Global Surface Water & generate permanent water mask.
  - Step 6: Query 10 Sentinel-1 RTC scenes and build aligned inundation stack.
  - Step 7: Compute empirical Inundation Frequency F(x, y) = sum(W) / sum(V), export GeoTIFFs & preview plots.
"""

import sys
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
import rasterio

WORKSPACE_ROOT = Path(__file__).resolve().parents[5]

from pipeline.hazard.flood.aoi import get_barpeta_bbox_wgs84
from pipeline.hazard.flood.stac import query_sentinel1_rtc
from pipeline.hazard.flood.water_mask import save_raster_geotiff
from pipeline.hazard.flood.permanent_water import generate_permanent_water_mask
from pipeline.hazard.flood.cropland import generate_cropland_fraction
from pipeline.hazard.flood.frequency_stack import (
    create_master_grid,
    accumulate_inundation_stack,
    calculate_inundation_frequency,
)


def main():
    print("=" * 70)
    print("SETU-DRR: Flood Susceptibility Pipeline - Milestone B (Steps 5-7)")
    print("Pilot: Barpeta (Brahmaputra Floodplain, Assam)")
    print("=" * 70)

    bbox_wgs84 = get_barpeta_bbox_wgs84()
    master_crs = "EPSG:32645"  # UTM Zone 45N

    # -------------------------------------------------------------
    # Step 5: Master Grid & JRC Permanent Water Removal
    # -------------------------------------------------------------
    print("\n[Step 5] Initializing Master Grid & Ingesting JRC Global Surface Water...")
    master_transform, master_shape, bounds_proj = create_master_grid(
        bbox_wgs84=bbox_wgs84,
        target_crs=master_crs,
        resolution_m=10.0,
    )
    print(f"  [+] Master Grid Shape: {master_shape[0]} rows x {master_shape[1]} cols ({master_shape[0]*master_shape[1]:,} pixels)")
    print(f"  [+] Master CRS: {master_crs} | Pixel Resolution: 10.0m x 10.0m")

    print("  [+] Streaming JRC GSW v1.5 (1984-2024) occurrence layer from cloud...")
    permanent_water_mask, jrc_occurrence = generate_permanent_water_mask(
        reference_shape=master_shape,
        reference_transform=master_transform,
        reference_crs=master_crs,
        bbox_wgs84=bbox_wgs84,
        occurrence_threshold_pct=80.0,
    )
    perm_pixels = np.sum(permanent_water_mask)
    perm_area_km2 = (perm_pixels * 100.0) / 1e6
    print(f"  [+] Identified Permanent Water: {perm_pixels:,} pixels ({perm_area_km2:.2f} km2)")

    out_dir = WORKSPACE_ROOT / "data" / "interim" / "frequency"
    out_dir.mkdir(parents=True, exist_ok=True)
    save_raster_geotiff(
        out_dir / "barpeta_jrc_permanent_water.tif",
        permanent_water_mask.astype(np.uint8),
        master_transform,
        master_crs,
        nodata=255,
        dtype="uint8",
    )

    # -------------------------------------------------------------
    # Step 5.2: ESA WorldCover v200 Cropland Fraction Layer
    # -------------------------------------------------------------
    print("\n  [+] Ingesting ESA WorldCover v200 (10m) from Planetary Computer STAC...")
    cropland_fraction = generate_cropland_fraction(
        reference_shape=master_shape,
        reference_transform=master_transform,
        reference_crs=master_crs,
        bbox_wgs84=bbox_wgs84,
        year=2021,
    )
    mean_crop = float(np.nanmean(cropland_fraction))
    heavy_crop_pixels = int(np.sum(cropland_fraction > 0.5))
    heavy_crop_area_km2 = (heavy_crop_pixels * 100.0) / 1e6
    print(f"  [+] Cropland Fraction: mean = {mean_crop:.3f}, >50% cropland area = {heavy_crop_area_km2:.2f} km2 ({heavy_crop_pixels:,} pixels)")

    crop_tif_path = out_dir / "barpeta_cropland_fraction.tif"
    save_raster_geotiff(
        crop_tif_path,
        cropland_fraction,
        master_transform,
        master_crs,
        nodata=np.nan,
        dtype="float32",
    )
    print(f"  [+] Exported Cropland Fraction GeoTIFF to: {crop_tif_path}")

    # Also save to canonical interim path data/interim/flood/barpeta/cropland_fraction.tif
    flood_dir = WORKSPACE_ROOT / "data" / "interim" / "flood" / "barpeta"
    flood_dir.mkdir(parents=True, exist_ok=True)
    save_raster_geotiff(
        flood_dir / "cropland_fraction.tif",
        cropland_fraction,
        master_transform,
        master_crs,
        nodata=np.nan,
        dtype="float32",
    )

    # -------------------------------------------------------------
    # Step 6: Multi-Date Sentinel-1 Query & Inundation Stacking
    # -------------------------------------------------------------
    print("\n[Step 6] Querying Sentinel-1 RTC STAC catalog for multi-date time series...")
    # Query scenes covering 2020 monsoon (June-Oct) & post-monsoon/winter
    scenes = query_sentinel1_rtc(
        bbox=bbox_wgs84,
        datetime_range="2020-06-01/2020-12-31",
        limit=10,
    )
    print(f"  [+] Retrieved {len(scenes)} Sentinel-1 RTC scenes for stacking.")

    print("\n  [+] Accumulating temporal inundation stack...")
    water_counts, valid_counts, processed_metas = accumulate_inundation_stack(
        scenes=scenes,
        master_shape=master_shape,
        master_transform=master_transform,
        master_crs=master_crs,
        permanent_water_mask=permanent_water_mask,
        bbox_wgs84=bbox_wgs84,
        threshold_db=-16.0,
        verbose=True,
    )

    # -------------------------------------------------------------
    # Step 7: Calculate Inundation Frequency
    # -------------------------------------------------------------
    print("\n[Step 7] Computing empirical inundation frequency F(x, y)...")
    frequency, confidence_mask = calculate_inundation_frequency(
        water_counts,
        valid_counts,
        min_observations=1,
    )

    valid_cells = np.sum(confidence_mask)
    flooded_cells = np.sum((frequency > 0) & confidence_mask)
    mean_freq = np.nanmean(frequency)
    max_freq = np.nanmax(frequency)

    print(f"  [+] Valid observed cells: {valid_cells:,} / {frequency.size:,} ({valid_cells/frequency.size*100:.1f}%)")
    print(f"  [+] Flood-affected cells (F > 0): {flooded_cells:,} ({(flooded_cells*100.0)/1e6:.2f} km2)")
    print(f"  [+] Mean Inundation Frequency: {mean_freq:.4f}")
    print(f"  [+] Max Inundation Frequency:  {max_freq:.4f}")

    # Export GeoTIFFs
    freq_tif_path = out_dir / "barpeta_inundation_frequency.tif"
    save_raster_geotiff(freq_tif_path, frequency, master_transform, master_crs, nodata=np.nan, dtype="float32")
    print(f"  [+] Exported Inundation Frequency GeoTIFF to: {freq_tif_path}")

    obs_tif_path = out_dir / "barpeta_valid_observation_count.tif"
    save_raster_geotiff(obs_tif_path, valid_counts, master_transform, master_crs, nodata=0, dtype="uint16")
    print(f"  [+] Exported Valid Observations GeoTIFF to: {obs_tif_path}")

    water_tif_path = out_dir / "barpeta_water_detection_count.tif"
    save_raster_geotiff(water_tif_path, water_counts, master_transform, master_crs, nodata=0, dtype="uint16")
    print(f"  [+] Exported Flood Detection Count GeoTIFF to: {water_tif_path}")

    # Generate multi-panel preview visualization (6 panels)
    preview_path = out_dir / "barpeta_milestone_b_preview.png"
    generate_milestone_b_preview(
        jrc_occurrence=jrc_occurrence,
        permanent_mask=permanent_water_mask,
        cropland_fraction=cropland_fraction,
        valid_counts=valid_counts,
        water_counts=water_counts,
        frequency=frequency,
        num_scenes=len(scenes),
        out_path=preview_path,
    )
    print(f"  [+] Exported Milestone B Verification Preview PNG to: {preview_path}")

    print("\n" + "=" * 70)
    print("Milestone B completed successfully!")
    print("=" * 70)


def generate_milestone_b_preview(
    jrc_occurrence: np.ndarray,
    permanent_mask: np.ndarray,
    cropland_fraction: np.ndarray,
    valid_counts: np.ndarray,
    water_counts: np.ndarray,
    frequency: np.ndarray,
    num_scenes: int,
    out_path: Path,
):
    """Render a 6-panel visual summary of Milestone B results (including Step 5.2 cropland fraction)."""
    fig, axes = plt.subplots(2, 3, figsize=(24, 16), dpi=150)

    # Panel 1: JRC Global Surface Water Occurrence & Permanent Water
    im1 = axes[0, 0].imshow(jrc_occurrence, cmap="Blues", vmin=0, vmax=100)
    axes[0, 0].set_title("1. JRC Global Surface Water Occurrence (1984–2024)\n(>80% classified as Permanent Water)", fontsize=11, fontweight="bold")
    axes[0, 0].axis("off")
    cbar1 = plt.colorbar(im1, ax=axes[0, 0], fraction=0.046, pad=0.04)
    cbar1.set_label("Water Occurrence (%)", fontsize=10)

    # Panel 2: ESA WorldCover v200 Cropland Fraction (Step 5.2)
    crop_display = np.ma.masked_invalid(cropland_fraction)
    im2 = axes[0, 1].imshow(crop_display, cmap="YlGn", vmin=0.0, vmax=1.0)
    axes[0, 1].set_title("2. ESA WorldCover v200 Cropland Fraction (Step 5.2)\n(Resampled onto 10m SAR Grid)", fontsize=11, fontweight="bold")
    axes[0, 1].axis("off")
    cbar2 = plt.colorbar(im2, ax=axes[0, 1], fraction=0.046, pad=0.04)
    cbar2.set_label("Cropland Fraction [0.0 - 1.0]", fontsize=10)

    # Panel 3: Sentinel-1 Valid Observation Count
    im3 = axes[0, 2].imshow(valid_counts, cmap="viridis", vmin=0, vmax=num_scenes)
    axes[0, 2].set_title(f"3. Sentinel-1 Valid Observation Count\n(Total Scenes = {num_scenes})", fontsize=11, fontweight="bold")
    axes[0, 2].axis("off")
    cbar3 = plt.colorbar(im3, ax=axes[0, 2], fraction=0.046, pad=0.04)
    cbar3.set_label("Number of Valid Passes", fontsize=10)

    # Panel 4: Inundation / Flood Detection Count (Permanent Water Removed)
    im4 = axes[1, 0].imshow(water_counts, cmap="YlOrRd", vmin=0, vmax=max(1, np.max(water_counts)))
    axes[1, 0].set_title("4. Temporary Inundation Detection Count\n(Permanent Water Filtered Out)", fontsize=11, fontweight="bold")
    axes[1, 0].axis("off")
    cbar4 = plt.colorbar(im4, ax=axes[1, 0], fraction=0.046, pad=0.04)
    cbar4.set_label("Flood Detections Count", fontsize=10)

    # Panel 5: Inundation Frequency Surface F(x, y)
    freq_display = np.ma.masked_invalid(frequency)
    im5 = axes[1, 1].imshow(freq_display, cmap="magma", vmin=0.0, vmax=1.0)
    axes[1, 1].set_title("5. Empirical Inundation Frequency F(x, y)\nF = (Flood Detections) / (Valid Observations)", fontsize=11, fontweight="bold")
    axes[1, 1].axis("off")
    cbar5 = plt.colorbar(im5, ax=axes[1, 1], fraction=0.046, pad=0.04)
    cbar5.set_label("Inundation Frequency [0.0 - 1.0]", fontsize=10)

    # Panel 6: Flooded Cropland Flagging Analysis (F > 0 & Cropland Fraction > 0.5)
    flooded_cropland = np.zeros_like(cropland_fraction)
    flooded_cropland[(frequency > 0) & (cropland_fraction > 0.5)] = 1.0
    im6 = axes[1, 2].imshow(flooded_cropland, cmap="autumn", vmin=0, vmax=1)
    axes[1, 2].set_title("6. Flagged Flooded Cropland (F > 0 & Crop > 50%)\n(Qualified in Dossier, not hard masked)", fontsize=11, fontweight="bold")
    axes[1, 2].axis("off")
    cbar6 = plt.colorbar(im6, ax=axes[1, 2], fraction=0.046, pad=0.04)
    cbar6.set_label("Flagged Cropland (1 = Flagged)", fontsize=10)

    plt.suptitle("SETU-DRR Flood Susceptibility Pipeline — Milestone B (Barpeta Pilot)", fontsize=16, fontweight="bold", y=0.99)
    plt.tight_layout()
    plt.savefig(out_path, bbox_inches="tight")
    plt.close()


if __name__ == "__main__":
    main()
