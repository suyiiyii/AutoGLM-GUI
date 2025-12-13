import React, { useRef, useEffect, useState } from 'react';
import { ScrcpyPlayer } from './ScrcpyPlayer';
import type { ScreenshotResponse } from '../api';
import { getScreenshot } from '../api';

interface Message {
  id: string;
  role: 'user' | 'agent';
  content: string;
  timestamp: Date;
  steps?: number;
  success?: boolean;
  thinking?: string[];
  actions?: any[];
  isStreaming?: boolean;
}

interface DeviceState {
  messages: Message[];
  loading: boolean;
  error: string | null;
  initialized: boolean;
  chatStream: { close: () => void } | null;  // 聊天流
  videoStream: { close: () => void } | null;  // 视频流
  screenshot: ScreenshotResponse | null;
  useVideoStream: boolean;
  videoStreamFailed: boolean;
  displayMode: 'auto' | 'video' | 'screenshot';
  tapFeedback: string | null;
}

interface DevicePanelProps {
  deviceId: string;
  deviceName: string;
  deviceState: DeviceState;
  input: string;
  onInputChange: (value: string) => void;
  onSendMessage: () => void;
  onReset: () => void;
  onInitialize: () => void;
  updateDeviceState: (deviceId: string, updates: Partial<DeviceState>) => void;
}

