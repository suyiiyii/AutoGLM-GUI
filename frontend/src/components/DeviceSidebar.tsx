import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Smartphone,
  Settings,
  ChevronLeft,
  ChevronRight,
  Plug,
  Plus,
  Wifi,
  AlertCircle,
  Loader2,
  CheckCircle,
  XCircle,
} from 'lucide-react';
import { DeviceCard } from './DeviceCard';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { QRCodeSVG } from 'qrcode.react';
import type { Device, MdnsDevice, RemoteDeviceInfo } from '../api';
import {
  addRemoteDevice,
  cancelQRPairing,
  connectWifiManual,
  discoverMdnsDevices,
  discoverRemoteDevices,
  generateQRPairing,
  getQRPairingStatus,
  pairWifi,
} from '../api';
import { useTranslation } from '../lib/i18n-context';
import { useDebouncedState } from '@/hooks/useDebouncedState';

const getInitialCollapsedState = (): boolean => {
  try {
    const saved = localStorage.getItem('sidebar-collapsed');
    return saved !== null ? JSON.parse(saved) : false;
  } catch (error) {
    console.warn('Failed to load sidebar collapsed state:', error);
    return false;
  }
};

interface DeviceSidebarProps {
  devices: Device[];
  currentDeviceId: string;
  onSelectDevice: (deviceId: string) => void;
  onOpenConfig: () => void;
  onConnectWifi: (deviceId: string) => void;
  onDisconnectWifi: (deviceId: string) => void;
}

