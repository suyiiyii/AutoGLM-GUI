import React, { useEffect, useState } from 'react';
import { History, Trash, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { HistoryGroup } from './HistoryGroup';
import {
  loadHistoryItems,
  clearHistory,
  groupHistoryByDate,
} from '../utils/history';
import type { HistoryItem } from '../types/history';
import { useTranslation } from '../lib/i18n-context';

interface HistoryDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  deviceId: string;
  deviceName: string;
  onSelectHistory: (item: HistoryItem) => void;
}

export function HistoryDialog({
  open,
  onOpenChange,
  deviceId,
  deviceName,
  onSelectHistory,
}: HistoryDialogProps) {
  const t = useTranslation();
  const [historyItems, setHistoryItems] = useState<ReturnType<
    typeof loadHistoryItems
  > | null>(null);

  // 当对话框打开时加载历史记录
  useEffect(() => {
    if (open && deviceId) {
      const items = loadHistoryItems(deviceId);
      setHistoryItems(items);
    }
  }, [open, deviceId]);

  const handleClearAll = () => {
    if (confirm(t.history.clearAllConfirm)) {
      clearHistory(deviceId);
      setHistoryItems([]);
    }
  };

  const handleSelectHistory = (item: HistoryItem) => {
    onSelectHistory(item);
    onOpenChange(false); // 关闭侧边栏
  };

  if (!historyItems) {
    return null;
  }

  const grouped = groupHistoryByDate(historyItems);

  return (
    <>
      {/* Backdrop */}
      {open && (
        <div
          className="fixed inset-0 bg-black/50 z-40 transition-opacity"
          onClick={() => onOpenChange(false)}
        />
      )}

      {/* Sidebar */}
      <div
        className={`fixed right-0 top-0 h-full w-96 bg-white dark:bg-slate-900 shadow-2xl z-50 transform transition-transform duration-300 ease-in-out flex flex-col ${
          open ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-200 dark:border-slate-800">
          <div className="flex items-center gap-2">
            <History className="w-5 h-5 text-[#1d9bf0]" />
            <div>
              <h2 className="font-semibold text-slate-900 dark:text-slate-100">
                {t.history.title}
              </h2>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                {deviceName}
              </p>
            </div>
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => onOpenChange(false)}
          >
            <X className="w-4 h-4" />
          </Button>
        </div>

        {/* Scrollable history list */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {grouped.today.length > 0 && (
            <HistoryGroup
              title={t.history.today}
              items={grouped.today}
              onSelect={handleSelectHistory}
            />
          )}
          {grouped.yesterday.length > 0 && (
            <HistoryGroup
              title={t.history.yesterday}
              items={grouped.yesterday}
              onSelect={handleSelectHistory}
            />
          )}
          {grouped.earlier.length > 0 && (
            <HistoryGroup
              title={t.history.earlier}
              items={grouped.earlier}
              onSelect={handleSelectHistory}
            />
          )}

          {/* Empty state */}
          {historyItems.length === 0 && (
            <div className="text-center py-12">
              <div className="flex h-16 w-16 items-center justify-center rounded-full bg-slate-100 dark:bg-slate-800 mx-auto mb-4">
                <History className="h-8 w-8 text-slate-400" />
              </div>
              <p className="font-medium text-slate-900 dark:text-slate-100">
                {t.history.noHistory}
              </p>
              <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                {t.history.noHistoryDescription}
              </p>
            </div>
          )}
        </div>

        {/* Footer */}
        {historyItems.length > 0 && (
          <div className="p-4 border-t border-slate-200 dark:border-slate-800">
            <Button
              variant="outline"
              onClick={handleClearAll}
              className="w-full"
            >
              <Trash className="w-4 h-4 mr-2" />
              {t.history.clearAll}
            </Button>
          </div>
        )}
      </div>
    </>
  );
}
