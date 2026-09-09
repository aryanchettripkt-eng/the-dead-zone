'use client';

import { useEffect, useRef, type ReactNode } from 'react';
import { useGSAP } from '@gsap/react';
import gsap from 'gsap';

import { usePrefersReducedMotion } from '@/lib/hooks/usePrefersReducedMotion';

export interface RelocationParcelDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  children: ReactNode;
  className?: string;
}

export const RelocationParcelDrawer = ({
  isOpen,
  onClose,
  children,
  className = '',
}: RelocationParcelDrawerProps) => {
  const drawerRef = useRef<HTMLDivElement>(null);
  const prefersReducedMotion = usePrefersReducedMotion();

  useGSAP(
    () => {
      if (!drawerRef.current || prefersReducedMotion) return;
      if (isOpen) {
        gsap.fromTo(
          drawerRef.current,
          { x: '100%', opacity: 0 },
          { x: '0%', opacity: 1, duration: 0.35, ease: 'power3.out' },
        );
      }
    },
    { dependencies: [isOpen, prefersReducedMotion] },
  );

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="absolute inset-0 z-30 pointer-events-none overflow-hidden">
      {/* Semi-translucent backdrop click-away */}
      <div
        className="absolute inset-0 bg-black/30 backdrop-blur-2xs pointer-events-auto transition-opacity"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Slide-over panel */}
      <div
        ref={drawerRef}
        role="dialog"
        aria-modal="true"
        aria-label="Candidate Destination Parcels"
        className={[
          'pointer-events-auto absolute right-0 top-0 bottom-0 flex w-full max-w-md flex-col',
          'border-l border-line bg-surface-0/95 dark:bg-forest-surface/95 shadow-2xl backdrop-blur-md',
          className,
        ]
          .filter(Boolean)
          .join(' ')}
      >
        {/* Drawer Header */}
        <div className="flex items-center justify-between border-b border-line px-4 py-3">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-accent animate-pulse" />
            <h2 className="text-sm font-bold text-ink">Candidate Safe Havens</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close drawer"
            className="flex h-7 w-7 items-center justify-center rounded-lg border border-line/60 bg-surface-1/50 text-ink-muted hover:bg-surface-2 hover:text-ink cursor-pointer transition-colors"
          >
            ✕
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 min-h-0 overflow-y-auto">{children}</div>
      </div>
    </div>
  );
};
