import React from 'react';
import { CheckCircle2, AlertCircle, Trash2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import type { HistoryRecordResponse } from '../api';
import { useTranslation } from '../lib/i18n-context';

interface HistoryItemCardProps {
  item: HistoryRecordResponse;
  onSelect: (item: HistoryRecordResponse) => void;
  onDelete: (itemId: string) => void;
}

function formatHistoryTime(timestamp: string): string {
  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMinutes = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMinutes < 1) return 'Just now';
  if (diffMinutes < 60) return `${diffMinutes}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;

  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatDuration(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;

  if (minutes === 0) {
    return `${seconds}s`;
  }
  return `${minutes}m ${seconds}s`;
}

export function HistoryItemCard({
  item,
  onSelect,
  onDelete,
}: HistoryItemCardProps) {
  const t = useTranslation();

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation(); // 阻止冒泡，避免触发 onSelect
    if (confirm(t.history.deleteConfirm)) {
      onDelete(item.id);
    }
  };

  return (
    <Card
      className="hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors cursor-pointer group"
      onClick={() => onSelect(item)}
    >
      <div className="p-3 space-y-2">
        {/* Task Text */}
        <p className="text-sm font-medium text-slate-900 dark:text-slate-100 line-clamp-2">
          {item.task_text}
        </p>

        {/* Metadata Row */}
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
            <span>{formatHistoryTime(item.start_time)}</span>
            <span>•</span>
            <span>
              {item.steps} {item.steps === 1 ? 'step' : 'steps'}
            </span>
            <span>•</span>
            <span>{formatDuration(item.duration_ms)}</span>
          </div>

          <div className="flex items-center gap-2">
            {/* Status Badge */}
            <Badge
              variant={item.success ? 'success' : 'destructive'}
              className="shrink-0"
            >
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

            {/* Delete Button */}
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 opacity-0 group-hover:opacity-100 transition-opacity text-slate-400 hover:text-red-500 dark:text-slate-500 dark:hover:text-red-400"
              onClick={handleDelete}
              title={t.history.deleteItem}
            >
              <Trash2 className="w-3 h-3" />
            </Button>
          </div>
        </div>
      </div>
    </Card>
  );
}