export function DeviceSidebar({
  devices,
  currentDeviceId,
  onSelectDevice,
  onOpenConfig,
  onConnectWifi,
  onDisconnectWifi,
}: DeviceSidebarProps) {
  const t = useTranslation();
  const [isCollapsed, setIsCollapsed] = useState(getInitialCollapsedState);

  // Manual WiFi connection
  const [showManualConnect, setShowManualConnect] = useState(false);
  const [manualConnectIp, setManualConnectIp] = useState('');
  const [manualConnectPort, setManualConnectPort] = useState('5555');
  const [ipError, setIpError] = useState('');
  const [portError, setPortError] = useState('');

  // WiFi pairing (Android 11+)
  const [activeTab, setActiveTab] = useState('direct');
  const [pairingCode, setPairingCode] = useState('');
  const [pairingPort, setPairingPort] = useState('');
  const [connectionPort, setConnectionPort] = useState('5555');
  const [pairingCodeError, setPairingCodeError] = useState('');
  const [isConnecting, setIsConnecting] = useState(false);

  // mDNS device discovery
  const [discoveredDevices, setDiscoveredDevices] = useState<MdnsDevice[]>([]);
  const [isScanning, setIsScanning] = useDebouncedState(false, 300);
  const [scanError, setScanError] = useState('');

  // QR pairing state
  interface QRPairingSession {
    sessionId: string;
    payload: string;
    status:
      | 'listening'
      | 'pairing'
      | 'paired'
      | 'connecting'
      | 'connected'
      | 'timeout'
      | 'error';
    expiresAt: number;
  }
  const [qrSession, setQrSession] = useState<QRPairingSession | null>(null);
  const [isGeneratingQR, setIsGeneratingQR] = useState(false);
  const qrPollIntervalRef = useRef<number | null>(null);

  const [remoteBaseUrl, setRemoteBaseUrl] = useState('');
  const [remoteUrlError, setRemoteUrlError] = useState('');
  const [isDiscoveringRemote, setIsDiscoveringRemote] = useState(false);
  const [discoveredRemoteDevices, setDiscoveredRemoteDevices] = useState<
    RemoteDeviceInfo[]
  >([]);
  const [selectedRemoteDevice, setSelectedRemoteDevice] = useState<
    string | null
  >(null);
  const [isConnectingRemote, setIsConnectingRemote] = useState(false);

  useEffect(() => {
    localStorage.setItem('sidebar-collapsed', JSON.stringify(isCollapsed));
  }, [isCollapsed]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key === 'b') {
        event.preventDefault();
        setIsCollapsed(!isCollapsed);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isCollapsed]);

  const toggleCollapse = () => {
    setIsCollapsed(!isCollapsed);
  };

  // Validation helpers
  const validateIp = (ip: string): boolean => {
    const ipPattern = /^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$/;
    if (!ipPattern.test(ip)) return false;
    const parts = ip.split('.');
    return parts.every(part => {
      const num = parseInt(part, 10);
      return num >= 0 && num <= 255;
    });
  };

  const validatePort = (port: string): boolean => {
    const num = parseInt(port, 10);
    return !isNaN(num) && num >= 1 && num <= 65535;
  };

  const validatePairingCode = (code: string): boolean => {
    return /^\d{6}$/.test(code);
  };

  const handleManualConnect = async () => {
    setIpError('');
    setPortError('');

    let hasError = false;

    if (!validateIp(manualConnectIp)) {
      setIpError(t.deviceSidebar.invalidIpError);
      hasError = true;
    }

    if (!validatePort(manualConnectPort)) {
      setPortError(t.deviceSidebar.invalidPortError);
      hasError = true;
    }

    if (hasError) return;

    setIsConnecting(true);
    try {
      const result = await connectWifiManual({
        ip: manualConnectIp,
        port: parseInt(manualConnectPort, 10),
      });

      if (result.success) {
        setShowManualConnect(false);
        setManualConnectIp('');
        setManualConnectPort('5555');
        // Device list will auto-refresh via polling
      } else {
        setIpError(result.message || t.toasts.wifiManualConnectError);
      }
    } catch {
      setIpError(t.toasts.wifiManualConnectError);
    } finally {
      setIsConnecting(false);
    }
  };

  const handlePair = async () => {
    setPairingCodeError('');
    setIpError('');
    setPortError('');

    let hasError = false;

    if (!validateIp(manualConnectIp)) {
      setIpError(t.deviceSidebar.invalidIpError);
      hasError = true;
    }

    if (!validatePort(pairingPort)) {
      setPortError(t.deviceSidebar.invalidPortError);
      hasError = true;
    }

    if (!validatePort(connectionPort)) {
      setPortError(t.deviceSidebar.invalidPortError);
      hasError = true;
    }

    if (!validatePairingCode(pairingCode)) {
      setPairingCodeError(t.deviceSidebar.invalidPairingCodeError);
      hasError = true;
    }

    if (hasError) return;

    setIsConnecting(true);
    try {
      const result = await pairWifi({
        ip: manualConnectIp,
        pairing_port: parseInt(pairingPort, 10),
        pairing_code: pairingCode,
        connection_port: parseInt(connectionPort, 10),
      });

      if (result.success) {
        setShowManualConnect(false);
        // Reset form
        setManualConnectIp('');
        setManualConnectPort('5555');
        setPairingCode('');
        setPairingPort('');
        setConnectionPort('5555');
        setActiveTab('direct');
        // Device list will auto-refresh via polling
      } else {
        // Show error based on error code
        if (result.error === 'invalid_pairing_code') {
          setPairingCodeError(result.message);
        } else if (result.error === 'invalid_ip') {
          setIpError(result.message);
        } else {
          setIpError(result.message || t.toasts.wifiPairError);
        }
      }
    } catch {
      setIpError(t.toasts.wifiPairError);
    } finally {
      setIsConnecting(false);
    }
  };

  // QR pairing handlers
  const stopQRStatusPolling = useCallback(() => {
    if (qrPollIntervalRef.current !== null) {
      clearInterval(qrPollIntervalRef.current);
      qrPollIntervalRef.current = null;
    }
  }, []);

  const startQRStatusPolling = useCallback(
    (sessionId: string) => {
      stopQRStatusPolling();

      qrPollIntervalRef.current = window.setInterval(async () => {
        try {
          const status = await getQRPairingStatus(sessionId);

          setQrSession(prev =>
            prev
              ? {
                  ...prev,
                  status: status.status as QRPairingSession['status'],
                }
              : null
          );

          // Stop polling on terminal states
          if (['connected', 'timeout', 'error'].includes(status.status)) {
            stopQRStatusPolling();

            if (status.status === 'connected') {
              // Success - close dialog after 2 seconds
              setTimeout(() => {
                setShowManualConnect(false);
                setQrSession(null);
              }, 2000);
            }
          }
        } catch (error) {
          console.error('[QR Pairing] Status poll failed:', error);
        }
      }, 1000);
    },
    [stopQRStatusPolling]
  );

  const handleGenerateQRCode = useCallback(async () => {
    setIsGeneratingQR(true);

    try {
      const result = await generateQRPairing();

      if (result.success && result.qr_payload && result.session_id) {
        setQrSession({
          sessionId: result.session_id,
          payload: result.qr_payload,
          status: 'listening',
          expiresAt: result.expires_at ?? Date.now() + 120000,
        });

        startQRStatusPolling(result.session_id);
      }
    } catch (error) {
      console.error('[QR Pairing] Generation failed:', error);
    } finally {
      setIsGeneratingQR(false);
    }
  }, [startQRStatusPolling]);

  const handleCancelQRPairing = useCallback(async () => {
    if (!qrSession) return;

    try {
      await cancelQRPairing(qrSession.sessionId);
      setQrSession(null);
      stopQRStatusPolling();
    } catch (error) {
      console.error('[QR Pairing] Cancel failed:', error);
    }
  }, [qrSession, stopQRStatusPolling]);

  const handleDiscoverRemote = async () => {
    setRemoteUrlError('');

    if (!remoteBaseUrl.trim()) {
      setRemoteUrlError(
        t.deviceSidebar.remoteUrlRequired || '请输入远程服务器地址'
      );
      return;
    }
    if (
      !remoteBaseUrl.startsWith('http://') &&
      !remoteBaseUrl.startsWith('https://')
    ) {
      setRemoteUrlError(
        t.deviceSidebar.remoteUrlInvalid ||
          '地址必须以 http:// 或 https:// 开头'
      );
      return;
    }

    setIsDiscoveringRemote(true);
    try {
      const result = await discoverRemoteDevices({
        base_url: remoteBaseUrl,
        timeout: 5,
      });

      if (result.success) {
        setDiscoveredRemoteDevices(result.devices);
        setSelectedRemoteDevice(null);
      } else {
        setRemoteUrlError(result.message || '发现设备失败');
        setDiscoveredRemoteDevices([]);
      }
    } catch {
      setRemoteUrlError('连接失败，请检查地址是否正确');
      setDiscoveredRemoteDevices([]);
    } finally {
      setIsDiscoveringRemote(false);
    }
  };

  const handleAddRemoteDevice = async () => {
    if (!selectedRemoteDevice) return;

    setIsConnectingRemote(true);
    try {
      const result = await addRemoteDevice({
        base_url: remoteBaseUrl,
        device_id: selectedRemoteDevice,
      });

      if (result.success) {
        setShowManualConnect(false);
        setRemoteBaseUrl('');
        setDiscoveredRemoteDevices([]);
        setSelectedRemoteDevice(null);
      } else {
        setRemoteUrlError(result.message || t.toasts.remoteDeviceAddError);
      }
    } catch {
      setRemoteUrlError(t.toasts.remoteDeviceAddError);
    } finally {
      setIsConnectingRemote(false);
    }
  };

  // Cleanup QR session when dialog closes or tab changes
  useEffect(() => {
    if (!showManualConnect || activeTab !== 'pair') {
      if (qrSession && qrSession.status === 'listening') {
        handleCancelQRPairing();
      }
      stopQRStatusPolling();
    }
  }, [
    showManualConnect,
    activeTab,
    qrSession,
    stopQRStatusPolling,
    handleCancelQRPairing,
  ]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopQRStatusPolling();
    };
  }, [stopQRStatusPolling]);

  // Auto-generate QR code when switching to pair tab
  useEffect(() => {
    if (
      showManualConnect &&
      activeTab === 'pair' &&
      !qrSession &&
      !isGeneratingQR
    ) {
      handleGenerateQRCode();
    }
  }, [
    showManualConnect,
    activeTab,
    qrSession,
    isGeneratingQR,
    handleGenerateQRCode,
  ]);

  // mDNS device discovery handler
  const handleDiscover = useCallback(async () => {
    setIsScanning(true);
    setScanError('');

    try {
      const result = await discoverMdnsDevices();

      if (result.success) {
        setDiscoveredDevices(result.devices);
      } else {
        setScanError(
          result.error ||
            t.deviceSidebar.scanError.replace('{error}', 'Unknown error')
        );
        setDiscoveredDevices([]);
      }
    } catch (error) {
      setScanError(t.deviceSidebar.scanError.replace('{error}', String(error)));
      setDiscoveredDevices([]);
    } finally {
      setIsScanning(false);
    }
  }, [t.deviceSidebar.scanError, setIsScanning]);

  // Handle clicking on a discovered device
  const handleDeviceClick = async (
    device: MdnsDevice,
    inPairingTab: boolean
  ) => {
    if (!inPairingTab && !device.has_pairing) {
      // In direct connect tab, connect directly
      setIsConnecting(true);
      setIpError('');

      try {
        const result = await connectWifiManual({
          ip: device.ip,
          port: device.port,
        });

        if (result.success) {
          setShowManualConnect(false);
          // Device list will auto-refresh via polling
        } else {
          setIpError(result.message || t.toasts.wifiManualConnectError);
        }
      } catch (error) {
        setIpError(t.toasts.wifiManualConnectError);
        console.error('[DeviceSidebar] Error connecting:', error);
      } finally {
        setIsConnecting(false);
      }
    } else if (inPairingTab && device.has_pairing) {
      // In pairing tab, auto-fill the form
      setManualConnectIp(device.ip);
      setPairingPort(device.pairing_port ? String(device.pairing_port) : '');
      setConnectionPort(String(device.port));
      // Focus on pairing code input
      setTimeout(() => {
        document.getElementById('pairing-code')?.focus();
      }, 100);
    }
  };

  // Auto-scan when dialog opens and poll for updates
  useEffect(() => {
    if (showManualConnect) {
      // Initial scan
      handleDiscover();

      // Poll every 5 seconds for device updates
      const pollInterval = setInterval(() => {
        handleDiscover();
      }, 5000);

      // Cleanup interval on unmount or when dialog closes
      return () => {
        clearInterval(pollInterval);
      };
    }
  }, [showManualConnect, handleDiscover]);

  return (
    <>
      {/* Collapsed toggle button */}
      {isCollapsed && (
        <Button
          variant="outline"
          size="icon"
          onClick={toggleCollapse}
          className="absolute left-0 top-20 z-50 h-16 w-8 rounded-r-lg rounded-l-none border-l-0 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700"
          title="Expand sidebar"
        >
          <ChevronRight className="h-4 w-4" />
        </Button>
      )}

      {/* Sidebar */}
      <div
        className={`
          ${isCollapsed ? 'w-0 -ml-4 opacity-0' : 'w-80 opacity-100'}
          transition-all duration-300 ease-in-out
          h-full min-h-0
          bg-white dark:bg-slate-950
          border-r border-slate-200 dark:border-slate-800
          flex flex-col
          overflow-hidden
        `}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4">
          <div className="flex items-center gap-2">
            <div>
              <h2 className="text-base font-bold text-slate-900 dark:text-slate-100">
                AutoGLM
              </h2>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                {devices.length}{' '}
                {devices.length === 1
                  ? t.deviceSidebar.devices
                  : t.deviceSidebar.devices}
              </p>
            </div>
          </div>

          <Button
            variant="ghost"
            size="icon"
            onClick={toggleCollapse}
            className="h-8 w-8 rounded-full text-slate-400 hover:text-slate-600 dark:text-slate-500 dark:hover:text-slate-300"
            title="Collapse sidebar"
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
        </div>

        <Separator className="mx-4" />

        {/* Device list */}
        <div className="flex-1 overflow-y-auto p-3 space-y-2 min-h-0">
          {devices.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <div className="flex h-16 w-16 items-center justify-center rounded-full bg-slate-100 dark:bg-slate-800">
                <Plug className="h-8 w-8 text-slate-400" />
              </div>
              <p className="mt-4 font-medium text-slate-900 dark:text-slate-100">
                {t.deviceSidebar.noDevicesConnected}
              </p>
              <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                {t.deviceSidebar.clickToRefresh}
              </p>
            </div>
          ) : (
            devices.map(device => (
              <DeviceCard
                key={device.id}
                id={device.id}
                serial={device.serial}
                model={device.model}
                status={device.status}
                connectionType={device.connection_type}
                agent={device.agent}
                isActive={currentDeviceId === device.id}
                onClick={() => onSelectDevice(device.id)}
                onConnectWifi={async () => {
                  await onConnectWifi(device.id);
                }}
                onDisconnectWifi={async () => {
                  await onDisconnectWifi(device.id);
                }}
              />
            ))
          )}
        </div>

        <Separator className="mx-4" />

        {/* Bottom actions */}
        <div className="p-3 space-y-2">
          <Button
            variant="outline"
            onClick={() => setShowManualConnect(true)}
            className="w-full justify-start gap-2 rounded-full border-slate-200 dark:border-slate-700"
          >
            <Plus className="h-4 w-4" />
            {t.deviceSidebar.addDevice}
          </Button>
          <Button
            variant="outline"
            onClick={onOpenConfig}
            className="w-full justify-start gap-2 rounded-full border-slate-200 dark:border-slate-700"
          >
            <Settings className="h-4 w-4" />
            {t.deviceSidebar.settings}
          </Button>
        </div>

        {/* Manual WiFi Connect Dialog */}
        <Dialog open={showManualConnect} onOpenChange={setShowManualConnect}>
          <DialogContent className="sm:max-w-md max-h-[80vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>{t.deviceSidebar.manualConnectTitle}</DialogTitle>
              <DialogDescription>
                {t.deviceSidebar.manualConnectDescription}
              </DialogDescription>
            </DialogHeader>

            <Tabs
              value={activeTab}
              onValueChange={setActiveTab}
              className="w-full"
            >
              <TabsList className="grid w-full grid-cols-3">
                <TabsTrigger value="direct">
                  {t.deviceSidebar.directConnectTab}
                </TabsTrigger>
                <TabsTrigger value="pair">
                  {t.deviceSidebar.pairTab}
                </TabsTrigger>
                <TabsTrigger value="remote">
                  {t.deviceSidebar.remoteTab || '远程设备'}
                </TabsTrigger>
              </TabsList>

              {/* Direct Connect Tab */}
              <TabsContent value="direct" className="space-y-4 mt-4">
                {/* Scan Control */}
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-medium text-slate-900 dark:text-slate-100">
                    {t.deviceSidebar.discoveredDevices}
                  </h3>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleDiscover}
                    disabled={isScanning}
                    className="h-8"
                  >
                    {isScanning ? (
                      <>
                        <span className="mr-2 h-3 w-3 animate-spin rounded-full border-2 border-slate-400 border-t-transparent" />
                        {t.deviceSidebar.scanning}
                      </>
                    ) : (
                      t.deviceSidebar.scanAgain
                    )}
                  </Button>
                </div>

                {/* Scan Error */}
                {scanError && (
                  <div className="rounded-lg bg-red-50 dark:bg-red-950/20 p-3">
                    <p className="text-sm text-red-700 dark:text-red-300">
                      {scanError}
                    </p>
                  </div>
                )}

                {/* Discovered Devices List - Filter has_pairing=false */}
                {(() => {
                  const directDevices = discoveredDevices.filter(
                    d => !d.has_pairing
                  );
                  if (!isScanning && directDevices.length === 0) {
                    return (
                      <div className="rounded-lg bg-slate-50 dark:bg-slate-900 p-4 text-center">
                        <Wifi className="mx-auto h-8 w-8 text-slate-400" />
                        <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
                          {t.deviceSidebar.noDirectDevices}
                        </p>
                      </div>
                    );
                  }
                  if (directDevices.length > 0) {
                    return (
                      <div className="space-y-2">
                        {directDevices.map(device => (
                          <button
                            key={`${device.ip}:${device.port}`}
                            onClick={() => handleDeviceClick(device, false)}
                            disabled={isConnecting}
                            className="w-full rounded-lg border border-slate-200 dark:border-slate-700 p-3 text-left transition-colors hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-50 disabled:cursor-not-allowed"
                          >
                            <div className="flex items-start justify-between">
                              <div className="flex-1">
                                <div className="flex items-center gap-2">
                                  <Smartphone className="h-4 w-4 text-[#1d9bf0]" />
                                  <span className="font-medium text-slate-900 dark:text-slate-100">
                                    {device.name}
                                  </span>
                                </div>
                                <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                                  {device.ip}:{device.port}
                                </p>
                              </div>
                            </div>
                          </button>
                        ))}
                      </div>
                    );
                  }
                  return null;
                })()}

                {/* Connection Error */}
                {ipError && activeTab === 'direct' && (
                  <div className="rounded-lg bg-red-50 dark:bg-red-950/20 p-3">
                    <p className="text-sm text-red-700 dark:text-red-300">
                      {ipError}
                    </p>
                  </div>
                )}

                {/* Separator */}
                <div className="relative my-4">
                  <Separator />
                  <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 bg-white dark:bg-slate-950 px-2 text-sm text-slate-500">
                    {t.deviceSidebar.orManualConnect}
                  </span>
                </div>

                {/* Manual Connect Form */}
                <div className="space-y-3">
                  <div className="rounded-lg bg-amber-50 dark:bg-amber-950/20 p-3 text-sm">
                    <p className="text-amber-800 dark:text-amber-200">
                      {t.deviceSidebar.directConnectNote}
                    </p>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="ip">{t.deviceSidebar.ipAddress}</Label>
                    <Input
                      id="ip"
                      placeholder="192.168.1.100"
                      value={manualConnectIp}
                      onChange={e => setManualConnectIp(e.target.value)}
                      onKeyDown={e =>
                        e.key === 'Enter' && handleManualConnect()
                      }
                      className={ipError ? 'border-red-500' : ''}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="port">{t.deviceSidebar.port}</Label>
                    <Input
                      id="port"
                      type="number"
                      value={manualConnectPort}
                      onChange={e => setManualConnectPort(e.target.value)}
                      onKeyDown={e =>
                        e.key === 'Enter' && handleManualConnect()
                      }
                      className={portError ? 'border-red-500' : ''}
                    />
                    {portError && (
                      <p className="text-sm text-red-500">{portError}</p>
                    )}
                  </div>
                  <Button
                    onClick={handleManualConnect}
                    disabled={isConnecting}
                    className="w-full"
                  >
                    {isConnecting ? t.common.loading : t.deviceSidebar.connect}
                  </Button>
                </div>
              </TabsContent>

              {/* Pairing Tab */}
              <TabsContent value="pair" className="space-y-4 mt-4">
                {/* Scan Control (shared state) */}
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-medium text-slate-900 dark:text-slate-100">
                    {t.deviceSidebar.discoveredDevices}
                  </h3>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleDiscover}
                    disabled={isScanning}
                    className="h-8"
                  >
                    {isScanning ? (
                      <>
                        <span className="mr-2 h-3 w-3 animate-spin rounded-full border-2 border-slate-400 border-t-transparent" />
                        {t.deviceSidebar.scanning}
                      </>
                    ) : (
                      t.deviceSidebar.scanAgain
                    )}
                  </Button>
                </div>

                {/* Scan Error */}
                {scanError && (
                  <div className="rounded-lg bg-red-50 dark:bg-red-950/20 p-3">
                    <p className="text-sm text-red-700 dark:text-red-300">
                      {scanError}
                    </p>
                  </div>
                )}

                {/* Discovered Devices List - Filter has_pairing=true */}
                {(() => {
                  const pairingDevices = discoveredDevices.filter(
                    d => d.has_pairing
                  );
                  if (!isScanning && pairingDevices.length === 0) {
                    return (
                      <div className="rounded-lg bg-slate-50 dark:bg-slate-900 p-4 text-center">
                        <Wifi className="mx-auto h-8 w-8 text-slate-400" />
                        <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
                          {t.deviceSidebar.noPairingDevices}
                        </p>
                      </div>
                    );
                  }
                  if (pairingDevices.length > 0) {
                    return (
                      <div className="space-y-2">
                        {pairingDevices.map(device => (
                          <button
                            key={`${device.ip}:${device.port}`}
                            onClick={() => handleDeviceClick(device, true)}
                            disabled={isConnecting}
                            className="w-full rounded-lg border border-slate-200 dark:border-slate-700 p-3 text-left transition-colors hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-50 disabled:cursor-not-allowed"
                          >
                            <div className="flex items-start justify-between">
                              <div className="flex-1">
                                <div className="flex items-center gap-2">
                                  <Smartphone className="h-4 w-4 text-[#1d9bf0]" />
                                  <span className="font-medium text-slate-900 dark:text-slate-100">
                                    {device.name}
                                  </span>
                                </div>
                                <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                                  {device.ip}:{device.port}
                                </p>
                                <div className="mt-2 flex items-center gap-1 text-xs text-amber-600 dark:text-amber-400">
                                  <AlertCircle className="h-3 w-3" />
                                  <span>{t.deviceSidebar.pairingRequired}</span>
                                </div>
                              </div>
                            </div>
                          </button>
                        ))}
                      </div>
                    );
                  }
                  return null;
                })()}

                {/* QR Code Pairing Section */}
                <div className="space-y-3">
                  {/* QR Separator */}
                  <div className="relative my-4">
                    <Separator />
                    <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 bg-white dark:bg-slate-950 px-2 text-sm text-slate-500">
                      {t.deviceSidebar.orQrPair}
                    </span>
                  </div>

                  {/* QR Instructions */}
                  <div className="rounded-lg bg-purple-50 dark:bg-purple-950/20 p-3 text-sm">
                    <p className="font-medium text-purple-900 dark:text-purple-100 mb-2">
                      {t.deviceSidebar.qrPairingTitle}
                    </p>
                    <ol className="space-y-1 text-purple-700 dark:text-purple-300 text-xs">
                      <li>{t.deviceSidebar.qrStep1}</li>
                      <li>{t.deviceSidebar.qrStep2}</li>
                      <li>{t.deviceSidebar.qrStep3}</li>
                    </ol>
                  </div>

                  {/* QR Display Area (when session active) */}
                  {qrSession && (
                    <div className="rounded-lg border border-slate-200 dark:border-slate-700 p-4 bg-white dark:bg-slate-900">
                      <div className="flex flex-col items-center space-y-3">
                        {/* QR Code Image */}
                        <div className="bg-white p-4 rounded-lg">
                          <QRCodeSVG
                            value={qrSession.payload}
                            size={200}
                            level="M"
                          />
                        </div>

                        {/* Status Display */}
                        <div className="flex items-center gap-2">
                          {qrSession.status === 'listening' && (
                            <>
                              <span className="h-2 w-2 rounded-full bg-blue-500 animate-pulse" />
                              <span className="text-sm text-slate-600 dark:text-slate-400">
                                {t.deviceSidebar.qrWaitingForScan}
                              </span>
                            </>
                          )}
                          {qrSession.status === 'pairing' && (
                            <>
                              <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
                              <span className="text-sm text-slate-600 dark:text-slate-400">
                                {t.deviceSidebar.qrPairing}
                              </span>
                            </>
                          )}
                          {qrSession.status === 'connected' && (
                            <>
                              <CheckCircle className="h-4 w-4 text-green-500" />
                              <span className="text-sm text-green-600 dark:text-green-400">
                                {t.deviceSidebar.qrConnected}
                              </span>
                            </>
                          )}
                          {qrSession.status === 'timeout' && (
                            <>
                              <XCircle className="h-4 w-4 text-amber-500" />
                              <span className="text-sm text-amber-600 dark:text-amber-400">
                                {t.deviceSidebar.qrTimeout}
                              </span>
                            </>
                          )}
                          {qrSession.status === 'error' && (
                            <>
                              <XCircle className="h-4 w-4 text-red-500" />
                              <span className="text-sm text-red-600 dark:text-red-400">
                                {t.deviceSidebar.qrError}
                              </span>
                            </>
                          )}
                        </div>

                        {/* Action Buttons */}
                        <div className="flex gap-2 w-full">
                          {(qrSession.status === 'timeout' ||
                            qrSession.status === 'error') && (
                            <Button
                              variant="outline"
                              onClick={handleGenerateQRCode}
                              className="flex-1"
                            >
                              {t.deviceSidebar.qrRegenerate}
                            </Button>
                          )}
                          {qrSession.status === 'listening' && (
                            <Button
                              variant="outline"
                              onClick={handleCancelQRPairing}
                              className="flex-1"
                            >
                              {t.common.cancel}
                            </Button>
                          )}
                          {qrSession.status === 'connected' && (
                            <Button
                              onClick={() => setShowManualConnect(false)}
                              className="flex-1"
                            >
                              {t.common.confirm}
                            </Button>
                          )}
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Loading state when auto-generating */}
                  {!qrSession && isGeneratingQR && (
                    <div className="flex items-center justify-center gap-2 py-4 text-slate-600 dark:text-slate-400">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      <span className="text-sm">{t.common.loading}</span>
                    </div>
                  )}
                </div>

                {/* Separator */}
                <div className="relative my-4">
                  <Separator />
                  <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 bg-white dark:bg-slate-950 px-2 text-sm text-slate-500">
                    {t.deviceSidebar.orManualPair}
                  </span>
                </div>

                {/* Pairing Instructions */}
                <div className="rounded-lg bg-blue-50 dark:bg-blue-950/20 p-3 text-sm">
                  <p className="font-medium text-blue-900 dark:text-blue-100 mb-2">
                    {t.deviceSidebar.pairingInstructions}
                  </p>
                  <ol className="space-y-1 text-blue-700 dark:text-blue-300 text-xs">
                    <li>{t.deviceSidebar.pairingStep1}</li>
                    <li>{t.deviceSidebar.pairingStep2}</li>
                    <li>{t.deviceSidebar.pairingStep3}</li>
                    <li>{t.deviceSidebar.pairingStep4}</li>
                  </ol>
                  <p className="mt-2 text-xs text-blue-600 dark:text-blue-400">
                    {t.deviceSidebar.pairingNote}
                  </p>
                </div>

                {/* Pairing Form */}
                <div className="space-y-3">
                  <div className="space-y-2">
                    <Label htmlFor="pair-ip">{t.deviceSidebar.ipAddress}</Label>
                    <Input
                      id="pair-ip"
                      placeholder="192.168.1.100"
                      value={manualConnectIp}
                      onChange={e => setManualConnectIp(e.target.value)}
                      className={ipError ? 'border-red-500' : ''}
                    />
                    {ipError && activeTab === 'pair' && (
                      <p className="text-sm text-red-500">{ipError}</p>
                    )}
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="pairing-port">
                      {t.deviceSidebar.pairingPort}
                    </Label>
                    <Input
                      id="pairing-port"
                      type="number"
                      placeholder="37831"
                      value={pairingPort}
                      onChange={e => setPairingPort(e.target.value)}
                      className={portError ? 'border-red-500' : ''}
                    />
                    {portError && (
                      <p className="text-sm text-red-500">{portError}</p>
                    )}
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="pairing-code">
                      {t.deviceSidebar.pairingCode}
                    </Label>
                    <Input
                      id="pairing-code"
                      type="text"
                      placeholder="123456"
                      maxLength={6}
                      value={pairingCode}
                      onChange={e =>
                        setPairingCode(e.target.value.replace(/\D/g, ''))
                      }
                      onKeyDown={e => e.key === 'Enter' && handlePair()}
                      className={pairingCodeError ? 'border-red-500' : ''}
                    />
                    {pairingCodeError && (
                      <p className="text-sm text-red-500">{pairingCodeError}</p>
                    )}
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="connection-port">
                      {t.deviceSidebar.connectionPort}
                    </Label>
                    <Input
                      id="connection-port"
                      type="number"
                      value={connectionPort}
                      onChange={e => setConnectionPort(e.target.value)}
                      onKeyDown={e => e.key === 'Enter' && handlePair()}
                    />
                  </div>

                  <Button
                    onClick={handlePair}
                    disabled={isConnecting}
                    className="w-full"
                  >
                    {isConnecting
                      ? t.common.loading
                      : t.deviceSidebar.pairAndConnect}
                  </Button>
                </div>
              </TabsContent>

              {/* Remote Device Tab */}
              <TabsContent value="remote" className="space-y-4 mt-4">
                <div className="space-y-2">
                  <Label htmlFor="remote-url">
                    {t.deviceSidebar.remoteUrl || '远程服务器地址'}
                  </Label>
                  <Input
                    id="remote-url"
                    placeholder="http://192.168.1.100:8001"
                    value={remoteBaseUrl}
                    onChange={e => {
                      setRemoteBaseUrl(e.target.value);
                      setRemoteUrlError('');
                    }}
                    disabled={isDiscoveringRemote}
                    onKeyDown={e => e.key === 'Enter' && handleDiscoverRemote()}
                    className={remoteUrlError ? 'border-red-500' : ''}
                  />
                  {remoteUrlError && (
                    <p className="text-sm text-red-500">{remoteUrlError}</p>
                  )}
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    {t.deviceSidebar.remoteUrlHint ||
                      '运行 Device Agent Server 的地址'}
                  </p>
                  <Button
                    onClick={handleDiscoverRemote}
                    disabled={isDiscoveringRemote || !remoteBaseUrl}
                    className="w-full"
                  >
                    {isDiscoveringRemote ? '正在发现...' : '发现设备'}
                  </Button>
                </div>

                {discoveredRemoteDevices.length > 0 && (
                  <div className="space-y-2">
                    <Label>可用设备</Label>
                    <div className="space-y-2">
                      {discoveredRemoteDevices.map(device => (
                        <button
                          key={device.device_id}
                          onClick={() =>
                            setSelectedRemoteDevice(device.device_id)
                          }
                          className={`
                            w-full rounded-lg border p-3 text-left transition-colors
                            ${
                              selectedRemoteDevice === device.device_id
                                ? 'border-[#1d9bf0] bg-blue-50 dark:bg-blue-950/20'
                                : 'border-slate-200 hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800'
                            }
                          `}
                        >
                          <div className="flex items-center gap-2">
                            <Smartphone className="h-4 w-4 text-[#1d9bf0]" />
                            <div className="flex-1">
                              <p className="font-medium text-sm">
                                {device.device_id}
                              </p>
                              <p className="text-xs text-slate-500">
                                {device.model} · {device.platform}
                              </p>
                            </div>
                            {selectedRemoteDevice === device.device_id && (
                              <CheckCircle className="h-4 w-4 text-[#1d9bf0]" />
                            )}
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {selectedRemoteDevice && (
                  <Button
                    onClick={handleAddRemoteDevice}
                    disabled={isConnectingRemote}
                    className="w-full"
                  >
                    {isConnectingRemote ? '正在连接...' : '连接远程设备'}
                  </Button>
                )}
              </TabsContent>
            </Tabs>

            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => {
                  setShowManualConnect(false);
                  setIpError('');
                  setPortError('');
                  setPairingCodeError('');
                  setScanError('');
                  setManualConnectIp('');
                  setManualConnectPort('5555');
                  setPairingCode('');
                  setPairingPort('');
                  setConnectionPort('5555');
                  setActiveTab('direct');
                  setDiscoveredDevices([]);
                }}
              >
                {t.common.cancel}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </>
  );
}
