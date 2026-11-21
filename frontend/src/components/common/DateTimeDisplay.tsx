import React from 'react';

interface DateTimeDisplayProps {
  isoString: string | null | undefined;
  includeTime?: boolean;
}

export const DateTimeDisplay: React.FC<DateTimeDisplayProps> = ({
  isoString,
  includeTime = true,
}) => {
  if (!isoString) return <span className="text-slate-400 text-xs">—</span>;

  try {
    const date = new Date(isoString);
    if (isNaN(date.getTime())) return <span>{isoString}</span>;

    const options: Intl.DateTimeFormatOptions = {
      timeZone: 'Asia/Kolkata',
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      ...(includeTime
        ? {
            hour: '2-digit',
            minute: '2-digit',
            hour12: true,
          }
        : {}),
    };

    const formatted = new Intl.DateTimeFormat('en-IN', options).format(date);

    return (
      <span className="text-xs text-slate-600 dark:text-slate-300 font-medium whitespace-nowrap">
        {formatted}
      </span>
    );
  } catch {
    return <span>{isoString}</span>;
  }
};
