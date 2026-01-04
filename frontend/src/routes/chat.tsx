import { createFileRoute, useNavigate } from '@tanstack/react-router';
import * as React from 'react';
import { useState, useEffect, useCallback } from 'react';
import {
  connectWifi,
  disconnectWifi,
  listDevices,
  getConfig,
  saveConfig,
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

// 决策模型预设配置
const DECISION_PRESETS = [
  {
    name: 'bigmodel',
    config: {
      base_url: 'https://open.bigmodel.cn/api/paas/v4',
      model_name: 'glm-4.7',
    },
    apiKeyUrl: 'https://bigmodel.cn/usercenter/proj-mgmt/apikeys',
  },
  {
    name: 'modelscope',
    config: {
      base_url: 'https://api-inference.modelscope.cn/v1',
      model_name: 'ZhipuAI/GLM-4.7',
    },
    apiKeyUrl: 'https://www.modelscope.cn/my/myaccesstoken',
  },
  {
    name: 'custom',
    config: {
      base_url: '',
      model_name: '',
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

// Search params type for URL persistence
type ChatSearchParams = {
  serial?: string;
  mode?: 'classic' | 'dual' | 'chatkit';
};

export const Route = createFileRoute('/chat')({
  component: ChatComponent,
  validateSearch: (search: Record<string, unknown>): ChatSearchParams => {
    const mode = search.mode;
    return {
      serial: typeof search.serial === 'string' ? search.serial : undefined,
      mode:
        mode === 'classic' || mode === 'dual' || mode === 'chatkit'
          ? mode
          : undefined,
    };
  },
});

function ChatComponent() {
  const t = useTranslation();
  const searchParams = Route.useSearch();
  const navigate = useNavigate();
  const [devices, setDevices] = useState<Device[]>([]);
  const [currentDeviceId, setCurrentDeviceId] = useState<string>('');
  const [configTab, setConfigTab] = useState<'vision' | 'decision'>('vision');
  const [deviceThinkingModes, setDeviceThinkingModes] = useState<
    Record<string, 'fast' | 'deep' | 'turbo'>
  >({});
  // Chat mode: 'classic' for DevicePanel (single model), 'dual' for DevicePanel (dual model), 'chatkit' for ChatKitPanel (layered agent)
  // Initialize from URL search params if available
  const [chatMode, setChatMode] = useState<'classic' | 'dual' | 'chatkit'>(
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
  const [showDecisionApiKey, setShowDecisionApiKey] = useState(false);
  const [tempConfig, setTempConfig] = useState({
    base_url: VISION_PRESETS[0].config.base_url as string,
    model_name: VISION_PRESETS[0].config.model_name as string,
    api_key: '',
    dual_model_enabled: false,
    decision_base_url: DECISION_PRESETS[0].config.base_url as string,
    decision_model_name: DECISION_PRESETS[0].config.model_name as string,
    decision_api_key: '',
    agent_type: 'glm',
    agent_config_params: {} as Record<string, unknown>,
    default_max_steps: 100,
  });

  useEffect(() => {
    const loadConfiguration = async () => {
      try {
        const data = await getConfig();
        setConfig({
          base_url: data.base_url,
          model_name: data.model_name,
          api_key: data.api_key || undefined,
          dual_model_enabled: data.dual_model_enabled || false,
          decision_base_url: data.decision_base_url || undefined,
          decision_model_name: data.decision_model_name || undefined,
          decision_api_key: data.decision_api_key || undefined,
          agent_type: data.agent_type || 'glm',
          agent_config_params: data.agent_config_params || undefined,
          default_max_steps: data.default_max_steps || 100,
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
          dual_model_enabled: data.dual_model_enabled || false,
          decision_base_url:
            data.decision_base_url || DECISION_PRESETS[0].config.base_url,
          decision_model_name:
            data.decision_model_name || DECISION_PRESETS[0].config.model_name,
          decision_api_key: data.decision_api_key || '',
          agent_type: data.agent_type || 'glm',
          agent_config_params: data.agent_config_params || {},
          default_max_steps: data.default_max_steps || 100,
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
        const remoteDevice = devices.find(
          (d: Device) => d.connection_type === 'remote'
        );
        const selectedDevice = remoteDevice || devices[0];
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
      await saveConfig({
        base_url: tempConfig.base_url,
        model_name: tempConfig.model_name || 'autoglm-phone-9b',
        api_key: tempConfig.api_key || undefined,
        dual_model_enabled: tempConfig.dual_model_enabled,
        decision_base_url: tempConfig.decision_base_url || undefined,
        decision_model_name: tempConfig.decision_model_name || undefined,
        decision_api_key: tempConfig.decision_api_key || undefined,
        agent_type: tempConfig.agent_type,
        agent_config_params:
          Object.keys(tempConfig.agent_config_params).length > 0
            ? tempConfig.agent_config_params
            : undefined,
        default_max_steps: tempConfig.default_max_steps,
      });

      setConfig({
        base_url: tempConfig.base_url,
        model_name: tempConfig.model_name,
        api_key: tempConfig.api_key || undefined,
        dual_model_enabled: tempConfig.dual_model_enabled,
        decision_base_url: tempConfig.decision_base_url || undefined,
        decision_model_name: tempConfig.decision_model_name || undefined,
        decision_api_key: tempConfig.decision_api_key || undefined,
        agent_type: tempConfig.agent_type,
        agent_config_params:
          Object.keys(tempConfig.agent_config_params).length > 0
            ? tempConfig.agent_config_params
            : undefined,
        default_max_steps: tempConfig.default_max_steps,
      });
      setShowConfig(false);
      showToast(t.toasts.configSaved, 'success');
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

          {/* Tab 切换 */}
          <div className="flex gap-1 p-1 bg-slate-100 dark:bg-slate-800 rounded-lg">
            <button
              type="button"
              onClick={() => setConfigTab('vision')}
              className={`flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all ${
                configTab === 'vision'
                  ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 shadow-sm'
                  : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300'
              }`}
            >
              <Eye className="w-4 h-4" />
              {t.chat.visionModel || '视觉模型'}
            </button>
            <button
              type="button"
              onClick={() => setConfigTab('decision')}
              className={`flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all ${
                configTab === 'decision'
                  ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 shadow-sm'
                  : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300'
              }`}
            >
              <Brain className="w-4 h-4" />
              {t.chat.decisionModel || '决策模型'}
            </button>
          </div>

          <div className="space-y-4 pt-3 overflow-y-auto flex-1 min-h-0">
            {configTab === 'vision' ? (
              <>
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
                                tempConfig.base_url ===
                                  preset.config.base_url &&
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
              </>
            ) : (
              <>
                {/* 决策模型预设配置 */}
                <div className="space-y-2">
                  <Label className="text-sm font-medium">
                    {t.chat.selectPreset}
                  </Label>
                  <div className="grid grid-cols-1 gap-2">
                    {DECISION_PRESETS.map(preset => (
                      <div key={preset.name} className="relative">
                        <button
                          type="button"
                          onClick={() =>
                            setTempConfig(prev => ({
                              ...prev,
                              decision_base_url: preset.config.base_url,
                              decision_model_name: preset.config.model_name,
                            }))
                          }
                          className={`w-full text-left p-3 rounded-lg border transition-all ${
                            tempConfig.decision_base_url ===
                              preset.config.base_url &&
                            (preset.name !== 'custom' ||
                              (preset.name === 'custom' &&
                                tempConfig.decision_base_url === ''))
                              ? 'border-[#1d9bf0] bg-[#1d9bf0]/5'
                              : 'border-slate-200 dark:border-slate-700 hover:border-[#1d9bf0]/50 hover:bg-slate-50 dark:hover:bg-slate-800/50'
                          }`}
                        >
                          <div className="flex items-center gap-2">
                            <Server
                              className={`w-4 h-4 ${
                                tempConfig.decision_base_url ===
                                  preset.config.base_url &&
                                (preset.name !== 'custom' ||
                                  (preset.name === 'custom' &&
                                    tempConfig.decision_base_url === ''))
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
                  <Label htmlFor="decision_base_url">{t.chat.baseUrl} *</Label>
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

                <div className="space-y-2">
                  <Label htmlFor="decision_api_key">{t.chat.apiKey}</Label>
                  <div className="relative">
                    <Input
                      id="decision_api_key"
                      type={showDecisionApiKey ? 'text' : 'password'}
                      value={tempConfig.decision_api_key}
                      onChange={e =>
                        setTempConfig({
                          ...tempConfig,
                          decision_api_key: e.target.value,
                        })
                      }
                      placeholder="Leave empty if not required"
                      className="pr-10"
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      onClick={() => setShowDecisionApiKey(!showDecisionApiKey)}
                      className="absolute right-0 top-0 h-full px-3 hover:bg-transparent"
                    >
                      {showDecisionApiKey ? (
                        <EyeOff className="w-4 h-4 text-slate-400" />
                      ) : (
                        <Eye className="w-4 h-4 text-slate-400" />
                      )}
                    </Button>
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="decision_model_name">
                    {t.chat.modelName}
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
                    placeholder="glm-4.7"
                  />
                </div>
              </>
            )}
          </div>

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
                    dual_model_enabled: config.dual_model_enabled || false,
                    decision_base_url: config.decision_base_url || '',
                    decision_model_name: config.decision_model_name || '',
                    decision_api_key: config.decision_api_key || '',
                    agent_type: config.agent_type || 'glm',
                    agent_config_params: config.agent_config_params || {},
                    default_max_steps: config.default_max_steps || 100,
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
                    setChatMode('dual');
                    if (!config?.decision_api_key) {
                      showToast(t.toasts.decisionModelNotConfigured, 'warning');
                    }
                  }}
                  className={`flex items-center gap-1.5 px-4 py-2 rounded-full text-sm font-medium transition-all ${
                    chatMode === 'dual'
                      ? 'bg-purple-600 text-white shadow-sm'
                      : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700'
                  }`}
                >
                  <Brain className="w-4 h-4" />
                  {t.chatkit?.dualMode || '双模型协作'}
                </button>
              </TooltipTrigger>
              <TooltipContent side="bottom" sideOffset={8} className="max-w-xs">
                <div className="space-y-1">
                  <p className="font-medium">
                    {t.chatkit?.dualMode || '双模型协作'}
                  </p>
                  <p className="text-xs opacity-80">
                    {t.chatkit?.dualModeDesc ||
                      '决策模型逐步指导，视觉模型执行，精细控制'}
                  </p>
                </div>
              </TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  onClick={() => {
                    setChatMode('chatkit');
                    if (!config?.decision_api_key) {
                      showToast(t.toasts.decisionModelNotConfigured, 'warning');
                    }
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
                <div
                  className={`w-full flex items-stretch justify-center ${
                    chatMode === 'chatkit' ? '' : 'hidden'
                  }`}
                >
                  <ChatKitPanel
                    deviceId={device.id}
                    deviceSerial={device.serial}
                    deviceName={device.model}
                    isVisible={
                      device.id === currentDeviceId && chatMode === 'chatkit'
                    }
                  />
                </div>
                <div
                  className={`w-full flex items-stretch justify-center ${
                    chatMode === 'chatkit' ? 'hidden' : ''
                  }`}
                >
                  <DevicePanel
                    deviceId={device.id}
                    deviceSerial={device.serial}
                    deviceName={device.model}
                    config={config}
                    isVisible={
                      device.id === currentDeviceId && chatMode !== 'chatkit'
                    }
                    isConfigured={!!config?.base_url}
                    thinkingMode={deviceThinkingModes[device.serial] || 'deep'}
                    onThinkingModeChange={mode => {
                      setDeviceThinkingModes(prev => ({
                        ...prev,
                        [device.serial]: mode,
                      }));
                    }}
                    dualModelEnabled={chatMode === 'dual'}
                  />
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
