import { Sparkles, Layers } from 'lucide-react';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import type { Translations } from '../lib/i18n';

interface ChatModeToggleProps {
  chatMode: 'classic' | 'chatkit';
  onModeChange: (mode: 'classic' | 'chatkit') => void;
  t: Translations;
}

export function ChatModeToggle({ chatMode, onModeChange, t }: ChatModeToggleProps) {
  return (
    <div className="flex items-center gap-0.5 bg-white/95 dark:bg-slate-800/95 backdrop-blur-sm rounded-full p-1 shadow-lg border border-slate-200 dark:border-slate-700">
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            onClick={() => onModeChange('classic')}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-full text-sm font-medium transition-all ${
              chatMode === 'classic'
                ? 'bg-slate-900 dark:bg-white text-white dark:text-slate-900 shadow-sm'
                : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700'
            }`}
          >
            <Sparkles className="w-4 h-4" />
            {t.chatkit?.classicMode || '经典模式'}
          </button>
        </TooltipTrigger>
        <TooltipContent
          side="bottom"
          sideOffset={8}
          className="max-w-xs"
        >
          <div className="space-y-1">
            <p className="font-medium">{t.chatkit?.classicMode || '经典模式'}</p>
            <p className="text-xs opacity-80">
              {t.chatkit?.classicModeDesc || '视觉模型直接执行任务'}
            </p>
          </div>
        </TooltipContent>
      </Tooltip>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            onClick={() => {
              onModeChange('chatkit');
            }}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-full text-sm font-medium transition-all ${
              chatMode === 'chatkit'
                ? 'bg-indigo-600 text-white shadow-sm'
                : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700'
            }`}
          >
            <Layers className="w-4 h-4" />
            {t.chatkit?.layeredMode || '分层代理'}
          </button>
        </TooltipTrigger>
        <TooltipContent
          side="bottom"
          sideOffset={8}
          className="max-w-xs"
        >
          <div className="space-y-1">
            <p className="font-medium">{t.chatkit?.layeredMode || '分层代理'}</p>
            <p className="text-xs opacity-80">
              {t.chatkit?.layeredModeDesc || '规划层分解任务，执行层独立完成子任务'}
            </p>
          </div>
        </TooltipContent>
      </Tooltip>
    </div>
  );
}
