import type { ReactNode } from 'react';

export interface LeftPanelProps {
  children: ReactNode;
  /** Explicit panel width override in pixels or CSS value. Omit for responsive laptop-optimized default. */
  width?: number | string;
  className?: string;
  classNames?: {
    root?: string;
    scroll?: string;
  };
}

export const LeftPanel = ({ children, width, className = '', classNames = {} }: LeftPanelProps) => (
  <aside
    style={width ? { width } : undefined}
    className={[
      'flex shrink-0 flex-col border-r border-line bg-surface-0 transition-all duration-200',
      width ? '' : 'w-[270px] xl:w-[290px] 2xl:w-[320px]',
      classNames.root ?? '',
      className,
    ]
      .filter(Boolean)
      .join(' ')}
  >
    <div className={['flex-1 overflow-y-auto p-2.5 sm:p-3', classNames.scroll ?? ''].join(' ')}>{children}</div>
  </aside>
);
