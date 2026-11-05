import React from 'react';

type StatusType =
  | 'pending' | 'scanning' | 'deploying' | 'verifying'
  | 'paused'
  | 'active' | 'failed' | 'rolled_back' | 'cancelled'
  | 'passed' | 'warning' | 'clean' | 'critical' | 'unscanned';

interface StatusBadgeProps {
  status: StatusType | string;
  size?: 'sm' | 'md';
  showDot?: boolean;
}

const CONFIG: Record<string, { bg: string; text: string; border: string; dot: string; label: string }> = {
  pending:      { bg: 'bg-slate-800/80',    text: 'text-slate-300',   border: 'border-slate-700/60',  dot: 'bg-slate-400',   label: 'Pending' },
  paused:       { bg: 'bg-amber-500/10',    text: 'text-amber-300',    border: 'border-amber-500/30',   dot: 'bg-amber-400',   label: 'Paused' },
  scanning:     { bg: 'bg-cyan-500/10',     text: 'text-cyan-400',    border: 'border-cyan-500/30',   dot: 'bg-cyan-400',    label: 'Scanning' },
  deploying:    { bg: 'bg-blue-500/10',     text: 'text-blue-400',    border: 'border-blue-500/30',   dot: 'bg-blue-400',    label: 'Deploying' },
  verifying:    { bg: 'bg-violet-500/10',   text: 'text-violet-400',  border: 'border-violet-500/30', dot: 'bg-violet-400',  label: 'Verifying' },
  active:       { bg: 'bg-emerald-500/10',  text: 'text-emerald-400', border: 'border-emerald-500/30',dot: 'bg-emerald-400', label: 'Active' },
  failed:       { bg: 'bg-rose-500/10',     text: 'text-rose-400',    border: 'border-rose-500/30',   dot: 'bg-rose-400',    label: 'Failed' },
  rolled_back:  { bg: 'bg-purple-500/10',   text: 'text-purple-400',  border: 'border-purple-500/30', dot: 'bg-purple-400',  label: 'Rolled Back' },
  cancelled:    { bg: 'bg-slate-800/80',    text: 'text-slate-400',   border: 'border-slate-700/60',  dot: 'bg-slate-500',   label: 'Cancelled' },
  passed:       { bg: 'bg-emerald-500/10',  text: 'text-emerald-400', border: 'border-emerald-500/30',dot: 'bg-emerald-400', label: 'Passed' },
  warning:      { bg: 'bg-amber-500/10',    text: 'text-amber-400',   border: 'border-amber-500/30',  dot: 'bg-amber-400',   label: 'Warning' },
  clean:        { bg: 'bg-emerald-500/10',  text: 'text-emerald-400', border: 'border-emerald-500/30',dot: 'bg-emerald-400', label: 'Clean' },
  critical:     { bg: 'bg-rose-500/10',     text: 'text-rose-400',    border: 'border-rose-500/30',   dot: 'bg-rose-400',    label: 'Critical' },
  unscanned:    { bg: 'bg-slate-800/80',    text: 'text-slate-400',   border: 'border-slate-700/60',  dot: 'bg-slate-500',   label: 'Unscanned' },
};

const ANIMATED_STATUSES = new Set(['scanning', 'deploying', 'verifying', 'pending']);

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, size = 'sm', showDot = true }) => {
  const cfg = CONFIG[status] ?? {
    bg: 'bg-slate-800/80',
    text: 'text-slate-300',
    border: 'border-slate-700/60',
    dot: 'bg-slate-400',
    label: status,
  };

  const isAnimated = ANIMATED_STATUSES.has(status);
  const sizeClasses = size === 'md' ? 'text-xs px-3 py-1.5 gap-2' : 'text-[11px] px-2.5 py-1 gap-1.5';

  return (
    <span
      className={`inline-flex items-center font-semibold rounded-full border ${cfg.bg} ${cfg.text} ${cfg.border} ${sizeClasses}`}
    >
      {showDot && (
        <span className="relative flex items-center">
          <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} />
          {isAnimated && (
            <span className={`absolute inset-0 rounded-full ${cfg.dot} animate-ping opacity-60`} />
          )}
        </span>
      )}
      <span className="capitalize">{cfg.label}</span>
    </span>
  );
};
