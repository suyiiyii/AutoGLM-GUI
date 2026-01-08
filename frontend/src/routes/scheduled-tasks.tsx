import { createFileRoute } from '@tanstack/react-router';
import { useState, useEffect } from 'react';
import {
  listScheduledTasks,
  createScheduledTask,
  updateScheduledTask,
  deleteScheduledTask,
  enableScheduledTask,
  disableScheduledTask,
  listWorkflows,
  getDevices,
  type ScheduledTaskResponse,
  type Workflow,
  type Device,
} from '../api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
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
  Plus,
  Edit,
  Trash2,
  Loader2,
  Clock,
  CheckCircle,
  XCircle,
} from 'lucide-react';
import { useTranslation } from '../lib/i18n-context';

export const Route = createFileRoute('/scheduled-tasks')({
  component: ScheduledTasksComponent,
});

interface TaskFormData {
  name: string;
  workflow_uuid: string;
  device_serialno: string;
  cron_expression: string;
  enabled: boolean;
}

const cronPresets = [
  { key: 'everyHour', cron: '0 * * * *' },
  { key: 'daily8am', cron: '0 8 * * *' },
  { key: 'daily12pm', cron: '0 12 * * *' },
  { key: 'daily6pm', cron: '0 18 * * *' },
  { key: 'weeklyMonday', cron: '0 9 * * 1' },
] as const;

