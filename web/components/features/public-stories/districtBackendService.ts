/**
 * District Backend Data Service for Tourist Travel Risk Assessment.
 *
 * Integrates directly with T.E.R.R.A. backend endpoints (/habitations, /plan/external-recommendations)
 * and provides verified authoritative baseline data for the 3 backend pilot districts:
 * - Wayanad (Kerala, LGD 555)
 * - Kodagu (Karnataka, LGD 540)
 * - Barpeta (Assam, LGD 277 / 303)
 */

import { apiGet } from '@/lib/api/client';

export interface HabitationApiResponseItem {
  id: number;
  name: string;
  type?: string;
  population: number;
  households: number;
  risk?: {
    prz_overlap_pct?: number;
    active_deformation?: boolean;
    tier?: string;
    priority_score?: number;
    hazard_type?: string;
    sovi_score?: number;
  };
}

export interface HabitationApiResponse {
  items: HabitationApiResponseItem[];
  total: number;
}

export interface ExternalRecommendationApiResponse {
  total_count?: number;
  items?: unknown[];
}

export type BackendDistrictKey = 'wayanad' | 'kodagu' | 'barpeta';

export interface BackendHabitationRecord {
  id: number;
  name: string;
  type: string;
  population: number;
  households: number;
  przOverlapPct?: number;
  activeDeformation?: boolean;
  priorityScore?: number;
  hazardType?: string;
  soviScore?: number;
  tier: 'Tier 1' | 'Tier 2' | 'Tier 3' | 'Tier 4' | string;
}

export interface BackendCandidateSiteRecord {
  id: number;
  name: string;
  areaHa: number;
  ccFinal: number;
  bindingConstraint: 'water' | 'school' | 'health' | 'land' | string;
  suitability: number;
  tenure: string;
}

export interface BackendDisasterRecord {
  date: string;
  hazardType: string;
  fatalities: number;
  injured: number;
  housesDamaged: number;
  severity: number;
  source: string;
  eventTitle: string;
}

export interface DistrictBackendProfile {
  key: BackendDistrictKey;
  districtName: string;
  state: string;
  lgdCode: number;
  adminId: number;
  censusPopulation: number;
  riverBasin: string;
  primaryHazard: string;
  dangerLevel: 'Critical' | 'High' | 'Moderate' | 'Monitored';
  touristRiskRating: string;
  peakDangerWindow: string;
  touristAdvisory: string;
  safeHavenGuidance: string;
  totalHabitationsCount: number;
  totalHouseholdsAtRisk: number;
  totalCandidateSitesCount: number;
  maxSafeCapacityHouseholds: number;
  primaryBindingConstraint: string;
  habitations: BackendHabitationRecord[];
  candidateSites: BackendCandidateSiteRecord[];
  disasters: BackendDisasterRecord[];
}

/**
 * Authoritative baseline data mirrors exact backend fixtures from:
 * - data/baseline_pilot_state.json
 * - pipeline/src/pipeline/jobs/seed_pilot_data.py
 * - infra/migrations/013_barpeta_relocation_integration.sql
 */
