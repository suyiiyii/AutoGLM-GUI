import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { listDevices, type AgentStatus, type Device } from '../api';
import { usePageVisibility } from '../hooks/usePageVisibility';

interface DeviceContextValue {
  devices: Device[];
  currentDevice: Device | null;
  currentDeviceId: string;
  selectedSerial: string;
  isLoadingDevices: boolean;
  refreshDevices: () => Promise<void>;
  selectDeviceById: (deviceId: string) => void;
  selectDeviceBySerial: (serial: string | undefined) => void;
}

const DeviceContext = createContext<DeviceContextValue | undefined>(undefined);

function areAgentStatesEqual(
  left: AgentStatus | null,
  right: AgentStatus | null
): boolean {
  if (left === right) return true;
  if (!left || !right) return false;

  return (
    left.state === right.state &&
    left.created_at === right.created_at &&
    left.last_used === right.last_used &&
    left.error_message === right.error_message &&
    left.model_name === right.model_name
  );
}

function areDevicesEqual(previous: Device[], next: Device[]): boolean {
  if (previous === next) return true;
  if (previous.length !== next.length) return false;

  return previous.every((device, index) => {
    const nextDevice = next[index];
    if (!nextDevice) return false;

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

function normalizeDevices(devices: Device[]): Device[] {
  const connectedDevices = devices.filter(
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

  Array.from(serialMap.values()).forEach(devicesForSerial => {
    const wifiDevice = devicesForSerial.find(
      device => device.connection_type === 'wifi'
    );
    const selectedDevice = wifiDevice || devicesForSerial[0];
    deviceMap.set(selectedDevice.id, selectedDevice);
  });

  return Array.from(deviceMap.values());
}

export function DeviceProvider({ children }: { children: ReactNode }) {
  const isPageVisible = usePageVisibility();
  const [devices, setDevices] = useState<Device[]>([]);
  const [selectedSerial, setSelectedSerial] = useState<string>('');
  const [isLoadingDevices, setIsLoadingDevices] = useState(false);
  const isLoadingDevicesRef = useRef(false);
  const selectedSerialRef = useRef('');

  useEffect(() => {
    selectedSerialRef.current = selectedSerial;
  }, [selectedSerial]);

  const refreshDevices = useCallback(async () => {
    if (isLoadingDevicesRef.current) {
      return;
    }

    isLoadingDevicesRef.current = true;
    setIsLoadingDevices(true);

    try {
      const response = await listDevices();
      const filteredDevices = normalizeDevices(response.devices);

      setDevices(previousDevices =>
        areDevicesEqual(previousDevices, filteredDevices)
          ? previousDevices
          : filteredDevices
      );

      const currentSerial = selectedSerialRef.current;
      if (filteredDevices.length === 0) {
        if (currentSerial) {
          setSelectedSerial('');
        }
        return;
      }

      if (
        !currentSerial ||
        !filteredDevices.some(device => device.serial === currentSerial)
      ) {
        setSelectedSerial(filteredDevices[0].serial);
      }
    } catch (error) {
      console.error('Failed to load devices:', error);
    } finally {
      isLoadingDevicesRef.current = false;
      setIsLoadingDevices(false);
    }
  }, []);

  useEffect(() => {
    if (!isPageVisible) {
      return;
    }

    let isCancelled = false;
    let timeoutId: number | null = null;

    const pollDevices = async () => {
      await refreshDevices();

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
  }, [isPageVisible, refreshDevices]);

  const selectDeviceById = useCallback(
    (deviceId: string) => {
      const device = devices.find(device => device.id === deviceId);
      setSelectedSerial(device?.serial || '');
    },
    [devices]
  );

  const selectDeviceBySerial = useCallback((serial: string | undefined) => {
    setSelectedSerial(serial || '');
  }, []);

  const currentDevice = useMemo(() => {
    if (!selectedSerial) {
      return null;
    }
    return devices.find(device => device.serial === selectedSerial) || null;
  }, [devices, selectedSerial]);

  const value = useMemo<DeviceContextValue>(
    () => ({
      devices,
      currentDevice,
      currentDeviceId: currentDevice?.id || '',
      selectedSerial,
      isLoadingDevices,
      refreshDevices,
      selectDeviceById,
      selectDeviceBySerial,
    }),
    [
      currentDevice,
      devices,
      isLoadingDevices,
      refreshDevices,
      selectDeviceById,
      selectDeviceBySerial,
      selectedSerial,
    ]
  );

  return (
    <DeviceContext.Provider value={value}>{children}</DeviceContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useDevices(): DeviceContextValue {
  const context = useContext(DeviceContext);
  if (!context) {
    throw new Error('useDevices must be used within a DeviceProvider');
  }
  return context;
}
