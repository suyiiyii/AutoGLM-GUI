import { createFileRoute } from '@tanstack/react-router';
import { useState, useEffect, useCallback } from 'react';
import { FileText, FolderOpen, RefreshCw, AlertCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useTranslation } from '../lib/i18n-context';

interface LogFile {
  name: string;
  path: string;
  size: number;
  modified: Date;
  isError: boolean;
  isCompressed: boolean;
}

interface ElectronAPI {
  logs: {
    listFiles: () => Promise<LogFile[]>;
    readFile: (filename: string) => Promise<string>;
    openFolder: () => Promise<{ success: boolean; error?: string }>;
  };
}

export const Route = createFileRoute('/logs')({
  component: LogsComponent,
});

function LogsComponent() {
  const t = useTranslation();
  const [logFiles, setLogFiles] = useState<LogFile[]>([]);
  const [selectedLog, setSelectedLog] = useState<string | null>(null);
  const [logContent, setLogContent] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [contentLoading, setContentLoading] = useState(false);
  const [error, setError] = useState<string>('');
  const [isElectron, setIsElectron] = useState(false);

  const loadLogFiles = useCallback(async () => {
    try {
      setLoading(true);
      setError('');
      const electronAPI = (window as Window & { electronAPI?: ElectronAPI })
        .electronAPI;
      if (!electronAPI?.logs) return;
      const files = await electronAPI.logs.listFiles();
      setLogFiles(files);
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : String(err);
      setError(t.logs.loadFailed.replace('{error}', errorMsg));
    } finally {
      setLoading(false);
    }
  }, [t.logs.loadFailed]);

  useEffect(() => {
    const electronAPI = (window as Window & { electronAPI?: ElectronAPI })
      .electronAPI;
    if (electronAPI?.logs) {
      setIsElectron(true);
      loadLogFiles();
    }
  }, [loadLogFiles]);

  const viewLogFile = async (filename: string) => {
    setContentLoading(true);
    setError('');
    try {
      const electronAPI = (window as Window & { electronAPI?: ElectronAPI })
        .electronAPI;
      if (!electronAPI?.logs) return;
      const content = await electronAPI.logs.readFile(filename);
      setSelectedLog(filename);
      setLogContent(content);
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : String(err);
      setError(t.logs.readFailed.replace('{error}', errorMsg));
    } finally {
      setContentLoading(false);
    }
  };

  const openLogsFolder = async () => {
    try {
      const electronAPI = (window as Window & { electronAPI?: ElectronAPI })
        .electronAPI;
      if (!electronAPI?.logs) return;
      const result = await electronAPI.logs.openFolder();
      if (!result.success) {
        setError(
          t.logs.openFolderFailed.replace('{error}', result.error || '')
        );
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : String(err);
      setError(t.logs.openFolderFailed.replace('{error}', errorMsg));
    }
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  };

  const formatDate = (date: Date) => {
    return new Date(date).toLocaleString('zh-CN');
  };

  if (!isElectron) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <AlertCircle className="w-12 h-12 mx-auto mb-4 text-slate-400" />
          <p
            className="text-slate-600"
            dangerouslySetInnerHTML={{ __html: t.logs.webVersionNotice }}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex">
      <div className="w-80 border-r border-slate-200 dark:border-slate-800 flex flex-col">
        <div className="p-4 border-b border-slate-200 dark:border-slate-800">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-semibold">{t.logs.title}</h2>
            <Button
              variant="ghost"
              size="icon"
              onClick={loadLogFiles}
              disabled={loading}
              title={t.logs.refresh}
            >
              <RefreshCw
                className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`}
              />
            </Button>
          </div>
          <Button variant="outline" className="w-full" onClick={openLogsFolder}>
            <FolderOpen className="w-4 h-4 mr-2" />
            {t.logs.openFolder}
          </Button>
        </div>

        <div className="flex-1 overflow-y-auto">
          {logFiles.length === 0 ? (
            <div className="p-4 text-center text-slate-500 text-sm">
              {t.logs.noLogs}
            </div>
          ) : (
            <div className="divide-y divide-slate-200 dark:divide-slate-800">
              {logFiles.map(file => (
                <div
                  key={file.name}
                  className={`p-4 hover:bg-slate-50 dark:hover:bg-slate-900 cursor-pointer transition-colors ${
                    selectedLog === file.name
                      ? 'bg-slate-50 dark:bg-slate-900'
                      : ''
                  }`}
                  onClick={() => !file.isCompressed && viewLogFile(file.name)}
                >
                  <div className="flex items-start gap-3">
                    {file.isError ? (
                      <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
                    ) : (
                      <FileText className="w-5 h-5 text-slate-400 flex-shrink-0 mt-0.5" />
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="font-medium text-sm truncate">
                        {file.name}
                      </div>
                      <div className="text-xs text-slate-500 mt-1">
                        {formatFileSize(file.size)} •{' '}
                        {formatDate(file.modified)}
                      </div>
                    </div>
                  </div>
                  {file.isCompressed && (
                    <div className="text-xs text-slate-400 mt-2 ml-8">
                      {t.logs.compressedFileNote}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="flex-1 flex flex-col">
        {selectedLog ? (
          <>
            <div className="p-4 border-b border-slate-200 dark:border-slate-800">
              <h3 className="font-semibold">{selectedLog}</h3>
            </div>
            <div className="flex-1 overflow-auto p-4 bg-slate-50 dark:bg-slate-950">
              {contentLoading ? (
                <div className="flex items-center justify-center h-full">
                  <div className="text-slate-500">{t.logs.loading}</div>
                </div>
              ) : (
                <pre className="text-xs font-mono whitespace-pre-wrap break-all">
                  {logContent}
                </pre>
              )}
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center text-slate-500">
            <div className="text-center">
              <FileText className="w-12 h-12 mx-auto mb-4 text-slate-300" />
              <p>{t.logs.selectLog}</p>
            </div>
          </div>
        )}
      </div>

      {error && (
        <div className="fixed bottom-4 right-4 max-w-md bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4 shadow-lg">
          <div className="flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
            <div className="flex-1 text-sm text-red-600 dark:text-red-400">
              {error}
            </div>
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 text-red-400 hover:text-red-600"
              onClick={() => setError('')}
            >
              ✕
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
