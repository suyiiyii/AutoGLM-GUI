import React, { useState, useEffect, useCallback } from 'react';
import {
  Smartphone,
  Settings,
  ChevronLeft,
  ChevronRight,
  Plug,
  Plus,
  Wifi,
  AlertCircle,
  ChevronDown,
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
import {
  Collapsible,
  CollapsibleTrigger,
  CollapsibleContent,
} from '@/components/ui/collapsible';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import type { Device, MdnsDevice } from '../api';
import { connectWifiManual, pairWifi, discoverMdnsDevices } from '../api';
import { useTranslation } from '../lib/i18n-context';

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
  const [isScanning, setIsScanning] = useState(false);
  const [scanError, setScanError] = useState('');
  const [isManualOpen, setIsManualOpen] = useState(false);

  // Quick pairing dialog for discovered devices
  const [showQuickPair, setShowQuickPair] = useState(false);
  const [quickPairDevice, setQuickPairDevice] = useState<MdnsDevice | null>(
    null
  );
  const [quickPairingCode, setQuickPairingCode] = useState('');
  const [quickPairingPort, setQuickPairingPort] = useState('');
  const [quickPairingError, setQuickPairingError] = useState('');

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
  }, [t.deviceSidebar.scanError]);

  // Handle clicking on a discovered device
  const handleDeviceClick = async (device: MdnsDevice) => {
    // If device requires pairing, show quick pair dialog
    if (device.has_pairing) {
      setQuickPairDevice(device);
      setQuickPairingCode('');
      // Auto-fill pairing port if available from mDNS
      setQuickPairingPort(
        device.pairing_port ? String(device.pairing_port) : ''
      );
      setQuickPairingError('');
      setShowQuickPair(true);
      return;
    }

    // Otherwise, try to connect directly
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
  };

  // Handle quick pairing for discovered devices
  const handleQuickPair = async () => {
    if (!quickPairDevice) return;

    setQuickPairingError('');

    // Validate pairing code (6 digits)
    if (!/^\d{6}$/.test(quickPairingCode)) {
      setQuickPairingError(t.deviceSidebar.invalidPairingCodeError);
      return;
    }

    // Validate pairing port
    const pairingPortNum = parseInt(quickPairingPort, 10);
    if (isNaN(pairingPortNum) || pairingPortNum < 1 || pairingPortNum > 65535) {
      setQuickPairingError(t.deviceSidebar.invalidPortError);
      return;
    }

    setIsConnecting(true);

    try {
      const result = await pairWifi({
        ip: quickPairDevice.ip,
        pairing_port: pairingPortNum,
        pairing_code: quickPairingCode,
        connection_port: quickPairDevice.port,
      });

      if (result.success) {
        setShowQuickPair(false);
        setShowManualConnect(false);
        setQuickPairDevice(null);
        setQuickPairingCode('');
        setQuickPairingPort('');
        // Device list will auto-refresh via polling
      } else {
        setQuickPairingError(result.message || t.toasts.wifiPairError);
      }
    } catch (error) {
      console.error('[DeviceSidebar] Error pairing:', error);
      setQuickPairingError(t.toasts.wifiPairError);
    } finally {
      setIsConnecting(false);
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
          className="fixed left-0 top-20 z-50 h-16 w-8 rounded-r-lg rounded-l-none border-l-0 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700"
          title="Expand sidebar"
          style={{ left: 0 }}
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
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[#1d9bf0]/10">
              <Smartphone className="h-5 w-5 text-[#1d9bf0]" />
            </div>
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
                model={device.model}
                status={device.status}
                connectionType={device.connection_type}
                isInitialized={device.is_initialized}
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
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>{t.deviceSidebar.manualConnectTitle}</DialogTitle>
              <DialogDescription>
                {t.deviceSidebar.manualConnectDescription}
              </DialogDescription>
            </DialogHeader>

            {/* mDNS Discovery Section */}
            <div className="space-y-3">
              {/* Scan Button */}
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

              {/* No Devices Found */}
              {!isScanning && !scanError && discoveredDevices.length === 0 && (
                <div className="rounded-lg bg-slate-50 dark:bg-slate-900 p-4 text-center">
                  <Wifi className="mx-auto h-8 w-8 text-slate-400" />
                  <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
                    {t.deviceSidebar.noDevicesFound}
                  </p>
                </div>
              )}

              {/* Discovered Devices List */}
              {discoveredDevices.length > 0 && (
                <div className="space-y-2">
                  {discoveredDevices.map(device => (
                    <button
                      key={`${device.ip}:${device.port}`}
                      onClick={() => handleDeviceClick(device)}
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
                          {device.has_pairing && (
                            <div className="mt-2 flex items-center gap-1 text-xs text-amber-600 dark:text-amber-400">
                              <AlertCircle className="h-3 w-3" />
                              <span>{t.deviceSidebar.pairingRequired}</span>
                            </div>
                          )}
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              )}

              {/* Connection Error Display */}
              {ipError && (
                <div className="rounded-lg bg-red-50 dark:bg-red-950/20 p-3">
                  <p className="text-sm text-red-700 dark:text-red-300">
                    {ipError}
                  </p>
                </div>
              )}
            </div>

            {/* Manual Connection Collapsible */}
            <Collapsible open={isManualOpen} onOpenChange={setIsManualOpen}>
              <CollapsibleTrigger asChild>
                <Button
                  variant="ghost"
                  className="flex w-full items-center justify-between p-2 text-sm font-medium"
                >
                  <span>{t.deviceSidebar.manualConnection}</span>
                  <ChevronDown
                    className={`h-4 w-4 transition-transform ${
                      isManualOpen ? 'rotate-180' : ''
                    }`}
                  />
                </Button>
              </CollapsibleTrigger>

              <CollapsibleContent className="space-y-4 pt-2">
                <Tabs
                  value={activeTab}
                  onValueChange={setActiveTab}
                  className="w-full"
                >
                  <TabsList className="grid w-full grid-cols-2">
                    <TabsTrigger value="direct">
                      {t.deviceSidebar.directConnectTab}
                    </TabsTrigger>
                    <TabsTrigger value="pair">
                      {t.deviceSidebar.pairTab}
                    </TabsTrigger>
                  </TabsList>

                  <TabsContent value="direct" className="space-y-4">
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
                      {ipError && (
                        <p className="text-sm text-red-500">{ipError}</p>
                      )}
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
                  </TabsContent>

                  <TabsContent value="pair" className="space-y-4">
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

                    <div className="space-y-2">
                      <Label htmlFor="pair-ip">
                        {t.deviceSidebar.ipAddress}
                      </Label>
                      <Input
                        id="pair-ip"
                        placeholder="192.168.1.100"
                        value={manualConnectIp}
                        onChange={e => setManualConnectIp(e.target.value)}
                        className={ipError ? 'border-red-500' : ''}
                      />
                      {ipError && (
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
                        <p className="text-sm text-red-500">
                          {pairingCodeError}
                        </p>
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
                  </TabsContent>
                </Tabs>
              </CollapsibleContent>
            </Collapsible>

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
                  setIsManualOpen(false);
                }}
              >
                {t.common.cancel}
              </Button>
              <Button
                onClick={
                  activeTab === 'direct' ? handleManualConnect : handlePair
                }
                disabled={isConnecting}
              >
                {isConnecting ? t.common.loading : t.common.confirm}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Quick Pairing Dialog for Discovered Devices */}
        <Dialog open={showQuickPair} onOpenChange={setShowQuickPair}>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>{t.deviceSidebar.pairTab}</DialogTitle>
              <DialogDescription>
                {quickPairDevice
                  ? `${quickPairDevice.name} (${quickPairDevice.ip}:${quickPairDevice.port})`
                  : ''}
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4">
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
              </div>

              <div className="space-y-2">
                <Label htmlFor="quick-pairing-port">
                  {t.deviceSidebar.pairingPort}
                  {quickPairDevice?.pairing_port && (
                    <span className="ml-2 text-xs text-green-600 dark:text-green-400">
                      (Auto-detected)
                    </span>
                  )}
                </Label>
                <Input
                  id="quick-pairing-port"
                  type="number"
                  placeholder="40817"
                  value={quickPairingPort}
                  onChange={e => setQuickPairingPort(e.target.value)}
                  readOnly={!!quickPairDevice?.pairing_port}
                  className={
                    quickPairingError
                      ? 'border-red-500'
                      : quickPairDevice?.pairing_port
                        ? 'bg-slate-50 dark:bg-slate-900'
                        : ''
                  }
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="quick-pairing-code">
                  {t.deviceSidebar.pairingCode}
                </Label>
                <Input
                  id="quick-pairing-code"
                  type="text"
                  maxLength={6}
                  value={quickPairingCode}
                  onChange={e =>
                    setQuickPairingCode(e.target.value.replace(/\D/g, ''))
                  }
                  onKeyDown={e => e.key === 'Enter' && handleQuickPair()}
                  className={quickPairingError ? 'border-red-500' : ''}
                />
              </div>

              {quickPairingError && (
                <div className="rounded-lg bg-red-50 dark:bg-red-950/20 p-3">
                  <p className="text-sm text-red-700 dark:text-red-300">
                    {quickPairingError}
                  </p>
                </div>
              )}
            </div>

            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => {
                  setShowQuickPair(false);
                  setQuickPairDevice(null);
                  setQuickPairingCode('');
                  setQuickPairingPort('');
                  setQuickPairingError('');
                }}
              >
                {t.common.cancel}
              </Button>
              <Button onClick={handleQuickPair} disabled={isConnecting}>
                {isConnecting ? t.common.loading : t.common.confirm}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </>
  );
}
