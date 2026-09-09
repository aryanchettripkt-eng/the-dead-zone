'use client';

import React from 'react';
import { ZoneId } from './storyData';
import { DistrictRiskModal } from './DistrictRiskModal';

export interface HazardSlideshowModalProps {
  /** Modal open status */
  isOpen: boolean;
  /** Active zone being explored */
  zone: ZoneId;
  /** Callback to close modal */
  onClose: () => void;
  /** Custom root className */
  className?: string;
}

/**
 * Re-exports the authoritative DistrictRiskModal for backward compatibility.
 * Connects the pop-up directly to backend habitations and risk dossiers.
 */
export const HazardSlideshowModal: React.FC<HazardSlideshowModalProps> = (props) => {
  return <DistrictRiskModal {...props} />;
};

export default HazardSlideshowModal;
