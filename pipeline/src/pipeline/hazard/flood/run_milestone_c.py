"""Milestone C Runner: End-to-End Step 8 (HAND & Slope) for Barpeta, Assam.

Executes Step 8 of the SETU-DRR Flood Susceptibility Pipeline:
  - Ingests pre-computed ASF GLO-30 HAND (derived from Copernicus GLO-30 across continental basins).
  - Streams Copernicus DEM GLO-30 elevation surface.
  - Reprojects both onto the standard 10m UTM Zone 45N Master Grid.
  - Computes terrain slope in degrees.
  - Generates the FR-3.17 hard-zero exclusion mask (HAND > 30m OR slope > 15°).
  - Exports GeoTIFFs and verification 4-panel preview to data/interim/hand/.
"""

import sys
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
import rasterio

# Ensure workspace root and package folder are in sys.path
WORKSPACE_ROOT = Path(__file__).resolve().parents[5]
PACKAGE_DIR = Path(__file__).resolve().parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))
if str(PACKAGE_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGE_DIR))

try:
    from .aoi import get_barpeta_bbox_wgs84
    from .frequency_stack import create_master_grid
    from .water_mask import save_raster_geotiff
    from .hand_terrain import (
        stream_and_reproject_hand,
        stream_and_reproject_dem,
        compute_slope_degrees,
        compute_hard_zero_mask,
        DEFAULT_HARD_ZERO_HAND_THRESHOLD_M,
        DEFAULT_HARD_ZERO_SLOPE_THRESHOLD_DEG,
    )
except (ImportError, ValueError):
    from aoi import get_barpeta_bbox_wgs84
    from frequency_stack import create_master_grid
    from water_mask import save_raster_geotiff
    from hand_terrain import (
        stream_and_reproject_hand,
        stream_and_reproject_dem,
        compute_slope_degrees,
        compute_hard_zero_mask,
        DEFAULT_HARD_ZERO_HAND_THRESHOLD_M,
        DEFAULT_HARD_ZERO_SLOPE_THRESHOLD_DEG,
    )


