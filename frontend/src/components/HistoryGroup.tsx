import React from 'react';
import type { HistoryItem } from '../types/history';
import { HistoryItemCard } from './HistoryItemCard';

interface HistoryGroupProps {
  title: string;
  items: HistoryItem[];
  onSelect: (item: HistoryItem) => void;
}

export function HistoryGroup({ title, items, onSelect }: HistoryGroupProps) {
  if (items.length === 0) return null;

  return (
    <div className="space-y-2">
      <h3 className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider px-1">
        {title}
      </h3>
      <div className="space-y-2">
        {items.map(item => (
          <HistoryItemCard key={item.id} item={item} onSelect={onSelect} />
        ))}
      </div>
    </div>
  );
}
