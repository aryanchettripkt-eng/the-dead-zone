'use client';

import React from 'react';

export interface FooterTelemetryProps {
  /** Optional custom className */
  className?: string;
}

export const FooterTelemetry: React.FC<FooterTelemetryProps> = ({
  className = '',
}) => {
  const handleScrollToTop = () => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  return (
    <div className={`flex flex-wrap items-center gap-3 ${className}`}>
      {/* 24/7 Emergency NDRF Hotline (Phone Link, Clean Static Indicator) */}
      <a
        href="tel:1078"
        className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-critical/10 hover:bg-critical/15 border border-critical/30 text-xs font-mono text-critical transition-all active:scale-95"
        title="Call NDRF Emergency Helpline"
      >
        <span className="w-1.5 h-1.5 rounded-full bg-critical shrink-0" />
        <span className="font-bold">NDRF Helpline:</span>
        <span className="tabular-nums">1078</span>
      </a>

      {/* Back to top button */}
      <button
        type="button"
        onClick={handleScrollToTop}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-mono font-medium text-ink-muted dark:text-text-secondary hover:text-ink dark:hover:text-text-primary bg-surface-1 dark:bg-forest-surface border border-line dark:border-white/10 hover:border-line-strong transition-all active:scale-95 cursor-pointer"
        aria-label="Scroll back to top"
      >
        <span>Top</span>
        <span aria-hidden="true">↑</span>
      </button>
    </div>
  );
};