export function DevicePanel({
  deviceId,
  deviceName,
  deviceState,
  input,
  onInputChange,
  onSendMessage,
  onReset,
  onInitialize,
  updateDeviceState,
}: DevicePanelProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const screenshotFetchingRef = useRef(false);

  // 滚动到底部
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [deviceState.messages]);

  // 截图轮询
  useEffect(() => {
    if (!deviceId) return;

    const shouldPollScreenshots =
      deviceState.displayMode === 'screenshot' ||
      (deviceState.displayMode === 'auto' && deviceState.videoStreamFailed);

    if (!shouldPollScreenshots) {
      return;
    }

    const fetchScreenshot = async () => {
      if (screenshotFetchingRef.current) return;

      screenshotFetchingRef.current = true;
      try {
        const data = await getScreenshot(deviceId);
        if (data.success) {
          updateDeviceState(deviceId, { screenshot: data });
        }
      } catch (e) {
        console.error('Failed to fetch screenshot:', e);
      } finally {
        screenshotFetchingRef.current = false;
      }
    };

    fetchScreenshot();
    const interval = setInterval(fetchScreenshot, 500);

    return () => clearInterval(interval);
  }, [deviceId, deviceState.videoStreamFailed, deviceState.displayMode]);

  const handleInputKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      onSendMessage();
    }
  };

  // 处理视频流就绪事件
  const handleVideoStreamReady = (stream: { close: () => void } | null) => {
    updateDeviceState(deviceId, { videoStream: stream });
  };

  return (
    <div className="flex-1 flex gap-4 p-4 items-center justify-center">
      {/* Chatbox */}
      <div className="flex flex-col w-full max-w-2xl h-[750px] border border-gray-200 dark:border-gray-700 rounded-2xl shadow-lg bg-white dark:bg-gray-800">
        {/* 头部 */}
        <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700 rounded-t-2xl">
          <div>
            <h2 className="text-lg font-semibold">{deviceName}</h2>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              {deviceId}
            </p>
          </div>
          <div className="flex gap-2">
            {!deviceState.initialized ? (
              <button
                onClick={onInitialize}
                className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors text-sm"
              >
                初始化设备
              </button>
            ) : (
              <span className="px-3 py-1 bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200 rounded-full text-sm">
                已初始化
              </span>
            )}
            <button
              onClick={onReset}
              className="px-4 py-2 bg-gray-200 dark:bg-gray-700 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors text-sm"
            >
              重置
            </button>
          </div>
        </div>

        {/* 错误提示 */}
        {deviceState.error && (
          <div className="mx-4 mt-4 p-3 bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-200 rounded-lg text-sm">
            {deviceState.error}
          </div>
        )}

        {/* 消息列表 */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {deviceState.messages.length === 0 ? (
            <div className="text-center text-gray-500 dark:text-gray-400 mt-8">
              <p className="text-lg">设备已选择</p>
              <p className="text-sm mt-2">输入任务描述，让 AI 帮你操作手机</p>
            </div>
          ) : null}

          {deviceState.messages.map(message => (
            <div
              key={message.id}
              className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              {message.role === 'agent' ? (
                <div className="max-w-[80%] space-y-2">
                  {/* 显示每步思考过程 */}
                  {message.thinking?.map((think, idx) => (
                    <div
                      key={idx}
                      className="bg-gray-100 dark:bg-gray-700 rounded-2xl px-4 py-3 border-l-4 border-blue-500"
                    >
                      <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">
                        💭 步骤 {idx + 1} - 思考过程
                      </div>
                      <p className="text-sm whitespace-pre-wrap">{think}</p>

                      {message.actions?.[idx] && (
                        <details className="mt-2 text-xs">
                          <summary className="cursor-pointer text-blue-500 hover:text-blue-600">
                            查看动作
                          </summary>
                          <pre className="mt-1 p-2 bg-gray-800 text-gray-200 rounded overflow-x-auto text-xs">
                            {JSON.stringify(message.actions[idx], null, 2)}
                          </pre>
                        </details>
                      )}
                    </div>
                  ))}

                  {/* 最终结果 */}
                  {message.content && (
                    <div
                      className={`rounded-2xl px-4 py-3 ${
                        message.success === false
                          ? 'bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-200'
                          : 'bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200'
                      }`}
                    >
                      <p className="whitespace-pre-wrap">{message.content}</p>
                      {message.steps !== undefined && (
                        <p className="text-xs mt-2 opacity-70">
                          总步数: {message.steps}
                        </p>
                      )}
                    </div>
                  )}

                  {/* 流式加载提示 */}
                  {message.isStreaming && (
                    <div className="text-sm text-gray-500 dark:text-gray-400 animate-pulse">
                      正在执行...
                    </div>
                  )}
                </div>
              ) : (
                <div className="max-w-[70%] rounded-2xl px-4 py-3 bg-blue-500 text-white">
                  <p className="whitespace-pre-wrap">{message.content}</p>
                </div>
              )}
            </div>
          ))}

          <div ref={messagesEndRef} />
        </div>

        {/* 输入区域 */}
        <div className="p-4 border-t border-gray-200 dark:border-gray-700 rounded-b-2xl">
          <div className="flex gap-2">
            <input
              type="text"
              value={input}
              onChange={e => onInputChange(e.target.value)}
              onKeyDown={handleInputKeyDown}
              placeholder={
                !deviceState.initialized
                  ? '请先初始化设备'
                  : '输入任务描述...'
              }
              disabled={deviceState.loading}
              className="flex-1 px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-xl bg-white dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            />
            <button
              onClick={onSendMessage}
              disabled={deviceState.loading || !input.trim()}
              className="px-6 py-3 bg-blue-500 text-white rounded-xl hover:bg-blue-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              发送
            </button>
          </div>
        </div>
      </div>

      {/* Screen Monitor */}
      <div className="w-full max-w-xs h-[750px] border border-gray-200 dark:border-gray-700 rounded-2xl shadow-lg bg-gray-900 overflow-hidden relative">
        {/* Mode Switch Button */}
        <div className="absolute top-2 right-2 z-10 flex gap-1 bg-black/70 rounded-lg p-1">
          <button
            onClick={() =>
              updateDeviceState(deviceId, { displayMode: 'auto' })
            }
            className={`px-3 py-1 text-xs rounded transition-colors ${
              deviceState.displayMode === 'auto'
                ? 'bg-blue-500 text-white'
                : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
            }`}
          >
            自动
          </button>
          <button
            onClick={() =>
              updateDeviceState(deviceId, { displayMode: 'video' })
            }
            className={`px-3 py-1 text-xs rounded transition-colors ${
              deviceState.displayMode === 'video'
                ? 'bg-blue-500 text-white'
                : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
            }`}
          >
            视频流
          </button>
          <button
            onClick={() =>
              updateDeviceState(deviceId, { displayMode: 'screenshot' })
            }
            className={`px-3 py-1 text-xs rounded transition-colors ${
              deviceState.displayMode === 'screenshot'
                ? 'bg-blue-500 text-white'
                : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
            }`}
          >
            截图
          </button>
        </div>

        {deviceState.displayMode === 'video' ||
        (deviceState.displayMode === 'auto' &&
          deviceState.useVideoStream &&
          !deviceState.videoStreamFailed) ? (
          <>
            {deviceState.tapFeedback && (
              <div className="absolute top-14 right-2 z-20 px-3 py-2 bg-blue-500 text-white text-sm rounded-lg shadow-lg">
                {deviceState.tapFeedback}
              </div>
            )}

            <ScrcpyPlayer
              deviceId={deviceId}
              className="w-full h-full"
              enableControl={true}
              onFallback={() => {
                updateDeviceState(deviceId, {
                  videoStreamFailed: true,
                  useVideoStream: false,
                });
              }}
              onTapSuccess={() => {
                updateDeviceState(deviceId, { tapFeedback: 'Tap executed' });
                setTimeout(
                  () => updateDeviceState(deviceId, { tapFeedback: null }),
                  2000
                );
              }}
              onTapError={error => {
                updateDeviceState(deviceId, {
                  tapFeedback: `Tap failed: ${error}`,
                });
                setTimeout(
                  () => updateDeviceState(deviceId, { tapFeedback: null }),
                  3000
                );
              }}
              onSwipeSuccess={() => {
                updateDeviceState(deviceId, {
                  tapFeedback: 'Swipe executed',
                });
                setTimeout(
                  () => updateDeviceState(deviceId, { tapFeedback: null }),
                  2000
                );
              }}
              onSwipeError={error => {
                updateDeviceState(deviceId, {
                  tapFeedback: `Swipe failed: ${error}`,
                });
                setTimeout(
                  () => updateDeviceState(deviceId, { tapFeedback: null }),
                  3000
                );
              }}
              onStreamReady={handleVideoStreamReady}
              fallbackTimeout={100000}
            />
          </>
        ) : (
          <div className="w-full h-full flex items-center justify-center bg-gray-900">
            {deviceState.screenshot && deviceState.screenshot.success ? (
              <div className="relative w-full h-full flex items-center justify-center">
                <img
                  src={`data:image/png;base64,${deviceState.screenshot.image}`}
                  alt="Device Screenshot"
                  className="max-w-full max-h-full object-contain"
                  style={{
                    width:
                      deviceState.screenshot.width >
                      deviceState.screenshot.height
                        ? '100%'
                        : 'auto',
                    height:
                      deviceState.screenshot.width >
                      deviceState.screenshot.height
                        ? 'auto'
                        : '100%',
                  }}
                />
                {deviceState.screenshot.is_sensitive && (
                  <div className="absolute top-12 right-2 px-2 py-1 bg-yellow-500 text-white text-xs rounded">
                    敏感内容
                  </div>
                )}
                <div className="absolute bottom-2 left-2 px-2 py-1 bg-blue-500 text-white text-xs rounded">
                  截图模式 (0.5s 刷新)
                  {deviceState.displayMode === 'auto' &&
                    deviceState.videoStreamFailed &&
                    ' - 视频流不可用'}
                </div>
              </div>
            ) : deviceState.screenshot?.error ? (
              <div className="text-center text-red-500 dark:text-red-400">
                <p className="mb-2">截图失败</p>
                <p className="text-xs">{deviceState.screenshot.error}</p>
              </div>
            ) : (
              <div className="text-center text-gray-500 dark:text-gray-400">
                <div className="w-8 h-8 border-4 border-gray-300 border-t-blue-500 rounded-full animate-spin mx-auto mb-2" />
                <p>加载中...</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
