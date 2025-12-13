import { createFileRoute } from '@tanstack/react-router';
import * as React from 'react';
import { useState, useRef, useEffect } from 'react';
import {
  sendMessageStream,
  initAgent,
  resetChat,
  listDevices,
  type StepEvent,
  type DoneEvent,
  type ErrorEvent,
  type ScreenshotResponse,
  type Device,
} from '../api';
import { DeviceSidebar } from '../components/DeviceSidebar';
import { DevicePanel } from '../components/DevicePanel';

export const Route = createFileRoute('/chat')({
  component: ChatComponent,
});

interface Message {
  id: string;
  role: 'user' | 'agent';
  content: string;
  timestamp: Date;
  steps?: number;
  success?: boolean;
  thinking?: string[]; // 存储每步的思考过程
  actions?: any[]; // 存储每步的动作
  isStreaming?: boolean; // 标记是否正在流式接收
}

// 每个设备的独立状态
interface DeviceState {
  messages: Message[];
  loading: boolean;
  error: string | null;
  initialized: boolean;
  chatStream: { close: () => void } | null;  // 聊天流（设备切换时不中断）
  videoStream: { close: () => void } | null;  // 视频流（设备切换时中断）
  screenshot: ScreenshotResponse | null;
  useVideoStream: boolean;
  videoStreamFailed: boolean;
  displayMode: 'auto' | 'video' | 'screenshot';
  tapFeedback: string | null;
}