def main():
    print("=" * 75)
    print("SETU-DRR: Flood Susceptibility Pipeline - Milestone C (Step 8)")
    print("Pilot: Barpeta (Brahmaputra Floodplain, Assam)")
    print("Task: Height Above Nearest Drainage (HAND) & Slope Terrain Derivatives")
    print("=" * 75)

    bbox_wgs84 = get_barpeta_bbox_wgs84()
    master_crs = "EPSG:32645"  # UTM Zone 45N

    # Output directory
    out_dir = WORKSPACE_ROOT / "data" / "interim" / "hand"
    out_dir.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------
    # 1. Master Grid Definition (10m UTM 45N)
    # -------------------------------------------------------------
    print("\n[1/5] Initializing Master Grid (10m UTM Zone 45N)...")
    master_transform, master_shape, bounds_proj = create_master_grid(
        bbox_wgs84=bbox_wgs84,
        target_crs=master_crs,
        resolution_m=10.0,
    )
    print(f"  [+] Master Grid Shape: {master_shape[0]:,} rows x {master_shape[1]:,} cols ({master_shape[0]*master_shape[1]:,} pixels)")
    print(f"  [+] Master CRS: {master_crs} | Pixel Resolution: 10.0m x 10.0m")

    # -------------------------------------------------------------
    # 2. Ingest & Reproject ASF GLO-30 HAND
    # -------------------------------------------------------------
    print("\n[2/5] Ingesting ASF GLO-30 HAND (AWS Open Data)...")
    hand_cache = out_dir / "barpeta_hand.tif"
    hand_m = stream_and_reproject_hand(
        master_shape=master_shape,
        master_transform=master_transform,
        master_crs=master_crs,
        bbox_wgs84=bbox_wgs84,
        cache_path=hand_cache,
    )

    valid_hand = np.isfinite(hand_m)
    print(f"  [+] Valid HAND pixels: {np.sum(valid_hand):,} ({np.mean(valid_hand)*100:.1f}%)")
    print(f"  [+] HAND range: min = {np.nanmin(hand_m):.2f}m, max = {np.nanmax(hand_m):.2f}m, mean = {np.nanmean(hand_m):.2f}m, median = {np.nanmedian(hand_m):.2f}m")

    # -------------------------------------------------------------
    # 3. Ingest & Reproject Copernicus DEM GLO-30 Elevation
    # -------------------------------------------------------------
    print("\n[3/5] Ingesting Copernicus DEM GLO-30 Elevation...")
    dem_cache = out_dir / "barpeta_dem_elevation.tif"
    dem_elevation_m = stream_and_reproject_dem(
        master_shape=master_shape,
        master_transform=master_transform,
        master_crs=master_crs,
        bbox_wgs84=bbox_wgs84,
        cache_path=dem_cache,
    )

    valid_dem = np.isfinite(dem_elevation_m)
    print(f"  [+] Valid DEM pixels: {np.sum(valid_dem):,} ({np.mean(valid_dem)*100:.1f}%)")
    print(f"  [+] Elevation range: min = {np.nanmin(dem_elevation_m):.1f}m, max = {np.nanmax(dem_elevation_m):.1f}m, mean = {np.nanmean(dem_elevation_m):.1f}m")

    # -------------------------------------------------------------
    # 4. Compute Terrain Slope & FR-3.17 Hard-Zero Mask
    # -------------------------------------------------------------
    print("\n[4/5] Computing Terrain Slope (degrees) and FR-3.17 Screening Mask...")
    slope_deg = compute_slope_degrees(dem_elevation_m, resolution_m=10.0)
    slope_tif_path = out_dir / "barpeta_slope.tif"
    save_raster_geotiff(slope_tif_path, slope_deg, master_transform, master_crs, nodata=np.nan, dtype="float32")
    print(f"  [+] Exported Slope GeoTIFF to: {slope_tif_path}")
    print(f"  [+] Slope range: min = {np.nanmin(slope_deg):.2f}°, max = {np.nanmax(slope_deg):.2f}°, mean = {np.nanmean(slope_deg):.2f}°, median = {np.nanmedian(slope_deg):.2f}°")

    hard_zero_mask, flood_eligible_mask = compute_hard_zero_mask(
        hand_m,
        slope_deg,
        max_hand_m=DEFAULT_HARD_ZERO_HAND_THRESHOLD_M,
        max_slope_deg=DEFAULT_HARD_ZERO_SLOPE_THRESHOLD_DEG,
    )

    # Export hard zero mask GeoTIFF (1=hard zero, 0=eligible, 255=nodata)
    mask_raster = np.full(master_shape, 255, dtype=np.uint8)
    valid_terrain = np.isfinite(hand_m) & np.isfinite(slope_deg)
    mask_raster[valid_terrain & flood_eligible_mask] = 0
    mask_raster[valid_terrain & hard_zero_mask] = 1
    mask_tif_path = out_dir / "barpeta_hard_zero_mask.tif"
    save_raster_geotiff(mask_tif_path, mask_raster, master_transform, master_crs, nodata=255, dtype="uint8")
    print(f"  [+] Exported Hard-Zero Mask GeoTIFF to: {mask_tif_path}")

    total_valid = np.sum(valid_terrain)
    hard_zero_count = np.sum(hard_zero_mask & valid_terrain)
    eligible_count = np.sum(flood_eligible_mask)

    hand_excl = np.sum((hand_m > DEFAULT_HARD_ZERO_HAND_THRESHOLD_M) & valid_terrain)
    slope_excl = np.sum((slope_deg > DEFAULT_HARD_ZERO_SLOPE_THRESHOLD_DEG) & valid_terrain)

    print("\n  --- FR-3.17 Screening Summary ---")
    print(f"  Total Valid Terrain Pixels:    {total_valid:,} ({(total_valid*100.0)/1e6:.2f} km2)")
    print(f"  Excluded by HAND > 30m:        {hand_excl:,} ({hand_excl/total_valid*100:.2f}%)")
    print(f"  Excluded by Slope > 15°:       {slope_excl:,} ({slope_excl/total_valid*100:.2f}%)")
    print(f"  Total Hard-Zero Excluded:      {hard_zero_count:,} ({hard_zero_count/total_valid*100:.2f}%)")
    print(f"  Flood-Eligible Domain:         {eligible_count:,} ({eligible_count/total_valid*100:.2f}%) [{(eligible_count*100.0)/1e6:.2f} km2]")

    # -------------------------------------------------------------
    # 5. Generate Multi-Panel Preview Visualization
    # -------------------------------------------------------------
    print("\n[5/5] Generating Milestone C Verification Preview PNG...")
    preview_path = out_dir / "barpeta_milestone_c_preview.png"
    generate_milestone_c_preview(
        dem_elevation=dem_elevation_m,
        slope=slope_deg,
        hand=hand_m,
        hard_zero_mask=hard_zero_mask,
        flood_eligible=flood_eligible_mask,
        out_path=preview_path,
    )
    print(f"  [+] Exported Milestone C Verification Preview to: {preview_path}")

    print("\n" + "=" * 75)
    print("Milestone C (Step 8: HAND & Slope) completed successfully!")
    print("=" * 75)


