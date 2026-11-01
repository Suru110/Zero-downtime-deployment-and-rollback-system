import React from 'react';

interface SkeletonProps {
  className?: string;
  count?: number;
}

export const Skeleton: React.FC<SkeletonProps> = ({ className = '' }) => (
  <div className={`skeleton ${className}`} aria-hidden="true" />
);

export const CardSkeleton: React.FC = () => (
  <div className="p-5 rounded-2xl glass-card space-y-3 animate-pulse">
    <div className="flex items-center justify-between">
      <Skeleton className="h-3 w-24" />
      <Skeleton className="h-4 w-4 rounded-full" />
    </div>
    <Skeleton className="h-8 w-16" />
    <Skeleton className="h-3 w-32" />
  </div>
);

export const RowSkeleton: React.FC = () => (
  <div className="flex items-center gap-3 p-4 border-b border-slate-800/60 animate-pulse">
    <Skeleton className="h-8 w-8 rounded-lg shrink-0" />
    <div className="flex-1 space-y-2">
      <Skeleton className="h-3 w-40" />
      <Skeleton className="h-2.5 w-24" />
    </div>
    <Skeleton className="h-6 w-20 rounded-full" />
  </div>
);

export const TableSkeleton: React.FC<{ rows?: number }> = ({ rows = 5 }) => (
  <div>
    {Array.from({ length: rows }).map((_, i) => (
      <RowSkeleton key={i} />
    ))}
  </div>
);
