import React from 'react';

interface DeviceCardProps {
  id: string;
  model: string;
  status: string;
  connectionType?: string;
  isInitialized: boolean;
  isActive: boolean;
  onClick: () => void;
  onEnableWifi?: () => void;
}

export function DeviceCard({
  id,
  model,
  status,
  connectionType,
  isInitialized,
  isActive,
  onClick,
  onEnableWifi,
}: DeviceCardProps) {
  const isOnline = status === 'device';
  const isUsb = connectionType === 'usb';

  return (
    <div
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={e => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onClick();
        }
      }}
      className={`w-full text-left px-4 py-3 rounded-lg transition-all duration-500 ease-[cubic-bezier(0.4,0.0,0.2,1)] h-12 shrink-0 cursor-pointer ${
        isActive
          ? 'bg-blue-500 text-white shadow-md'
          : 'bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700'
      }`}
    >
      <div className="flex items-center gap-2">
        <div className="flex items-center gap-3 min-w-0 flex-1">
          {/* 状态指示器 */}
          <div
            className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${
              isOnline
                ? 'bg-green-400 shadow-[0_0_4px_rgba(74,222,128,0.6)]'
                : 'bg-gray-400'
            }`}
            title={isOnline ? '在线' : '离线'}
          />

          <div className="min-w-0 flex-1">
            {/* 设备型号 */}
            <div
              className={`font-medium text-sm truncate ${
                isActive ? 'text-white' : 'text-gray-900 dark:text-gray-100'
              }`}
            >
              {model || '未知设备'}
            </div>

            {/* 设备 ID */}
            <div
              className={`text-xs truncate ${
                isActive ? 'text-blue-100' : 'text-gray-500 dark:text-gray-400'
              }`}
            >
              {id}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          {/* 初始化状态标识 */}
          {isInitialized && (
            <div
              className={`w-5 h-5 rounded-full flex items-center justify-center ${
                isActive ? 'bg-white/20' : 'bg-green-100 dark:bg-green-900'
              }`}
            >
              <svg
                className={`w-3 h-3 ${
                  isActive ? 'text-white' : 'text-green-600 dark:text-green-400'
                }`}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M5 13l4 4L19 7"
                />
              </svg>
            </div>
          )}

          {/* 有线转无线快捷按钮，仅 USB 在线设备显示 */}
          {isUsb && isOnline && onEnableWifi && (
            <button
              type="button"
              onClick={e => {
                e.stopPropagation();
                onClick();
                onEnableWifi();
              }}
              className={`group flex items-center justify-center p-1.5 rounded-md transition-all duration-200 ${
                isActive
                  ? 'bg-white/20 hover:bg-white/30 text-white shadow-sm'
                  : 'bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 hover:bg-blue-100 dark:hover:bg-blue-900/50'
              }`}
              title="切换到无线连接"
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
                  d="M8.111 16.404a5.5 5.5 0 017.778 0M12 20h.01m-7.08-7.071c3.904-3.905 10.236-3.905 14.141 0M1.394 9.393c5.857-5.857 15.355-5.857 21.213 0"
                />
              </svg>
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
