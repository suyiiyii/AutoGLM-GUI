import React from 'react';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { Minus, Plus, Maximize } from 'lucide-react';
import { useTranslation } from '../lib/i18n-context';

export type WidthPreset = 'compact' | 'standard' | 'wide' | 'auto';

interface WidthControlProps {
  currentWidth: number | 'auto';
  onWidthChange: (width: number | 'auto') => void;
}

const WIDTH_PRESETS: Record<WidthPreset, number | 'auto'> = {
  compact: 320,
  standard: 400,
  wide: 480,
  auto: 'auto',
};

export function WidthControl({
  currentWidth,
  onWidthChange,
}: WidthControlProps) {
  const t = useTranslation();

  const handlePresetClick = (preset: WidthPreset) => {
    onWidthChange(WIDTH_PRESETS[preset]);
  };

  const handleDecrease = () => {
    if (typeof currentWidth !== 'number') return;
    const newWidth = Math.max(240, currentWidth - 40);
    onWidthChange(newWidth);
  };

  const handleIncrease = () => {
    if (typeof currentWidth !== 'number') return;
    const newWidth = Math.min(640, currentWidth + 40);
    onWidthChange(newWidth);
  };

  return (
    <div className="flex items-center gap-1 bg-popover/90 backdrop-blur rounded-xl p-1 shadow-lg border border-border">
      {/* Decrease button */}
      {typeof currentWidth === 'number' && (
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleDecrease}
              className="h-7 w-7 p-0 rounded-lg"
              disabled={currentWidth <= 240}
            >
              <Minus className="w-3 h-3" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            <p>{t.deviceMonitor?.decreaseWidth || 'Decrease width'}</p>
          </TooltipContent>
        </Tooltip>
      )}

      {/* Preset buttons */}
      <Button
        variant="ghost"
        size="sm"
        onClick={() => handlePresetClick('compact')}
        className={`h-7 px-2 text-xs rounded-lg transition-colors ${
          currentWidth === 320
            ? 'bg-primary text-primary-foreground'
            : 'text-foreground hover:bg-accent hover:text-accent-foreground'
        }`}
      >
        {t.deviceMonitor?.compact || 'Compact'}
      </Button>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => handlePresetClick('standard')}
        className={`h-7 px-2 text-xs rounded-lg transition-colors ${
          currentWidth === 400
            ? 'bg-primary text-primary-foreground'
            : 'text-foreground hover:bg-accent hover:text-accent-foreground'
        }`}
      >
        {t.deviceMonitor?.standard || 'Standard'}
      </Button>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => handlePresetClick('wide')}
        className={`h-7 px-2 text-xs rounded-lg transition-colors ${
          currentWidth === 480
            ? 'bg-primary text-primary-foreground'
            : 'text-foreground hover:bg-accent hover:text-accent-foreground'
        }`}
      >
        {t.deviceMonitor?.wide || 'Wide'}
      </Button>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => handlePresetClick('auto')}
        className={`h-7 px-2 text-xs rounded-lg transition-colors ${
          currentWidth === 'auto'
            ? 'bg-primary text-primary-foreground'
            : 'text-foreground hover:bg-accent hover:text-accent-foreground'
        }`}
      >
        <Maximize className="w-3 h-3 mr-1" />
        {t.deviceMonitor?.auto || 'Auto'}
      </Button>

      {/* Increase button */}
      {typeof currentWidth === 'number' && (
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleIncrease}
              className="h-7 w-7 p-0 rounded-lg"
              disabled={currentWidth >= 640}
            >
              <Plus className="w-3 h-3" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            <p>{t.deviceMonitor?.increaseWidth || 'Increase width'}</p>
          </TooltipContent>
        </Tooltip>
      )}
    </div>
  );
}
