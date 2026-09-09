import type { ReactNode } from 'react';

export interface RightPanelProps {
  children: ReactNode;
  /** Explicit panel width override in pixels or CSS value. Omit for responsive laptop-optimized default. */
  width?: number | string;
  className?: string;
  classNames?: {
    root?: string;
    scroll?: string;
  };
}

export const RightPanel = ({ children, width, className = '', classNames = {} }: RightPanelProps) => (
  <aside
    style={width ? { width } : undefined}
    className={[
      'flex shrink-0 flex-col border-l border-line bg-surface-0 transition-all duration-200',
      width ? '' : 'w-[290px] xl:w-[320px] 2xl:w-[360px]',
      classNames.root ?? '',
      className,
    ]
      .filter(Boolean)
      .join(' ')}
  >
    <div className={['flex-1 overflow-y-auto p-2.5 sm:p-3', classNames.scroll ?? ''].join(' ')}>{children}</div>
  </aside>
);
