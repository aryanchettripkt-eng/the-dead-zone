export type BackendDistrictId = 'Wayanad' | 'Kodagu' | 'Barpeta';
export type LegacyZoneId = 'North' | 'West' | 'Central' | 'East' | 'South';
export type ZoneId = BackendDistrictId | LegacyZoneId;

export const FEATURED_DISTRICTS: BackendDistrictId[] = ['Wayanad', 'Kodagu', 'Barpeta'];

export interface StorySlide {
  id: string;
  title: string;
  subtitle: string;
  hazardType: string;
  riskSeverity: 'Critical' | 'High' | 'Moderate' | 'Monitored';
  image: string;
  description: string;
  telemetry: {
    label: string;
    value: string;
  }[];
  mitigation: string;
}

export interface ZoneStoryData {
  id: ZoneId;
  districtId: BackendDistrictId;
  label: string;
  regionName: string;
  districtName: string;
  stateName: string;
  adminId: number;
  lgdCode: number;
  dangerLevel: 'Critical' | 'High' | 'Moderate' | 'Monitored';
  touristAdvisory: string;
  coordinates: {
    display: {
      lat: string;
      lng: string;
    };
    raw: {
      lat: number;
      lng: number;
    };
  };
  mapCoords: {
    x: number; // percentage on SVG
    y: number;
  };
  previewImage: string;
  shortSummary: string;
  primaryHazard: string;
  popularTouristSpots: string[];
  slides: StorySlide[];
}

