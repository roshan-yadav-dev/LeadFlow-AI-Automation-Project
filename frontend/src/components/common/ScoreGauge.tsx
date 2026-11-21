import React from 'react';

interface ScoreGaugeProps {
  score: number | null | undefined;
  size?: 'sm' | 'md' | 'lg';
}

export const ScoreGauge: React.FC<ScoreGaugeProps> = ({ score, size = 'md' }) => {
  if (score === null || score === undefined) {
    return <span className="text-xs text-slate-400 font-medium">—</span>;
  }

  let color = 'text-blue-600 bg-blue-50 border-blue-200';
  let tierLabel = 'COLD';
  if (score >= 70) {
    color = 'text-red-600 bg-red-50 border-red-200';
    tierLabel = 'HOT';
  } else if (score >= 40) {
    color = 'text-amber-600 bg-amber-50 border-amber-200';
    tierLabel = 'WARM';
  }

  const sizeClasses = {
    sm: 'text-xs px-2 py-0.5',
    md: 'text-sm px-2.5 py-1',
    lg: 'text-xl px-4 py-2 font-black',
  }[size];

  return (
    <div className="inline-flex items-center gap-1.5">
      <span
        className={`inline-flex items-center justify-center font-bold rounded-lg border shadow-xs ${sizeClasses} ${color}`}
      >
        {score}
      </span>
      {size === 'lg' && (
        <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
          / 100 ({tierLabel})
        </span>
      )}
    </div>
  );
};
