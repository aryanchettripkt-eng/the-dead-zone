'use client';

import React from 'react';
import Link from 'next/link';

export interface FooterBrandProps {
  /** Optional custom className */
  className?: string;
}

export const FooterBrand: React.FC<FooterBrandProps> = ({ className = '' }) => {
  return (
    <div className={`flex flex-col items-start gap-1.5 ${className}`}>
      <Link
        href="/"
        className="flex items-center gap-2.5 group transition-transform active:scale-95"
      >
        {/* Emblem Crest */}
        <div className="w-7 h-7 rounded-md bg-surface-1 dark:bg-forest-surface border border-line dark:border-white/15 flex items-center justify-center font-serif font-black text-xs text-ochre shadow-xs">
          सं
        </div>
        <div className="flex items-baseline gap-2">
          <span className="font-display font-bold text-sm tracking-tight text-ink dark:text-text-primary group-hover:text-accent transition-colors">
            SETU-DRR
          </span>
          <span className="text-[11px] font-mono text-ink-muted dark:text-text-muted">
            v2.4
          </span>
        </div>
      </Link>

      <p className="text-xs text-ink-muted dark:text-text-secondary max-w-md leading-relaxed">
        Disaster Management Division · Ministry of Home Affairs · Government of India.
        Frontline hazard intelligence and relocation decision support.
      </p>
    </div>
  );
};

