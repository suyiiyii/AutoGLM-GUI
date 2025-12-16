import { createFileRoute } from '@tanstack/react-router';
import * as React from 'react';
import { useState, useEffect } from 'react';
import { listDevices, type Device } from '../api';
import { DeviceSidebar } from '../components/DeviceSidebar';
import { DevicePanel } from '../components/DevicePanel';

export const Route = createFileRoute('/chat')({
  component: ChatComponent,
});

function ChatComponent() {
  // 设备列表和当前选中设备
  const [devices, setDevices] = useState<Device[]>([]);
  const [currentDeviceId, setCurrentDeviceId] = useState<string>('');

  // 全局配置（所有设备共享）
  const [config, setConfig] = useState({
    baseUrl: '',
    apiKey: '',
    modelName: '',
  });
  const [showConfig, setShowConfig] = useState(false);

  // 保存配置（仅内存，不持久化）
  const saveConfig = (newConfig: typeof config) => {
    setConfig(newConfig);
  };

  // 加载设备列表 - 提取为独立函数供外部调用
  const loadDevices = React.useCallback(async () => {
    try {
      const response = await listDevices();
      setDevices(response.devices);

      // 自动选择第一个设备（如果当前没有选中设备）
      if (response.devices.length > 0 && !currentDeviceId) {
        setCurrentDeviceId(response.devices[0].id);
      }

      // ✅ 新增：处理当前设备被移除的情况
      if (
        currentDeviceId &&
        !response.devices.find(d => d.id === currentDeviceId)
      ) {
        setCurrentDeviceId(response.devices[0]?.id || '');
      }
    } catch (error) {
      console.error('Failed to load devices:', error);
    }
  }, [currentDeviceId]);

  useEffect(() => {
    let mounted = true;

    const fetchDevices = async () => {
      try {
        const response = await listDevices();
        if (!mounted) return;

        setDevices(response.devices);

        // 自动选择第一个设备（如果当前没有选中设备）
        if (response.devices.length > 0 && !currentDeviceId) {
          setCurrentDeviceId(response.devices[0].id);
        }

        // ✅ 新增：处理当前设备被移除的情况
        if (
          currentDeviceId &&
          !response.devices.find(d => d.id === currentDeviceId)
        ) {
          setCurrentDeviceId(response.devices[0]?.id || '');
        }
      } catch (error) {
        console.error('Failed to load devices:', error);
      }
    };

    fetchDevices();
    // 每3秒刷新设备列表
    const interval = setInterval(fetchDevices, 3000);

    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, [currentDeviceId]);

  return (
    <div className="h-full flex relative min-h-0">
      {/* Config Modal */}
      {showConfig && (
        <div className="absolute inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-800 p-6 rounded-2xl w-96 shadow-xl border border-gray-200 dark:border-gray-700">
            <h2 className="text-xl font-bold mb-4 text-gray-900 dark:text-gray-100">
              Agent 配置
            </h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
                  Base URL
                </label>
                <input
                  type="text"
                  value={config.baseUrl}
                  onChange={e =>
                    saveConfig({ ...config, baseUrl: e.target.value })
                  }
                  placeholder="https://api-inference.modelscope.cn/v1"
                  className="w-full px-3 py-2 border rounded-lg bg-white dark:bg-gray-700 border-gray-300 dark:border-gray-600 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500 outline-none"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
                  API Key
                </label>
                <input
                  type="password"
                  value={config.apiKey}
                  onChange={e =>
                    saveConfig({ ...config, apiKey: e.target.value })
                  }
                  placeholder="ms-xxxxxx"
                  className="w-full px-3 py-2 border rounded-lg bg-white dark:bg-gray-700 border-gray-300 dark:border-gray-600 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500 outline-none"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
                  Model Name
                </label>
                <input
                  type="text"
                  value={config.modelName}
                  onChange={e =>
                    saveConfig({ ...config, modelName: e.target.value })
                  }
                  placeholder="ZhipuAI/AutoGLM-Phone-9B"
                  className="w-full px-3 py-2 border rounded-lg bg-white dark:bg-gray-700 border-gray-300 dark:border-gray-600 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500 outline-none"
                />
              </div>
              <div className="flex justify-end gap-2 mt-6">
                <button
                  onClick={() => setShowConfig(false)}
                  className="px-4 py-2 text-gray-600 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-200"
                >
                  取消
                </button>
                <button
                  onClick={() => setShowConfig(false)}
                  className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
                >
                  确认配置
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 左侧边栏 */}
      <DeviceSidebar
        devices={devices}
        currentDeviceId={currentDeviceId}
        onSelectDevice={setCurrentDeviceId}
        onOpenConfig={() => setShowConfig(true)}
        onRefreshDevices={loadDevices}
      />

      {/* 右侧主内容区 - 多实例架构 */}
      <div className="flex-1 relative flex items-stretch justify-center min-h-0">
        {devices.length === 0 ? (
          <div className="absolute inset-0 flex items-center justify-center bg-gray-50 dark:bg-gray-900">
            <div className="text-center text-gray-500 dark:text-gray-400">
              <svg
                className="w-16 h-16 mx-auto mb-4 opacity-50"
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
              <h3 className="text-lg font-medium mb-2">
                欢迎使用 AutoGLM Chat
              </h3>
              <p className="text-sm">未检测到设备，请连接 ADB 设备</p>
            </div>
          </div>
        ) : (
          devices.map(device => (
            <div
              key={device.id}
              className={`w-full h-full flex items-stretch justify-center min-h-0 ${
                device.id === currentDeviceId ? '' : 'hidden'
              }`}
            >
              <DevicePanel
                deviceId={device.id}
                deviceName={device.model}
                config={config}
                isVisible={device.id === currentDeviceId}
              />
            </div>
          ))
        )}
      </div>
    </div>
  );
}
