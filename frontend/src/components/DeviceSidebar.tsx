import React, { useState, useEffect } from 'react';
import {
  Smartphone,
  Settings,
  ChevronLeft,
  ChevronRight,
  Plug,
} from 'lucide-react';
import { DeviceCard } from './DeviceCard';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import type { Device } from '../api';

const getInitialCollapsedState = (): boolean => {
  try {
    const saved = localStorage.getItem('sidebar-collapsed');
    return saved !== null ? JSON.parse(saved) : false;
  } catch (error) {
    console.warn('Failed to load sidebar collapsed state:', error);
    return false;
  }
};

interface DeviceSidebarProps {
  devices: Device[];
  currentDeviceId: string;
  onSelectDevice: (deviceId: string) => void;
  onOpenConfig: () => void;
  onConnectWifi: (deviceId: string) => void;
  onDisconnectWifi: (deviceId: string) => void;
}

export function DeviceSidebar({
  devices,
  currentDeviceId,
  onSelectDevice,
  onOpenConfig,
  onConnectWifi,
  onDisconnectWifi,
}: DeviceSidebarProps) {
  const [isCollapsed, setIsCollapsed] = useState(getInitialCollapsedState);

  useEffect(() => {
    localStorage.setItem('sidebar-collapsed', JSON.stringify(isCollapsed));
  }, [isCollapsed]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key === 'b') {
        event.preventDefault();
        setIsCollapsed(!isCollapsed);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isCollapsed]);

  const toggleCollapse = () => {
    setIsCollapsed(!isCollapsed);
  };

  return (
    <>
      {/* Collapsed toggle button */}
      {isCollapsed && (
        <Button
          variant="outline"
          size="icon"
          onClick={toggleCollapse}
          className="fixed left-0 top-20 z-50 h-16 w-8 rounded-r-lg rounded-l-none border-l-0 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700"
          title="Expand sidebar"
          style={{ left: 0 }}
        >
          <ChevronRight className="h-4 w-4" />
        </Button>
      )}

      {/* Sidebar */}
      <div
        className={`
          ${isCollapsed ? 'w-0 -ml-4 opacity-0' : 'w-80 opacity-100'}
          transition-all duration-300 ease-in-out
          h-full min-h-0
          bg-white dark:bg-slate-950
          border-r border-slate-200 dark:border-slate-800
          flex flex-col
          overflow-hidden
        `}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4">
          <div className="flex items-center gap-2">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[#1d9bf0]/10">
              <Smartphone className="h-5 w-5 text-[#1d9bf0]" />
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-900 dark:text-slate-100">
                AutoGLM
              </h2>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                {devices.length} {devices.length === 1 ? 'device' : 'devices'}
              </p>
            </div>
          </div>

          <Button
            variant="ghost"
            size="icon"
            onClick={toggleCollapse}
            className="h-8 w-8 rounded-full text-slate-400 hover:text-slate-600 dark:text-slate-500 dark:hover:text-slate-300"
            title="Collapse sidebar"
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
        </div>

        <Separator className="mx-4" />

        {/* Device list */}
        <div className="flex-1 overflow-y-auto p-3 space-y-2 min-h-0">
          {devices.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <div className="flex h-16 w-16 items-center justify-center rounded-full bg-slate-100 dark:bg-slate-800">
                <Plug className="h-8 w-8 text-slate-400" />
              </div>
              <p className="mt-4 font-medium text-slate-900 dark:text-slate-100">
                No devices connected
              </p>
              <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                Connect an ADB device to get started
              </p>
            </div>
          ) : (
            devices.map(device => (
              <DeviceCard
                key={device.id}
                id={device.id}
                model={device.model}
                status={device.status}
                connectionType={device.connection_type}
                isInitialized={device.is_initialized}
                isActive={currentDeviceId === device.id}
                onClick={() => onSelectDevice(device.id)}
                onConnectWifi={async () => {
                  await onConnectWifi(device.id);
                }}
                onDisconnectWifi={async () => {
                  await onDisconnectWifi(device.id);
                }}
              />
            ))
          )}
        </div>

        <Separator className="mx-4" />

        {/* Bottom actions */}
        <div className="p-3">
          <Button
            variant="outline"
            onClick={onOpenConfig}
            className="w-full justify-start gap-2 rounded-full border-slate-200 dark:border-slate-700"
          >
            <Settings className="h-4 w-4" />
            Settings
          </Button>
        </div>
      </div>
    </>
  );
}
