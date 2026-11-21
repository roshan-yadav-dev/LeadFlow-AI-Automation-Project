import React from 'react';

interface StatusBadgeProps {
  status: string | null | undefined;
  variant?: 'tier' | 'task' | 'approval' | 'general';
  size?: 'sm' | 'md';
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({
  status,
  variant = 'general',
  size = 'md',
}) => {
  if (!status) return <span className="text-slate-400 text-xs">—</span>;

  const normalized = status.toUpperCase();

  let colorClasses = 'bg-slate-100 text-slate-700 border-slate-200';

  if (variant === 'tier' || ['HOT', 'WARM', 'COLD'].includes(normalized)) {
    switch (normalized) {
      case 'HOT':
        colorClasses = 'bg-red-50 text-red-700 border-red-200 ring-1 ring-red-300';
        break;
      case 'WARM':
        colorClasses = 'bg-amber-50 text-amber-700 border-amber-200 ring-1 ring-amber-300';
        break;
      case 'COLD':
        colorClasses = 'bg-blue-50 text-blue-700 border-blue-200 ring-1 ring-blue-300';
        break;
    }
  } else if (
    ['COMPLETED', 'APPROVED', 'SUCCESS', 'ACTIVE', 'MATCHED', 'CONNECTED', 'SENT'].includes(normalized)
  ) {
    colorClasses = 'bg-emerald-50 text-emerald-700 border-emerald-200';
  } else if (
    ['PENDING', 'AWAITING_APPROVAL', 'IN_PROGRESS', 'SCHEDULED', 'ANALYZING'].includes(normalized)
  ) {
    colorClasses = 'bg-amber-50 text-amber-700 border-amber-200';
  } else if (
    ['FAILED', 'REJECTED', 'CANCELLED', 'EXPIRED', 'OVERDUE', 'URGENT'].includes(normalized)
  ) {
    colorClasses = 'bg-rose-50 text-rose-700 border-rose-200';
  } else if (['UNMATCHED', 'DISMISSED', 'SKIPPED', 'IGNORED'].includes(normalized)) {
    colorClasses = 'bg-slate-100 text-slate-600 border-slate-200';
  }

  const sizeClasses = size === 'sm' ? 'px-1.5 py-0.5 text-xs' : 'px-2.5 py-1 text-xs';

  return (
    <span
      className={`inline-flex items-center font-semibold rounded-full border tracking-wide uppercase ${sizeClasses} ${colorClasses}`}
    >
      {status}
    </span>
  );
};