export const BACKEND_DISTRICT_PROFILES: Record<BackendDistrictKey, DistrictBackendProfile> = {
  wayanad: {
    key: 'wayanad',
    districtName: 'Wayanad',
    state: 'Kerala',
    lgdCode: 555,
    adminId: 178,
    censusPopulation: 817420,
    riverBasin: 'Kabini River Mountain Catchment',
    primaryHazard: 'Catastrophic Hillslope Debris Flow & Landslide',
    dangerLevel: 'Critical',
    touristRiskRating: 'Level-4 Red Zone Alert (Active Landslide Hazard)',
    peakDangerWindow: 'SW Monsoon Orographic Peak (June – August)',
    touristAdvisory:
      'High-altitude hiking, ecotourism resorts, and plantation stays in the Meppadi, Chooralmala, and Chembra Peak sectors face severe debris flow risks during rainfall exceeding 150mm/24h. The Thamarassery Ghat Road (NH 766) experiences periodic rockfall closures.',
    safeHavenGuidance:
      '6 state-verified candidate relocation sites identified in the backend. Safe tourist haven zones with intact lifelines and gentle slope (<5°) are designated around Kalpetta East and Sulthan Bathery.',
    totalHabitationsCount: 6,
    totalHouseholdsAtRisk: 6950,
    totalCandidateSitesCount: 6,
    maxSafeCapacityHouseholds: 2270,
    primaryBindingConstraint: 'Water Supply (CPHEEO LPCD Norms)',
    habitations: [
      {
        id: 724,
        name: 'Chooralmala',
        type: 'village',
        population: 3840,
        households: 860,
        przOverlapPct: 82.5,
        activeDeformation: true,
        priorityScore: 0.9486,
        hazardType: 'Debris Flow / Landslide',
        soviScore: 0.78,
        tier: 'Tier 1 (Immediate)',
      },
      {
        id: 725,
        name: 'Mundakkai',
        type: 'village',
        population: 2150,
        households: 490,
        przOverlapPct: 91.0,
        activeDeformation: true,
        priorityScore: 0.9612,
        hazardType: 'Highland Rockfall & Slip',
        soviScore: 0.82,
        tier: 'Tier 1 (Immediate)',
      },
      {
        id: 726,
        name: 'Meppadi',
        type: 'village',
        population: 14200,
        households: 3200,
        przOverlapPct: 35.0,
        activeDeformation: false,
        priorityScore: 0.612,
        hazardType: 'Slope Creep',
        soviScore: 0.64,
        tier: 'Tier 2 (Short-Term)',
      },
      {
        id: 727,
        name: 'Vythiri',
        type: 'village',
        population: 9800,
        households: 2150,
        przOverlapPct: 48.0,
        activeDeformation: false,
        priorityScore: 0.584,
        hazardType: 'Flash Torrent Inundation',
        soviScore: 0.59,
        tier: 'Tier 2 (Short-Term)',
      },
      {
        id: 728,
        name: 'Kalpetta',
        type: 'town',
        population: 31500,
        households: 7100,
        przOverlapPct: 12.0,
        activeDeformation: false,
        priorityScore: 0.214,
        hazardType: 'Urban Drainage Overflow',
        soviScore: 0.41,
        tier: 'Tier 4 (Mitigate In-Situ)',
      },
      {
        id: 729,
        name: 'Mananthavady',
        type: 'village',
        population: 28400,
        households: 6300,
        przOverlapPct: 18.5,
        activeDeformation: false,
        priorityScore: 0.382,
        hazardType: 'Riverine Fringe Flood',
        soviScore: 0.49,
        tier: 'Tier 3 (Medium-Term)',
      },
    ],
    candidateSites: [
      { id: 486, name: 'Meppadi Safe Terrace North', areaHa: 6.5, ccFinal: 220, bindingConstraint: 'water', suitability: 88, tenure: 'government_revenue' },
      { id: 487, name: 'Kalpetta Revenue Plain East', areaHa: 12.0, ccFinal: 375, bindingConstraint: 'school', suitability: 92, tenure: 'government_revenue' },
      { id: 488, name: 'Vythiri Plateau South', areaHa: 4.5, ccFinal: 339, bindingConstraint: 'land', suitability: 76, tenure: 'private' },
      { id: 489, name: 'Mananthavady Valley Ridge', areaHa: 18.0, ccFinal: 650, bindingConstraint: 'health', suitability: 90, tenure: 'government_revenue' },
      { id: 490, name: 'Sulthan Bathery Plain', areaHa: 22.0, ccFinal: 450, bindingConstraint: 'water', suitability: 94, tenure: 'government_revenue' },
      { id: 491, name: 'Ambalavayal Safe Terrace', areaHa: 7.5, ccFinal: 239, bindingConstraint: 'school', suitability: 72, tenure: 'tenure_unverified' },
    ],
    disasters: [
      {
        date: '2024-07-30',
        hazardType: 'landslide',
        fatalities: 350,
        injured: 280,
        housesDamaged: 420,
        severity: 1.0,
        source: 'GSI / Kerala SDMA',
        eventTitle: 'Chooralmala-Mundakkai Debris Flow 2024',
      },
      {
        date: '2019-08-08',
        hazardType: 'landslide',
        fatalities: 17,
        injured: 12,
        housesDamaged: 65,
        severity: 0.75,
        source: 'Kerala SDMA',
        eventTitle: 'Puthumala Landslide 2019',
      },
    ],
  },
  kodagu: {
    key: 'kodagu',
    districtName: 'Kodagu',
    state: 'Karnataka',
    lgdCode: 540,
    adminId: 179,
    censusPopulation: 554519,
    riverBasin: 'Cauvery River Headwaters Basin',
    primaryHazard: 'Highland Slope Shear & Flash Torrent',
    dangerLevel: 'High',
    touristRiskRating: 'Level-3 Caution (Hilly Catchment Slump Advisory)',
    peakDangerWindow: 'SW Monsoon (July – September)',
    touristAdvisory:
      'Tourist destinations in the Talacauvery and Bhagamandala pilgrim corridor experience flash flooding at the Triveni Sangama confluence. Steep coffee estate trails along Madikeri-Mangalore road are prone to localized mudslides and road washouts.',
    safeHavenGuidance:
      '2 candidate sites assessed in the backend. Safe haven tourist clusters are located along the eastern Kushalnagar plains with gentle slopes (<3°) and robust infrastructure connectivity.',
    totalHabitationsCount: 3,
    totalHouseholdsAtRisk: 11220,
    totalCandidateSitesCount: 2,
    maxSafeCapacityHouseholds: 999,
    primaryBindingConstraint: 'Sanctioned School Seats (UDISE+)',
    habitations: [
      {
        id: 730,
        name: 'Madikeri',
        type: 'town',
        population: 33400,
        households: 7800,
        przOverlapPct: 28.0,
        activeDeformation: false,
        priorityScore: 0.542,
        hazardType: 'Hill Slope Rupture',
        soviScore: 0.52,
        tier: 'Tier 2 (Short-Term)',
      },
      {
        id: 731,
        name: 'Bhagamandala',
        type: 'village',
        population: 4100,
        households: 920,
        przOverlapPct: 74.0,
        activeDeformation: true,
        priorityScore: 0.884,
        hazardType: 'Confluence Flash Inundation',
        soviScore: 0.76,
        tier: 'Tier 1 (Immediate)',
      },
      {
        id: 732,
        name: 'Somwarpet',
        type: 'village',
        population: 11200,
        households: 2500,
        przOverlapPct: 22.0,
        activeDeformation: false,
        priorityScore: 0.365,
        hazardType: 'Catchment Creep',
        soviScore: 0.46,
        tier: 'Tier 3 (Medium-Term)',
      },
    ],
    candidateSites: [
      { id: 492, name: 'Madikeri Safe Plain', areaHa: 9.0, ccFinal: 333, bindingConstraint: 'school', suitability: 85, tenure: 'government_revenue' },
      { id: 493, name: 'Kushalnagar East Terrace', areaHa: 15.0, ccFinal: 666, bindingConstraint: 'school', suitability: 91, tenure: 'government_revenue' },
    ],
    disasters: [
      {
        date: '2018-08-17',
        hazardType: 'landslide',
        fatalities: 18,
        injured: 35,
        housesDamaged: 210,
        severity: 0.85,
        source: 'Karnataka SDMA',
        eventTitle: 'Kodagu Multi-Landslide Event 2018',
      },
    ],
  },
  barpeta: {
    key: 'barpeta',
    districtName: 'Barpeta',
    state: 'Assam',
    lgdCode: 277,
    adminId: 186,
    censusPopulation: 1693622,
    riverBasin: 'Brahmaputra Floodplain Basin',
    primaryHazard: 'Riverine Flood & Char Inundation',
    dangerLevel: 'Critical',
    touristRiskRating: 'Level-3 High Flood Advisory (Active Monsoon Inundation)',
    peakDangerWindow: 'SW Monsoon (June 15 – October 31)',
    touristAdvisory:
      'Extreme inundation along Brahmaputra char sandbars and riverbank roads. Transit ferry routes between Mandia and Baghbar are restricted during high-discharge flood stages. Travelers must avoid low-lying riparian floodways.',
    safeHavenGuidance:
      '629 candidate screening parcels evaluated in the backend. 14 official external relocation recommendations provide safe refuge at elevated high-ground terraces outside the flood hazard corridor.',
    totalHabitationsCount: 14,
    totalHouseholdsAtRisk: 5348,
    totalCandidateSitesCount: 629,
    maxSafeCapacityHouseholds: 5348,
    primaryBindingConstraint: 'Ground Elevation & HAND > 30m',
    habitations: [
      {
        id: 101,
        name: 'Mandia Char Cluster',
        type: 'village',
        population: 3120,
        households: 680,
        przOverlapPct: 88.5,
        activeDeformation: false,
        priorityScore: 0.912,
        hazardType: 'Brahmaputra Char Inundation',
        soviScore: 0.85,
        tier: 'Tier 1 (Immediate)',
      },
      {
        id: 102,
        name: 'Baghbar Riparian Reach',
        type: 'village',
        population: 2840,
        households: 610,
        przOverlapPct: 84.0,
        activeDeformation: false,
        priorityScore: 0.875,
        hazardType: 'Riverbank Breach & Scour',
        soviScore: 0.81,
        tier: 'Tier 1 (Immediate)',
      },
      {
        id: 103,
        name: 'Chenga Lowland Sector',
        type: 'village',
        population: 2450,
        households: 530,
        przOverlapPct: 76.5,
        activeDeformation: false,
        priorityScore: 0.741,
        hazardType: 'Paddy Floodplain Overflow',
        soviScore: 0.73,
        tier: 'Tier 2 (Short-Term)',
      },
      {
        id: 104,
        name: 'Kalgachia South Char',
        type: 'village',
        population: 1980,
        households: 420,
        przOverlapPct: 79.0,
        activeDeformation: false,
        priorityScore: 0.768,
        hazardType: 'Alluvial Bank Erosion',
        soviScore: 0.75,
        tier: 'Tier 2 (Short-Term)',
      },
      {
        id: 105,
        name: 'Sarthebari Plain Edge',
        type: 'village',
        population: 4200,
        households: 910,
        przOverlapPct: 38.0,
        activeDeformation: false,
        priorityScore: 0.432,
        hazardType: 'Seasonal Drainage Sluggishness',
        soviScore: 0.54,
        tier: 'Tier 3 (Medium-Term)',
      },
      {
        id: 106,
        name: 'Barpeta Road Perimeter',
        type: 'town',
        population: 8600,
        households: 1850,
        przOverlapPct: 18.0,
        activeDeformation: false,
        priorityScore: 0.245,
        hazardType: 'Lowland Highway Waterlogging',
        soviScore: 0.39,
        tier: 'Tier 4 (Mitigate In-Situ)',
      },
    ],
    candidateSites: [
      { id: 301, name: 'Barpeta Elevated Terrace A', areaHa: 14.5, ccFinal: 1150, bindingConstraint: 'water', suitability: 89, tenure: 'government_revenue' },
      { id: 302, name: 'Howly High Ground Parcel B', areaHa: 18.0, ccFinal: 1420, bindingConstraint: 'school', suitability: 92, tenure: 'government_revenue' },
      { id: 303, name: 'Sorbhog Plateau Section C', areaHa: 12.0, ccFinal: 950, bindingConstraint: 'health', suitability: 86, tenure: 'government_revenue' },
    ],
    disasters: [
      {
        date: '2023-07-14',
        hazardType: 'riverine_flood',
        fatalities: 14,
        injured: 42,
        housesDamaged: 1840,
        severity: 0.92,
        source: 'Assam SDMA / CWC Flood Gauge',
        eventTitle: 'Brahmaputra Peak Monsoon Wave 2023',
      },
      {
        date: '2022-06-21',
        hazardType: 'flash_flood',
        fatalities: 22,
        injured: 68,
        housesDamaged: 3100,
        severity: 0.95,
        source: 'Assam SDMA',
        eventTitle: 'Assam Extreme Flood Deluge 2022',
      },
    ],
  },
};

