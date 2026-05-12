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
import { GroupManageDialog } from '../components/GroupManageDialog';
import { ConfigDialog } from '../components/ConfigDialog';
import { ChatModeToggle } from '../components/ChatModeToggle';
import { DeviceEmptyState } from '../components/DeviceEmptyState';
import { Toast, type ToastType } from '../components/Toast';
import { useTranslation } from '../lib/i18n-context';
import { usePageVisibility } from '../hooks/usePageVisibility';
import {
  VISION_PRESETS,
  getSelectedVisionPreset,
  getSelectedDecisionPreset,
} from '../lib/chat-constants';

// Search params type for URL persistence
type ChatSearchParams = {
  serial?: string;
  mode?: 'classic' | 'chatkit';
};

type ElectronRelaunchAPI = {
  app?: {
    relaunch: () => Promise<{ success: boolean }>;
  };
};

function areAgentStatesEqual(left: Device['agent'] | null, right: Device['agent'] | null): boolean {
  if (left === right) {
    return true;
  }

  if (!left || !right) {
    return false;
  }

  return (
    left.state === right.state &&
    left.created_at === right.created_at &&
    left.last_used === right.last_used &&
    left.error_message === right.error_message &&
    left.model_name === right.model_name
  );
}

function areDevicesEqual(previous: Device[], next: Device[]): boolean {
  if (previous.length !== next.length) {
    return false;
  }

  return previous.every((device, index) => {
    const nextDevice = next[index];

    return (
      device.id === nextDevice.id &&
      device.serial === nextDevice.serial &&
      device.model === nextDevice.model &&
      device.status === nextDevice.status &&
      device.connection_type === nextDevice.connection_type &&
      device.state === nextDevice.state &&
      device.is_available_only === nextDevice.is_available_only &&
      device.display_name === nextDevice.display_name &&
      device.group_id === nextDevice.group_id &&
      areAgentStatesEqual(device.agent, nextDevice.agent)
    );
  });
}

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
  const isPageVisible = usePageVisibility();
  const [devices, setDevices] = useState<Device[]>([]);
  const [currentDeviceId, setCurrentDeviceId] = useState<string>('');
  // Chat mode: 'classic' for DevicePanel (single model), 'chatkit' for ChatKitPanel (layered agent)
  // Initialize from URL search params if available
  const [chatMode, setChatMode] = useState<'classic' | 'chatkit'>(searchParams.mode || 'classic');

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
  const [showGroupManager, setShowGroupManager] = useState(false);
  const [showApiKey, setShowApiKey] = useState(false);
  const isLoadingDevicesRef = React.useRef(false);
  const [tempConfig, setTempConfig] = useState({
    base_url: VISION_PRESETS[0].config.base_url as string,
    model_name: VISION_PRESETS[0].config.model_name as string,
    api_key: '',
    agent_type: 'glm-async',
    agent_config_params: {} as Record<string, unknown>,
    default_max_steps: 100 as number | '',
    layered_max_turns: 50,
    decision_base_url: '',
    decision_model_name: '',
    decision_api_key: '',
  });
  const selectedVisionPreset = getSelectedVisionPreset(tempConfig.base_url);
  const selectedDecisionPreset = getSelectedDecisionPreset(tempConfig.decision_base_url);

  useEffect(() => {
    const loadConfiguration = async () => {
      try {
        const data = await getConfig();
        setConfig({
          base_url: data.base_url,
          model_name: data.model_name,
          api_key: data.api_key || undefined,
          agent_type: data.agent_type || 'glm-async',
          agent_config_params: data.agent_config_params || undefined,
          default_max_steps: data.default_max_steps ?? null,
          layered_max_turns: data.layered_max_turns || 50,
          decision_base_url: data.decision_base_url || undefined,
          decision_model_name: data.decision_model_name || undefined,
          decision_api_key: data.decision_api_key || undefined,
        });
        // 当后端返回空配置时，使用智谱预设作为默认值
        const useDefault = !data.base_url;
        setTempConfig({
          base_url: useDefault ? VISION_PRESETS[0].config.base_url : data.base_url,
          model_name: useDefault ? VISION_PRESETS[0].config.model_name : data.model_name,
          api_key: data.api_key || '',
          agent_type: data.agent_type || 'glm-async',
          agent_config_params: data.agent_config_params || {},
          default_max_steps: data.default_max_steps ?? '',
          layered_max_turns: data.layered_max_turns || 50,
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
    if (isLoadingDevicesRef.current) {
      return;
    }

    isLoadingDevicesRef.current = true;
    try {
      const response = await listDevices();

      // Filter out disconnected devices
      const connectedDevices = response.devices.filter((device) => device.state !== 'disconnected');

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

      Array.from(serialMap.values()).forEach((devices) => {
        const wifiDevice = devices.find((d: Device) => d.connection_type === 'wifi');
        const selectedDevice = wifiDevice || devices[0];
        deviceMap.set(selectedDevice.id, selectedDevice);
      });

      const filteredDevices = Array.from(deviceMap.values());
      setDevices((previousDevices) =>
        areDevicesEqual(previousDevices, filteredDevices) ? previousDevices : filteredDevices
      );

      // On initial load, try to select device from URL serial param
      if (filteredDevices.length > 0 && !initialDeviceSet) {
        const urlSerial = searchParams.serial;
        if (urlSerial) {
          const deviceFromUrl = filteredDevices.find((d) => d.serial === urlSerial);
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

      if (currentDeviceId && !filteredDevices.find((d) => d.id === currentDeviceId)) {
        setCurrentDeviceId(filteredDevices[0]?.id || '');
      }
    } catch (error) {
      console.error('Failed to load devices:', error);
    } finally {
      isLoadingDevicesRef.current = false;
    }
  }, [currentDeviceId, initialDeviceSet, searchParams.serial]);

  useEffect(() => {
    if (!isPageVisible) {
      return;
    }

    let isCancelled = false;
    let timeoutId: number | null = null;

    const pollDevices = async () => {
      await loadDevices();

      if (isCancelled) {
        return;
      }

      timeoutId = window.setTimeout(() => {
        void pollDevices();
      }, 3000);
    };

    void pollDevices();

    return () => {
      isCancelled = true;
      if (timeoutId !== null) {
        window.clearTimeout(timeoutId);
      }
    };
  }, [isPageVisible, loadDevices]);

  // Sync state changes to URL search params
  useEffect(() => {
    // Get current device's serial
    const currentDevice = devices.find((d) => d.id === currentDeviceId);
    const currentSerial = currentDevice?.serial;

    // Only update URL after initial device selection is done
    if (!initialDeviceSet) return;

    // Check if URL needs updating
    const needsUpdate = currentSerial !== searchParams.serial || chatMode !== searchParams.mode;

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
      const saveResult = await saveConfig({
        base_url: tempConfig.base_url,
        model_name: tempConfig.model_name || 'autoglm-phone-9b',
        api_key: tempConfig.api_key || undefined,
        agent_type: tempConfig.agent_type,
        agent_config_params:
          Object.keys(tempConfig.agent_config_params).length > 0
            ? tempConfig.agent_config_params
            : undefined,
        default_max_steps:
          tempConfig.default_max_steps === '' ? null : tempConfig.default_max_steps,
        layered_max_turns: tempConfig.layered_max_turns,
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
        default_max_steps:
          tempConfig.default_max_steps === '' ? null : tempConfig.default_max_steps,
        layered_max_turns: tempConfig.layered_max_turns,
        decision_base_url: tempConfig.decision_base_url || undefined,
        decision_model_name: tempConfig.decision_model_name || undefined,
        decision_api_key: tempConfig.decision_api_key || undefined,
      });

      showToast(t.toasts.configSaved, 'success');

      const electronApp = (window as Window & { electronAPI?: ElectronRelaunchAPI }).electronAPI
        ?.app;

      if (saveResult.restart_required && electronApp?.relaunch) {
        showToast('配置已保存，应用将立即重启以应用新配置', 'warning');
        await new Promise((resolve) => setTimeout(resolve, 600));
        await electronApp.relaunch();
        return;
      }

      if (saveResult.restart_required) {
        showToast('配置已保存，请手动重启应用以立即生效', 'warning');
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
        showToast(res.message || res.error || t.toasts.connectionFailed, 'error');
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
        showToast(res.message || res.error || t.toasts.disconnectFailed, 'error');
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
          onClose={() => setToast((prev) => ({ ...prev, visible: false }))}
        />
      )}

      {/* Config Dialog */}
      <ConfigDialog
        open={showConfig}
        onOpenChange={setShowConfig}
        config={config}
        tempConfig={tempConfig}
        setTempConfig={setTempConfig}
        onSave={handleSaveConfig}
        showApiKey={showApiKey}
        setShowApiKey={setShowApiKey}
        selectedVisionPreset={selectedVisionPreset}
        selectedDecisionPreset={selectedDecisionPreset}
        t={t}
      />

      {/* Sidebar */}
      <DeviceSidebar
        devices={devices}
        currentDeviceId={currentDeviceId}
        onSelectDevice={setCurrentDeviceId}
        onOpenConfig={() => setShowConfig(true)}
        onOpenGroupManager={() => setShowGroupManager(true)}
        onConnectWifi={handleConnectWifi}
        onDisconnectWifi={handleDisconnectWifi}
        onRefreshDevices={loadDevices}
        showToast={showToast}
      />

      {/* Main content */}
      <div className="flex-1 flex flex-col min-h-0 relative">
        {/* Mode Toggle - Floating Capsule */}
        <div className="absolute top-4 left-1/2 -translate-x-1/2 z-20">
          <ChatModeToggle
            chatMode={chatMode}
            onModeChange={setChatMode}
            t={t}
          />
        </div>

        {/* Content area */}
        <div className="flex-1 flex items-stretch justify-center min-h-0 px-4 py-4 pt-16">
          {devices.length === 0 ? (
            <DeviceEmptyState t={t} />
          ) : (
            devices
              .filter((device) => device.id === currentDeviceId)
              .map((device) => (
                <div
                  key={device.serial}
                  className="w-full max-w-7xl flex items-stretch justify-center min-h-0"
                >
                  {chatMode === 'chatkit' ? (
                    <div className="w-full flex items-stretch justify-center">
                      <ChatKitPanel
                        deviceId={device.id}
                        deviceSerial={device.serial}
                        deviceName={device.model}
                        deviceConnectionType={device.connection_type}
                        isVisible={device.id === currentDeviceId}
                        unlimitedStepsEnabled={config?.default_max_steps === null}
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
                        isVisible={device.id === currentDeviceId} // ✅ 新增：传递可见性状态
                        unlimitedStepsEnabled={config?.default_max_steps === null}
                      />
                    </div>
                  )}
                </div>
              ))
          )}
        </div>
      </div>

      {/* Group Manager Dialog */}
      <GroupManageDialog
        isOpen={showGroupManager}
        onClose={() => setShowGroupManager(false)}
        onGroupsChanged={loadDevices}
        showToast={showToast}
      />
    </div>
  );
}
