import React from 'react';

export const LoadingSkeleton: React.FC<{ lines?: number }> = ({ lines = 3 }) => (
  <div className="animate-pulse space-y-2.5">
    {Array.from({ length: lines }).map((_, i) => (
      <div key={i} className="h-4 bg-slate-200 dark:bg-slate-700 rounded w-full" />
    ))}
  </div>
);

export const TableSkeleton: React.FC<{ rows?: number; columns?: number }> = ({
  rows = 5,
  columns = 5,
}) => (
  <div className="animate-pulse space-y-3">
    <div className="h-10 bg-slate-200 dark:bg-slate-700 rounded-lg w-full" />
    {Array.from({ length: rows }).map((_, i) => (
      <div key={i} className="flex gap-4">
        {Array.from({ length: columns }).map((_, j) => (
          <div
            key={j}
            className="h-8 bg-slate-100 dark:bg-slate-800 rounded flex-1"
          />
        ))}
      </div>
    ))}
  </div>
);

export const CardSkeleton: React.FC = () => (
  <div className="animate-pulse bg-white dark:bg-slate-800 rounded-xl p-5 border border-slate-200 dark:border-slate-700">
    <div className="h-4 bg-slate-200 dark:bg-slate-700 rounded w-1/3 mb-3" />
    <div className="h-8 bg-slate-100 dark:bg-slate-800 rounded w-1/2 mb-2" />
    <div className="h-3 bg-slate-100 dark:bg-slate-800 rounded w-2/3" />
  </div>
);