function ScheduledTasksComponent() {
  const t = useTranslation();
  const [tasks, setTasks] = useState<ScheduledTaskResponse[]>([]);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [devices, setDevices] = useState<Device[]>([]);
  const [loading, setLoading] = useState(true);
  const [showDialog, setShowDialog] = useState(false);
  const [editingTask, setEditingTask] = useState<ScheduledTaskResponse | null>(
    null
  );
  const [formData, setFormData] = useState<TaskFormData>({
    name: '',
    workflow_uuid: '',
    device_serialno: '',
    cron_expression: '',
    enabled: true,
  });
  const [saving, setSaving] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [taskToDelete, setTaskToDelete] = useState<string | null>(null);

  // Load data on mount
  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const [tasksData, workflowsData, devicesData] = await Promise.all([
        listScheduledTasks(),
        listWorkflows(),
        getDevices(),
      ]);
      setTasks(tasksData.tasks);
      setWorkflows(workflowsData.workflows);
      setDevices(devicesData);
    } catch (error) {
      console.error('Failed to load data:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = () => {
    setEditingTask(null);
    setFormData({
      name: '',
      workflow_uuid: '',
      device_serialno: '',
      cron_expression: '',
      enabled: true,
    });
    setShowDialog(true);
  };

  const handleEdit = (task: ScheduledTaskResponse) => {
    setEditingTask(task);
    setFormData({
      name: task.name,
      workflow_uuid: task.workflow_uuid,
      device_serialno: task.device_serialno,
      cron_expression: task.cron_expression,
      enabled: task.enabled,
    });
    setShowDialog(true);
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      if (editingTask) {
        await updateScheduledTask(editingTask.id, formData);
      } else {
        await createScheduledTask(formData);
      }
      setShowDialog(false);
      loadData();
    } catch (error) {
      console.error('Failed to save task:', error);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!taskToDelete) return;
    try {
      await deleteScheduledTask(taskToDelete);
      loadData();
    } catch (error) {
      console.error('Failed to delete task:', error);
    }
    setDeleteDialogOpen(false);
    setTaskToDelete(null);
  };

  const handleToggleEnabled = async (task: ScheduledTaskResponse) => {
    try {
      if (task.enabled) {
        await disableScheduledTask(task.id);
      } else {
        await enableScheduledTask(task.id);
      }
      loadData();
    } catch (error) {
      console.error('Failed to toggle task:', error);
    }
  };

  const getWorkflowName = (uuid: string): string => {
    const workflow = workflows.find(w => w.uuid === uuid);
    return workflow?.name || uuid;
  };

  const getDeviceName = (serialno: string): string => {
    const device = devices.find(d => d.serial === serialno);
    return device?.model || serialno;
  };

  const formatTime = (timeStr: string | null): string => {
    if (!timeStr) return t.scheduledTasks.never;
    const date = new Date(timeStr);
    return date.toLocaleString('zh-CN', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const isFormValid =
    formData.name.trim() &&
    formData.workflow_uuid &&
    formData.device_serialno &&
    formData.cron_expression.trim();

  return (
    <div className="container mx-auto p-6 max-w-7xl">
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold">{t.scheduledTasks.title}</h1>
        <Button onClick={handleCreate}>
          <Plus className="w-4 h-4 mr-2" />
          {t.scheduledTasks.create}
        </Button>
      </div>

      {/* Content */}
      {loading ? (
        <div className="flex justify-center items-center h-64">
          <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
        </div>
      ) : tasks.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-slate-500 dark:text-slate-400">
            {t.scheduledTasks.noTasks}
          </p>
          <p className="text-sm text-slate-400 dark:text-slate-500 mt-2">
            {t.scheduledTasks.noTasksDesc}
          </p>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {tasks.map(task => (
            <Card key={task.id} className="hover:shadow-md transition-shadow">
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-lg truncate flex-1 mr-2">
                    {task.name}
                  </CardTitle>
                  <Switch
                    checked={task.enabled}
                    onCheckedChange={() => handleToggleEnabled(task)}
                  />
                </div>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {/* Workflow */}
                  <div className="text-sm">
                    <span className="text-slate-500 dark:text-slate-400">
                      {t.scheduledTasks.workflow}:{' '}
                    </span>
                    <span className="font-medium">
                      {getWorkflowName(task.workflow_uuid)}
                    </span>
                  </div>

                  {/* Device */}
                  <div className="text-sm">
                    <span className="text-slate-500 dark:text-slate-400">
                      {t.scheduledTasks.device}:{' '}
                    </span>
                    <span className="font-medium">
                      {getDeviceName(task.device_serialno)}
                    </span>
                  </div>

                  {/* Cron */}
                  <div className="text-sm">
                    <Badge variant="outline" className="font-mono">
                      <Clock className="w-3 h-3 mr-1" />
                      {task.cron_expression}
                    </Badge>
                  </div>

                  {/* Last run */}
                  <div className="text-sm flex items-center gap-2">
                    <span className="text-slate-500 dark:text-slate-400">
                      {t.scheduledTasks.lastRun}:
                    </span>
                    {task.last_run_time ? (
                      <>
                        {task.last_run_success ? (
                          <CheckCircle className="w-4 h-4 text-green-500" />
                        ) : (
                          <XCircle className="w-4 h-4 text-red-500" />
                        )}
                        <span>{formatTime(task.last_run_time)}</span>
                      </>
                    ) : (
                      <span className="text-slate-400">
                        {t.scheduledTasks.never}
                      </span>
                    )}
                  </div>

                  {/* Next run */}
                  <div className="text-sm">
                    <span className="text-slate-500 dark:text-slate-400">
                      {t.scheduledTasks.nextRun}:{' '}
                    </span>
                    <span>{formatTime(task.next_run_time)}</span>
                  </div>

                  {/* Actions */}
                  <div className="flex gap-2 pt-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleEdit(task)}
                    >
                      <Edit className="w-3 h-3 mr-1" />
                      {t.common.edit}
                    </Button>
                    <Button
                      variant="destructive"
                      size="sm"
                      onClick={() => {
                        setTaskToDelete(task.id);
                        setDeleteDialogOpen(true);
                      }}
                    >
                      <Trash2 className="w-3 h-3 mr-1" />
                      {t.common.delete}
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Create/Edit Dialog */}
      <Dialog open={showDialog} onOpenChange={setShowDialog}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle>
              {editingTask ? t.scheduledTasks.edit : t.scheduledTasks.create}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            {/* Task Name */}
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

            {/* Workflow */}
            <div className="space-y-2">
              <Label>{t.scheduledTasks.workflow}</Label>
              {workflows.length === 0 ? (
                <p className="text-sm text-amber-600 dark:text-amber-400">
                  {t.scheduledTasks.noWorkflows}
                </p>
              ) : (
                <Select
                  value={formData.workflow_uuid}
                  onValueChange={(value: string) =>
                    setFormData(prev => ({ ...prev, workflow_uuid: value }))
                  }
                >
                  <SelectTrigger>
                    <SelectValue
                      placeholder={t.scheduledTasks.selectWorkflow}
                    />
                  </SelectTrigger>
                  <SelectContent>
                    {workflows.map(workflow => (
                      <SelectItem key={workflow.uuid} value={workflow.uuid}>
                        {workflow.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>

            {/* Device */}
            <div className="space-y-2">
              <Label>{t.scheduledTasks.device}</Label>
              {devices.length === 0 ? (
                <p className="text-sm text-amber-600 dark:text-amber-400">
                  {t.scheduledTasks.noDevicesOnline}
                </p>
              ) : (
                <Select
                  value={formData.device_serialno}
                  onValueChange={(value: string) =>
                    setFormData(prev => ({ ...prev, device_serialno: value }))
                  }
                >
                  <SelectTrigger>
                    <SelectValue placeholder={t.scheduledTasks.selectDevice} />
                  </SelectTrigger>
                  <SelectContent>
                    {devices.map(device => (
                      <SelectItem key={device.serial} value={device.serial}>
                        {device.model || device.serial}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>

            {/* Cron Expression */}
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
              <p className="text-xs text-slate-500 dark:text-slate-400">
                {t.scheduledTasks.cronHelp}
              </p>
            </div>

            {/* Presets */}
            <div className="space-y-2">
              <Label>{t.scheduledTasks.presets}</Label>
              <div className="flex flex-wrap gap-2">
                {cronPresets.map(preset => (
                  <Button
                    key={preset.key}
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      setFormData(prev => ({
                        ...prev,
                        cron_expression: preset.cron,
                      }))
                    }
                  >
                    {
                      t.scheduledTasks.preset[
                        preset.key as keyof typeof t.scheduledTasks.preset
                      ]
                    }
                  </Button>
                ))}
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowDialog(false)}>
              {t.common.cancel}
            </Button>
            <Button onClick={handleSave} disabled={!isFormValid || saving}>
              {saving ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  {t.common.loading}
                </>
              ) : (
                t.common.save
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Dialog */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t.common.delete}</AlertDialogTitle>
            <AlertDialogDescription>
              {t.scheduledTasks.deleteConfirm}
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
    </div>
  );
}
