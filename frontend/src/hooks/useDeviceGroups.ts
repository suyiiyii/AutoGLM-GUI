import { useCallback, useEffect, useState } from 'react';
import { listDeviceGroups, type DeviceGroup } from '../api';

interface UseDeviceGroupsResult {
  groups: DeviceGroup[];
  refreshGroups: () => Promise<void>;
}

export function useDeviceGroups(): UseDeviceGroupsResult {
  const [groups, setGroups] = useState<DeviceGroup[]>([]);

  const refreshGroups = useCallback(async () => {
    try {
      const response = await listDeviceGroups();
      setGroups(response.groups);
    } catch (error) {
      console.error('Failed to fetch device groups:', error);
    }
  }, []);

  useEffect(() => {
    queueMicrotask(() => {
      void refreshGroups();
    });
  }, [refreshGroups]);

  return { groups, refreshGroups };
}
