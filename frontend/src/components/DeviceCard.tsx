import React, { useState } from 'react';
import {
  Edit,
  Loader2,
  Server,
  Smartphone,
  Trash2,
  Wifi,
  WifiOff,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ConfirmDialog } from './ConfirmDialog';
import { useTranslation } from '../lib/i18n-context';
import { removeRemoteDevice, updateDeviceName } from '../api';
import type { AgentStatus } from '../api';
import type { ToastType } from './Toast';

interface DeviceCardProps {
  id: string;
  serial: string;
  model: string;
  status: string;
  connectionType?: string;
  displayName?: string | null;
  agent?: AgentStatus | null;
  isActive: boolean;
  onClick: () => void;
  onConnectWifi?: () => Promise<void>;
  onDisconnectWifi?: () => Promise<void>;
  onNameUpdated?: () => void;
  showToast?: (message: string, type: ToastType) => void;
}

export function DeviceCard({
  id: _id,
  serial,
  model,
  status,
  connectionType,
  displayName,
  agent,
  isActive,
  onClick,
  onConnectWifi,
  onDisconnectWifi,
  onNameUpdated,
  showToast,
}: DeviceCardProps) {
  const t = useTranslation();
  const isOnline = status === 'device';
  const isUsb = connectionType === 'usb';
  const isWifi = connectionType === 'wifi';
  const isRemote = connectionType === 'remote';
  const [loading, setLoading] = useState(false);
  const [showWifiConfirm, setShowWifiConfirm] = useState(false);
  const [showDisconnectConfirm, setShowDisconnectConfirm] = useState(false);
  const [showEditDialog, setShowEditDialog] = useState(false);
  const [editingName, setEditingName] = useState('');
  const [saving, setSaving] = useState(false);

  const actualDisplayName = displayName || model || t.deviceCard.unknownDevice;

  // Determine agent status indicator class and tooltip
  const getAgentStatusClass = () => {
    if (!isOnline) return 'status-agent-none';
    if (!agent) return 'status-agent-none';
    switch (agent.state) {
      case 'idle':
        return 'status-agent-idle';
      case 'busy':
        return 'status-agent-busy';
      case 'error':
        return 'status-agent-error';
      case 'initializing':
        return 'status-agent-initializing';
      default:
        return 'status-agent-none';
    }
  };

  const getCurrentStatusText = () => {
    if (!isOnline) return t.deviceCard.statusTooltip.none;
    if (!agent) return t.deviceCard.statusTooltip.none;
    switch (agent.state) {
      case 'idle':
        return t.deviceCard.statusTooltip.idle;
      case 'busy':
        return t.deviceCard.statusTooltip.busy;
      case 'error':
        return t.deviceCard.statusTooltip.error;
      case 'initializing':
        return t.deviceCard.statusTooltip.initializing;
      default:
        return t.deviceCard.statusTooltip.none;
    }
  };

  const handleWifiClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (loading || !onConnectWifi) return;
    setShowWifiConfirm(true);
  };

  const handleDisconnectClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (loading || !onDisconnectWifi) return;
    setShowDisconnectConfirm(true);
  };

  const handleConfirmWifi = async () => {
    setShowWifiConfirm(false);
    setLoading(true);
    try {
      if (onConnectWifi) {
        await onConnectWifi();
      }
    } finally {
      setLoading(false);
    }
  };

  const handleConfirmDisconnect = async () => {
    setShowDisconnectConfirm(false);
    setLoading(true);
    try {
      if (onDisconnectWifi) {
        await onDisconnectWifi();
      }
    } finally {
      setLoading(false);
    }
  };

  const handleEditClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingName(displayName || model || '');
    setShowEditDialog(true);
  };

  const handleSaveName = async () => {
    try {
      setSaving(true);
      const trimmedName = editingName.trim();
      const response = await updateDeviceName(serial, trimmedName || null);

      if (!response.success) {
        if (showToast) {
          showToast(response.error || t.deviceCard.saveNameError, 'error');
        }
        return;
      }

      setShowEditDialog(false);
      if (onNameUpdated) {
        onNameUpdated();
      }
      if (showToast) {
        showToast(t.deviceCard.saveNameSuccess, 'success');
      }
    } catch (error) {
      console.error('Failed to update device name:', error);
      if (showToast) {
        showToast(t.deviceCard.saveNameError, 'error');
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <div
        onClick={onClick}
        role="button"
        tabIndex={0}
        onKeyDown={e => {
          if (e.key === 'Enter' || e.key === ' ') {
            onClick();
          }
        }}
        className={`
          group relative w-full text-left p-4 rounded-xl transition-all duration-200 cursor-pointer
          border-2
          ${
            isActive
              ? 'bg-slate-50 border-[#1d9bf0] dark:bg-slate-800/50 dark:border-[#1d9bf0]'
              : 'bg-white border-transparent hover:border-slate-200 dark:bg-slate-900 dark:hover:border-slate-700'
          }
        `}
      >
        {/* Active indicator bar */}
        {isActive && (
          <div className="absolute left-0 top-2 bottom-2 w-1 bg-[#1d9bf0] rounded-r" />
        )}

        <div className="flex items-center gap-3 pl-2">
          {/* Agent status indicator with tooltip */}
          <Tooltip>
            <TooltipTrigger asChild>
              <div
                className={`relative flex-shrink-0 ${getAgentStatusClass()} w-3 h-3 rounded-full transition-all cursor-help ${
                  isActive ? 'scale-110' : ''
                }`}
              />
            </TooltipTrigger>
            <TooltipContent side="right" sideOffset={8} className="max-w-xs">
              <div className="space-y-1.5">
                <p className="font-medium">
                  {t.deviceCard.statusTooltip.title}
                  {getCurrentStatusText()}
                </p>
                <div className="text-xs opacity-80 space-y-0.5">
                  <p>{t.deviceCard.statusTooltip.legend.green}</p>
                  <p>{t.deviceCard.statusTooltip.legend.yellow}</p>
                  <p>{t.deviceCard.statusTooltip.legend.red}</p>
                  <p>{t.deviceCard.statusTooltip.legend.gray}</p>
                </div>
              </div>
            </TooltipContent>
          </Tooltip>

          {/* Device icon and info */}
          <div className="flex-1 min-w-0 flex flex-col justify-center gap-0.5">
            <div className="flex items-center gap-2">
              <Smartphone
                className={`w-4 h-4 flex-shrink-0 ${
                  isActive
                    ? 'text-[#1d9bf0]'
                    : 'text-slate-400 dark:text-slate-500'
                }`}
              />
              <span
                className={`font-semibold text-sm truncate ${
                  isActive
                    ? 'text-slate-900 dark:text-slate-100'
                    : 'text-slate-700 dark:text-slate-300'
                }`}
              >
                {actualDisplayName}
              </span>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={handleEditClick}
                    className="h-5 w-5 text-slate-400 hover:text-[#1d9bf0] opacity-0 group-hover:opacity-100 transition-opacity"
                  >
                    <Edit className="w-3 h-3" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>
                  <p>{t.deviceCard.editName}</p>
                </TooltipContent>
              </Tooltip>
            </div>
            <span
              className={`text-xs font-mono truncate ${
                isActive
                  ? 'text-slate-500 dark:text-slate-400'
                  : 'text-slate-400 dark:text-slate-500'
              }`}
            >
              {serial}
            </span>
          </div>

          {/* Right column: Connection type badges */}
          <div className="flex-shrink-0 flex flex-col items-end gap-1">
            {/* Connection type badge */}
            {(() => {
              if (isRemote) {
                return (
                  <Badge
                    variant="outline"
                    className="text-xs border-slate-200 text-slate-600 dark:border-slate-700 dark:text-slate-400"
                  >
                    <Server className="w-2.5 h-2.5 mr-1" />
                    {t.deviceCard.remote || 'Remote'}
                  </Badge>
                );
              } else if (isWifi) {
                return (
                  <Badge
                    variant="outline"
                    className="text-xs border-slate-200 text-slate-600 dark:border-slate-700 dark:text-slate-400"
                  >
                    <Wifi className="w-2.5 h-2.5 mr-1" />
                    {t.deviceCard.wifi || 'WiFi'}
                  </Badge>
                );
              } else if (isUsb) {
                return (
                  <Badge
                    variant="outline"
                    className="text-xs border-slate-200 text-slate-600 dark:border-slate-700 dark:text-slate-400"
                  >
                    USB
                  </Badge>
                );
              }
              return null;
            })()}
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-1 flex-shrink-0">
            {onConnectWifi && isUsb && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={handleWifiClick}
                    disabled={loading}
                    className="h-7 w-7 text-slate-400 hover:text-[#1d9bf0]"
                  >
                    {loading ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Wifi className="w-3.5 h-3.5" />
                    )}
                  </Button>
                </TooltipTrigger>
                <TooltipContent>
                  <p>{t.deviceCard.connectViaWifi}</p>
                </TooltipContent>
              </Tooltip>
            )}
            {onDisconnectWifi && isWifi && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={handleDisconnectClick}
                    disabled={loading}
                    className="h-7 w-7 text-slate-400 hover:text-orange-500"
                  >
                    {loading ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <WifiOff className="w-3.5 h-3.5" />
                    )}
                  </Button>
                </TooltipTrigger>
                <TooltipContent>
                  <p>{t.deviceCard.disconnectWifi}</p>
                </TooltipContent>
              </Tooltip>
            )}
            {isRemote && (
              <Button
                variant="ghost"
                size="icon"
                onClick={async e => {
                  e.stopPropagation();
                  setLoading(true);
                  try {
                    await removeRemoteDevice(serial);
                    // Refresh will happen via polling
                  } catch (error) {
                    console.error('Failed to remove remote device:', error);
                  } finally {
                    setLoading(false);
                  }
                }}
                disabled={loading}
                className="h-7 w-7 text-slate-400 hover:text-red-500"
                title={t.deviceCard.removeRemote || '移除远程设备'}
              >
                {loading ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Trash2 className="w-3.5 h-3.5" />
                )}
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* WiFi Connection Confirmation Dialog */}
      <ConfirmDialog
        isOpen={showWifiConfirm}
        title={t.deviceCard.connectWifiTitle}
        content={t.deviceCard.connectWifiContent}
        onConfirm={handleConfirmWifi}
        onCancel={() => setShowWifiConfirm(false)}
      />

      {/* WiFi Disconnect Confirmation Dialog */}
      <ConfirmDialog
        isOpen={showDisconnectConfirm}
        title={t.deviceCard.disconnectWifiTitle}
        content={t.deviceCard.disconnectWifiContent}
        onConfirm={handleConfirmDisconnect}
        onCancel={() => setShowDisconnectConfirm(false)}
      />

      {/* Device Name Edit Dialog */}
      <Dialog open={showEditDialog} onOpenChange={setShowEditDialog}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t.deviceCard.editNameDialogTitle}</DialogTitle>
            <DialogDescription>
              {t.deviceCard.editNameDialogDescription}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="device-name">
                {t.deviceCard.deviceNameLabel}
              </Label>
              <Input
                id="device-name"
                value={editingName}
                onChange={e => setEditingName(e.target.value)}
                placeholder={t.deviceCard.deviceNamePlaceholder}
                maxLength={100}
                onKeyDown={e => {
                  if (e.key === 'Enter' && !saving) {
                    handleSaveName();
                  }
                }}
              />
              <p className="text-xs text-slate-500 dark:text-slate-400">
                {t.deviceCard.deviceSerialLabel}: {serial}
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowEditDialog(false)}
              disabled={saving}
            >
              {t.common.cancel}
            </Button>
            <Button onClick={handleSaveName} disabled={saving}>
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
    </>
  );
}
