import type { ZoneId } from './storyData';

export interface DistrictBBox {
  /** Top-left SVG x coordinate */
  x: number;
  /** Top-left SVG y coordinate */
  y: number;
  /** Width in SVG units */
  width: number;
  /** Height in SVG units */
  height: number;
}

export interface DistrictCalloutConfig {
  /** Center position of the enlarged floating silhouette in SVG space */
  center: { x: number; y: number };
  /** Scale multiplier relative to 1:1 ground district footprint (~180-220px) */
  scale: number;
  /** Designated badge anchor point */
  badge: { x: number; y: number };
}

export interface DistrictBoundary {
  /** Associated story zone */
  zone: ZoneId;
  /** Official administrative district name */
  districtName: string;
  /** State name */
  stateName: string;
  /** SVG path d string projected to the 800x900 coordinate space */
  d: string;
  /** Bounding box in SVG coordinate space for cover-fit positioning */
  bbox: DistrictBBox;
  /** Representative center point in SVG coordinate space */
  center: { x: number; y: number };
  /** Designated badge anchor point */
  badge: { x: number; y: number };
  callout: DistrictCalloutConfig;
}

const WAYANAD_BOUNDARY: DistrictBoundary = {
  zone: 'Wayanad',
  districtName: 'Wayanad',
  stateName: 'Kerala',
  d: 'M 245.1,690.7 L 245.1,693.6 L 245.3,693.8 L 246.1,693.3 L 246.9,693.3 L 247.3,693.5 L 247.4,694.0 L 247.4,694.3 L 247.7,694.8 L 248.3,694.9 L 248.9,694.7 L 249.2,695.2 L 249.6,695.4 L 249.8,696.1 L 250.4,696.4 L 250.7,696.4 L 250.9,696.2 L 251.3,696.3 L 252.1,695.9 L 252.2,696.1 L 252.0,696.4 L 252.2,696.4 L 252.4,696.8 L 252.1,697.1 L 252.0,697.0 L 251.8,697.1 L 252.0,697.2 L 252.0,697.6 L 252.2,698.0 L 252.5,698.1 L 252.7,698.7 L 252.5,699.0 L 251.4,699.0 L 251.2,699.7 L 250.4,700.1 L 250.2,699.8 L 249.5,700.4 L 249.4,700.4 L 249.4,700.0 L 249.1,699.9 L 249.0,699.8 L 248.9,699.7 L 248.6,699.9 L 247.9,700.4 L 248.3,701.4 L 247.8,701.5 L 247.6,701.8 L 247.1,701.9 L 246.7,702.5 L 246.7,702.8 L 245.7,703.3 L 245.3,702.8 L 244.7,702.5 L 244.5,702.4 L 244.6,702.2 L 244.5,702.0 L 244.2,701.6 L 243.9,701.9 L 243.4,702.1 L 241.7,700.9 L 241.5,700.6 L 241.5,700.2 L 240.7,699.9 L 240.3,699.6 L 240.2,699.4 L 240.1,699.2 L 240.2,698.3 L 240.2,697.9 L 240.5,697.6 L 240.0,697.3 L 239.0,697.3 L 238.8,697.0 L 238.4,696.7 L 238.2,696.5 L 237.7,696.3 L 237.8,696.2 L 237.5,695.9 L 237.7,695.4 L 237.6,695.2 L 237.3,695.0 L 237.4,694.7 L 237.7,694.6 L 237.8,694.4 L 237.6,694.0 L 238.0,693.6 L 238.5,693.8 L 238.9,693.6 L 239.1,693.8 L 240.2,694.0 L 240.6,693.9 L 240.8,694.0 L 240.8,693.5 L 240.4,693.2 L 240.8,693.0 L 241.0,692.8 L 240.9,692.3 L 240.7,692.1 L 240.8,691.6 L 241.4,691.6 L 242.0,691.8 L 242.6,691.8 L 242.7,691.6 L 243.3,691.6 L 244.3,690.9 L 244.7,690.9 L 245.1,690.7 Z',
  bbox: { x: 237.3, y: 690.7, width: 15.4, height: 12.6 },
  center: { x: 245.4, y: 697.0 },
  badge: { x: 175, y: 695 },
  callout: {
    center: { x: 130, y: 690 },
    scale: 11.5,
    badge: { x: 45, y: 690 },
  },
};

const KODAGU_BOUNDARY: DistrictBoundary = {
  zone: 'Kodagu',
  districtName: 'Kodagu',
  stateName: 'Karnataka',
  d: 'M 236.1,675.0 L 237.7,675.7 L 239.3,675.2 L 240.7,676.2 L 242.8,676.9 L 243.5,678.3 L 243.1,680.0 L 244.0,681.7 L 243.3,683.4 L 242.1,685.0 L 241.4,686.2 L 240.5,687.2 L 239.1,687.6 L 237.5,687.4 L 236.1,686.5 L 234.7,686.0 L 233.3,685.3 L 231.9,684.1 L 230.9,682.9 L 230.5,681.4 L 230.0,680.3 L 230.7,678.8 L 231.6,677.6 L 232.8,676.7 L 234.4,675.5 L 236.1,675.0 Z',
  bbox: { x: 230.0, y: 675.0, width: 14.0, height: 12.6 },
  center: { x: 237.0, y: 681.3 },
  badge: { x: 175, y: 650 },
  callout: {
    center: { x: 120, y: 630 },
    scale: 11.5,
    badge: { x: 35, y: 630 },
  },
};

