import React, { useState, useEffect } from 'react';
import {
  ChevronDown,
  ChevronRight,
  FolderOpen,
  GripVertical,
} from 'lucide-react';
import { DeviceCard } from './DeviceCard';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import type { Device, DeviceGroup } from '../api';
import { assignDeviceToGroup } from '../api';
import { useTranslation } from '../lib/i18n-context';
import type { ToastType } from './Toast';

interface GroupedDeviceListProps {
  devices: Device[];
  groups: DeviceGroup[];
  currentDeviceId: string;
  onSelectDevice: (deviceId: string) => void;
  onConnectWifi: (deviceId: string) => void;
  onDisconnectWifi: (deviceId: string) => void;
  onRefreshDevices?: () => void;
  onRefreshGroups?: () => void;
  showToast?: (message: string, type: ToastType) => void;
}

interface CollapsedState {
  [groupId: string]: boolean;
}

const COLLAPSED_STATE_KEY = 'device-group-collapsed';

function getInitialCollapsedState(): CollapsedState {
  try {
    const saved = localStorage.getItem(COLLAPSED_STATE_KEY);
    return saved ? JSON.parse(saved) : {};
  } catch {
    return {};
  }
}

export function GroupedDeviceList({
  devices,
  groups,
  currentDeviceId,
  onSelectDevice,
  onConnectWifi,
  onDisconnectWifi,
  onRefreshDevices,
  onRefreshGroups,
  showToast,
}: GroupedDeviceListProps) {
  const t = useTranslation();
  const [collapsedState, setCollapsedState] = useState<CollapsedState>(
    getInitialCollapsedState
  );
  const [movingDevice, setMovingDevice] = useState<string | null>(null);

  // Save collapsed state to localStorage
  useEffect(() => {
    localStorage.setItem(COLLAPSED_STATE_KEY, JSON.stringify(collapsedState));
  }, [collapsedState]);

  // Group devices by group_id
  const devicesByGroup = React.useMemo(() => {
    const map = new Map<string, Device[]>();

    // Initialize with empty arrays for all groups
    for (const group of groups) {
      map.set(group.id, []);
    }

    // Assign devices to their groups
    for (const device of devices) {
      const groupId = device.group_id || 'default';
      const groupDevices = map.get(groupId) || [];
      groupDevices.push(device);
      map.set(groupId, groupDevices);
    }

    return map;
  }, [devices, groups]);

  const toggleGroup = (groupId: string) => {
    setCollapsedState(prev => ({
      ...prev,
      [groupId]: !prev[groupId],
    }));
  };

  const handleMoveDevice = async (serial: string, targetGroupId: string) => {
    setMovingDevice(serial);
    try {
      const result = await assignDeviceToGroup(serial, targetGroupId);
      if (result.success) {
        if (onRefreshDevices) onRefreshDevices();
        if (onRefreshGroups) onRefreshGroups();
        if (showToast) {
          showToast(t.deviceGroups?.deviceMoved || '设备已移动', 'success');
        }
      } else {
        if (showToast) {
          showToast(
            result.message || t.deviceGroups?.moveFailed || '移动失败',
            'error'
          );
        }
      }
    } catch (error) {
      console.error('Failed to move device:', error);
      if (showToast) {
        showToast(t.deviceGroups?.moveFailed || '移动失败', 'error');
      }
    } finally {
      setMovingDevice(null);
    }
  };

  // Sort groups by order
  const sortedGroups = React.useMemo(() => {
    return [...groups].sort((a, b) => a.order - b.order);
  }, [groups]);

  return (
    <div className="space-y-2">
      {sortedGroups.map(group => {
        const groupDevices = devicesByGroup.get(group.id) || [];
        const isCollapsed = collapsedState[group.id] || false;
        const deviceCount = groupDevices.length;

        return (
          <div key={group.id} className="space-y-1">
            {/* Group Header */}
            <button
              onClick={() => toggleGroup(group.id)}
              className="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors text-left"
            >
              {isCollapsed ? (
                <ChevronRight className="w-4 h-4 text-slate-400 flex-shrink-0" />
              ) : (
                <ChevronDown className="w-4 h-4 text-slate-400 flex-shrink-0" />
              )}
              <FolderOpen className="w-4 h-4 text-slate-400 flex-shrink-0" />
              <span className="flex-1 text-sm font-medium text-slate-700 dark:text-slate-300 truncate">
                {group.name}
              </span>
              <span className="text-xs text-slate-400 dark:text-slate-500">
                ({deviceCount})
              </span>
            </button>

            {/* Device List */}
            {!isCollapsed && (
              <div className="pl-2 space-y-1">
                {groupDevices.length === 0 ? (
                  <div className="px-4 py-3 text-xs text-slate-400 dark:text-slate-500 italic">
                    {t.deviceGroups?.noDevicesInGroup || '该分组暂无设备'}
                  </div>
                ) : (
                  groupDevices.map(device => (
                    <div
                      key={device.id}
                      className="group/card relative flex items-center gap-1"
                    >
                      {/* Drag handle / Move button */}
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-6 w-6 opacity-0 group-hover/card:opacity-100 transition-opacity flex-shrink-0 text-slate-400 hover:text-slate-600"
                            disabled={movingDevice === device.serial}
                          >
                            <GripVertical className="w-3.5 h-3.5" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="start" className="w-48">
                          <div className="px-2 py-1.5 text-xs font-medium text-slate-500">
                            {t.deviceGroups?.moveTo || '移动到分组'}
                          </div>
                          {sortedGroups.map(targetGroup => (
                            <DropdownMenuItem
                              key={targetGroup.id}
                              disabled={targetGroup.id === device.group_id}
                              onClick={() =>
                                handleMoveDevice(device.serial, targetGroup.id)
                              }
                              className={
                                targetGroup.id === device.group_id
                                  ? 'opacity-50'
                                  : ''
                              }
                            >
                              <FolderOpen className="w-4 h-4 mr-2" />
                              {targetGroup.name}
                              {targetGroup.id === device.group_id && (
                                <span className="ml-auto text-xs text-slate-400">
                                  {t.deviceGroups?.currentGroup || '当前'}
                                </span>
                              )}
                            </DropdownMenuItem>
                          ))}
                        </DropdownMenuContent>
                      </DropdownMenu>

                      {/* Device Card */}
                      <div className="flex-1 min-w-0">
                        <DeviceCard
                          id={device.id}
                          serial={device.serial}
                          model={device.model}
                          displayName={device.display_name}
                          status={device.status}
                          connectionType={device.connection_type}
                          agent={device.agent}
                          isActive={currentDeviceId === device.id}
                          onClick={() => onSelectDevice(device.id)}
                          onConnectWifi={async () => {
                            await onConnectWifi(device.id);
                          }}
                          onDisconnectWifi={async () => {
                            await onDisconnectWifi(device.id);
                          }}
                          onNameUpdated={() => {
                            if (onRefreshDevices) {
                              onRefreshDevices();
                            }
                          }}
                          showToast={showToast}
                        />
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
