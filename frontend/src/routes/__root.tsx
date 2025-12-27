import * as React from 'react';
import { Outlet, createRootRoute } from '@tanstack/react-router';
import { TanStackRouterDevtools } from '@tanstack/react-router-devtools';
import { getStatus, checkVersion, type VersionCheckResponse } from '../api';
import { Separator } from '@/components/ui/separator';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Github, Globe } from 'lucide-react';
import { useLocale, useTranslation } from '../lib/i18n-context';
import { ThemeToggle } from '../components/ThemeToggle';
import { NavigationSidebar } from '../components/NavigationSidebar';

export const Route = createRootRoute({
  component: RootComponent,
});

function Footer() {
  const [version, setVersion] = React.useState<string>('...');
  const { locale, setLocale, localeName } = useLocale();
  const t = useTranslation();
  const [updateInfo, setUpdateInfo] =
    React.useState<VersionCheckResponse | null>(null);
  const [showUpdateBadge, setShowUpdateBadge] = React.useState(false);
  const [isUpdateDialogOpen, setIsUpdateDialogOpen] = React.useState(false);

  React.useEffect(() => {
    getStatus()
      .then(status => setVersion(status.version))
      .catch(() => setVersion('unknown'));

    // Check for updates
    const checkForUpdates = async () => {
      // 1. Check session storage cache (1 hour TTL)
      const cachedCheck = sessionStorage.getItem('version_check');
      if (cachedCheck) {
        try {
          const { data, timestamp } = JSON.parse(cachedCheck);
          if (Date.now() - timestamp < 3600000) {
            // 1 hour
            setUpdateInfo(data);
            setShowUpdateBadge(data.has_update);
            return;
          }
        } catch (e) {
          console.log(e);
          // Invalid cache, continue to fetch
        }
      }

      // 2. Fetch from API
      try {
        const result = await checkVersion();
        setUpdateInfo(result);

        // Cache in session storage
        sessionStorage.setItem(
          'version_check',
          JSON.stringify({
            data: result,
            timestamp: Date.now(),
          })
        );

        // Show badge if update available
        setShowUpdateBadge(result.has_update);
      } catch (err) {
        console.error('Failed to check for updates:', err);
        // Silently fail - non-critical feature
      }
    };

    checkForUpdates();
  }, []);

  const toggleLocale = () => {
    setLocale(locale === 'en' ? 'zh' : 'en');
  };

  const handleUpdateClick = () => {
    if (updateInfo?.release_url) {
      // Open release page in new tab
      window.open(updateInfo.release_url, '_blank', 'noopener,noreferrer');
    }
  };

  const releaseNotes = updateInfo?.release_notes?.trim();

  return (
    <footer className="mt-auto border-t border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950">
      <div className="max-w-7xl mx-auto px-4 py-3 flex flex-col sm:flex-row items-center justify-between gap-2 text-sm">
        <div className="flex items-center gap-2 text-slate-500 dark:text-slate-400">
          <span className="flex items-center gap-1.5">
            v{version}
            {showUpdateBadge && updateInfo?.latest_version && (
              <Badge
                variant="warning"
                className="cursor-pointer hover:opacity-80 transition-opacity"
                onClick={() => setIsUpdateDialogOpen(true)}
                title={t.footer.updateAvailable.replace(
                  '{version}',
                  updateInfo.latest_version
                )}
              >
                {t.footer.newVersion}
              </Badge>
            )}
          </span>
          <Separator
            orientation="vertical"
            className="h-4 bg-slate-200 dark:bg-slate-700"
          />
          <button
            onClick={toggleLocale}
            className="hover:text-[#1d9bf0] transition-colors flex items-center gap-1"
            title="Switch language"
          >
            <Globe className="w-4 h-4" />
            {localeName}
          </button>
          <Separator
            orientation="vertical"
            className="h-4 bg-slate-200 dark:bg-slate-700"
          />
          <ThemeToggle />
          <Separator
            orientation="vertical"
            className="h-4 bg-slate-200 dark:bg-slate-700"
          />
          <a
            href="https://github.com/suyiiyii/AutoGLM-GUI"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-[#1d9bf0] transition-colors flex items-center gap-1"
          >
            <Github className="w-4 h-4" />
            GitHub
          </a>
        </div>
        <div className="text-center">
          <a
            href="https://github.com/suyiiyii/AutoGLM-GUI"
            target="_blank"
            rel="noopener noreferrer"
            className="text-slate-500 dark:text-slate-400 hover:text-[#1d9bf0] transition-colors"
          >
            Star{' '}
            <span className="font-semibold" role="img" aria-label="star">
              ⭐
            </span>{' '}
            on GitHub
          </a>
        </div>
      </div>
      <Dialog open={isUpdateDialogOpen} onOpenChange={setIsUpdateDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t.footer.newVersionTitle}</DialogTitle>
            {updateInfo?.latest_version && (
              <DialogDescription>
                {t.footer.updateAvailable.replace(
                  '{version}',
                  updateInfo.latest_version
                )}
              </DialogDescription>
            )}
          </DialogHeader>
          <div className="space-y-2">
            <div className="text-sm font-medium text-slate-700 dark:text-slate-300">
              {t.footer.releaseNotes}
            </div>
            <ScrollArea className="max-h-60 rounded-md border border-slate-200 dark:border-slate-800">
              <pre className="whitespace-pre-wrap text-sm text-slate-600 dark:text-slate-300 p-3">
                {releaseNotes || t.footer.noReleaseNotes}
              </pre>
            </ScrollArea>
          </div>
          <DialogFooter>
            {updateInfo?.release_url && (
              <Button variant="twitter" onClick={handleUpdateClick}>
                {t.footer.viewRelease}
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </footer>
  );
}

function RootComponent() {
  return (
    <div className="h-screen flex flex-col overflow-hidden">
      <div className="flex-1 flex overflow-hidden">
        <NavigationSidebar />
        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="flex-1 overflow-auto">
            <Outlet />
          </div>
          <Footer />
        </div>
      </div>
      <TanStackRouterDevtools position="bottom-right" />
    </div>
  );
}
