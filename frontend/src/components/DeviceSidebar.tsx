import React, { useState, useEffect } from 'react';
import { DeviceCard } from './DeviceCard';
import type { Device } from '../api';

// 初始状态从 localStorage 读取
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
}

export function DeviceSidebar({
  devices,
  currentDeviceId,
  onSelectDevice,
  onOpenConfig,
  onConnectWifi,
}: DeviceSidebarProps) {
  const [isCollapsed, setIsCollapsed] = useState(getInitialCollapsedState);

  useEffect(() => {
    localStorage.setItem('sidebar-collapsed', JSON.stringify(isCollapsed));
  }, [isCollapsed]);

  // 键盘快捷键支持
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
      {/* 半圆形展开按钮（当侧边栏隐藏时显示） */}
      {isCollapsed && (
        <button
          onClick={toggleCollapse}
          className="fixed left-0 top-20 w-8 h-16 bg-blue-500 hover:bg-blue-600 text-white rounded-r-full shadow-lg transition-all duration-300 z-50 flex items-center justify-center"
          title="展开侧边栏"
        >
          <svg
            className="w-4 h-4 transition-transform duration-300"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9 5l7 7-7 7"
            />
          </svg>
        </button>
      )}

      {/* 侧边栏主体 */}
      <div
        className={`${isCollapsed ? 'w-0 -ml-8' : 'w-64'} transition-all duration-500 ease-[cubic-bezier(0.4,0.0,0.2,1)] h-full min-h-0 bg-gray-50 dark:bg-gray-900 border-r border-gray-200 dark:border-gray-700 flex flex-col overflow-hidden`}
      >
        {/* 头部 */}
        <div className="border-b border-gray-200 dark:border-gray-700 flex items-center justify-between p-4 whitespace-nowrap">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
              <svg
                className="w-5 h-5"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z"
                />
              </svg>
              设备列表
            </h2>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              共 {devices.length} 个设备
            </p>
          </div>

          <button
            onClick={toggleCollapse}
            className="p-1.5 hover:bg-gray-200 dark:hover:bg-gray-700 rounded transition-all duration-300 ease-[cubic-bezier(0.4,0.0,0.2,1)]"
            title="收缩侧边栏"
          >
            <svg
              className="w-4 h-4 text-gray-500 dark:text-gray-400 transition-transform duration-500 ease-[cubic-bezier(0.4,0.0,0.2,1)]"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M15 19l-7-7 7-7"
              />
            </svg>
          </button>
        </div>

        {/* 设备列表 */}
        <div className="flex-1 overflow-y-auto p-3 space-y-2 min-h-0">
          {devices.length === 0 ? (
            <div className="text-center py-8 text-gray-500 dark:text-gray-400">
              <svg
                className="w-12 h-12 mx-auto mb-2 opacity-50"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z"
                />
              </svg>
              <p className="text-sm">未检测到设备</p>
              <p className="text-xs mt-1">请连接 ADB 设备</p>
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
                isActive={device.id === currentDeviceId}
                onClick={() => onSelectDevice(device.id)}
                onConnectWifi={async () => {
                  await onConnectWifi(device.id);
                }}
              />
            ))
          )}
        </div>

        {/* 底部操作栏 */}
        <div className="p-3 border-t border-gray-200 dark:border-gray-700 space-y-2 whitespace-nowrap">
          <button
            onClick={onOpenConfig}
            className="w-full px-4 py-2 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg transition-all duration-500 ease-[cubic-bezier(0.4,0.0,0.2,1)] font-medium text-gray-700 dark:text-gray-300 flex items-center justify-center gap-2"
          >
            <svg
              className="w-4 h-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
              />
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
              />
            </svg>
            全局配置
          </button>
        </div>
      </div>
    </>
  );
}