function ChatComponent() {
  // 设备列表和当前选中设备
  const [devices, setDevices] = useState<Device[]>([]);
  const [currentDeviceId, setCurrentDeviceId] = useState<string>('');

  // 每个设备的独立状态
  const [deviceStates, setDeviceStates] = useState<Map<string, DeviceState>>(
    new Map()
  );

  // 全局配置（所有设备共享）
  const [config, setConfig] = useState({
    baseUrl: '',
    apiKey: '',
    modelName: '',
  });
  const [showConfig, setShowConfig] = useState(false);

  // 旧状态保留用于向后兼容（已废弃）
  const [input, setInput] = useState('');

  // 用于追踪当前流式消息的最新数据，避免状态更新竞态
  const currentThinkingRef = useRef<string[]>([]);
  const currentActionsRef = useRef<any[]>([]);

  // 获取当前设备的状态（如果不存在则返回默认值）
  const getCurrentDeviceState = (): DeviceState => {
    return (
      deviceStates.get(currentDeviceId) || {
        messages: [],
        loading: false,
        error: null,
        initialized: false,
        chatStream: null,
        videoStream: null,
        screenshot: null,
        useVideoStream: true,
        videoStreamFailed: false,
        displayMode: 'auto' as const,
        tapFeedback: null,
      }
    );
  };

  // 更新特定设备的状态
  const updateDeviceState = (
    deviceId: string,
    updates: Partial<DeviceState>
  ) => {
    setDeviceStates(prev => {
      const newMap = new Map(prev);
      const currentState = newMap.get(deviceId) || {
        messages: [],
        loading: false,
        error: null,
        initialized: false,
        chatStream: null,
        videoStream: null,
        screenshot: null,
        useVideoStream: true,
        videoStreamFailed: false,
        displayMode: 'auto' as const,
        tapFeedback: null,
      };
      newMap.set(deviceId, { ...currentState, ...updates });
      return newMap;
    });
  };

  // 当前设备状态的快捷访问
  const currentState = getCurrentDeviceState();

  // 加载设备列表
  useEffect(() => {
    const loadDevices = async () => {
      try {
        const response = await listDevices();
        setDevices(response.devices);

        // 自动选择第一个设备（如果当前没有选中设备）
        if (response.devices.length > 0 && !currentDeviceId) {
          setCurrentDeviceId(response.devices[0].id);
        }
      } catch (error) {
        console.error('Failed to load devices:', error);
      }
    };

    loadDevices();
    // 每3秒刷新设备列表
    const interval = setInterval(loadDevices, 3000);
    return () => clearInterval(interval);
  }, [currentDeviceId]);

  // 初始化特定设备的 Agent
  const handleInit = async (deviceId: string) => {
    try {
      await initAgent({
        model_config: {
          base_url: config.baseUrl || undefined,
          api_key: config.apiKey || undefined,
          model_name: config.modelName || undefined,
        },
        agent_config: {
          device_id: deviceId,
        },
      });
      updateDeviceState(deviceId, { initialized: true, error: null });
      setShowConfig(false);
    } catch (error) {
      updateDeviceState(deviceId, {
        error:
          error instanceof Error
            ? error.message
            : '初始化失败，请检查配置或确保后端服务正在运行',
      });
    }
  };

  // 发送消息（流式）
  const handleSend = async () => {
    if (!input.trim() || currentState.loading) return;

    // 检查是否选中了设备
    if (!currentDeviceId) {
      alert('请先选择一个设备');
      return;
    }

    // 如果设备未初始化，先初始化
    if (!currentState.initialized) {
      await handleInit(currentDeviceId);
    }

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input.trim(),
      timestamp: new Date(),
    };

    // 更新设备状态：添加用户消息
    updateDeviceState(currentDeviceId, {
      messages: [...currentState.messages, userMessage],
      loading: true,
      error: null,
    });

    setInput('');

    // 重置当前流式消息的 ref
    currentThinkingRef.current = [];
    currentActionsRef.current = [];

    // 创建占位 Agent 消息
    const agentMessageId = (Date.now() + 1).toString();
    const agentMessage: Message = {
      id: agentMessageId,
      role: 'agent',
      content: '',
      timestamp: new Date(),
      thinking: [],
      actions: [],
      isStreaming: true,
    };

    // 更新设备状态：添加 Agent 消息占位符
    updateDeviceState(currentDeviceId, {
      messages: [...currentState.messages, userMessage, agentMessage],
    });

    // 启动流式接收
    const stream = sendMessageStream(
      userMessage.content,
      currentDeviceId, // 传递设备 ID
      // onStep
      (event: StepEvent) => {
        console.log('[Chat] Processing step event:', event);

        // 先更新 ref（这是同步的，不会有竞态）
        currentThinkingRef.current.push(event.thinking);
        currentActionsRef.current.push(event.action);

        // 获取最新的设备状态并更新消息
        setDeviceStates(prev => {
          const newMap = new Map(prev);
          const state = newMap.get(currentDeviceId);
          if (!state) return prev;

          const updatedMessages = state.messages.map(msg =>
            msg.id === agentMessageId
              ? {
                  ...msg,
                  thinking: [...currentThinkingRef.current],
                  actions: [...currentActionsRef.current],
                  steps: event.step,
                }
              : msg
          );

          newMap.set(currentDeviceId, { ...state, messages: updatedMessages });
          return newMap;
        });
      },
      // onDone
      (event: DoneEvent) => {
        setDeviceStates(prev => {
          const newMap = new Map(prev);
          const state = newMap.get(currentDeviceId);
          if (!state) return prev;

          const updatedMessages = state.messages.map(msg =>
            msg.id === agentMessageId
              ? {
                  ...msg,
                  content: event.message,
                  success: event.success,
                  isStreaming: false,
                }
              : msg
          );

          newMap.set(currentDeviceId, {
            ...state,
            messages: updatedMessages,
            loading: false,
            chatStream: null,
          });
          return newMap;
        });
      },
      // onError
      (event: ErrorEvent) => {
        setDeviceStates(prev => {
          const newMap = new Map(prev);
          const state = newMap.get(currentDeviceId);
          if (!state) return prev;

          const updatedMessages = state.messages.map(msg =>
            msg.id === agentMessageId
              ? {
                  ...msg,
                  content: `错误: ${event.message}`,
                  success: false,
                  isStreaming: false,
                }
              : msg
          );

          newMap.set(currentDeviceId, {
            ...state,
            messages: updatedMessages,
            loading: false,
            chatStream: null,
            error: event.message,
          });
          return newMap;
        });
      }
    );

    // 保存流对象到设备状态
    updateDeviceState(currentDeviceId, { chatStream: stream });
  };

  // 重置当前设备的对话
  const handleReset = async () => {
    if (!currentDeviceId) return;

    // 取消正在进行的流式请求
    if (currentState.chatStream) {
      currentState.chatStream.close();
    }

    // 重置设备状态
    updateDeviceState(currentDeviceId, {
      messages: [],
      loading: false,
      error: null,
      chatStream: null,
    });

    // 调用后端重置
    await resetChat(currentDeviceId);
  };

  // 切换设备
  const handleDeviceChange = (deviceId: string) => {
    // 只停止当前设备的视频流，保留聊天流继续运行
    if (currentState.videoStream) {
      currentState.videoStream.close();
      updateDeviceState(currentDeviceId, { videoStream: null });
    }

    setCurrentDeviceId(deviceId);
  };

  return (
    <div className="h-full flex relative">
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
                    setConfig({ ...config, baseUrl: e.target.value })
                  }
                  placeholder="留空使用默认值"
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
                    setConfig({ ...config, apiKey: e.target.value })
                  }
                  placeholder="留空使用默认值"
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
                    setConfig({ ...config, modelName: e.target.value })
                  }
                  placeholder="留空使用默认值"
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
                  onClick={() => {
                    if (currentDeviceId) {
                      handleInit(currentDeviceId);
                    } else {
                      alert('请先选择一个设备');
                    }
                  }}
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
        onSelectDevice={handleDeviceChange}
        onOpenConfig={() => setShowConfig(true)}
      />

      {/* 右侧主内容区 */}
      {currentDeviceId ? (
        <DevicePanel
          deviceId={currentDeviceId}
          deviceName={
            devices.find(d => d.id === currentDeviceId)?.model || '未知设备'
          }
          deviceState={currentState}
          input={input}
          onInputChange={setInput}
          onSendMessage={handleSend}
          onReset={handleReset}
          onInitialize={() => handleInit(currentDeviceId)}
          updateDeviceState={updateDeviceState}
        />
      ) : (
        <div className="flex-1 flex items-center justify-center bg-gray-50 dark:bg-gray-900">
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
            <h3 className="text-lg font-medium mb-2">欢迎使用 AutoGLM Chat</h3>
            <p className="text-sm">请从左侧选择一个设备开始</p>
          </div>
        </div>
      )}
    </div>
  );
}
