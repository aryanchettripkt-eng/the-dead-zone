// Root barrel export for Relocation Decision Support module

export * from './triage';
export * from './map';
export * from './sites';
export * from './solver';

export { DistrictSelect, deriveDistricts } from './DistrictSelect';
export type { DistrictSelectProps, DistrictOption } from './DistrictSelect';

export { RelocationHeaderMeta } from './RelocationHeaderMeta';
export type { RelocationHeaderMetaProps } from './RelocationHeaderMeta';

export { RelocationWorkspace } from './RelocationWorkspace';
export type { RelocationWorkspaceProps } from './RelocationWorkspace';

export { TierBadge } from './TierBadge';
export type { TierBadgeProps } from './TierBadge';

export {
  CONSTRAINT_HINTS,
  CONSTRAINT_LABELS,
  TENURE_LABELS,
  TIER_LABELS,
  TIER_VARIANTS,
  UNMEASURED_LABEL,
} from './constants';
