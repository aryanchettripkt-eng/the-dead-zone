'use client';

import React from 'react';
import { FooterBrand } from './FooterBrand';
import { FooterNav } from './FooterNav';
import { FooterTelemetry } from './FooterTelemetry';

export interface FrostedFooterProps {
  /** Optional custom className */
  className?: string;
  /** Granular classNames */
  classNames?: {
    container?: string;
    topRow?: string;
    bottomRow?: string;
  };
}

export const FrostedFooter: React.FC<FrostedFooterProps> = ({
  className = '',
  classNames = {},
}) => {
  return (
    <footer
      id="landing-footer"
      className={`relative z-20 w-full rounded-t-3xl border-t border-line/80 dark:border-white/10 bg-surface-0/80 dark:bg-[#0b1612]/80 backdrop-blur-2xl shadow-[0_-8px_32px_rgba(0,0,0,0.08)] transition-colors duration-300 overflow-hidden ${className}`}
    >
      {/* Subtle top ambient rim light */}
      <div className="absolute top-0 inset-x-0 h-px bg-gradient-to-r from-transparent via-accent/30 dark:via-accent-emerald/30 to-transparent pointer-events-none" />

      <div
        className={`max-w-7xl mx-auto px-6 sm:px-10 lg:px-16 pt-7 pb-8 flex flex-col gap-6 ${
          classNames.container ?? ''
        }`}
      >
        {/* Top Segment: Brand on Left, Essential Lifeline on Right */}
        <div
          className={`flex flex-col md:flex-row md:items-center justify-between gap-5 ${
            classNames.topRow ?? ''
          }`}
        >
          <FooterBrand />
          <FooterTelemetry />
        </div>

        {/* Bottom Segment: Editorial Nav with Dot Dividers & Clean Copyright */}
        <div
          className={`flex flex-col sm:flex-row sm:items-center justify-between gap-4 pt-5 border-t border-line/60 dark:border-white/10 ${
            classNames.bottomRow ?? ''
          }`}
        >
          <FooterNav />

          <p className="text-[11px] font-mono text-ink-muted dark:text-text-muted">
            © 2026 SETU-DRR · NDMD / NDRF · All Rights Reserved
          </p>
        </div>
      </div>
    </footer>
  );
};

