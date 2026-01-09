import { createFileRoute } from '@tanstack/react-router';
import { useState, useEffect, useCallback } from 'react';
import {
  listHistory,
  clearHistory,
  deleteHistoryRecord,
  getDevices,
  type HistoryRecordResponse,
  type Device,
} from '../api';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Loader2,
  Trash2,
  CheckCircle,
  XCircle,
  Clock,
  User,
  Bot,
  ChevronDown,
  ChevronRight,
  Eye,
} from 'lucide-react';
import { useTranslation } from '../lib/i18n-context';

export const Route = createFileRoute('/history')({
  component: HistoryComponent,
});

function HistoryComponent() {
  const t = useTranslation();
  const [devices, setDevices] = useState<Device[]>([]);
  const [selectedSerial, setSelectedSerial] = useState<string>('');
  const [records, setRecords] = useState<HistoryRecordResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [clearDialogOpen, setClearDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [recordToDelete, setRecordToDelete] = useState<string | null>(null);
  const [detailDialogOpen, setDetailDialogOpen] = useState(false);
  const [selectedRecord, setSelectedRecord] =
    useState<HistoryRecordResponse | null>(null);
  const [expandedSteps, setExpandedSteps] = useState<Set<number>>(new Set());
  const limit = 20;

  // Load devices
  useEffect(() => {
    const loadDevices = async () => {
      try {
        const deviceList = await getDevices();
        setDevices(deviceList);
        // Auto-select first device if available
        if (deviceList.length > 0 && !selectedSerial) {
          setSelectedSerial(deviceList[0].serial);
        }
      } catch (error) {
        console.error('Failed to load devices:', error);
      }
    };
    loadDevices();
  }, [selectedSerial]);

  // Load history when device changes
  const loadHistory = useCallback(
    async (serial: string, reset = true) => {
      if (!serial) return;

      try {
        if (reset) {
          setLoading(true);
          setOffset(0);
        } else {
          setLoadingMore(true);
        }

        const newOffset = reset ? 0 : offset;
        const data = await listHistory(serial, limit, newOffset);

        if (reset) {
          setRecords(data.records);
        } else {
          setRecords(prev => [...prev, ...data.records]);
        }
        setTotal(data.total);
        setOffset(newOffset + data.records.length);
      } catch (error) {
        console.error('Failed to load history:', error);
      } finally {
        setLoading(false);
        setLoadingMore(false);
      }
    },
    [offset]
  );

  useEffect(() => {
    if (selectedSerial) {
      loadHistory(selectedSerial, true);
    }
  }, [selectedSerial]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleLoadMore = () => {
    if (selectedSerial && records.length < total) {
      loadHistory(selectedSerial, false);
    }
  };

  const handleClearAll = async () => {
    if (!selectedSerial) return;
    try {
      await clearHistory(selectedSerial);
      setRecords([]);
      setTotal(0);
      setOffset(0);
    } catch (error) {
      console.error('Failed to clear history:', error);
    }
    setClearDialogOpen(false);
  };

  const handleDelete = async () => {
    if (!selectedSerial || !recordToDelete) return;
    try {
      await deleteHistoryRecord(selectedSerial, recordToDelete);
      setRecords(prev => prev.filter(r => r.id !== recordToDelete));
      setTotal(prev => prev - 1);
    } catch (error) {
      console.error('Failed to delete record:', error);
    }
    setDeleteDialogOpen(false);
    setRecordToDelete(null);
  };

  const handleViewDetail = (record: HistoryRecordResponse) => {
    setSelectedRecord(record);
    // 默认展开所有步骤
    const allSteps = new Set<number>();
    record.messages.forEach(msg => {
      if (msg.step !== null && msg.step !== undefined) {
        allSteps.add(msg.step);
      }
    });
    setExpandedSteps(allSteps);
    setDetailDialogOpen(true);
  };

  const toggleStepExpanded = (step: number) => {
    setExpandedSteps(prev => {
      const next = new Set(prev);
      if (next.has(step)) {
        next.delete(step);
      } else {
        next.add(step);
      }
      return next;
    });
  };

  const formatDuration = (ms: number): string => {
    if (ms < 1000) return `${ms}ms`;
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
    return `${(ms / 60000).toFixed(1)}min`;
  };

  const formatTime = (timeStr: string): string => {
    const date = new Date(timeStr);
    const now = new Date();
    const isToday = date.toDateString() === now.toDateString();
    const yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);
    const isYesterday = date.toDateString() === yesterday.toDateString();

    const timeFormat = date.toLocaleTimeString('zh-CN', {
      hour: '2-digit',
      minute: '2-digit',
    });

    if (isToday) {
      return `${t.history.today} ${timeFormat}`;
    } else if (isYesterday) {
      return `${t.history.yesterday} ${timeFormat}`;
    } else {
      return date.toLocaleDateString('zh-CN', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    }
  };

  const getSourceLabel = (source: string): string => {
    const sourceMap: Record<string, string> = {
      chat: t.historyPage.source.chat,
      layered: t.historyPage.source.layered,
      scheduled: t.historyPage.source.scheduled,
    };
    return sourceMap[source] || source;
  };

  const getSourceColor = (source: string): string => {
    switch (source) {
      case 'chat':
        return 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300';
      case 'layered':
        return 'bg-purple-100 text-purple-700 dark:bg-purple-900 dark:text-purple-300';
      case 'scheduled':
        return 'bg-orange-100 text-orange-700 dark:bg-orange-900 dark:text-orange-300';
      default:
        return 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300';
    }
  };

  return (
    <div className="container mx-auto p-6 max-w-4xl">
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold">{t.historyPage.title}</h1>
        <div className="flex items-center gap-4">
          <Select value={selectedSerial} onValueChange={setSelectedSerial}>
            <SelectTrigger className="w-[200px]">
              <SelectValue placeholder={t.historyPage.selectDevice} />
            </SelectTrigger>
            <SelectContent>
              {devices.length === 0 ? (
                <SelectItem value="_none" disabled>
                  {t.historyPage.noDevices}
                </SelectItem>
              ) : (
                devices.map(device => (
                  <SelectItem key={device.serial} value={device.serial}>
                    {device.model || device.serial}
                  </SelectItem>
                ))
              )}
            </SelectContent>
          </Select>
          {records.length > 0 && (
            <Button
              variant="destructive"
              size="sm"
              onClick={() => setClearDialogOpen(true)}
            >
              <Trash2 className="w-4 h-4 mr-2" />
              {t.historyPage.clearAll}
            </Button>
          )}
        </div>
      </div>

      {/* Content */}
      {loading ? (
        <div className="flex justify-center items-center h-64">
          <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
        </div>
      ) : records.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-slate-500 dark:text-slate-400">
            {t.historyPage.noRecords}
          </p>
          <p className="text-sm text-slate-400 dark:text-slate-500 mt-2">
            {t.historyPage.noRecordsDesc}
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {records.map(record => (
            <Card
              key={record.id}
              className="hover:shadow-md transition-shadow cursor-pointer"
              onClick={() => handleViewDetail(record)}
            >
              <CardContent className="p-4">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    {/* Task text */}
                    <p className="text-sm font-medium text-slate-900 dark:text-slate-100 line-clamp-2 mb-2">
                      {record.task_text}
                    </p>

                    {/* Result message */}
                    <p className="text-sm text-slate-600 dark:text-slate-400 line-clamp-2 mb-3">
                      {record.final_message}
                    </p>

                    {/* Metadata row */}
                    <div className="flex flex-wrap items-center gap-2 text-xs">
                      {/* Success/Failed badge */}
                      {record.success ? (
                        <Badge
                          variant="outline"
                          className="text-green-600 border-green-300 dark:text-green-400 dark:border-green-700"
                        >
                          <CheckCircle className="w-3 h-3 mr-1" />
                          {t.historyPage.success}
                        </Badge>
                      ) : (
                        <Badge
                          variant="outline"
                          className="text-red-600 border-red-300 dark:text-red-400 dark:border-red-700"
                        >
                          <XCircle className="w-3 h-3 mr-1" />
                          {t.historyPage.failed}
                        </Badge>
                      )}

                      {/* Source badge */}
                      <Badge className={getSourceColor(record.source)}>
                        {getSourceLabel(record.source)}
                        {record.source_detail && `: ${record.source_detail}`}
                      </Badge>

                      {/* Steps */}
                      {record.steps > 0 && (
                        <span className="text-slate-500 dark:text-slate-400">
                          {t.historyPage.steps.replace(
                            '{count}',
                            String(record.steps)
                          )}
                        </span>
                      )}

                      {/* Duration */}
                      <span className="text-slate-500 dark:text-slate-400 flex items-center">
                        <Clock className="w-3 h-3 mr-1" />
                        {formatDuration(record.duration_ms)}
                      </span>

                      {/* Time */}
                      <span className="text-slate-400 dark:text-slate-500">
                        {formatTime(record.start_time)}
                      </span>
                    </div>
                  </div>

                  {/* Action buttons */}
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-slate-400 hover:text-blue-500"
                      onClick={e => {
                        e.stopPropagation();
                        handleViewDetail(record);
                      }}
                    >
                      <Eye className="w-4 h-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-slate-400 hover:text-red-500"
                      onClick={e => {
                        e.stopPropagation();
                        setRecordToDelete(record.id);
                        setDeleteDialogOpen(true);
                      }}
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}

          {/* Load more button */}
          {records.length < total && (
            <div className="text-center py-4">
              <Button
                variant="outline"
                onClick={handleLoadMore}
                disabled={loadingMore}
              >
                {loadingMore ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    {t.historyPage.loading}
                  </>
                ) : (
                  t.historyPage.loadMore
                )}
              </Button>
            </div>
          )}
        </div>
      )}

      {/* Clear All Dialog */}
      <AlertDialog open={clearDialogOpen} onOpenChange={setClearDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t.historyPage.clearAll}</AlertDialogTitle>
            <AlertDialogDescription>
              {t.historyPage.clearAllConfirm}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t.common.cancel}</AlertDialogCancel>
            <AlertDialogAction onClick={handleClearAll}>
              {t.common.confirm}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Delete Dialog */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t.common.delete}</AlertDialogTitle>
            <AlertDialogDescription>
              {t.historyPage.deleteConfirm}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t.common.cancel}</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete}>
              {t.common.confirm}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Detail Dialog */}
      <Dialog open={detailDialogOpen} onOpenChange={setDetailDialogOpen}>
        <DialogContent className="max-w-2xl max-h-[80vh] flex flex-col overflow-hidden">
          <DialogHeader className="flex-shrink-0">
            <DialogTitle className="flex items-center gap-2">
              {selectedRecord?.success ? (
                <CheckCircle className="w-5 h-5 text-green-500" />
              ) : (
                <XCircle className="w-5 h-5 text-red-500" />
              )}
              {t.historyPage.detailTitle || '对话详情'}
            </DialogTitle>
          </DialogHeader>

          {selectedRecord && (
            <div className="overflow-y-auto max-h-[calc(80vh-120px)] pr-4">
              <div className="space-y-4">
                {/* Task summary */}
                <div className="p-3 bg-slate-50 dark:bg-slate-900 rounded-lg">
                  <p className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                    {t.historyPage.taskLabel || '任务'}
                  </p>
                  <p className="text-sm text-slate-900 dark:text-slate-100">
                    {selectedRecord.task_text}
                  </p>
                </div>

                {/* Messages */}
                <div className="space-y-3">
                  {selectedRecord.messages.length > 0 ? (
                    selectedRecord.messages.map((msg, idx) => (
                      <div key={idx} className="space-y-2">
                        {msg.role === 'user' ? (
                          <div className="flex items-start gap-3">
                            <div className="w-8 h-8 rounded-full bg-blue-100 dark:bg-blue-900 flex items-center justify-center flex-shrink-0">
                              <User className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                            </div>
                            <div className="flex-1 p-3 bg-blue-50 dark:bg-blue-900/30 rounded-lg">
                              <p className="text-sm text-slate-900 dark:text-slate-100">
                                {msg.content}
                              </p>
                            </div>
                          </div>
                        ) : (
                          <div className="flex items-start gap-3">
                            <div className="w-8 h-8 rounded-full bg-emerald-100 dark:bg-emerald-900 flex items-center justify-center flex-shrink-0">
                              <Bot className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                            </div>
                            <div className="flex-1 space-y-2">
                              {/* Step header */}
                              {msg.step !== null && msg.step !== undefined && (
                                <button
                                  className="flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
                                  onClick={() =>
                                    toggleStepExpanded(msg.step as number)
                                  }
                                >
                                  {expandedSteps.has(msg.step) ? (
                                    <ChevronDown className="w-3 h-3" />
                                  ) : (
                                    <ChevronRight className="w-3 h-3" />
                                  )}
                                  {t.historyPage.stepLabel?.replace(
                                    '{step}',
                                    String(msg.step)
                                  ) || `步骤 ${msg.step}`}
                                </button>
                              )}

                              {/* Thinking */}
                              {msg.thinking &&
                                (msg.step === null ||
                                  msg.step === undefined ||
                                  expandedSteps.has(msg.step)) && (
                                  <div className="p-3 bg-slate-100 dark:bg-slate-800 rounded-lg">
                                    <p className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">
                                      {t.historyPage.thinkingLabel || '思考'}
                                    </p>
                                    <p className="text-sm text-slate-700 dark:text-slate-300 whitespace-pre-wrap">
                                      {msg.thinking}
                                    </p>
                                  </div>
                                )}

                              {/* Action */}
                              {msg.action &&
                                (msg.step === null ||
                                  msg.step === undefined ||
                                  expandedSteps.has(msg.step)) && (
                                  <div className="p-3 bg-amber-50 dark:bg-amber-900/20 rounded-lg">
                                    <p className="text-xs font-medium text-amber-600 dark:text-amber-400 mb-1">
                                      {t.historyPage.actionLabel || '动作'}
                                    </p>
                                    <pre className="text-xs text-slate-700 dark:text-slate-300 overflow-x-auto">
                                      {JSON.stringify(msg.action, null, 2)}
                                    </pre>
                                  </div>
                                )}
                            </div>
                          </div>
                        )}
                      </div>
                    ))
                  ) : (
                    <p className="text-sm text-slate-500 dark:text-slate-400 text-center py-4">
                      {t.historyPage.noMessages || '暂无详细消息记录'}
                    </p>
                  )}
                </div>

                {/* Final result */}
                <div
                  className={`p-3 rounded-lg ${
                    selectedRecord.success
                      ? 'bg-green-50 dark:bg-green-900/20'
                      : 'bg-red-50 dark:bg-red-900/20'
                  }`}
                >
                  <p
                    className={`text-xs font-medium mb-1 ${
                      selectedRecord.success
                        ? 'text-green-600 dark:text-green-400'
                        : 'text-red-600 dark:text-red-400'
                    }`}
                  >
                    {t.historyPage.resultLabel || '结果'}
                  </p>
                  <p className="text-sm text-slate-900 dark:text-slate-100">
                    {selectedRecord.final_message}
                  </p>
                </div>

                {/* Metadata */}
                <div className="flex flex-wrap gap-3 text-xs text-slate-500 dark:text-slate-400 pt-2 border-t border-slate-200 dark:border-slate-700">
                  <span>
                    {t.historyPage.steps.replace(
                      '{count}',
                      String(selectedRecord.steps)
                    )}
                  </span>
                  <span className="flex items-center">
                    <Clock className="w-3 h-3 mr-1" />
                    {formatDuration(selectedRecord.duration_ms)}
                  </span>
                  <Badge className={getSourceColor(selectedRecord.source)}>
                    {getSourceLabel(selectedRecord.source)}
                  </Badge>
                </div>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
