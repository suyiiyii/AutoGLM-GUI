import React, { useState } from 'react';
import {
  Wifi,
  WifiOff,
  CheckCircle2,
  Smartphone,
  Loader2,
  XCircle,
  Clock,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ConfirmDialog } from './ConfirmDialog';
import { useTranslation } from '../lib/i18n-context';
import type { AgentStatus } from '../api';

interface DeviceCardProps {
  id: string;
  serial: string;
  model: string;
  status: string;
  connectionType?: string;
  agent?: AgentStatus | null;
  isActive: boolean;
  onClick: () => void;
  onConnectWifi?: () => Promise<void>;
  onDisconnectWifi?: () => Promise<void>;
}

export function DeviceCard({
  id,
  serial: _serial,
  model,
  status,
  connectionType,
  agent,
  isActive,
  onClick,
  onConnectWifi,
  onDisconnectWifi,
}: DeviceCardProps) {
  const t = useTranslation();
  const isOnline = status === 'device';
  const isUsb = connectionType === 'usb';
  const isRemote = connectionType === 'remote';
  const [loading, setLoading] = useState(false);
  const [showWifiConfirm, setShowWifiConfirm] = useState(false);
  const [showDisconnectConfirm, setShowDisconnectConfirm] = useState(false);

  const displayName = model || t.deviceCard.unknownDevice;

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
          {/* Status indicator */}
          <div
            className={`relative flex-shrink-0 ${
              isOnline ? 'status-online' : 'status-offline'
            } w-3 h-3 rounded-full transition-all ${
              isActive ? 'scale-110' : ''
            }`}
          />

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
                {displayName}
              </span>
            </div>
            <span
              className={`text-xs font-mono truncate ${
                isActive
                  ? 'text-slate-500 dark:text-slate-400'
                  : 'text-slate-400 dark:text-slate-500'
              }`}
            >
              {model || id}
            </span>
          </div>

          {/* Right column: Agent status + Connection type badges */}
          <div className="flex-shrink-0 flex flex-col items-end gap-1">
            {/* Agent status */}
            {agent && (
              <>
                {agent.state === 'busy' && (
                  <Badge
                    variant="secondary"
                    className="text-xs px-1.5 py-0 bg-[#1d9bf0]/10 text-[#1d9bf0] hover:bg-[#1d9bf0]/20"
                  >
                    <Loader2 className="w-2.5 h-2.5 animate-spin mr-1" />
                    {t.deviceCard.agentBusy}
                  </Badge>
                )}
                {agent.state === 'idle' && (
                  <Badge
                    variant="secondary"
                    className="text-xs px-1.5 py-0 bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-400"
                  >
                    <CheckCircle2 className="w-2.5 h-2.5 mr-1" />
                    {t.deviceCard.agentIdle}
                  </Badge>
                )}
                {agent.state === 'error' && (
                  <Badge
                    variant="secondary"
                    className="text-xs px-1.5 py-0 bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400"
                  >
                    <XCircle className="w-2.5 h-2.5 mr-1" />
                    {t.deviceCard.agentError}
                  </Badge>
                )}
                {agent.state === 'initializing' && (
                  <Badge
                    variant="secondary"
                    className="text-xs px-1.5 py-0 bg-blue-50 text-blue-700 dark:bg-blue-900/20 dark:text-blue-400"
                  >
                    <Clock className="w-2.5 h-2.5 mr-1" />
                    {t.deviceCard.agentInitializing}
                  </Badge>
                )}
              </>
            )}

            {/* Connection type badge */}
            {isUsb && (
              <Badge
                variant="outline"
                className="text-xs border-slate-200 text-slate-600 dark:border-slate-700 dark:text-slate-400"
              >
                USB
              </Badge>
            )}
            {isRemote && (
              <Badge
                variant="outline"
                className="text-xs border-slate-200 text-slate-600 dark:border-slate-700 dark:text-slate-400"
              >
                <WifiOff className="w-2.5 h-2.5 mr-1" />
                Remote
              </Badge>
            )}
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-1 flex-shrink-0">
            {onConnectWifi && isUsb && (
              <Button
                variant="ghost"
                size="icon"
                onClick={handleWifiClick}
                disabled={loading}
                className="h-7 w-7 text-slate-400 hover:text-[#1d9bf0]"
                title={t.deviceCard.connectViaWifi}
              >
                {loading ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Wifi className="w-3.5 h-3.5" />
                )}
              </Button>
            )}
            {onDisconnectWifi && isRemote && (
              <Button
                variant="ghost"
                size="icon"
                onClick={handleDisconnectClick}
                disabled={loading}
                className="h-7 w-7 text-slate-400 hover:text-orange-500"
                title={t.deviceCard.disconnectWifi}
              >
                {loading ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <WifiOff className="w-3.5 h-3.5" />
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
    </>
  );
}
