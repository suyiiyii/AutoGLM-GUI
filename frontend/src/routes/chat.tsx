import { createFileRoute } from '@tanstack/react-router';
import * as React from 'react';
import { useState, useRef, useEffect } from 'react';
import {
  sendMessageStream,
  initAgent,
  resetChat,
  getStatus,
  getScreenshot,
  type StepEvent,
  type DoneEvent,
  type ErrorEvent,
  type ScreenshotResponse,
} from '../api';
import { ScrcpyPlayer } from '../components/ScrcpyPlayer';

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

function ChatComponent() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [initialized, setInitialized] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [screenshot, setScreenshot] = useState<ScreenshotResponse | null>(null);
  const [currentStream, setCurrentStream] = useState<any>(null);
  const [config, setConfig] = useState({
    baseUrl: '',
    apiKey: '',
    modelName: '',
  });
  const [showConfig, setShowConfig] = useState(false);
  const [useVideoStream, setUseVideoStream] = useState(true); // Try video stream first
  const [videoStreamFailed, setVideoStreamFailed] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const screenshotFetchingRef = useRef(false);

  // 用于追踪当前流式消息的最新数据，避免状态更新竞态
  const currentThinkingRef = useRef<string[]>([]);
  const currentActionsRef = useRef<any[]>([]);

  // 滚动到底部
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // 检查初始化状态并自动初始化
  useEffect(() => {
    const initializeAgent = async () => {
      try {
        const status = await getStatus();
        if (status.initialized) {
          setInitialized(true);
        } else {
          // 尝试自动初始化（使用后端默认值）
          try {
            await initAgent();
            setInitialized(true);
          } catch {
            // 自动初始化失败，等待用户手动配置
            setInitialized(false);
          }
        }
      } catch (error) {
        setInitialized(false);
        setError('无法连接到后端服务');
      }
    };

    initializeAgent();
  }, []);

  // 截图轮询 (仅在 fallback 模式下运行)
  useEffect(() => {
    if (!videoStreamFailed) {
      return; // Video stream is working, don't poll screenshots
    }

    const fetchScreenshot = async () => {
      // 如果有正在进行的请求，跳过本次请求
      if (screenshotFetchingRef.current) {
        return;
      }

      screenshotFetchingRef.current = true;
      try {
        const data = await getScreenshot();
        if (data.success) {
          setScreenshot(data);
        }
      } catch (e) {
        console.error('Failed to fetch screenshot:', e);
      } finally {
        screenshotFetchingRef.current = false;
      }
    };

    // 立即获取一次
    fetchScreenshot();

    // 设置定时器每 0.5 秒刷新
    const interval = setInterval(fetchScreenshot, 500);

    return () => clearInterval(interval);
  }, [videoStreamFailed]);

  // 初始化 Agent
  const handleInit = async () => {
    setError(null);
    try {
      await initAgent({
        model_config: {
          base_url: config.baseUrl || undefined,
          api_key: config.apiKey || undefined,
          model_name: config.modelName || undefined,
        },
      });
      setInitialized(true);
      setShowConfig(false);
    } catch {
      setError('初始化失败，请检查配置或确保后端服务正在运行');
    }
  };

  // 发送消息（流式）
  const handleSend = async () => {
    if (!input.trim() || loading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input.trim(),
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setLoading(true);
    setError(null);

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
    setMessages(prev => [...prev, agentMessage]);

    // 启动流式接收
    const stream = sendMessageStream(
      userMessage.content,
      // onStep
      (event: StepEvent) => {
        console.log('[Chat] Processing step event:', event);

        // 先更新 ref（这是同步的，不会有竞态）
        currentThinkingRef.current.push(event.thinking);
        currentActionsRef.current.push(event.action);

        // 再基于 ref 更新状态
        setMessages(prev =>
          prev.map(msg =>
            msg.id === agentMessageId
              ? {
                  ...msg,
                  thinking: [...currentThinkingRef.current],
                  actions: [...currentActionsRef.current],
                  steps: event.step,
                }
              : msg
          )
        );
      },
      // onDone
      (event: DoneEvent) => {
        setMessages(prev =>
          prev.map(msg =>
            msg.id === agentMessageId
              ? {
                  ...msg,
                  content: event.message,
                  success: event.success,
                  isStreaming: false,
                }
              : msg
          )
        );
        setLoading(false);
        setCurrentStream(null);
      },
      // onError
      (event: ErrorEvent) => {
        setMessages(prev =>
          prev.map(msg =>
            msg.id === agentMessageId
              ? {
                  ...msg,
                  content: `错误: ${event.message}`,
                  success: false,
                  isStreaming: false,
                }
              : msg
          )
        );
        setLoading(false);
        setCurrentStream(null);
      }
    );

    setCurrentStream(stream);
  };

  // 重置对话
  const handleReset = async () => {
    // 取消正在进行的流式请求
    if (currentStream) {
      currentStream.close();
      setCurrentStream(null);
    }

    // 重置所有状态
    setLoading(false);
    setMessages([]);
    setError(null);

    // 调用后端重置
    await resetChat();
  };

  const handleInputKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="h-full flex items-center justify-center p-4 gap-4 relative">
      {/* Config Modal */}
      {showConfig && (
        <div className="absolute inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 rounded-2xl">
          <div className="bg-white dark:bg-gray-800 p-6 rounded-2xl w-96 shadow-xl border border-gray-200 dark:border-gray-700">
            <h2 className="text-xl font-bold mb-4 text-gray-900 dark:text-gray-100">Agent 配置</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">Base URL</label>
                <input
                  type="text"
                  value={config.baseUrl}
                  onChange={e => setConfig({ ...config, baseUrl: e.target.value })}
                  placeholder="留空使用默认值"
                  className="w-full px-3 py-2 border rounded-lg bg-white dark:bg-gray-700 border-gray-300 dark:border-gray-600 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500 outline-none"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">API Key</label>
                <input
                  type="password"
                  value={config.apiKey}
                  onChange={e => setConfig({ ...config, apiKey: e.target.value })}
                  placeholder="留空使用默认值"
                  className="w-full px-3 py-2 border rounded-lg bg-white dark:bg-gray-700 border-gray-300 dark:border-gray-600 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500 outline-none"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">Model Name</label>
                <input
                  type="text"
                  value={config.modelName}
                  onChange={e => setConfig({ ...config, modelName: e.target.value })}
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
                  onClick={handleInit}
                  className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
                >
                  确认初始化
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Chatbox */}
      <div className="flex flex-col w-full max-w-2xl h-[750px] border border-gray-200 dark:border-gray-700 rounded-2xl shadow-lg bg-white dark:bg-gray-800">
        {/* 头部 */}
        <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700 rounded-t-2xl">
          <h1 className="text-xl font-semibold">AutoGLM Chat</h1>
          <div className="flex gap-2">
            {!initialized ? (
              <button
                onClick={() => setShowConfig(true)}
                className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors flex items-center justify-center"
              >
                配置 Agent
              </button>
            ) : (
              <span className="px-3 py-1 bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200 rounded-full text-sm flex items-center justify-center">
                已初始化
              </span>
            )}
            <button
              onClick={handleReset}
              className="px-4 py-2 bg-gray-200 dark:bg-gray-700 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors flex items-center justify-center"
            >
              重置
            </button>
          </div>
        </div>

        {/* 错误提示 */}
        {error && (
          <div className="mx-4 mt-4 p-3 bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-200 rounded-lg">
            {error}
          </div>
        )}

        {/* 消息列表 */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.length === 0 && (
            <div className="text-center text-gray-500 dark:text-gray-400 mt-8">
              <p className="text-lg">欢迎使用 AutoGLM Chat</p>
              <p className="text-sm mt-2">输入任务描述，让 AI 帮你操作手机</p>
            </div>
          )}

          {messages.map(message => (
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
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleInputKeyDown}
              placeholder={initialized ? '输入任务描述...' : '请先初始化 Agent'}
              disabled={!initialized || loading}
              className="flex-1 px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-xl bg-white dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            />
            <button
              onClick={handleSend}
              disabled={!initialized || loading || !input.trim()}
              className="px-6 py-3 bg-blue-500 text-white rounded-xl hover:bg-blue-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center"
            >
              发送
            </button>
          </div>
        </div>
      </div>

      {/* Real-time Video Stream or Screenshot Fallback */}
      <div className="w-full max-w-xs h-[750px] border border-gray-200 dark:border-gray-700 rounded-2xl shadow-lg bg-gray-900 overflow-hidden">
        {useVideoStream && !videoStreamFailed ? (
          <ScrcpyPlayer
            className="w-full h-full"
            onFallback={() => {
              console.log('[Chat] Video stream failed, falling back to screenshots');
              setVideoStreamFailed(true);
              setUseVideoStream(false);
            }}
            fallbackTimeout={5000}
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center bg-gray-900">
            {screenshot && screenshot.success ? (
              <div className="relative w-full h-full flex items-center justify-center">
                <img
                  src={`data:image/png;base64,${screenshot.image}`}
                  alt="Device Screenshot"
                  className="max-w-full max-h-full object-contain"
                  style={{
                    width: screenshot.width > screenshot.height ? '100%' : 'auto',
                    height: screenshot.width > screenshot.height ? 'auto' : '100%',
                  }}
                />
                {screenshot.is_sensitive && (
                  <div className="absolute top-2 right-2 px-2 py-1 bg-yellow-500 text-white text-xs rounded">
                    敏感内容
                  </div>
                )}
                {/* Fallback indicator */}
                <div className="absolute bottom-2 left-2 px-2 py-1 bg-blue-500 text-white text-xs rounded">
                  截图模式 (0.5s 刷新)
                </div>
              </div>
            ) : screenshot?.error ? (
              <div className="text-center text-red-500 dark:text-red-400">
                <p className="mb-2">截图失败</p>
                <p className="text-xs">{screenshot.error}</p>
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
