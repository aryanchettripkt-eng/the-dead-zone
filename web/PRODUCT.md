# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Primary Audience: Disaster Management Planners & Government Officials**
  - National Disaster Response Force (NDRF), State Disaster Management Authorities (SDMA), and District Collectors/Administrators.
  - Job: Identify and monitor Permanent Red Zones (PRZ), manage the prioritized habitations triage queue (Immediate, Short-term, Mitigate in situ), screen and assess candidate relocation sites against carrying capacity norms, and run optimal relocation allocation models.
- **Secondary Audience: Public Travelers & Tourists**
  - Trekkers, tourists, and visitors traveling through volatile geohazard terrain corridors (e.g. Wayanad, Kodagu, Barpeta).
  - Job: Assess geotechnical landslide, flash flood, and terrain danger ratings before planning visits, review historical disaster records, and receive actionable travel advisories.

## Product Purpose

SETU-DRR (Hazard Red Zone & Relocation Decision Support Platform) bridges frontline climate geohazard data with scientifically backed relocation and in-situ mitigation planning. It eliminates guesswork and political inertia in disaster risk reduction by providing cell-level risk dossiers, rigorous carrying capacity assessments, and transparent decision-support tools for both government decision-makers and the traveling public.

## Positioning

Unlike conventional disaster mapping dashboards that merely overlay passive satellite rasters, SETU-DRR combines high-resolution InSAR/SAR interferometry with localized Social Vulnerability Indices (SoVI), multi-hazard index (MHI) threshold crossing models, and an algorithmic carrying capacity optimization solver that directly allocates endangered populations to safe, viable relocation destinations with infrastructure binding constraint calculations.

## Operating Context

- **Government Operations**: Emergency operations centers, district collectorate disaster response reviews, urban and rural planning boards, post-disaster rehabilitation meetings.
- **Field & Public Intelligence**: Travelers inspecting route safety before entering mountain passes or riverine floodplains, checking live alerts and past disaster footprints.

## Capabilities and Constraints

- **Multi-Hazard Geospatial Grid**: H3 hexagonal grid resolution (res-8 pilot, res-6 overview) tracking multi-hazard intensity, landslide susceptibility, and riverine flooding.
- **Authoritative Pilot Districts**: Authoritative backend data and habitations for Wayanad (Kerala), Kodagu (Karnataka), and Barpeta (Assam).
- **Habitation Triage**: Ranked triage queue based on Per-Capita Urgency ($PS_j$) and aggregate Caseload ($PS_j \times \text{population}$).
- **Carrying Capacity Assessment**: Norm-based capacity calculation across land, water supply, school seats, and healthcare access.
- **Technical Architecture**: Next.js 16 + React 19 + TypeScript + Tailwind CSS v4 on frontend; FastAPI + PostgreSQL + PostGIS (Neon) on backend.

## Brand Commitments

- **Tone & Voice**: Authoritative, scientific, respectful, un-sensationalized, resilient.
- **Design Language**: Rich cartographic aesthetics, glassmorphism, universal dark/light theme compliance, high tactile GSAP microinteractions, and precision typography.
- **Name**: SETU-DRR (Hazard Red Zone & Relocation Decision Support Platform).

## Evidence on Hand

- Authoritative database records: 23 habitations and 637 candidate sites across Wayanad, Kodagu, and Barpeta.
- Real past disaster events: 2024 Chooralmala-Mundakkai debris flow (350 fatalities), 2018 Kodagu multi-landslide event, 2022 Brahmaputra flood breach.
- Sentinel-1 SAR RTC scenes and InSAR geodesy calibration datasets.

## Product Principles

1. **Precision Over Generalization**: Cell-level geotechnical truth and specific bounding constraints outrank broad regional generalizations.
2. **Actionable Decision Support**: Never present a risk score without an actionable triage path (Relocation vs. In-Situ Mitigation vs. Tourist Caution).
3. **Transparent Provenance**: Clearly distinguish verified data from screening-grade indicators, citing authoritative sources (GSI, SDMA, Open-Meteo, Sentinel-1).
4. **Dual Stakeholder Clarity**: Keep official planning tools rigorously technical while making tourist hazard intelligence intuitive, fast, and protective of life.
