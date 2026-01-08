import { createFileRoute, useNavigate } from '@tanstack/react-router';
import * as React from 'react';
import { useState, useEffect, useCallback } from 'react';
import {
  connectWifi,
  disconnectWifi,
  listDevices,
  getConfig,
  saveConfig,
  reinitAllAgents,
  getErrorMessage,
  type Device,
  type ConfigSaveRequest,
} from '../api';
import { DeviceSidebar } from '../components/DeviceSidebar';
import { DevicePanel } from '../components/DevicePanel';
import { ChatKitPanel } from '../components/ChatKitPanel';
import { Toast, type ToastType } from '../components/Toast';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import {
  Settings,
  CheckCircle2,
  AlertCircle,
  Eye,
  EyeOff,
  Server,
  ExternalLink,
  Brain,
  Layers,
  Sparkles,
  Cpu,
  Info,
} from 'lucide-react';
import { useTranslation } from '../lib/i18n-context';

// 视觉模型预设配置
const VISION_PRESETS = [
  {
    name: 'bigmodel',
    config: {
      base_url: 'https://open.bigmodel.cn/api/paas/v4',
      model_name: 'autoglm-phone',
    },
    apiKeyUrl: 'https://bigmodel.cn/usercenter/proj-mgmt/apikeys',
  },
  {
    name: 'modelscope',
    config: {
      base_url: 'https://api-inference.modelscope.cn/v1',
      model_name: 'ZhipuAI/AutoGLM-Phone-9B',
    },
    apiKeyUrl: 'https://www.modelscope.cn/my/myaccesstoken',
  },
  {
    name: 'custom',
    config: {
      base_url: '',
      model_name: 'autoglm-phone-9b',
    },
  },
] as const;

// Agent 类型预设配置
const AGENT_PRESETS = [
  {
    name: 'glm',
    displayName: 'GLM Agent',
    description: '基于 GLM 模型优化，成熟稳定，适合大多数任务',
    icon: Cpu,
    defaultConfig: {},
  },
  {
    name: 'mai',
    displayName: 'MAI Agent',
    description: '阿里通义团队开发，支持多张历史截图上下文',
    icon: Brain,
    defaultConfig: {
      history_n: 3,
    },
  },
] as const;

// 决策模型预设配置（与视觉模型保持一致）
const DECISION_PRESETS = [
  {
    name: 'bigmodel',
    config: {
      decision_base_url: 'https://open.bigmodel.cn/api/paas/v4',
      decision_model_name: 'glm-4.7',
    },
    apiKeyUrl: 'https://bigmodel.cn/usercenter/proj-mgmt/apikeys',
  },
  {
    name: 'modelscope',
    config: {
      decision_base_url: 'https://api-inference.modelscope.cn/v1',
      decision_model_name: 'Qwen/Qwen3-235B-A22B-Instruct-2507',
    },
    apiKeyUrl: 'https://www.modelscope.cn/my/myaccesstoken',
  },
  {
    name: 'custom',
    config: {
      decision_base_url: '',
      decision_model_name: '',
    },
  },
] as const;

// Search params type for URL persistence
type ChatSearchParams = {
  serial?: string;
  mode?: 'classic' | 'chatkit';
};

export const Route = createFileRoute('/chat')({
  component: ChatComponent,
  validateSearch: (search: Record<string, unknown>): ChatSearchParams => {
    const mode = search.mode;
    return {
      serial: typeof search.serial === 'string' ? search.serial : undefined,
      mode: mode === 'classic' || mode === 'chatkit' ? mode : undefined,
    };
  },
});