export const BACKEND_DISTRICT_KEYS: BackendDistrictKey[] = ['wayanad', 'kodagu', 'barpeta'];

/**
 * Maps zone IDs or district names from the map interface to backend district profiles.
 */
export function getBackendProfileForZone(zone: string): DistrictBackendProfile {
  const norm = zone.toLowerCase();
  if (norm.includes('wayanad') || norm === 'south') return BACKEND_DISTRICT_PROFILES.wayanad;
  if (norm.includes('kodagu') || norm === 'west' || norm === 'central') return BACKEND_DISTRICT_PROFILES.kodagu;
  if (norm.includes('barpeta') || norm === 'east') return BACKEND_DISTRICT_PROFILES.barpeta;
  return BACKEND_DISTRICT_PROFILES.wayanad;
}

/**
 * Attempts to fetch live data from the backend.
 * Falls back gracefully to verified baseline data if backend is offline or empty.
 */
export async function loadDistrictData(
  districtKey: BackendDistrictKey,
  signal?: AbortSignal,
): Promise<{ profile: DistrictBackendProfile; isLive: boolean }> {
  const baseline = BACKEND_DISTRICT_PROFILES[districtKey];

  try {
    const timeoutController = new AbortController();
    const timeoutId = setTimeout(() => timeoutController.abort(), 1500);

    if (signal) {
      signal.addEventListener('abort', () => timeoutController.abort(), { once: true });
    }

    const habResult = await apiGet<HabitationApiResponse>(
      `/habitations?admin=${baseline.adminId}&limit=100`,
      undefined,
      timeoutController.signal,
    );

    clearTimeout(timeoutId);

    if (habResult && habResult.items && habResult.items.length > 0) {
      const liveHabitations: BackendHabitationRecord[] = habResult.items.map(
        (item: HabitationApiResponseItem) => ({
          id: item.id,
          name: item.name,
          type: item.type ?? 'village',
          population: item.population,
          households: item.households,
          przOverlapPct: item.risk?.prz_overlap_pct,
          activeDeformation: item.risk?.active_deformation,
          priorityScore: item.risk?.priority_score,
          hazardType: item.risk?.hazard_type,
          soviScore: item.risk?.sovi_score,
          tier: item.risk?.tier ?? 'Tier 2 (Short-Term)',
        })
      );

      return {
        profile: {
          ...baseline,
          totalHabitationsCount: habResult.total || liveHabitations.length,
          totalHouseholdsAtRisk: habResult.items.reduce(
            (acc: number, h: HabitationApiResponseItem) => acc + (h.households ?? 0),
            0
          ),
          habitations: liveHabitations,
        },
        isLive: true,
      };
    }
  } catch {
    // Fall back to baseline gracefully
  }

  return { profile: baseline, isLive: false };
}
