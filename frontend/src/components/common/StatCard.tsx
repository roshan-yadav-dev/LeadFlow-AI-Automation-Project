import React from 'react';
import { LucideIcon } from 'lucide-react';

interface StatCardProps {
  title: string;
  value: number | string;
  subtitle?: string;
  icon: LucideIcon;
  color?: 'indigo' | 'emerald' | 'amber' | 'rose' | 'blue' | 'slate';
  trend?: string;
  onClick?: () => void;
}

const colorMap = {
  indigo: {
    bg: 'bg-indigo-50 text-indigo-600 dark:bg-indigo-950/40 dark:text-indigo-400',
    border: 'border-indigo-100 dark:border-indigo-900/30',
  },
  emerald: {
    bg: 'bg-emerald-50 text-emerald-600 dark:bg-emerald-950/40 dark:text-emerald-400',
    border: 'border-emerald-100 dark:border-emerald-900/30',
  },
  amber: {
    bg: 'bg-amber-50 text-amber-600 dark:bg-amber-950/40 dark:text-amber-400',
    border: 'border-amber-100 dark:border-amber-900/30',
  },
  rose: {
    bg: 'bg-rose-50 text-rose-600 dark:bg-rose-950/40 dark:text-rose-400',
    border: 'border-rose-100 dark:border-rose-900/30',
  },
  blue: {
    bg: 'bg-blue-50 text-blue-600 dark:bg-blue-950/40 dark:text-blue-400',
    border: 'border-blue-100 dark:border-blue-900/30',
  },
  slate: {
    bg: 'bg-slate-50 text-slate-600 dark:bg-slate-800 dark:text-slate-400',
    border: 'border-slate-100 dark:border-slate-700',
  },
};

export const StatCard: React.FC<StatCardProps> = ({
  title,
  value,
  subtitle,
  icon: Icon,
  color = 'indigo',
  trend,
  onClick,
}) => {
  const styles = colorMap[color] || colorMap.indigo;

  return (
    <div
      onClick={onClick}
      className={`bg-white dark:bg-slate-800 rounded-xl p-5 border border-slate-200 dark:border-slate-700 shadow-sm transition-all duration-200 ${
        onClick ? 'cursor-pointer hover:shadow-md hover:border-indigo-300' : ''
      }`}
    >
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
            {title}
          </p>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-2xl font-bold text-slate-900 dark:text-white tracking-tight">
              {value}
            </span>
            {trend && <span className="text-xs text-slate-500 dark:text-slate-400">{trend}</span>}
          </div>
          {subtitle && (
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{subtitle}</p>
          )}
        </div>
        <div className={`p-3 rounded-lg ${styles.bg}`}>
          <Icon className="w-5 h-5" />
        </div>
      </div>
    </div>
  );
};
