import React, { useState, useEffect, useCallback } from 'react';
import {
  FolderOpen,
  Plus,
  Edit,
  Trash2,
  GripVertical,
  Loader2,
  AlertCircle,
} from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ConfirmDialog } from './ConfirmDialog';
import type { DeviceGroup } from '../api';
import {
  listDeviceGroups,
  createDeviceGroup,
  updateDeviceGroup,
  deleteDeviceGroup,
  reorderDeviceGroups,
} from '../api';
import { useTranslation } from '../lib/i18n-context';
import type { ToastType } from './Toast';

interface GroupManageDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onGroupsChanged?: () => void;
  showToast?: (message: string, type: ToastType) => void;
}

export function GroupManageDialog({
  isOpen,
  onClose,
  onGroupsChanged,
  showToast,
}: GroupManageDialogProps) {
  const t = useTranslation();
  const [groups, setGroups] = useState<DeviceGroup[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Create group state
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [newGroupName, setNewGroupName] = useState('');
  const [creating, setCreating] = useState(false);

  // Edit group state
  const [editingGroup, setEditingGroup] = useState<DeviceGroup | null>(null);
  const [editingName, setEditingName] = useState('');
  const [saving, setSaving] = useState(false);

  // Delete group state
  const [deletingGroup, setDeletingGroup] = useState<DeviceGroup | null>(null);
  const [deleting, setDeleting] = useState(false);

  // Drag and drop state
  const [draggedGroupId, setDraggedGroupId] = useState<string | null>(null);

  const fetchGroups = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await listDeviceGroups();
      setGroups(response.groups.sort((a, b) => a.order - b.order));
    } catch (err) {
      console.error('Failed to fetch groups:', err);
      setError(t.deviceGroups?.fetchError || '获取分组失败');
    } finally {
      setLoading(false);
    }
  }, [t.deviceGroups?.fetchError]);

  useEffect(() => {
    if (isOpen) {
      fetchGroups();
    }
  }, [isOpen, fetchGroups]);

  const handleCreateGroup = async () => {
    if (!newGroupName.trim()) return;

    setCreating(true);
    try {
      await createDeviceGroup(newGroupName.trim());
      setShowCreateDialog(false);
      setNewGroupName('');
      await fetchGroups();
      if (onGroupsChanged) onGroupsChanged();
      if (showToast) {
        showToast(t.deviceGroups?.createSuccess || '分组创建成功', 'success');
      }
    } catch (err) {
      console.error('Failed to create group:', err);
      if (showToast) {
        showToast(t.deviceGroups?.createError || '创建分组失败', 'error');
      }
    } finally {
      setCreating(false);
    }
  };

  const handleUpdateGroup = async () => {
    if (!editingGroup || !editingName.trim()) return;

    setSaving(true);
    try {
      await updateDeviceGroup(editingGroup.id, editingName.trim());
      setEditingGroup(null);
      setEditingName('');
      await fetchGroups();
      if (onGroupsChanged) onGroupsChanged();
      if (showToast) {
        showToast(t.deviceGroups?.updateSuccess || '分组更新成功', 'success');
      }
    } catch (err) {
      console.error('Failed to update group:', err);
      if (showToast) {
        showToast(t.deviceGroups?.updateError || '更新分组失败', 'error');
      }
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteGroup = async () => {
    if (!deletingGroup) return;

    setDeleting(true);
    try {
      const result = await deleteDeviceGroup(deletingGroup.id);
      if (result.success) {
        setDeletingGroup(null);
        await fetchGroups();
        if (onGroupsChanged) onGroupsChanged();
        if (showToast) {
          showToast(t.deviceGroups?.deleteSuccess || '分组删除成功', 'success');
        }
      } else {
        if (showToast) {
          showToast(
            result.message || t.deviceGroups?.deleteError || '删除分组失败',
            'error'
          );
        }
      }
    } catch (err) {
      console.error('Failed to delete group:', err);
      if (showToast) {
        showToast(t.deviceGroups?.deleteError || '删除分组失败', 'error');
      }
    } finally {
      setDeleting(false);
    }
  };

  const handleDragStart = (groupId: string) => {
    setDraggedGroupId(groupId);
  };

  const handleDragOver = (e: React.DragEvent, targetGroupId: string) => {
    e.preventDefault();
    if (!draggedGroupId || draggedGroupId === targetGroupId) return;

    // Reorder locally for visual feedback
    const newGroups = [...groups];
    const draggedIndex = newGroups.findIndex(g => g.id === draggedGroupId);
    const targetIndex = newGroups.findIndex(g => g.id === targetGroupId);

    if (draggedIndex === -1 || targetIndex === -1) return;

    const [removed] = newGroups.splice(draggedIndex, 1);
    newGroups.splice(targetIndex, 0, removed);

    setGroups(newGroups);
  };

  const handleDragEnd = async () => {
    if (!draggedGroupId) return;

    // Save the new order
    const groupIds = groups.map(g => g.id);
    try {
      await reorderDeviceGroups(groupIds);
      if (onGroupsChanged) onGroupsChanged();
    } catch (err) {
      console.error('Failed to reorder groups:', err);
      // Refresh to get the correct order
      await fetchGroups();
      if (showToast) {
        showToast(t.deviceGroups?.reorderError || '调整顺序失败', 'error');
      }
    } finally {
      setDraggedGroupId(null);
    }
  };

  return (
    <>
      <Dialog open={isOpen} onOpenChange={open => !open && onClose()}>
        <DialogContent className="sm:max-w-md max-h-[80vh] overflow-hidden flex flex-col">
          <DialogHeader>
            <DialogTitle>
              {t.deviceGroups?.manageTitle || '管理设备分组'}
            </DialogTitle>
            <DialogDescription>
              {t.deviceGroups?.manageDescription ||
                '创建、编辑、删除和排序设备分组。拖拽分组可调整顺序。'}
            </DialogDescription>
          </DialogHeader>

          <div className="flex-1 overflow-y-auto py-4">
            {loading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
              </div>
            ) : error ? (
              <div className="flex flex-col items-center justify-center py-8 text-center">
                <AlertCircle className="h-8 w-8 text-red-500 mb-2" />
                <p className="text-sm text-red-600 dark:text-red-400">
                  {error}
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={fetchGroups}
                  className="mt-2"
                >
                  {t.common?.retry || '重试'}
                </Button>
              </div>
            ) : (
              <div className="space-y-2">
                {groups.map(group => (
                  <div
                    key={group.id}
                    draggable={!group.is_default}
                    onDragStart={() => handleDragStart(group.id)}
                    onDragOver={e => handleDragOver(e, group.id)}
                    onDragEnd={handleDragEnd}
                    className={`
                      flex items-center gap-2 p-3 rounded-lg border
                      ${
                        draggedGroupId === group.id
                          ? 'border-[#1d9bf0] bg-blue-50 dark:bg-blue-950/20'
                          : 'border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800'
                      }
                      ${group.is_default ? 'opacity-80' : 'cursor-move'}
                      transition-colors
                    `}
                  >
                    {/* Drag handle */}
                    {!group.is_default && (
                      <GripVertical className="w-4 h-4 text-slate-400 flex-shrink-0 cursor-grab" />
                    )}
                    {group.is_default && <div className="w-4" />}

                    {/* Group icon and name */}
                    <FolderOpen className="w-4 h-4 text-slate-400 flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <span className="text-sm font-medium text-slate-700 dark:text-slate-300 truncate block">
                        {group.name}
                      </span>
                      <span className="text-xs text-slate-400 dark:text-slate-500">
                        {group.device_count}{' '}
                        {t.deviceGroups?.deviceCount || '台设备'}
                        {group.is_default && (
                          <span className="ml-2 text-slate-400">
                            ({t.deviceGroups?.defaultGroup || '默认'})
                          </span>
                        )}
                      </span>
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-1 flex-shrink-0">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-slate-400 hover:text-[#1d9bf0]"
                        onClick={() => {
                          setEditingGroup(group);
                          setEditingName(group.name);
                        }}
                      >
                        <Edit className="w-3.5 h-3.5" />
                      </Button>
                      {!group.is_default && (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 text-slate-400 hover:text-red-500"
                          onClick={() => setDeletingGroup(group)}
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </Button>
                      )}
                    </div>
                  </div>
                ))}

                {/* Add new group button */}
                <Button
                  variant="outline"
                  className="w-full justify-start gap-2"
                  onClick={() => setShowCreateDialog(true)}
                >
                  <Plus className="w-4 h-4" />
                  {t.deviceGroups?.createNew || '新建分组'}
                </Button>
              </div>
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={onClose}>
              {t.common?.close || '关闭'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Create Group Dialog */}
      <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>
              {t.deviceGroups?.createTitle || '新建分组'}
            </DialogTitle>
            <DialogDescription>
              {t.deviceGroups?.createDescription || '为设备创建一个新的分组。'}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="new-group-name">
                {t.deviceGroups?.groupNameLabel || '分组名称'}
              </Label>
              <Input
                id="new-group-name"
                value={newGroupName}
                onChange={e => setNewGroupName(e.target.value)}
                placeholder={
                  t.deviceGroups?.groupNamePlaceholder || '请输入分组名称'
                }
                maxLength={50}
                onKeyDown={e => {
                  if (e.key === 'Enter' && !creating) {
                    handleCreateGroup();
                  }
                }}
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowCreateDialog(false)}
              disabled={creating}
            >
              {t.common?.cancel || '取消'}
            </Button>
            <Button
              onClick={handleCreateGroup}
              disabled={!newGroupName.trim() || creating}
            >
              {creating ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  {t.common?.loading || '加载中...'}
                </>
              ) : (
                t.common?.create || '创建'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Group Dialog */}
      <Dialog
        open={!!editingGroup}
        onOpenChange={open => !open && setEditingGroup(null)}
      >
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>{t.deviceGroups?.editTitle || '编辑分组'}</DialogTitle>
            <DialogDescription>
              {t.deviceGroups?.editDescription || '修改分组名称。'}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="edit-group-name">
                {t.deviceGroups?.groupNameLabel || '分组名称'}
              </Label>
              <Input
                id="edit-group-name"
                value={editingName}
                onChange={e => setEditingName(e.target.value)}
                placeholder={
                  t.deviceGroups?.groupNamePlaceholder || '请输入分组名称'
                }
                maxLength={50}
                onKeyDown={e => {
                  if (e.key === 'Enter' && !saving) {
                    handleUpdateGroup();
                  }
                }}
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setEditingGroup(null)}
              disabled={saving}
            >
              {t.common?.cancel || '取消'}
            </Button>
            <Button
              onClick={handleUpdateGroup}
              disabled={!editingName.trim() || saving}
            >
              {saving ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  {t.common?.loading || '加载中...'}
                </>
              ) : (
                t.common?.save || '保存'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        isOpen={!!deletingGroup}
        title={t.deviceGroups?.deleteTitle || '删除分组'}
        content={
          t.deviceGroups?.deleteContent?.replace(
            '{name}',
            deletingGroup?.name || ''
          ) ||
          `确定要删除分组 "${deletingGroup?.name}" 吗？该分组内的设备将被移回默认分组。`
        }
        onConfirm={handleDeleteGroup}
        onCancel={() => setDeletingGroup(null)}
        confirmText={
          deleting
            ? t.common?.loading || '加载中...'
            : t.common?.delete || '删除'
        }
        confirmVariant="destructive"
        disabled={deleting}
      />
    </>
  );
}
