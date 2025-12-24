import React from 'react';
import { CheckCircle2, AlertCircle } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
import type { HistoryItem } from '../types/history';
import { formatHistoryTime, formatDuration } from '../utils/history';
import { useTranslation } from '../lib/i18n-context';

interface HistoryItemCardProps {
  item: HistoryItem;
  onSelect: (item: HistoryItem) => void;
}

export function HistoryItemCard({ item, onSelect }: HistoryItemCardProps) {
  const t = useTranslation();

  return (
    <Card
      className="hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors cursor-pointer"
      onClick={() => onSelect(item)}
    >
      <div className="p-3 space-y-2">
        {/* Task Text */}
        <p className="text-sm font-medium text-slate-900 dark:text-slate-100 line-clamp-2">
          {item.taskText}
        </p>

        {/* Metadata Row */}
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
            <span>{formatHistoryTime(item.startTime)}</span>
            <span>•</span>
            <span>
              {item.steps} {item.steps === 1 ? 'step' : 'steps'}
            </span>
            <span>•</span>
            <span>{formatDuration(item.duration)}</span>
          </div>

          {/* Status Badge */}
          <Badge variant={item.success ? 'success' : 'destructive'} className="shrink-0">
            {item.success ? (
              <>
                <CheckCircle2 className="w-3 h-3 mr-1" />
                {t.history.success}
              </>
            ) : (
              <>
                <AlertCircle className="w-3 h-3 mr-1" />
                {t.history.failed}
              </>
            )}
          </Badge>
        </div>
      </div>
    </Card>
  );
}