def generate_milestone_c_preview(
    dem_elevation: np.ndarray,
    slope: np.ndarray,
    hand: np.ndarray,
    hard_zero_mask: np.ndarray,
    flood_eligible: np.ndarray,
    out_path: Path,
):
    """Render a 4-panel visual validation summary of Milestone C outputs."""
    fig, axes = plt.subplots(2, 2, figsize=(18, 16), dpi=150)

    # Panel 1: Copernicus DEM GLO-30 Elevation
    dem_display = np.ma.masked_invalid(dem_elevation)
    im1 = axes[0, 0].imshow(dem_display, cmap="terrain", vmin=20, vmax=150)
    axes[0, 0].set_title("1. Copernicus DEM GLO-30 Elevation (m ASL)\n(Brahmaputra Floodplain & Valley Floor)", fontsize=11, fontweight="bold")
    axes[0, 0].axis("off")
    cbar1 = plt.colorbar(im1, ax=axes[0, 0], fraction=0.046, pad=0.04)
    cbar1.set_label("Elevation (m ASL)", fontsize=10)

    # Panel 2: Terrain Slope
    slope_display = np.ma.masked_invalid(slope)
    im2 = axes[0, 1].imshow(slope_display, cmap="inferno", vmin=0.0, vmax=20.0)
    axes[0, 1].set_title("2. Terrain Slope (Degrees)\n(Derived from DEM; >15° Excluded by FR-3.17)", fontsize=11, fontweight="bold")
    axes[0, 1].axis("off")
    cbar2 = plt.colorbar(im2, ax=axes[0, 1], fraction=0.046, pad=0.04)
    cbar2.set_label("Slope (Degrees)", fontsize=10)

    # Panel 3: Height Above Nearest Drainage (HAND)
    hand_display = np.ma.masked_invalid(hand)
    im3 = axes[1, 0].imshow(hand_display, cmap="Blues_r", vmin=0.0, vmax=40.0)
    axes[1, 0].set_title("3. Height Above Nearest Drainage (HAND, m)\n(Low values = Near river elevation; >30m Excluded)", fontsize=11, fontweight="bold")
    axes[1, 0].axis("off")
    cbar3 = plt.colorbar(im3, ax=axes[1, 0], fraction=0.046, pad=0.04)
    cbar3.set_label("HAND (m)", fontsize=10)

    # Panel 4: FR-3.17 Hard Zero Screening Mask
    # Display: 0 = Eligible (cyan/blue), 1 = Hard Zero Excluded (crimson red)
    status_display = np.zeros(hand.shape, dtype=np.float32)
    status_display[~np.isfinite(hand)] = np.nan
    status_display[flood_eligible] = 0.0
    status_display[hard_zero_mask & np.isfinite(hand)] = 1.0
    status_masked = np.ma.masked_invalid(status_display)

    cmap_status = mcolors.ListedColormap(["#2b83ba", "#d7191c"])
    bounds = [-0.5, 0.5, 1.5]
    norm_status = mcolors.BoundaryNorm(bounds, cmap_status.N)

    im4 = axes[1, 1].imshow(status_masked, cmap=cmap_status, norm=norm_status)
    axes[1, 1].set_title("4. FR-3.17 Flood Susceptibility Screening Mask\n(Blue: Flood-Eligible Domain | Red: Hard Zero Excluded)", fontsize=11, fontweight="bold")
    axes[1, 1].axis("off")
    cbar4 = plt.colorbar(im4, ax=axes[1, 1], fraction=0.046, pad=0.04, ticks=[0, 1])
    cbar4.ax.set_yticklabels(["Eligible (HAND≤30m & Slope≤15°)", "Hard Zero (HAND>30m | Slope>15°)"], fontsize=9)

    plt.suptitle("SETU-DRR Flood Susceptibility Pipeline — Milestone C (Step 8: HAND & Slope)", fontsize=15, fontweight="bold", y=0.99)
    plt.tight_layout()
    plt.savefig(out_path, bbox_inches="tight")
    plt.close()


if __name__ == "__main__":
    main()