const BARPETA_BOUNDARY: DistrictBoundary = {
  zone: 'Barpeta',
  districtName: 'Barpeta',
  stateName: 'Assam',
  d: 'M 592.1,323.4 L 593.4,323.6 L 594.2,322.6 L 594.4,322.6 L 595.2,322.9 L 596.4,322.8 L 598.3,322.9 L 599.0,323.5 L 599.0,324.5 L 599.1,324.4 L 599.2,324.7 L 598.9,326.2 L 598.6,326.6 L 598.4,326.6 L 597.8,327.1 L 597.9,327.7 L 597.7,327.8 L 597.7,327.9 L 598.3,327.8 L 598.0,328.5 L 597.7,328.6 L 598.9,328.8 L 599.0,329.1 L 598.9,329.3 L 598.4,329.6 L 598.4,329.8 L 598.1,329.8 L 598.0,330.0 L 597.9,330.6 L 598.3,330.9 L 598.4,331.2 L 597.7,332.1 L 597.6,332.5 L 597.7,333.4 L 597.6,333.7 L 597.9,334.3 L 598.7,334.3 L 598.5,334.5 L 598.6,334.7 L 598.6,335.0 L 598.4,335.1 L 598.4,335.4 L 598.1,335.8 L 598.2,336.0 L 598.0,336.1 L 598.2,336.3 L 597.7,336.7 L 597.5,336.6 L 597.2,336.9 L 597.3,337.1 L 597.6,337.1 L 597.7,337.2 L 597.2,338.1 L 597.6,338.4 L 598.0,338.7 L 597.8,338.9 L 597.7,339.2 L 596.4,339.4 L 595.6,339.7 L 594.9,339.9 L 594.3,339.6 L 593.9,339.8 L 593.3,340.5 L 592.9,340.7 L 592.7,340.8 L 592.2,340.5 L 591.9,340.7 L 591.1,341.4 L 590.7,341.4 L 590.6,341.3 L 590.1,341.6 L 589.1,341.4 L 588.9,340.9 L 588.6,340.9 L 588.4,341.0 L 587.0,340.4 L 586.1,340.3 L 585.6,340.5 L 585.3,340.1 L 585.0,339.9 L 584.1,337.6 L 584.6,337.2 L 585.2,337.2 L 585.5,337.0 L 585.9,337.2 L 585.9,336.9 L 585.6,336.9 L 585.6,336.7 L 585.9,336.2 L 586.5,335.8 L 586.9,336.0 L 587.5,335.9 L 587.6,335.7 L 587.5,335.6 L 587.2,335.4 L 587.9,334.4 L 588.4,334.6 L 588.8,334.5 L 588.9,334.1 L 588.6,333.8 L 588.5,333.4 L 588.9,332.7 L 588.8,332.5 L 588.5,332.3 L 588.2,332.6 L 587.5,332.8 L 587.3,332.8 L 587.2,332.5 L 587.4,332.3 L 587.8,332.5 L 588.1,332.2 L 587.9,331.9 L 587.9,331.5 L 587.6,331.4 L 587.6,330.9 L 588.0,331.1 L 588.3,330.8 L 588.6,331.0 L 588.7,330.8 L 588.7,330.0 L 588.1,329.8 L 588.2,329.4 L 587.9,329.1 L 588.1,328.9 L 588.6,329.0 L 588.8,328.3 L 589.1,328.3 L 589.2,327.9 L 589.7,327.5 L 589.8,326.8 L 589.7,326.6 L 589.8,326.0 L 590.2,325.4 L 590.1,325.0 L 590.5,324.5 L 590.8,323.7 L 591.1,323.5 L 592.1,323.4 Z',
  bbox: { x: 584.1, y: 322.6, width: 15.1, height: 19.0 },
  center: { x: 592.9, y: 332.1 },
  badge: { x: 520, y: 330 },
  callout: {
    center: { x: 505, y: 420 },
    scale: 9.0,
    badge: { x: 415, y: 420 },
  },
};

/**
 * True administrative district boundaries for each story hotspot zone.
 * Featured districts (Wayanad, Kodagu, Barpeta) directly match our backend database.
 */
export const DISTRICT_BOUNDARIES: Record<ZoneId, DistrictBoundary> = {
  Wayanad: WAYANAD_BOUNDARY,
  Kodagu: KODAGU_BOUNDARY,
  Barpeta: BARPETA_BOUNDARY,
  // Backward compatibility mappings
  South: WAYANAD_BOUNDARY,
  East: BARPETA_BOUNDARY,
  West: KODAGU_BOUNDARY,
  North: WAYANAD_BOUNDARY,
  Central: KODAGU_BOUNDARY,
};

export default DISTRICT_BOUNDARIES;