function ChatComponent() {
  const t = useTranslation();
  const searchParams = Route.useSearch();
  const navigate = useNavigate();
  const [devices, setDevices] = useState<Device[]>([]);
  const [currentDeviceId, setCurrentDeviceId] = useState<string>('');
  // Chat mode: 'classic' for DevicePanel (single model), 'chatkit' for ChatKitPanel (layered agent)
  // Initialize from URL search params if available
  const [chatMode, setChatMode] = useState<'classic' | 'chatkit'>(
    searchParams.mode || 'classic'
  );

  // Track if we've done initial device selection from URL
  const [initialDeviceSet, setInitialDeviceSet] = useState(false);
  const [toast, setToast] = useState<{
    message: string;
    type: ToastType;
    visible: boolean;
  }>({ message: '', type: 'info', visible: false });

  const showToast = (message: string, type: ToastType = 'info') => {
    setToast({ message, type, visible: true });
  };

  const [config, setConfig] = useState<ConfigSaveRequest | null>(null);
  const [showConfig, setShowConfig] = useState(false);
  const [showApiKey, setShowApiKey] = useState(false);
  const [tempConfig, setTempConfig] = useState({
    base_url: VISION_PRESETS[0].config.base_url as string,
    model_name: VISION_PRESETS[0].config.model_name as string,
    api_key: '',
    agent_type: 'glm',
    agent_config_params: {} as Record<string, unknown>,
    default_max_steps: 100,
    decision_base_url: '',
    decision_model_name: '',
    decision_api_key: '',
  });

  useEffect(() => {
    const loadConfiguration = async () => {
      try {
        const data = await getConfig();
        setConfig({
          base_url: data.base_url,
          model_name: data.model_name,
          api_key: data.api_key || undefined,
          agent_type: data.agent_type || 'glm',
          agent_config_params: data.agent_config_params || undefined,
          default_max_steps: data.default_max_steps || 100,
          decision_base_url: data.decision_base_url || undefined,
          decision_model_name: data.decision_model_name || undefined,
          decision_api_key: data.decision_api_key || undefined,
        });
        // 当后端返回空配置时，使用智谱预设作为默认值
        const useDefault = !data.base_url;
        setTempConfig({
          base_url: useDefault
            ? VISION_PRESETS[0].config.base_url
            : data.base_url,
          model_name: useDefault
            ? VISION_PRESETS[0].config.model_name
            : data.model_name,
          api_key: data.api_key || '',
          agent_type: data.agent_type || 'glm',
          agent_config_params: data.agent_config_params || {},
          default_max_steps: data.default_max_steps || 100,
          decision_base_url: data.decision_base_url || '',
          decision_model_name: data.decision_model_name || 'glm-4.7',
          decision_api_key: data.decision_api_key || '',
        });

        if (useDefault) {
          setShowConfig(true);
        }
      } catch (err) {
        console.error('Failed to load config:', err);
        setShowConfig(true);
      }
    };

    loadConfiguration();
  }, []);

  const loadDevices = useCallback(async () => {
    try {
      const response = await listDevices();

      // Filter out disconnected devices
      const connectedDevices = response.devices.filter(
        device => device.state !== 'disconnected'
      );

      const deviceMap = new Map<string, Device>();
      const serialMap = new Map<string, Device[]>();

      for (const device of connectedDevices) {
        if (device.serial) {
          const group = serialMap.get(device.serial) || [];
          group.push(device);
          serialMap.set(device.serial, group);
        } else {
          deviceMap.set(device.id, device);
        }
      }

      Array.from(serialMap.values()).forEach(devices => {
        const wifiDevice = devices.find(
          (d: Device) => d.connection_type === 'wifi'
        );
        const selectedDevice = wifiDevice || devices[0];
        deviceMap.set(selectedDevice.id, selectedDevice);
      });

      const filteredDevices = Array.from(deviceMap.values());
      setDevices(filteredDevices);

      // On initial load, try to select device from URL serial param
      if (filteredDevices.length > 0 && !initialDeviceSet) {
        const urlSerial = searchParams.serial;
        if (urlSerial) {
          const deviceFromUrl = filteredDevices.find(
            d => d.serial === urlSerial
          );
          if (deviceFromUrl) {
            setCurrentDeviceId(deviceFromUrl.id);
          } else {
            // URL serial not found, fallback to first device
            setCurrentDeviceId(filteredDevices[0].id);
          }
        } else if (!currentDeviceId) {
          setCurrentDeviceId(filteredDevices[0].id);
        }
        setInitialDeviceSet(true);
      }

      if (
        currentDeviceId &&
        !filteredDevices.find(d => d.id === currentDeviceId)
      ) {
        setCurrentDeviceId(filteredDevices[0]?.id || '');
      }
    } catch (error) {
      console.error('Failed to load devices:', error);
    }
  }, [currentDeviceId, initialDeviceSet, searchParams.serial]);

  useEffect(() => {
    // Initial load with a small delay to avoid synchronous setState
    const timeoutId = setTimeout(() => {
      loadDevices();
    }, 0);

    // Set up interval for periodic updates
    const intervalId = setInterval(loadDevices, 3000);

    return () => {
      clearTimeout(timeoutId);
      clearInterval(intervalId);
    };
  }, [loadDevices]);

  // Sync state changes to URL search params
  useEffect(() => {
    // Get current device's serial
    const currentDevice = devices.find(d => d.id === currentDeviceId);
    const currentSerial = currentDevice?.serial;

    // Only update URL after initial device selection is done
    if (!initialDeviceSet) return;

    // Check if URL needs updating
    const needsUpdate =
      currentSerial !== searchParams.serial || chatMode !== searchParams.mode;

    if (needsUpdate) {
      navigate({
        to: '/chat',
        search: {
          serial: currentSerial,
          mode: chatMode,
        },
        replace: true, // Don't create new history entry
      });
    }
  }, [
    currentDeviceId,
    chatMode,
    devices,
    initialDeviceSet,
    navigate,
    searchParams.serial,
    searchParams.mode,
  ]);

  const handleSaveConfig = async () => {
    if (!tempConfig.base_url) {
      showToast(t.chat.baseUrlRequired, 'error');
      return;
    }

    try {
      // 1. 保存配置
      await saveConfig({
        base_url: tempConfig.base_url,
        model_name: tempConfig.model_name || 'autoglm-phone-9b',
        api_key: tempConfig.api_key || undefined,
        agent_type: tempConfig.agent_type,
        agent_config_params:
          Object.keys(tempConfig.agent_config_params).length > 0
            ? tempConfig.agent_config_params
            : undefined,
        default_max_steps: tempConfig.default_max_steps,
        decision_base_url: tempConfig.decision_base_url || undefined,
        decision_model_name: tempConfig.decision_model_name || undefined,
        decision_api_key: tempConfig.decision_api_key || undefined,
      });

      setConfig({
        base_url: tempConfig.base_url,
        model_name: tempConfig.model_name,
        api_key: tempConfig.api_key || undefined,
        agent_type: tempConfig.agent_type,
        agent_config_params:
          Object.keys(tempConfig.agent_config_params).length > 0
            ? tempConfig.agent_config_params
            : undefined,
        default_max_steps: tempConfig.default_max_steps,
        decision_base_url: tempConfig.decision_base_url || undefined,
        decision_model_name: tempConfig.decision_model_name || undefined,
        decision_api_key: tempConfig.decision_api_key || undefined,
      });

      showToast(t.toasts.configSaved, 'success');

      // 2. 重新初始化所有 agent
      try {
        const reinitResult = await reinitAllAgents();

        if (reinitResult.total === 0) {
          // 没有需要更新的 agent - 静默处理
          console.log('No agents to reinitialize');
        } else if (reinitResult.success) {
          // 全部成功
          showToast(
            `Configuration applied to ${reinitResult.succeeded.length} device(s)`,
            'success'
          );
        } else {
          // 部分成功或全部失败
          const failedCount = Object.keys(reinitResult.failed).length;
          showToast(
            `Configuration partially applied: ${reinitResult.succeeded.length}/${reinitResult.total} succeeded, ${failedCount} failed`,
            'warning'
          );
        }
      } catch (reinitError) {
        // 重新初始化失败不影响配置保存
        console.error('Failed to reinitialize agents:', reinitError);
        showToast(
          'Configuration saved, but failed to update devices. Please reinitialize manually.',
          'warning'
        );
      }

      setShowConfig(false);
    } catch (err) {
      console.error('Failed to save config:', err);
      showToast(`Failed to save: ${getErrorMessage(err)}`, 'error');
    }
  };

  const handleConnectWifi = async (deviceId: string) => {
    try {
      const res = await connectWifi({ device_id: deviceId });
      if (res.success && res.device_id) {
        setCurrentDeviceId(res.device_id);
        showToast(t.toasts.wifiConnected, 'success');
      } else if (!res.success) {
        showToast(
          res.message || res.error || t.toasts.connectionFailed,
          'error'
        );
      }
    } catch (e) {
      showToast(t.toasts.wifiConnectionError, 'error');
      console.error('Connect WiFi error:', e);
    }
  };

  const handleDisconnectWifi = async (deviceId: string) => {
    try {
      const res = await disconnectWifi(deviceId);
      if (res.success) {
        showToast(t.toasts.wifiDisconnected, 'success');
      } else {
        showToast(
          res.message || res.error || t.toasts.disconnectFailed,
          'error'
        );
      }
    } catch (e) {
      showToast(t.toasts.wifiDisconnectError, 'error');
      console.error('Disconnect WiFi error:', e);
    }
  };

  return (
    <div className="h-full flex relative min-h-0">
      {toast.visible && (
        <Toast
          message={toast.message}
          type={toast.type}
          onClose={() => setToast(prev => ({ ...prev, visible: false }))}
        />
      )}

      {/* Config Dialog */}
      <Dialog open={showConfig} onOpenChange={setShowConfig}>
        <DialogContent className="sm:max-w-md h-[75vh] flex flex-col">
          <DialogHeader className="flex-shrink-0">
            <DialogTitle className="flex items-center gap-2">
              <Settings className="w-5 h-5 text-[#1d9bf0]" />
              {t.chat.configuration}
            </DialogTitle>
            <DialogDescription>{t.chat.configureApi}</DialogDescription>
          </DialogHeader>

          <Tabs defaultValue="vision" className="flex-1 flex flex-col min-h-0">
            <TabsList className="grid w-full grid-cols-2 flex-shrink-0">
              <TabsTrigger value="vision">
                <Eye className="w-4 h-4 mr-2" />
                {t.chat.visionModelTab}
              </TabsTrigger>
              <TabsTrigger value="decision">
                <Brain className="w-4 h-4 mr-2" />
                {t.chat.decisionModelTab}
              </TabsTrigger>
            </TabsList>

            {/* 视觉模型 Tab */}
            <TabsContent
              value="vision"
              className="space-y-4 mt-4 overflow-y-auto flex-1 min-h-0"
            >
              {/* 视觉模型预设配置 */}
              <div className="space-y-2">
                <Label className="text-sm font-medium">
                  {t.chat.selectPreset}
                </Label>
                <div className="grid grid-cols-1 gap-2">
                  {VISION_PRESETS.map(preset => (
                    <div key={preset.name} className="relative">
                      <button
                        type="button"
                        onClick={() =>
                          setTempConfig(prev => ({
                            ...prev,
                            base_url: preset.config.base_url,
                            model_name: preset.config.model_name,
                          }))
                        }
                        className={`w-full text-left p-3 rounded-lg border transition-all ${
                          tempConfig.base_url === preset.config.base_url &&
                          (preset.name !== 'custom' ||
                            (preset.name === 'custom' &&
                              tempConfig.base_url === ''))
                            ? 'border-[#1d9bf0] bg-[#1d9bf0]/5'
                            : 'border-slate-200 dark:border-slate-700 hover:border-[#1d9bf0]/50 hover:bg-slate-50 dark:hover:bg-slate-800/50'
                        }`}
                      >
                        <div className="flex items-center gap-2">
                          <Server
                            className={`w-4 h-4 ${
                              tempConfig.base_url === preset.config.base_url &&
                              (preset.name !== 'custom' ||
                                (preset.name === 'custom' &&
                                  tempConfig.base_url === ''))
                                ? 'text-[#1d9bf0]'
                                : 'text-slate-400 dark:text-slate-500'
                            }`}
                          />
                          <span className="font-medium text-sm text-slate-900 dark:text-slate-100">
                            {
                              t.presetConfigs[
                                preset.name as keyof typeof t.presetConfigs
                              ].name
                            }
                          </span>
                        </div>
                        <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 ml-6">
                          {
                            t.presetConfigs[
                              preset.name as keyof typeof t.presetConfigs
                            ].description
                          }
                        </p>
                      </button>
                      {'apiKeyUrl' in preset && (
                        <a
                          href={preset.apiKeyUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={e => e.stopPropagation()}
                          className="absolute top-3 right-3 p-1.5 rounded-md hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors group"
                          title={t.chat.getApiKey || '获取 API Key'}
                        >
                          <ExternalLink className="w-3.5 h-3.5 text-slate-400 group-hover:text-[#1d9bf0] transition-colors" />
                        </a>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="base_url">{t.chat.baseUrl} *</Label>
                <Input
                  id="base_url"
                  value={tempConfig.base_url}
                  onChange={e =>
                    setTempConfig({ ...tempConfig, base_url: e.target.value })
                  }
                  placeholder="http://localhost:8080/v1"
                />
                {!tempConfig.base_url && (
                  <p className="text-xs text-red-500 flex items-center gap-1">
                    <AlertCircle className="w-3 h-3" />
                    {t.chat.baseUrlRequired}
                  </p>
                )}
              </div>

              <div className="space-y-2">
                <Label htmlFor="api_key">{t.chat.apiKey}</Label>
                <div className="relative">
                  <Input
                    id="api_key"
                    type={showApiKey ? 'text' : 'password'}
                    value={tempConfig.api_key}
                    onChange={e =>
                      setTempConfig({
                        ...tempConfig,
                        api_key: e.target.value,
                      })
                    }
                    placeholder="Leave empty if not required"
                    className="pr-10"
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => setShowApiKey(!showApiKey)}
                    className="absolute right-0 top-0 h-full px-3 hover:bg-transparent"
                  >
                    {showApiKey ? (
                      <EyeOff className="w-4 h-4 text-slate-400" />
                    ) : (
                      <Eye className="w-4 h-4 text-slate-400" />
                    )}
                  </Button>
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="model_name">{t.chat.modelName}</Label>
                <Input
                  id="model_name"
                  value={tempConfig.model_name}
                  onChange={e =>
                    setTempConfig({
                      ...tempConfig,
                      model_name: e.target.value,
                    })
                  }
                  placeholder="autoglm-phone-9b"
                />
              </div>

              {/* Agent 类型选择 */}
              <div className="space-y-2">
                <Label className="text-sm font-medium">
                  {t.chat.agentType || 'Agent 类型'}
                </Label>
                <div className="grid grid-cols-2 gap-2">
                  {AGENT_PRESETS.map(preset => (
                    <button
                      key={preset.name}
                      type="button"
                      onClick={() =>
                        setTempConfig(prev => ({
                          ...prev,
                          agent_type: preset.name,
                          agent_config_params: preset.defaultConfig,
                        }))
                      }
                      className={`text-left p-3 rounded-lg border transition-all ${
                        tempConfig.agent_type === preset.name
                          ? 'border-[#1d9bf0] bg-[#1d9bf0]/5'
                          : 'border-slate-200 dark:border-slate-700 hover:border-[#1d9bf0]/50 hover:bg-slate-50 dark:hover:bg-slate-800/50'
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <preset.icon
                          className={`w-4 h-4 ${
                            tempConfig.agent_type === preset.name
                              ? 'text-[#1d9bf0]'
                              : 'text-slate-400 dark:text-slate-500'
                          }`}
                        />
                        <span
                          className={`font-medium text-sm ${
                            tempConfig.agent_type === preset.name
                              ? 'text-[#1d9bf0]'
                              : 'text-slate-900 dark:text-slate-100'
                          }`}
                        >
                          {preset.displayName}
                        </span>
                      </div>
                      <p
                        className={`text-xs mt-1 ml-6 ${
                          tempConfig.agent_type === preset.name
                            ? 'text-[#1d9bf0]/70'
                            : 'text-slate-500 dark:text-slate-400'
                        }`}
                      >
                        {preset.description}
                      </p>
                    </button>
                  ))}
                </div>
              </div>

              {/* MAI Agent 特定配置 */}
              {tempConfig.agent_type === 'mai' && (
                <div className="space-y-2">
                  <Label htmlFor="history_n">
                    {t.chat.history_n || '历史记录数量'}
                  </Label>
                  <Input
                    id="history_n"
                    type="number"
                    min={1}
                    max={10}
                    value={
                      (tempConfig.agent_config_params?.history_n as
                        | number
                        | undefined) || 3
                    }
                    onChange={e => {
                      const value = parseInt(e.target.value) || 3;
                      setTempConfig(prev => ({
                        ...prev,
                        agent_config_params: {
                          ...prev.agent_config_params,
                          history_n: value,
                        },
                      }));
                    }}
                    className="w-full"
                  />
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    {t.chat.history_n_hint || '包含的历史截图数量（1-10）'}
                  </p>
                </div>
              )}

              {/* 最大执行步数配置 */}
              <div className="space-y-2">
                <Label htmlFor="default_max_steps">
                  {t.chat.maxSteps || '最大执行步数'}
                </Label>
                <Input
                  id="default_max_steps"
                  type="number"
                  min={1}
                  max={1000}
                  value={tempConfig.default_max_steps}
                  onChange={e => {
                    const value = parseInt(e.target.value) || 100;
                    setTempConfig(prev => ({
                      ...prev,
                      default_max_steps: Math.min(1000, Math.max(1, value)),
                    }));
                  }}
                  className="w-full"
                />
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  {t.chat.maxStepsHint || '单次任务最大执行步数（1-1000）'}
                </p>
              </div>
            </TabsContent>

            {/* 决策模型 Tab */}
            <TabsContent
              value="decision"
              className="space-y-4 mt-4 overflow-y-auto flex-1 min-h-0"
            >
              {/* 提示信息 */}
              <div className="rounded-lg border border-indigo-200 bg-indigo-50 dark:border-indigo-900 dark:bg-indigo-950/30 p-3 text-sm text-indigo-900 dark:text-indigo-100">
                <div className="flex items-start gap-2">
                  <Info className="mt-0.5 h-4 w-4 flex-shrink-0" />
                  <div>{t.chat.decisionModelHint}</div>
                </div>
              </div>

              {/* 决策模型预设配置 */}
              <div className="space-y-2">
                <Label className="text-sm font-medium">
                  {t.chat.selectDecisionPreset}
                </Label>
                <div className="grid grid-cols-1 gap-2">
                  {DECISION_PRESETS.map(preset => (
                    <div key={preset.name} className="relative">
                      <button
                        type="button"
                        onClick={() =>
                          setTempConfig(prev => ({
                            ...prev,
                            decision_base_url: preset.config.decision_base_url,
                            decision_model_name:
                              preset.config.decision_model_name,
                          }))
                        }
                        className={`w-full text-left p-3 rounded-lg border transition-all ${
                          tempConfig.decision_base_url ===
                            preset.config.decision_base_url &&
                          (preset.name !== 'custom' ||
                            (preset.name === 'custom' &&
                              tempConfig.decision_base_url === ''))
                            ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-950/50'
                            : 'border-slate-200 dark:border-slate-700 hover:border-indigo-500/50 hover:bg-indigo-50 dark:hover:bg-indigo-950/30'
                        }`}
                      >
                        <div className="flex items-center gap-2">
                          <Server
                            className={`w-4 h-4 ${
                              tempConfig.decision_base_url ===
                                preset.config.decision_base_url &&
                              (preset.name !== 'custom' ||
                                (preset.name === 'custom' &&
                                  tempConfig.decision_base_url === ''))
                                ? 'text-indigo-600 dark:text-indigo-400'
                                : 'text-slate-400 dark:text-slate-500'
                            }`}
                          />
                          <span className="font-medium text-sm text-slate-900 dark:text-slate-100">
                            {
                              t.presetConfigs[
                                preset.name as keyof typeof t.presetConfigs
                              ].name
                            }
                          </span>
                        </div>
                        <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 ml-6">
                          {
                            t.presetConfigs[
                              preset.name as keyof typeof t.presetConfigs
                            ].description
                          }
                        </p>
                      </button>
                      {'apiKeyUrl' in preset && (
                        <a
                          href={preset.apiKeyUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={e => e.stopPropagation()}
                          className="absolute top-3 right-3 p-1.5 rounded-md hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors group"
                          title={t.chat.getApiKey || '获取 API Key'}
                        >
                          <ExternalLink className="w-3.5 h-3.5 text-slate-400 group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors" />
                        </a>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {/* Decision Base URL */}
              <div className="space-y-2">
                <Label htmlFor="decision_base_url">
                  {t.chat.decisionBaseUrl} *
                </Label>
                <Input
                  id="decision_base_url"
                  value={tempConfig.decision_base_url}
                  onChange={e =>
                    setTempConfig({
                      ...tempConfig,
                      decision_base_url: e.target.value,
                    })
                  }
                  placeholder="http://localhost:8080/v1"
                />
              </div>

              {/* Decision API Key */}
              <div className="space-y-2">
                <Label htmlFor="decision_api_key">
                  {t.chat.decisionApiKey}
                </Label>
                <div className="relative">
                  <Input
                    id="decision_api_key"
                    type={showApiKey ? 'text' : 'password'}
                    value={tempConfig.decision_api_key}
                    onChange={e =>
                      setTempConfig({
                        ...tempConfig,
                        decision_api_key: e.target.value,
                      })
                    }
                    placeholder="sk-..."
                    className="pr-10"
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => setShowApiKey(!showApiKey)}
                    className="absolute right-0 top-0 h-full px-3 hover:bg-transparent"
                  >
                    {showApiKey ? (
                      <EyeOff className="w-4 h-4 text-slate-400" />
                    ) : (
                      <Eye className="w-4 h-4 text-slate-400" />
                    )}
                  </Button>
                </div>
              </div>

              {/* Decision Model Name */}
              <div className="space-y-2">
                <Label htmlFor="decision_model_name">
                  {t.chat.decisionModelName} *
                </Label>
                <Input
                  id="decision_model_name"
                  value={tempConfig.decision_model_name}
                  onChange={e =>
                    setTempConfig({
                      ...tempConfig,
                      decision_model_name: e.target.value,
                    })
                  }
                  placeholder=""
                />
              </div>
            </TabsContent>
          </Tabs>

          <DialogFooter className="sm:justify-between gap-2 flex-shrink-0">
            <Button
              variant="outline"
              onClick={() => {
                setShowConfig(false);
                if (config) {
                  setTempConfig({
                    base_url: config.base_url,
                    model_name: config.model_name,
                    api_key: config.api_key || '',
                    agent_type: config.agent_type || 'glm',
                    agent_config_params: config.agent_config_params || {},
                    default_max_steps: config.default_max_steps || 100,
                    decision_base_url: config.decision_base_url || '',
                    decision_model_name:
                      config.decision_model_name || 'glm-4.7',
                    decision_api_key: config.decision_api_key || '',
                  });
                }
              }}
            >
              {t.chat.cancel}
            </Button>
            <Button onClick={handleSaveConfig} variant="twitter">
              <CheckCircle2 className="w-4 h-4 mr-2" />
              {t.chat.saveConfig}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Sidebar */}
      <DeviceSidebar
        devices={devices}
        currentDeviceId={currentDeviceId}
        onSelectDevice={setCurrentDeviceId}
        onOpenConfig={() => setShowConfig(true)}
        onConnectWifi={handleConnectWifi}
        onDisconnectWifi={handleDisconnectWifi}
      />

      {/* Main content */}
      <div className="flex-1 flex flex-col min-h-0 relative">
        {/* Mode Toggle - Floating Capsule */}
        <div className="absolute top-4 left-1/2 -translate-x-1/2 z-20">
          <div className="flex items-center gap-0.5 bg-white/95 dark:bg-slate-800/95 backdrop-blur-sm rounded-full p-1 shadow-lg border border-slate-200 dark:border-slate-700">
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  onClick={() => setChatMode('classic')}
                  className={`flex items-center gap-1.5 px-4 py-2 rounded-full text-sm font-medium transition-all ${
                    chatMode === 'classic'
                      ? 'bg-slate-900 dark:bg-white text-white dark:text-slate-900 shadow-sm'
                      : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700'
                  }`}
                >
                  <Sparkles className="w-4 h-4" />
                  {t.chatkit?.classicMode || '经典模式'}
                </button>
              </TooltipTrigger>
              <TooltipContent side="bottom" sideOffset={8} className="max-w-xs">
                <div className="space-y-1">
                  <p className="font-medium">
                    {t.chatkit?.classicMode || '经典模式'}
                  </p>
                  <p className="text-xs opacity-80">
                    {t.chatkit?.classicModeDesc || '视觉模型直接执行任务'}
                  </p>
                </div>
              </TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  onClick={() => {
                    setChatMode('chatkit');
                  }}
                  className={`flex items-center gap-1.5 px-4 py-2 rounded-full text-sm font-medium transition-all ${
                    chatMode === 'chatkit'
                      ? 'bg-indigo-600 text-white shadow-sm'
                      : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700'
                  }`}
                >
                  <Layers className="w-4 h-4" />
                  {t.chatkit?.layeredMode || '分层代理'}
                </button>
              </TooltipTrigger>
              <TooltipContent side="bottom" sideOffset={8} className="max-w-xs">
                <div className="space-y-1">
                  <p className="font-medium">
                    {t.chatkit?.layeredMode || '分层代理'}
                  </p>
                  <p className="text-xs opacity-80">
                    {t.chatkit?.layeredModeDesc ||
                      '规划层分解任务，执行层独立完成子任务'}
                  </p>
                </div>
              </TooltipContent>
            </Tooltip>
          </div>
        </div>

        {/* Content area */}
        <div className="flex-1 flex items-stretch justify-center min-h-0 px-4 py-4 pt-16">
          {devices.length === 0 ? (
            <div className="flex-1 flex items-center justify-center bg-slate-50 dark:bg-slate-950">
              <div className="text-center">
                <div className="flex h-20 w-20 items-center justify-center rounded-full bg-slate-100 dark:bg-slate-800 mx-auto mb-4">
                  <svg
                    className="w-10 h-10 text-slate-400"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={1.5}
                      d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z"
                    />
                  </svg>
                </div>
                <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100 mb-2">
                  {t.chat.welcomeTitle}
                </h3>
                <p className="text-slate-500 dark:text-slate-400">
                  {t.chat.connectDevice}
                </p>
              </div>
            </div>
          ) : (
            devices.map(device => (
              <div
                key={device.serial}
                className={`w-full max-w-7xl flex items-stretch justify-center min-h-0 ${
                  device.id === currentDeviceId ? '' : 'hidden'
                }`}
              >
                {chatMode === 'chatkit' ? (
                  <div className="w-full flex items-stretch justify-center">
                    <ChatKitPanel
                      deviceId={device.id}
                      deviceSerial={device.serial}
                      deviceName={device.model}
                      deviceConnectionType={device.connection_type}
                      isVisible={device.id === currentDeviceId}
                    />
                  </div>
                ) : (
                  <div className="w-full flex items-stretch justify-center">
                    <DevicePanel
                      deviceId={device.id}
                      deviceSerial={device.serial}
                      deviceName={device.model}
                      deviceConnectionType={device.connection_type}
                      isConfigured={!!config?.base_url}
                    />
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
