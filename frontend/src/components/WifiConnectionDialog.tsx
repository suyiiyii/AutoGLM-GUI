import React, { useState } from 'react';
import {
  connectDevice,
  disconnectDevice,
  enableTcpip,
  getDeviceIp,
  type Device,
} from '../api';

interface WifiConnectionDialogProps {
  isOpen: boolean;
  onClose: () => void;
  devices: Device[];
  onRefreshDevices: () => void;
}

export function WifiConnectionDialog({
  isOpen,
  onClose,
  devices,
  onRefreshDevices,
}: WifiConnectionDialogProps) {
  const [activeTab, setActiveTab] = useState<'connect' | 'enable'>('connect');
  const [address, setAddress] = useState('');
  const [port, setPort] = useState('5555');
  const [timeout, setTimeout] = useState('10');
  const [selectedDevice, setSelectedDevice] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<{
    type: 'success' | 'error' | 'info';
    text: string;
  } | null>(null);
  const [deviceIp, setDeviceIp] = useState<string | null>(null);

  // 过滤出 USB 连接的设备（用于启用 TCP/IP）
  const usbDevices = devices.filter(d => d.connection_type === 'usb');

  // 重置表单
  const resetForm = () => {
    setAddress('');
    setPort('5555');
    setTimeout('10');
    setSelectedDevice('');
    setMessage(null);
    setDeviceIp(null);
    setLoading(false);
  };

  // 关闭对话框
  const handleClose = () => {
    resetForm();
    onClose();
  };

  // WiFi 连接
  const handleConnect = async () => {
    if (!address.trim()) {
      setMessage({ type: 'error', text: '请输入设备地址' });
      return;
    }

    setLoading(true);
    setMessage(null);

    try {
      const fullAddress = address.includes(':')
        ? address
        : `${address}:${port}`;
      const result = await connectDevice(fullAddress, parseInt(timeout));

      if (result.success) {
        setMessage({ type: 'success', text: result.message });
        // 延迟刷新设备列表
        window.setTimeout(() => {
          onRefreshDevices();
        }, 1000);
      } else {
        setMessage({ type: 'error', text: result.message });
      }
    } catch (error) {
      setMessage({
        type: 'error',
        text: `连接失败: ${error instanceof Error ? error.message : '未知错误'}`,
      });
    } finally {
      setLoading(false);
    }
  };

  // 断开连接
  const handleDisconnect = async () => {
    if (!address.trim()) {
      setMessage({ type: 'error', text: '请输入要断开的设备地址' });
      return;
    }

    setLoading(true);
    setMessage(null);

    try {
      const fullAddress = address.includes(':')
        ? address
        : `${address}:${port}`;
      const result = await disconnectDevice(fullAddress);

      if (result.success) {
        setMessage({ type: 'success', text: result.message });
        setAddress('');
        // 刷新设备列表
        window.setTimeout(() => {
          onRefreshDevices();
        }, 500);
      } else {
        setMessage({ type: 'error', text: result.message });
      }
    } catch (error) {
      setMessage({
        type: 'error',
        text: `断开失败: ${error instanceof Error ? error.message : '未知错误'}`,
      });
    } finally {
      setLoading(false);
    }
  };

  // 启用 TCP/IP
  const handleEnableTcpip = async () => {
    setLoading(true);
    setMessage(null);
    setDeviceIp(null);

    try {
      // 如果没有选择设备，使用第一个 USB 设备
      const deviceId = selectedDevice || usbDevices[0]?.id || null;

      if (!deviceId) {
        setMessage({ type: 'error', text: '没有可用的 USB 设备' });
        setLoading(false);
        return;
      }

      const result = await enableTcpip(deviceId, parseInt(port) || 5555);

      if (result.success) {
        setMessage({ type: 'success', text: result.message });
        if (result.device_ip) {
          setDeviceIp(result.device_ip);
          setAddress(result.device_ip);

          // 刷新设备列表（移除已变成 offline 的 USB 设备）
          window.setTimeout(() => {
            onRefreshDevices();
          }, 500);

          // 自动切换到 WiFi 连接选项卡
          window.setTimeout(() => {
            setActiveTab('connect');
          }, 1500);
        }
      } else {
        setMessage({ type: 'error', text: result.message });
      }
    } catch (error) {
      setMessage({
        type: 'error',
        text: `启用失败: ${error instanceof Error ? error.message : '未知错误'}`,
      });
    } finally {
      setLoading(false);
    }
  };

  // 获取设备 IP
  const handleGetIp = async () => {
    setLoading(true);
    setMessage(null);
    setDeviceIp(null);

    try {
      // 如果没有选择设备，使用第一个 USB 设备
      const deviceId = selectedDevice || usbDevices[0]?.id || null;

      if (!deviceId) {
        setMessage({ type: 'error', text: '没有可用的 USB 设备' });
        setLoading(false);
        return;
      }

      const result = await getDeviceIp(deviceId);

      if (result.success && result.ip) {
        setDeviceIp(result.ip);
        setAddress(result.ip);
        setMessage({ type: 'success', text: `设备 IP: ${result.ip}` });
      } else {
        setMessage({
          type: 'error',
          text: result.message || '无法获取设备 IP',
        });
      }
    } catch (error) {
      setMessage({
        type: 'error',
        text: `获取失败: ${error instanceof Error ? error.message : '未知错误'}`,
      });
    } finally {
      setLoading(false);
    }
  };

  // 复制到剪贴板
  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text).then(() => {
      setMessage({ type: 'info', text: '已复制到剪贴板' });
      window.setTimeout(() => setMessage(null), 2000);
    });
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/40 backdrop-blur-lg flex items-center justify-center z-50">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">
        {/* 头部 */}
        <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <svg
              className="w-6 h-6 text-blue-500"
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
            <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">
              WiFi ADB 连接
            </h2>
          </div>
          <button
            onClick={handleClose}
            className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
          >
            <svg
              className="w-6 h-6"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>

        {/* 选项卡 */}
        <div className="flex border-b border-gray-200 dark:border-gray-700">
          <button
            onClick={() => setActiveTab('connect')}
            className={`flex-1 px-6 py-3 text-sm font-medium transition-colors ${
              activeTab === 'connect'
                ? 'text-blue-600 dark:text-blue-400 border-b-2 border-blue-600 dark:border-blue-400'
                : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'
            }`}
          >
            WiFi 连接
          </button>
          <button
            onClick={() => setActiveTab('enable')}
            className={`flex-1 px-6 py-3 text-sm font-medium transition-colors ${
              activeTab === 'enable'
                ? 'text-blue-600 dark:text-blue-400 border-b-2 border-blue-600 dark:border-blue-400'
                : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'
            }`}
          >
            启用 TCP/IP
          </button>
        </div>

        {/* 内容区域 */}
        <div className="flex-1 overflow-y-auto p-6">
          {/* WiFi 连接选项卡 */}
          {activeTab === 'connect' && (
            <div className="space-y-4">
              <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
                <div className="flex items-start gap-2">
                  <svg
                    className="w-5 h-5 text-blue-500 mt-0.5 flex-shrink-0"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                    />
                  </svg>
                  <div className="text-sm text-blue-800 dark:text-blue-300">
                    <p className="font-medium mb-1">连接方式：</p>
                    <div className="space-y-2">
                      <div>
                        <p className="font-semibold">
                          方式 1：传统 TCP/IP（推荐）
                        </p>
                        <ol className="list-decimal list-inside space-y-1 ml-2">
                          <li>
                            在&ldquo;启用 TCP/IP&rdquo;选项卡操作（自动使用 5555
                            端口）
                          </li>
                          <li>输入设备 IP 地址即可连接</li>
                        </ol>
                      </div>
                      <div>
                        <p className="font-semibold">
                          方式 2：Android 11+ 无线调试
                        </p>
                        <ol className="list-decimal list-inside space-y-1 ml-2">
                          <li>设备上手动开启&ldquo;无线调试&rdquo;</li>
                          <li>
                            查看设备显示的 IP:端口（例如 192.168.1.100:38273）
                          </li>
                          <li>完整输入到下方地址栏</li>
                        </ol>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  设备地址
                  <span className="ml-2 text-xs text-gray-500 dark:text-gray-400 font-normal">
                    （可输入 IP:端口 或仅 IP）
                  </span>
                </label>
                <input
                  type="text"
                  value={address}
                  onChange={e => setAddress(e.target.value)}
                  placeholder="例如: 192.168.1.100:5555 或 192.168.1.100"
                  className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  disabled={loading}
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    端口
                    <span className="ml-2 text-xs text-gray-500 dark:text-gray-400 font-normal">
                      （地址未含端口时使用）
                    </span>
                  </label>
                  <input
                    type="number"
                    value={port}
                    onChange={e => setPort(e.target.value)}
                    placeholder="5555"
                    className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    disabled={loading}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    超时时间（秒）
                  </label>
                  <input
                    type="number"
                    value={timeout}
                    onChange={e => setTimeout(e.target.value)}
                    placeholder="10"
                    className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    disabled={loading}
                  />
                </div>
              </div>

              <div className="flex gap-3">
                <button
                  onClick={handleConnect}
                  disabled={loading || !address.trim()}
                  className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white rounded-lg font-medium transition-colors flex items-center justify-center gap-2"
                >
                  {loading ? (
                    <>
                      <svg
                        className="animate-spin h-5 w-5"
                        fill="none"
                        viewBox="0 0 24 24"
                      >
                        <circle
                          className="opacity-25"
                          cx="12"
                          cy="12"
                          r="10"
                          stroke="currentColor"
                          strokeWidth="4"
                        />
                        <path
                          className="opacity-75"
                          fill="currentColor"
                          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                        />
                      </svg>
                      连接中...
                    </>
                  ) : (
                    '连接'
                  )}
                </button>
                <button
                  onClick={handleDisconnect}
                  disabled={loading || !address.trim()}
                  className="px-4 py-2 bg-red-600 hover:bg-red-700 disabled:bg-gray-400 text-white rounded-lg font-medium transition-colors"
                >
                  断开
                </button>
              </div>
            </div>
          )}

          {/* 启用 TCP/IP 选项卡 */}
          {activeTab === 'enable' && (
            <div className="space-y-4">
              <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-4">
                <div className="flex items-start gap-2">
                  <svg
                    className="w-5 h-5 text-amber-500 mt-0.5 flex-shrink-0"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                    />
                  </svg>
                  <div className="text-sm text-amber-800 dark:text-amber-300">
                    <p className="font-medium mb-1">操作步骤：</p>
                    <ol className="list-decimal list-inside space-y-1">
                      <li>通过 USB 连接设备</li>
                      <li>选择要启用 WiFi ADB 的设备</li>
                      <li>点击&ldquo;启用 TCP/IP&rdquo;按钮</li>
                      <li>获取设备 IP 后,拔掉 USB 线</li>
                      <li>在&ldquo;WiFi 连接&rdquo;选项卡使用该 IP 连接</li>
                    </ol>
                  </div>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  选择设备
                </label>
                <select
                  value={selectedDevice}
                  onChange={e => setSelectedDevice(e.target.value)}
                  className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  disabled={loading || usbDevices.length === 0}
                >
                  <option value="">
                    {usbDevices.length > 0
                      ? '自动选择（第一个设备）'
                      : '没有可用的 USB 设备'}
                  </option>
                  {usbDevices.map(device => (
                    <option key={device.id} value={device.id}>
                      {device.model} ({device.id})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  TCP/IP 端口
                </label>
                <input
                  type="number"
                  value={port}
                  onChange={e => setPort(e.target.value)}
                  placeholder="5555"
                  className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  disabled={loading}
                />
              </div>

              {deviceIp && (
                <div className="space-y-3">
                  <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium text-green-800 dark:text-green-300 mb-1">
                          设备 IP 地址
                        </p>
                        <p className="text-lg font-mono text-green-900 dark:text-green-200">
                          {deviceIp}:{port}
                        </p>
                      </div>
                      <button
                        onClick={() => copyToClipboard(`${deviceIp}:${port}`)}
                        className="px-3 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg text-sm font-medium transition-colors"
                      >
                        复制
                      </button>
                    </div>
                  </div>
                  <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-3">
                    <p className="text-sm text-blue-800 dark:text-blue-300">
                      💡 <strong>下一步：</strong>
                      拔掉 USB
                      线，在自动切换的&ldquo;WiFi连接&rdquo;选项卡点击连接即可
                    </p>
                  </div>
                </div>
              )}

              <div className="flex gap-3">
                <button
                  onClick={handleEnableTcpip}
                  disabled={loading || usbDevices.length === 0}
                  className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white rounded-lg font-medium transition-colors flex items-center justify-center gap-2"
                >
                  {loading ? (
                    <>
                      <svg
                        className="animate-spin h-5 w-5"
                        fill="none"
                        viewBox="0 0 24 24"
                      >
                        <circle
                          className="opacity-25"
                          cx="12"
                          cy="12"
                          r="10"
                          stroke="currentColor"
                          strokeWidth="4"
                        />
                        <path
                          className="opacity-75"
                          fill="currentColor"
                          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                        />
                      </svg>
                      处理中...
                    </>
                  ) : (
                    '启用 TCP/IP'
                  )}
                </button>
                <button
                  onClick={handleGetIp}
                  disabled={loading || usbDevices.length === 0}
                  className="px-4 py-2 bg-gray-600 hover:bg-gray-700 disabled:bg-gray-400 text-white rounded-lg font-medium transition-colors"
                >
                  获取 IP
                </button>
              </div>
            </div>
          )}

          {/* 消息提示 */}
          {message && (
            <div
              className={`mt-4 p-4 rounded-lg ${
                message.type === 'success'
                  ? 'bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 text-green-800 dark:text-green-300'
                  : message.type === 'error'
                    ? 'bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-800 dark:text-red-300'
                    : 'bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 text-blue-800 dark:text-blue-300'
              }`}
            >
              <p className="text-sm whitespace-pre-wrap">{message.text}</p>
            </div>
          )}
        </div>

        {/* 底部 */}
        <div className="px-6 py-4 border-t border-gray-200 dark:border-gray-700 flex justify-end">
          <button
            onClick={handleClose}
            className="px-4 py-2 bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 text-gray-800 dark:text-gray-200 rounded-lg font-medium transition-colors"
          >
            关闭
          </button>
        </div>
      </div>
    </div>
  );
}
