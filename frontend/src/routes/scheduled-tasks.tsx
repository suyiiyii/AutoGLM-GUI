import { createFileRoute } from '@tanstack/react-router';
import { useState, useEffect } from 'react';
import {
  listScheduledTasks,
  createScheduledTask,
  updateScheduledTask,
  deleteScheduledTask,
  enableScheduledTask,
  disableScheduledTask,
  runScheduledTaskNow,
  getTaskHistory,
  getDevices,
  type ScheduledTask,
  type TaskHistory,
  type Device,
  getErrorMessage,
} from '../api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import {
  Plus,
  Edit,
  Trash2,
  Loader2,
  Play,
  Power,
  PowerOff,
  Clock,
  History,
  Calendar,
  CheckCircle2,
  XCircle,
  AlertCircle,
} from 'lucide-react';
import { useTranslation } from '../lib/i18n-context';
import { useToast } from '@/components/ui/use-toast';

export const Route = createFileRoute('/scheduled-tasks')({
  component: ScheduledTasksComponent,
});

function ScheduledTasksComponent() {
  const t = useTranslation();
  const { toast } = useToast();
  const [tasks, setTasks] = useState<ScheduledTask[]>([]);
  const [devices, setDevices] = useState<Device[]>([]);
  const [loading, setLoading] = useState(true);
  const [showDialog, setShowDialog] = useState(false);
  const [showHistoryDialog, setShowHistoryDialog] = useState(false);
  const [editingTask, setEditingTask] = useState<ScheduledTask | null>(null);
  const [selectedTaskHistory, setSelectedTaskHistory] = useState<TaskHistory[]>(
    []
  );
  const [historyLoading, setHistoryLoading] = useState(false);
  const [formData, setFormData] = useState({
    name: '',
    device_id: '',
    message: '',
    cron_expression: '0 9 * * *',
    execution_mode: 'classic' as 'classic' | 'dual_model' | 'layered_agent',
    thinking_mode: 'deep' as 'fast' | 'deep' | 'turbo',
    enabled: true,
  });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadTasks();
    loadDevices();
  }, []);

  const loadTasks = async () => {
    try {
      setLoading(true);
      const data = await listScheduledTasks();
      setTasks(data.tasks);
    } catch (error) {
      toast({
        title: t.common.error,
        description: getErrorMessage(error),
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  const loadDevices = async () => {
    try {
      const deviceList = await getDevices();
      setDevices(deviceList);
    } catch (error) {
      console.error('Failed to load devices:', error);
    }
  };

  const handleCreate = () => {
    setEditingTask(null);
    setFormData({
      name: '',
      device_id: devices[0]?.id || '',
      message: '',
      cron_expression: '0 9 * * *',
      execution_mode: 'classic',
      thinking_mode: 'deep',
      enabled: true,
    });
    setShowDialog(true);
  };

  const handleEdit = (task: ScheduledTask) => {
    setEditingTask(task);
    setFormData({
      name: task.name,
      device_id: task.device_id,
      message: task.message,
      cron_expression: task.cron_expression,
      execution_mode: task.execution_mode || 'classic',
      thinking_mode: task.thinking_mode || 'deep',
      enabled: task.status === 'enabled',
    });
    setShowDialog(true);
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      if (editingTask) {
        await updateScheduledTask(editingTask.uuid, {
          name: formData.name,
          device_id: formData.device_id,
          message: formData.message,
          cron_expression: formData.cron_expression,
          execution_mode: formData.execution_mode,
          thinking_mode: formData.thinking_mode,
        });
        toast({
          title: t.common.success,
          description: t.scheduledTasks.taskUpdated,
        });
      } else {
        await createScheduledTask({
          ...formData,
          execution_mode: formData.execution_mode,
          thinking_mode: formData.thinking_mode,
        });
        toast({
          title: t.common.success,
          description: t.scheduledTasks.taskCreated,
        });
      }
      setShowDialog(false);
      loadTasks();
    } catch (error) {
      toast({
        title: t.common.error,
        description: getErrorMessage(error),
        variant: 'destructive',
      });
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (uuid: string) => {
    if (!window.confirm(t.scheduledTasks.deleteConfirm)) return;
    try {
      await deleteScheduledTask(uuid);
      toast({
        title: t.common.success,
        description: t.scheduledTasks.taskDeleted,
      });
      loadTasks();
    } catch (error) {
      toast({
        title: t.common.error,
        description: getErrorMessage(error),
        variant: 'destructive',
      });
    }
  };

  const handleToggleStatus = async (task: ScheduledTask) => {
    try {
      if (task.status === 'enabled') {
        await disableScheduledTask(task.uuid);
        toast({
          title: t.common.success,
          description: t.scheduledTasks.taskDisabled,
        });
      } else {
        await enableScheduledTask(task.uuid);
        toast({
          title: t.common.success,
          description: t.scheduledTasks.taskEnabled,
        });
      }
      loadTasks();
    } catch (error) {
      toast({
        title: t.common.error,
        description: getErrorMessage(error),
        variant: 'destructive',
      });
    }
  };

  const handleRunNow = async (uuid: string) => {
    try {
      await runScheduledTaskNow(uuid);
      toast({
        title: t.common.success,
        description: t.scheduledTasks.taskStarted,
      });
      
      // 轮询检查任务状态，直到任务完成
      const pollInterval = setInterval(async () => {
        try {
          const data = await listScheduledTasks();
          const task = data.tasks.find(t => t.uuid === uuid);
          
          if (task && task.status !== 'running') {
            // 任务已完成，停止轮询并刷新列表
            clearInterval(pollInterval);
            setTasks(data.tasks);
          } else if (task && task.status === 'running') {
            // 任务仍在运行，更新列表以显示最新状态
            setTasks(data.tasks);
          }
        } catch (error) {
          // 出错时停止轮询
          clearInterval(pollInterval);
          console.error('Failed to poll task status:', error);
        }
      }, 2000); // 每 2 秒检查一次
      
      // 设置最大轮询时间（5分钟）
      setTimeout(() => {
        clearInterval(pollInterval);
        loadTasks(); // 最后刷新一次
      }, 300000);
      
    } catch (error) {
      toast({
        title: t.common.error,
        description: getErrorMessage(error),
        variant: 'destructive',
      });
    }
  };

  const handleViewHistory = async (task: ScheduledTask) => {
    try {
      setHistoryLoading(true);
      setShowHistoryDialog(true);
      const data = await getTaskHistory(task.uuid, 20);
      setSelectedTaskHistory(data.history);
    } catch (error) {
      toast({
        title: t.common.error,
        description: getErrorMessage(error),
        variant: 'destructive',
      });
    } finally {
      setHistoryLoading(false);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'enabled':
        return (
          <Badge variant="default" className="bg-green-500">
            <Power className="w-3 h-3 mr-1" />
            {t.scheduledTasks.enabled}
          </Badge>
        );
      case 'disabled':
        return (
          <Badge variant="secondary">
            <PowerOff className="w-3 h-3 mr-1" />
            {t.scheduledTasks.disabled}
          </Badge>
        );
      case 'running':
        return (
          <Badge variant="default" className="bg-blue-500">
            <Loader2 className="w-3 h-3 mr-1 animate-spin" />
            {t.scheduledTasks.running}
          </Badge>
        );
      default:
        return <Badge variant="outline">{status}</Badge>;
    }
  };

  const getHistoryStatusIcon = (status: string) => {
    switch (status) {
      case 'success':
        return <CheckCircle2 className="w-4 h-4 text-green-500" />;
      case 'failed':
        return <XCircle className="w-4 h-4 text-red-500" />;
      case 'aborted':
        return <AlertCircle className="w-4 h-4 text-yellow-500" />;
      default:
        return null;
    }
  };

  const formatDateTime = (dateStr: string | null) => {
    if (!dateStr) return t.scheduledTasks.never;
    const date = new Date(dateStr);
    return date.toLocaleString();
  };

  const cronExamples = [
    { label: t.scheduledTasks.cronExampleDaily, value: '0 9 * * *' },
    { label: t.scheduledTasks.cronExampleEvery5Min, value: '*/5 * * * *' },
    { label: t.scheduledTasks.cronExampleHourly, value: '0 * * * *' },
    { label: t.scheduledTasks.cronExampleWeekdays, value: '0 9 * * 1-5' },
    { label: t.scheduledTasks.cronExampleSunday, value: '0 20 * * 0' },
    { label: t.scheduledTasks.cronExampleMonthly, value: '0 0 1 * *' },
  ];

  return (
    <div className="container mx-auto p-6 max-w-7xl">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <Clock className="w-8 h-8" />
            {t.scheduledTasks.title}
          </h1>
          <p className="text-slate-500 dark:text-slate-400 mt-1">
            {t.scheduledTasks.subtitle}
          </p>
        </div>
        <Button onClick={handleCreate}>
          <Plus className="w-4 h-4 mr-2" />
          {t.scheduledTasks.createTask}
        </Button>
      </div>

      {loading ? (
        <div className="flex justify-center items-center h-64">
          <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
        </div>
      ) : tasks.length === 0 ? (
        <div className="text-center py-12">
          <Clock className="w-16 h-16 mx-auto text-slate-300 dark:text-slate-600 mb-4" />
          <p className="text-slate-500 dark:text-slate-400 mb-4">
            {t.scheduledTasks.noTasks}
          </p>
          <Button onClick={handleCreate}>
            <Plus className="w-4 h-4 mr-2" />
            {t.scheduledTasks.createFirst}
          </Button>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {tasks.map(task => (
            <Card
              key={task.uuid}
              className="hover:shadow-md transition-shadow"
            >
              <CardHeader>
                <div className="flex justify-between items-start">
                  <CardTitle className="text-lg">{task.name}</CardTitle>
                  {getStatusBadge(task.status)}
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="text-sm space-y-2">
                  <div className="flex items-center gap-2 text-slate-600 dark:text-slate-400">
                    <Calendar className="w-4 h-4" />
                    <span className="font-mono">{task.cron_expression}</span>
                  </div>
                  <div className="text-slate-600 dark:text-slate-400">
                    <strong>{t.scheduledTasks.device}:</strong> {task.device_id}
                  </div>
                  <div className="text-slate-600 dark:text-slate-400">
                    <strong>{t.scheduledTasks.executionMode}:</strong>{' '}
                    {task.execution_mode === 'classic' && t.scheduledTasks.modeClassic}
                    {task.execution_mode === 'dual_model' && t.scheduledTasks.modeDualModel}
                    {task.execution_mode === 'layered_agent' && t.scheduledTasks.modeLayeredAgent}
                    {!task.execution_mode && t.scheduledTasks.modeClassic}
                  </div>
                  <div className="text-slate-600 dark:text-slate-400">
                    <strong>{t.scheduledTasks.nextRun}</strong> {formatDateTime(task.next_run)}
                  </div>
                  <div className="text-slate-600 dark:text-slate-400">
                    <strong>{t.scheduledTasks.lastRun}</strong> {formatDateTime(task.last_run)}
                  </div>
                </div>
                <p className="text-sm text-slate-600 dark:text-slate-400 line-clamp-2">
                  {task.message}
                </p>
                <div className="flex flex-wrap gap-2 pt-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleEdit(task)}
                  >
                    <Edit className="w-3 h-3 mr-1" />
                    {t.scheduledTasks.edit}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleToggleStatus(task)}
                    disabled={task.status === 'running'}
                  >
                    {task.status === 'enabled' ? (
                      <>
                        <PowerOff className="w-3 h-3 mr-1" />
                        {t.scheduledTasks.disable}
                      </>
                    ) : (
                      <>
                        <Power className="w-3 h-3 mr-1" />
                        {t.scheduledTasks.enable}
                      </>
                    )}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleRunNow(task.uuid)}
                    disabled={task.status === 'running'}
                  >
                    <Play className="w-3 h-3 mr-1" />
                    {t.scheduledTasks.runNow}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleViewHistory(task)}
                  >
                    <History className="w-3 h-3 mr-1" />
                    {t.scheduledTasks.history}
                  </Button>
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => handleDelete(task.uuid)}
                  >
                    <Trash2 className="w-3 h-3 mr-1" />
                    {t.scheduledTasks.delete}
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Create/Edit Dialog */}
      <Dialog open={showDialog} onOpenChange={setShowDialog}>
        <DialogContent className="sm:max-w-[700px] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {editingTask ? t.scheduledTasks.editTask : t.scheduledTasks.createNew}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="name">{t.scheduledTasks.taskName}</Label>
              <Input
                id="name"
                value={formData.name}
                onChange={e =>
                  setFormData(prev => ({ ...prev, name: e.target.value }))
                }
                placeholder={t.scheduledTasks.taskNamePlaceholder}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="device">{t.scheduledTasks.device}</Label>
              <Select
                value={formData.device_id}
                onValueChange={value =>
                  setFormData(prev => ({ ...prev, device_id: value }))
                }
              >
                <SelectTrigger>
                  <SelectValue placeholder={t.scheduledTasks.selectDevice} />
                </SelectTrigger>
                <SelectContent>
                  {devices.map(device => (
                    <SelectItem key={device.id} value={device.id}>
                      {device.model} ({device.id})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="execution_mode">{t.scheduledTasks.executionMode}</Label>
              <Select
                value={formData.execution_mode}
                onValueChange={value =>
                  setFormData(prev => ({
                    ...prev,
                    execution_mode: value as 'classic' | 'dual_model' | 'layered_agent',
                  }))
                }
              >
                <SelectTrigger>
                  <SelectValue placeholder={t.scheduledTasks.selectExecutionMode} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="classic">{t.scheduledTasks.modeClassic}</SelectItem>
                  <SelectItem value="dual_model">{t.scheduledTasks.modeDualModel}</SelectItem>
                  <SelectItem value="layered_agent">{t.scheduledTasks.modeLayeredAgent}</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-slate-500">
                {formData.execution_mode === 'classic' && t.scheduledTasks.modeClassicDesc}
                {formData.execution_mode === 'dual_model' && t.scheduledTasks.modeDualModelDesc}
                {formData.execution_mode === 'layered_agent' && t.scheduledTasks.modeLayeredAgentDesc}
              </p>
            </div>
            {formData.execution_mode === 'dual_model' && (
              <div className="space-y-2">
                <Label htmlFor="thinking_mode">{t.scheduledTasks.thinkingMode}</Label>
                <Select
                  value={formData.thinking_mode}
                  onValueChange={value =>
                    setFormData(prev => ({
                      ...prev,
                      thinking_mode: value as 'fast' | 'deep' | 'turbo',
                    }))
                  }
                >
                  <SelectTrigger>
                    <SelectValue placeholder={t.scheduledTasks.selectThinkingMode} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="fast">{t.scheduledTasks.thinkingFast}</SelectItem>
                    <SelectItem value="deep">{t.scheduledTasks.thinkingDeep}</SelectItem>
                    <SelectItem value="turbo">{t.scheduledTasks.thinkingTurbo}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            )}
            <div className="space-y-2">
              <Label htmlFor="cron">{t.scheduledTasks.cronExpression}</Label>
              <Input
                id="cron"
                value={formData.cron_expression}
                onChange={e =>
                  setFormData(prev => ({
                    ...prev,
                    cron_expression: e.target.value,
                  }))
                }
                placeholder={t.scheduledTasks.cronPlaceholder}
                className="font-mono"
              />
              <div className="text-xs text-slate-500 space-y-1">
                <p>{t.scheduledTasks.cronFormat}</p>
                <p className="font-semibold">{t.scheduledTasks.cronExamples}</p>
                <div className="grid grid-cols-2 gap-1">
                  {cronExamples.map(example => (
                    <button
                      key={example.value}
                      type="button"
                      className="text-left hover:text-blue-600 dark:hover:text-blue-400"
                      onClick={() =>
                        setFormData(prev => ({
                          ...prev,
                          cron_expression: example.value,
                        }))
                      }
                    >
                      • {example.label}: <code>{example.value}</code>
                    </button>
                  ))}
                </div>
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="message">{t.scheduledTasks.taskMessage}</Label>
              <Textarea
                id="message"
                value={formData.message}
                onChange={e =>
                  setFormData(prev => ({ ...prev, message: e.target.value }))
                }
                placeholder={t.scheduledTasks.taskMessagePlaceholder}
                rows={4}
                className="resize-none !rounded-lg"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowDialog(false)}>
              {t.scheduledTasks.cancel}
            </Button>
            <Button
              onClick={handleSave}
              disabled={
                !formData.name.trim() ||
                !formData.device_id ||
                !formData.message.trim() ||
                !formData.cron_expression.trim() ||
                saving
              }
            >
              {saving ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  {t.scheduledTasks.saving}
                </>
              ) : (
                t.scheduledTasks.save
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* History Dialog */}
      <Dialog open={showHistoryDialog} onOpenChange={setShowHistoryDialog}>
        <DialogContent className="sm:max-w-[800px] max-h-[90vh]">
          <DialogHeader>
            <DialogTitle>{t.scheduledTasks.executionHistory}</DialogTitle>
          </DialogHeader>
          <div className="py-4 max-h-[60vh] overflow-y-auto">
            {historyLoading ? (
              <div className="flex justify-center items-center h-32">
                <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
              </div>
            ) : selectedTaskHistory.length === 0 ? (
              <div className="text-center py-8 text-slate-500">
                {t.scheduledTasks.noHistoryYet}
              </div>
            ) : (
              <div className="space-y-3">
                {selectedTaskHistory.map(history => (
                  <Card key={history.uuid}>
                    <CardContent className="pt-4">
                      <div className="flex items-start gap-3">
                        {getHistoryStatusIcon(history.status)}
                        <div className="flex-1 space-y-1">
                          <div className="flex justify-between items-start">
                            <div>
                              <p className="font-medium">{history.task_name}</p>
                              <p className="text-sm text-slate-500">
                                {formatDateTime(history.started_at)}
                              </p>
                            </div>
                            <Badge
                              variant={
                                history.status === 'success'
                                  ? 'default'
                                  : 'destructive'
                              }
                            >
                              {history.status === 'success' && t.scheduledTasks.success}
                              {history.status === 'failed' && t.scheduledTasks.failed}
                              {history.status === 'aborted' && t.scheduledTasks.aborted}
                            </Badge>
                          </div>
                          {history.error && (
                            <p className="text-sm text-red-600 dark:text-red-400">
                              {t.scheduledTasks.error}: {history.error}
                            </p>
                          )}
                          {history.result && (
                            <div className="text-sm text-slate-600 dark:text-slate-400 whitespace-pre-wrap">
                              {history.result}
                            </div>
                          )}
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
