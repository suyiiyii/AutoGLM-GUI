import React from 'react';
import { Link, useMatchRoute } from '@tanstack/react-router';
import {
  MessageSquare,
  ListChecks,
  FileText,
  History,
  Clock,
  type LucideIcon,
} from 'lucide-react';
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
} from '@/components/ui/tooltip';
import { useTranslation } from '../lib/i18n-context';
import logoImage from '@/assets/logo.png';

interface NavigationItem {
  id: string;
  icon: LucideIcon;
  label: string;
  path: string;
}

interface NavigationSidebarProps {
  className?: string;
}

export function NavigationSidebar({ className }: NavigationSidebarProps) {
  const t = useTranslation();
  const matchRoute = useMatchRoute();

  const navigationItems: NavigationItem[] = [
    {
      id: 'chat',
      icon: MessageSquare,
      label: t.navigation.chat,
      path: '/chat',
    },
    {
      id: 'workflows',
      icon: ListChecks,
      label: t.navigation.workflows,
      path: '/workflows',
    },
    {
      id: 'history',
      icon: History,
      label: t.navigation.history || '历史记录',
      path: '/history',
    },
    {
      id: 'scheduled-tasks',
      icon: Clock,
      label: t.navigation.scheduledTasks || '定时任务',
      path: '/scheduled-tasks',
    },
    {
      id: 'logs',
      icon: FileText,
      label: t.navigation.logs,
      path: '/logs',
    },
  ];

  return (
    <nav
      className={`w-16 h-full flex flex-col bg-white dark:bg-slate-950 border-r border-slate-200 dark:border-slate-800 ${className || ''}`}
    >
      <div className="flex flex-col items-center py-4 gap-2">
        {/* Logo at top - clickable to navigate to /chat */}
        <div className="mb-4 pb-4 border-b border-slate-200 dark:border-slate-800 w-full flex justify-center">
          <Tooltip>
            <TooltipTrigger asChild>
              <Link to="/chat" className="block">
                <img
                  src={logoImage}
                  alt="AutoGLM Logo"
                  className="w-10 h-10 object-contain cursor-pointer hover:opacity-80 transition-opacity"
                />
              </Link>
            </TooltipTrigger>
            <TooltipContent side="right" sideOffset={8}>
              返回首页
            </TooltipContent>
          </Tooltip>
        </div>

        {/* Navigation items */}
        {navigationItems.map(item => {
          const Icon = item.icon;
          const isActive = matchRoute({ to: item.path });

          return (
            <Tooltip key={item.id}>
              <TooltipTrigger asChild>
                <Link
                  to={item.path}
                  className={`w-10 h-10 rounded-lg transition-all flex items-center justify-center ${
                    isActive
                      ? 'bg-[#1d9bf0]/10 text-[#1d9bf0] hover:bg-[#1d9bf0]/20'
                      : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'
                  }`}
                >
                  <Icon className="w-5 h-5" />
                </Link>
              </TooltipTrigger>
              <TooltipContent side="right" sideOffset={8}>
                {item.label}
              </TooltipContent>
            </Tooltip>
          );
        })}
      </div>
    </nav>
  );
}
