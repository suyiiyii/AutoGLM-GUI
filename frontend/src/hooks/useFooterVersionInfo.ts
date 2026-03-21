import * as React from 'react';
import { checkVersion, getStatus, type VersionCheckResponse } from '../api';

interface FooterVersionInfo {
  backendVersion: string | null;
  updateInfo: VersionCheckResponse | null;
  showUpdateBadge: boolean;
  versionMismatch: boolean;
}

const VERSION_CHECK_CACHE_KEY = 'version_check';
const VERSION_CHECK_TTL_MS = 3600000;

export function useFooterVersionInfo(
  buildBackendVersion: string
): FooterVersionInfo {
  const [backendVersion, setBackendVersion] = React.useState<string | null>(
    null
  );
  const [versionMismatch, setVersionMismatch] = React.useState(false);
  const [updateInfo, setUpdateInfo] =
    React.useState<VersionCheckResponse | null>(null);
  const [showUpdateBadge, setShowUpdateBadge] = React.useState(false);

  React.useEffect(() => {
    getStatus()
      .then(status => {
        setBackendVersion(status.version);
        setVersionMismatch(
          buildBackendVersion !== 'unknown' &&
            status.version !== buildBackendVersion
        );
      })
      .catch(() => setBackendVersion(null));

    const checkForUpdates = async () => {
      const cachedCheck = sessionStorage.getItem(VERSION_CHECK_CACHE_KEY);
      if (cachedCheck) {
        try {
          const { data, timestamp } = JSON.parse(cachedCheck) as {
            data: VersionCheckResponse;
            timestamp: number;
          };

          if (Date.now() - timestamp < VERSION_CHECK_TTL_MS) {
            setUpdateInfo(data);
            setShowUpdateBadge(data.has_update);
            return;
          }
        } catch {
          sessionStorage.removeItem(VERSION_CHECK_CACHE_KEY);
        }
      }

      try {
        const result = await checkVersion();
        setUpdateInfo(result);
        setShowUpdateBadge(result.has_update);
        sessionStorage.setItem(
          VERSION_CHECK_CACHE_KEY,
          JSON.stringify({
            data: result,
            timestamp: Date.now(),
          })
        );
      } catch (error) {
        console.error('Failed to check for updates:', error);
      }
    };

    void checkForUpdates();
  }, [buildBackendVersion]);

  return {
    backendVersion,
    updateInfo,
    showUpdateBadge,
    versionMismatch,
  };
}