export const REGIONAL_STORIES: Record<ZoneId, ZoneStoryData> = {
  Wayanad: {
    id: 'Wayanad',
    districtId: 'Wayanad',
    label: 'Wayanad',
    regionName: 'Wayanad Western Ghats, Kerala',
    districtName: 'Wayanad',
    stateName: 'Kerala',
    adminId: 178,
    lgdCode: 555,
    dangerLevel: 'Critical',
    touristAdvisory:
      'CRITICAL RED ZONE: Meppadi, Chooralmala, and Mundakkai corridors have high landslide debris flow susceptibility. Non-essential trekking strictly restricted during monsoon spells.',
    popularTouristSpots: ['Chembra Peak', 'Banasura Sagar Dam', 'Meppadi Tea Highlands', 'Soochipara Waterfalls', 'Edakkal Caves'],
    coordinates: {
      display: {
        lat: 'N 11° 38\' 24.000"',
        lng: 'E 76° 07\' 48.000"',
      },
      raw: { lat: 11.64, lng: 76.13 },
    },
    mapCoords: { x: 31, y: 77 },
    previewImage: '/stories/south.jpg',
    primaryHazard: 'Landslide & Debris Avalanche',
    shortSummary:
      'Steep high-altitude orographic terrain with extreme rainfall vulnerability. Mundakkai and Chooralmala habitations feature 91% Permanent Red Zone (PRZ) overlap following catastrophic slope shear events.',
    slides: [
      {
        id: 'wayanad-1',
        title: 'Mundakkai & Chooralmala Red Zone',
        subtitle: 'Catastrophic 2024 Orographic Debris Flow',
        hazardType: 'Debris Avalanche',
        riskSeverity: 'Critical',
        image: '/stories/south.jpg',
        description:
          'Over 372 mm of rain in 24 hours saturated steep tea garden slopes. The resulting debris flow breached riparian corridors with 350+ fatalities, marking Chooralmala and Mundakkai as Immediate Tier Permanent Red Zones.',
        telemetry: [
          { label: 'PRZ Overlap', value: '91.0%' },
          { label: 'Priority Score', value: '0.9486 (Immediate)' },
          { label: 'Hazard Intensity', value: '0.88' },
          { label: '2024 Fatalities', value: '350 Victims' },
        ],
        mitigation:
          'Strict tourist access control along Chooralmala-Mundakkai bridge pass and real-time precipitation gauge triggers.',
      },
      {
        id: 'wayanad-2',
        title: 'Vythiri & Meppadi Ghat Corridors',
        subtitle: 'National Highway & Tourist Route Vulnerability',
        hazardType: 'Slope Shear & Rockfall',
        riskSeverity: 'High',
        image: '/stories/south.jpg',
        description:
          'Vythiri (pop 9,800) and Meppadi (pop 14,200) sit along critical scenic transit spines. High saturation triggers localized mudslips and rockfall that cut off key tourist road arteries.',
        telemetry: [
          { label: 'Vythiri PRZ', value: '48.0%' },
          { label: 'Meppadi PRZ', value: '35.0%' },
          { label: 'Access SoVI', value: '0.74 (Isolated)' },
          { label: 'Triage Tier', value: 'Short-term Relocation' },
        ],
        mitigation:
          'Geotechnical netting along highway escarpments and automated route closure alerts before peak cloudbursts.',
      },
      {
        id: 'wayanad-3',
        title: 'Kalpetta Valley Safe Baseline',
        subtitle: 'Secure Foothill Base for Travelers',
        hazardType: 'Mitigate In Situ',
        riskSeverity: 'Moderate',
        image: '/stories/south.jpg',
        description:
          'Kalpetta (pop 31,500) functions as the district administrative hub located outside the active debris runout cone, featuring hospital infrastructure and emergency NDRF response units.',
        telemetry: [
          { label: 'PRZ Overlap', value: '12.0%' },
          { label: 'Priority Score', value: '0.0139' },
          { label: 'Hospital Access', value: '< 10 mins' },
          { label: 'Safety Grade', value: 'Secure Base' },
        ],
        mitigation:
          'Designated official safe assembly and transit hub for travelers stranded during high-range alerts.',
      },
    ],
  },
  Kodagu: {
    id: 'Kodagu',
    districtId: 'Kodagu',
    label: 'Kodagu',
    regionName: 'Kodagu (Coorg) Highlands, Karnataka',
    districtName: 'Kodagu',
    stateName: 'Karnataka',
    adminId: 179,
    lgdCode: 540,
    dangerLevel: 'High',
    touristAdvisory:
      'HIGH SLOPE ALERT: Heavy monsoon downpours across Bhagamandala and Talakaveri cause severe soil liquefaction and road washouts. Check Karnataka SDMA travel bulletins before hill trekking.',
    popularTouristSpots: ['Abbey Falls', 'Raja’s Seat Madikeri', 'Talakaveri Sacred Source', 'Bhagamandala Triveni', 'Nagarhole Fringe'],
    coordinates: {
      display: {
        lat: 'N 12° 25\' 27.000"',
        lng: 'E 75° 44\' 18.000"',
      },
      raw: { lat: 12.424, lng: 75.738 },
    },
    mapCoords: { x: 30, y: 75 },
    previewImage: '/stories/west.jpg',
    primaryHazard: 'Steep Slope Soil Creep & Flash Flood',
    shortSummary:
      'Renowned coffee heartland prone to severe geotechnical slope failures during peak monsoon rainfall. Bhagamandala settlement is classified as Immediate Tier with 74% Permanent Red Zone exposure.',
    slides: [
      {
        id: 'kodagu-1',
        title: 'Bhagamandala Temple Basin Cutoff',
        subtitle: 'Submerged Confluence & Slope Slump Hazard',
        hazardType: 'Flash Flood & Landslip',
        riskSeverity: 'Critical',
        image: '/stories/west.jpg',
        description:
          'Bhagamandala (pop 4,100) at the Kaveri river confluence faces recurring monsoon inundation. Adjacent coffee hills exhibit active ground fissures and soil slip that isolated hundreds of pilgrim tourists in 2018.',
        telemetry: [
          { label: 'PRZ Overlap', value: '74.0%' },
          { label: 'Priority Score', value: '0.4858 (Immediate)' },
          { label: 'Hazard Intensity', value: '0.88' },
          { label: '2018 Disaster', value: '18 Fatal, 210 Damaged' },
        ],
        mitigation:
          'Borehole soil pore monitoring and flood rescue motorboats stationed permanently at Triveni Sangama.',
      },
      {
        id: 'kodagu-2',
        title: 'Madikeri Hill Crest & Escarpments',
        subtitle: 'Urban Tourism Ridge Stability',
        hazardType: 'Hillside Mass Wasting',
        riskSeverity: 'High',
        image: '/stories/west.jpg',
        description:
          'Madikeri (pop 33,400) is the iconic tourist gateway of Coorg. Perimeter hotel overlooks along steep eastern cliffs experience accelerated soil erosion and drainage overflow during July-August.',
        telemetry: [
          { label: 'PRZ Overlap', value: '28.0%' },
          { label: 'Priority Score', value: '0.0373' },
          { label: 'Structural Vulnerability', value: '0.68' },
          { label: 'Caseload Score', value: '1,245.8' },
        ],
        mitigation:
          'Ban on unauthorized ridge excavations and reinforced concrete retaining walls along scenic viewpoints.',
      },
      {
        id: 'kodagu-3',
        title: 'Somwarpet Rolling Terraces',
        subtitle: 'Controlled Tourism Buffer Zone',
        hazardType: 'Mitigate In Situ',
        riskSeverity: 'Moderate',
        image: '/stories/west.jpg',
        description:
          'Somwarpet (pop 11,200) sits upon milder plateau topography with lower slope instability, providing safe travel corridors and ecotourism agro-farms away from high-hazard scarps.',
        telemetry: [
          { label: 'PRZ Overlap', value: '22.0%' },
          { label: 'Priority Score', value: '0.0337' },
          { label: 'Slope Stability', value: 'High' },
          { label: 'Safety Grade', value: 'Cautious Transit' },
        ],
        mitigation:
          'Agricultural runoff management and bio-engineering with deep-root vetiver grasses along plantation borders.',
      },
    ],
  },
  Barpeta: {
    id: 'Barpeta',
    districtId: 'Barpeta',
    label: 'Barpeta',
    regionName: 'Barpeta Floodplains, Assam',
    districtName: 'Barpeta',
    stateName: 'Assam',
    adminId: 186,
    lgdCode: 303,
    dangerLevel: 'High',
    touristAdvisory:
      'ANNUAL MONSOON FLOOD WATCH: Brahmaputra braided channels overflow between June and September. Safari routes into Manas National Park and river ferry transit may face sudden suspension.',
    popularTouristSpots: ['Manas National Park UNESCO Gateway', 'Historic Barpeta Satra', 'Bell Metal Heritage Sarthebari', 'Brahmaputra River Chars'],
    coordinates: {
      display: {
        lat: 'N 26° 19\' 12.000"',
        lng: 'E 91° 00\' 36.000"',
      },
      raw: { lat: 26.32, lng: 91.01 },
    },
    mapCoords: { x: 74, y: 38 },
    previewImage: '/stories/east.jpg',
    primaryHazard: 'Brahmaputra Fluvial Inundation',
    shortSummary:
      'Lower Assam alluvial floodplains containing 14 monitored habitations and 629 relocation candidate sites. Annual monsoon water surges from the Himalayas inundate char islands and low-lying embankment corridors.',
    slides: [
      {
        id: 'barpeta-1',
        title: 'Manas Gateway & Embankment Breach',
        subtitle: 'Braided River Dynamics in Lowland Assam',
        hazardType: 'Riverine Inundation',
        riskSeverity: 'Critical',
        image: '/stories/east.jpg',
        description:
          'During peak monsoon release, the Brahmaputra and Beki rivers swell up to 8 km wide. Flood currents erode silt riverbanks, submerging char roads and isolating villages for weeks at a time.',
        telemetry: [
          { label: 'Surveyed Habitations', value: '14 Townships' },
          { label: 'Candidate Sites', value: '629 Screened' },
          { label: 'PRZ Built-up Exposure', value: '25.0%' },
          { label: 'Hazard Intensity', value: '0.45' },
        ],
        mitigation:
          'High-precision Sentinel-1 SAR flood extent mapping and real-time river level gauge alerts to prompt evacuation.',
      },
      {
        id: 'barpeta-2',
        title: 'Howly & Barpeta Road Commercial Hubs',
        subtitle: 'Key Transit Spines to National Highway 27',
        hazardType: 'Flash Waterlogging',
        riskSeverity: 'Moderate',
        image: '/stories/east.jpg',
        description:
          'Howly (pop 2,870) and Barpeta Road (pop 3,243) provide access to rail and national highway arteries. Plinth elevations remain moderately vulnerable during severe continuous cloudbursts.',
        telemetry: [
          { label: 'Barpeta Road Pop', value: '3,243' },
          { label: 'Howly Pop', value: '2,870' },
          { label: 'Highway Proximity', value: '< 4 km' },
          { label: 'Warning Lead Time', value: '48 Hours' },
        ],
        mitigation:
          'Elevated storm culverts and multi-purpose flood shelter centers built with solar microgrids.',
      },
      {
        id: 'barpeta-3',
        title: 'Barpeta High Ridge Relocation Buffer',
        subtitle: 'Safe High Grounds for Resilient Tourism',
        hazardType: 'Relocation Destination',
        riskSeverity: 'Monitored',
        image: '/stories/east.jpg',
        description:
          'Inland paleochannel levees situated 14 km away from the shifting Brahmaputra banks offer dry bedrock foundation, housing eco-tourism lodges and emergency supply reserves.',
        telemetry: [
          { label: 'Safe Ground Elevation', value: '+12 m above char' },
          { label: '70-Yr Breach Record', value: 'Zero Breaches' },
          { label: 'Park Access', value: '35 mins' },
          { label: 'Water Quality', value: 'Arsenic Safe' },
        ],
        mitigation:
          'Community-led flood preparedness squads and designated dry-zone tourist parking depots.',
      },
    ],
  },
  // Legacy aliases for backward compatibility
  South: null as unknown as ZoneStoryData,
  East: null as unknown as ZoneStoryData,
  West: null as unknown as ZoneStoryData,
  North: null as unknown as ZoneStoryData,
  Central: null as unknown as ZoneStoryData,
};

// Populate backward compatible aliases
REGIONAL_STORIES.South = REGIONAL_STORIES.Wayanad;
REGIONAL_STORIES.East = REGIONAL_STORIES.Barpeta;
REGIONAL_STORIES.West = REGIONAL_STORIES.Kodagu;
REGIONAL_STORIES.North = REGIONAL_STORIES.Wayanad;
REGIONAL_STORIES.Central = REGIONAL_STORIES.Kodagu;

export default REGIONAL_STORIES;
