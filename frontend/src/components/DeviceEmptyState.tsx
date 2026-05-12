import type { Translations } from '../lib/i18n';

interface DeviceEmptyStateProps {
  t: Translations;
}

export function DeviceEmptyState({ t }: DeviceEmptyStateProps) {
  return (
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
        <p className="text-slate-500 dark:text-slate-400">{t.chat.connectDevice}</p>
      </div>
    </div>
  );
}
