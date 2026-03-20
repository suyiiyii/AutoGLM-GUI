import * as React from 'react';
import { X, ZoomIn } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  Dialog,
  DialogContent,
  DialogOverlay,
  DialogPortal,
  DialogClose,
} from '@/components/ui/dialog';

interface ImagePreviewProps {
  /** 图片源（支持 base64 data URI 或普通 URL） */
  src: string;
  /** 图片描述文字 */
  alt: string;
  /** 缩略图容器样式 */
  className?: string;
  /** 缩略图 img 元素样式 */
  thumbnailClassName?: string;
  /** 缩略图最大高度 */
  maxHeight?: string;
  /** 叠加层内容（如点击位置指示器） */
  children?: React.ReactNode;
}

/**
 * 可点击预览的图片组件
 * - 点击缩略图打开全屏预览
 * - 支持 ESC 键关闭
 * - 支持点击背景关闭
 * - 支持 children 渲染叠加层
 */
export function ImagePreview({
  src,
  alt,
  className,
  thumbnailClassName,
  maxHeight = '350px',
  children,
}: ImagePreviewProps) {
  const [isOpen, setIsOpen] = React.useState(false);

  return (
    <>
      {/* 缩略图 */}
      <div
        className={cn(
          'relative inline-block border border-slate-200 dark:border-slate-700 rounded overflow-hidden shadow-sm cursor-pointer group',
          className
        )}
        onClick={() => setIsOpen(true)}
      >
        <img
          src={src}
          alt={alt}
          style={{ maxHeight }}
          className={cn('w-auto block object-contain', thumbnailClassName)}
        />
        {/* 叠加层（如点击位置指示器） */}
        {children}
        {/* Hover 放大图标 */}
        <div className="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors flex items-center justify-center pointer-events-none">
          <ZoomIn className="w-6 h-6 text-white opacity-0 group-hover:opacity-100 transition-opacity drop-shadow-md" />
        </div>
      </div>

      {/* 全屏预览 */}
      <Dialog open={isOpen} onOpenChange={setIsOpen}>
        <DialogPortal>
          <DialogOverlay className="bg-black/80" />
          <DialogContent
            className="max-w-[95vw] max-h-[95vh] w-auto h-auto p-0 bg-transparent border-0 shadow-none"
            onPointerDownOutside={() => setIsOpen(false)}
          >
            <DialogClose className="fixed right-4 top-4 z-50 rounded-full bg-black/50 p-2 text-white/80 hover:text-white hover:bg-black/70 transition-colors">
              <X className="h-5 w-5" />
              <span className="sr-only">Close</span>
            </DialogClose>
            <img
              src={src}
              alt={alt}
              className="max-w-[95vw] max-h-[95vh] object-contain rounded-lg"
            />
          </DialogContent>
        </DialogPortal>
      </Dialog>
    </>
  );
}
