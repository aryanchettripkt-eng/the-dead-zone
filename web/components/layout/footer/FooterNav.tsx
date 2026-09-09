'use client';

import React from 'react';
import Link from 'next/link';

export interface FooterNavLink {
  label: string;
  href: string;
  isExternal?: boolean;
}

export interface FooterNavProps {
  /** Navigation links */
  links?: FooterNavLink[];
  /** Optional custom className */
  className?: string;
}

const DEFAULT_FOOTER_LINKS: FooterNavLink[] = [
  { label: 'Overview', href: '/' },
  { label: 'Tourist Risk', href: '/stories' },
  { label: 'Gov Console', href: '/gov' },
  { label: 'Triage Workspace', href: '/workspace' },
  { label: 'Portal Access', href: '/login' },
  { label: 'About', href: '/about' },
];

export const FooterNav: React.FC<FooterNavProps> = ({
  links = DEFAULT_FOOTER_LINKS,
  className = '',
}) => {
  return (
    <nav
      aria-label="Footer Navigation"
      className={`flex flex-wrap items-center gap-y-2 text-xs font-mono font-medium ${className}`}
    >
      {links.map((link, idx) => (
        <React.Fragment key={link.label}>
          {idx > 0 && (
            <span
              className="mx-2.5 text-line-strong dark:text-white/20 select-none"
              aria-hidden="true"
            >
              ·
            </span>
          )}
          <Link
            href={link.href}
            className="text-ink-muted dark:text-text-secondary hover:text-ink dark:hover:text-text-primary transition-colors py-1 hover:text-accent dark:hover:text-accent"
          >
            {link.label}
          </Link>
        </React.Fragment>
      ))}
    </nav>
  );
};

