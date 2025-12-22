import * as React from 'react';
import { Outlet, createRootRoute } from '@tanstack/react-router';
import { TanStackRouterDevtools } from '@tanstack/react-router-devtools';
import { getStatus } from '../api';
import { Separator } from '@/components/ui/separator';
import { Github } from 'lucide-react';

export const Route = createRootRoute({
  component: RootComponent,
});

function Footer() {
  const [version, setVersion] = React.useState<string>('...');

  React.useEffect(() => {
    getStatus()
      .then(status => setVersion(status.version))
      .catch(() => setVersion('unknown'));
  }, []);

  return (
    <footer className="mt-auto border-t border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950">
      <div className="max-w-7xl mx-auto px-4 py-3 flex flex-col sm:flex-row items-center justify-between gap-2 text-sm">
        <div className="flex items-center gap-2 text-slate-500 dark:text-slate-400">
          <span>v{version}</span>
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
    </footer>
  );
}

function RootComponent() {
  return (
    <div className="h-screen flex flex-col overflow-hidden">
      <div className="flex-1 overflow-auto">
        <Outlet />
      </div>
      <Footer />
      <TanStackRouterDevtools position="bottom-right" />
    </div>
  );
}
