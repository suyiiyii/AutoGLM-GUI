import React, { memo } from 'react';
import { Sparkles, Loader2, CheckCircle2 } from 'lucide-react';

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  steps?: number;
  success?: boolean;
  thinking?: string[];
  actions?: Record<string, unknown>[];
  isStreaming?: boolean;
  currentThinking?: string; // Current thinking text being streamed
}

interface ChatMessageProps {
  message: Message;
}

export const ChatMessage = memo(({ message }: ChatMessageProps) => {
  return (
    <div
      className={`flex ${
        message.role === 'user' ? 'justify-end' : 'justify-start'
      }`}
    >
      {message.role === 'assistant' ? (
        <div className="max-w-[85%] space-y-3">
          {/* Thinking process */}
          {message.thinking?.map((think, idx) => (
            <div
              key={idx}
              className="bg-slate-100 dark:bg-slate-800 rounded-2xl rounded-tl-sm px-4 py-3"
            >
              <div className="flex items-center gap-2 mb-2">
                <div className="flex h-6 w-6 items-center justify-center rounded-full bg-[#1d9bf0]/10">
                  <Sparkles className="h-3 w-3 text-[#1d9bf0]" />
                </div>
                <span className="text-xs font-medium text-slate-500 dark:text-slate-400">
                  Step {idx + 1}
                </span>
              </div>
              <p className="text-sm whitespace-pre-wrap text-slate-700 dark:text-slate-300">
                {think}
              </p>

              {message.actions?.[idx] && (
                <details className="mt-2 text-xs">
                  <summary className="cursor-pointer text-[#1d9bf0] hover:text-[#1a8cd8]">
                    View action
                  </summary>
                  <pre className="mt-2 p-2 bg-slate-900 text-slate-200 rounded-lg overflow-x-auto text-xs">
                    {JSON.stringify(message.actions[idx], null, 2)}
                  </pre>
                </details>
              )}
            </div>
          ))}

          {/* Current thinking being streamed */}
          {message.currentThinking && (
            <div className="bg-slate-100 dark:bg-slate-800 rounded-2xl rounded-tl-sm px-4 py-3">
              <div className="flex items-center gap-2 mb-2">
                <div className="flex h-6 w-6 items-center justify-center rounded-full bg-[#1d9bf0]/10">
                  <Sparkles className="h-3 w-3 text-[#1d9bf0] animate-pulse" />
                </div>
                <span className="text-xs font-medium text-slate-500 dark:text-slate-400">
                  Thinking...
                </span>
              </div>
              <p className="text-sm whitespace-pre-wrap text-slate-700 dark:text-slate-300">
                {message.currentThinking}
                <span className="inline-block w-1 h-4 ml-0.5 bg-[#1d9bf0] animate-pulse" />
              </p>
            </div>
          )}

          {/* Final result */}
          {message.content && (
            <div
              className={`
              rounded-2xl px-4 py-3 flex items-start gap-2
              ${
                message.success === false
                  ? 'bg-red-100 dark:bg-red-900/20 text-red-600 dark:text-red-400'
                  : 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300'
              }
            `}
            >
              <CheckCircle2
                className={`w-5 h-5 flex-shrink-0 mt-0.5 ${
                  message.success === false ? 'text-red-500' : 'text-green-500'
                }`}
              />
              <div>
                <p className="whitespace-pre-wrap">{message.content}</p>
                {message.steps !== undefined && (
                  <p className="text-xs mt-2 opacity-60 text-slate-500 dark:text-slate-400">
                    {message.steps} steps completed
                  </p>
                )}
              </div>
            </div>
          )}

          {/* Streaming indicator */}
          {message.isStreaming && (
            <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
              <Loader2 className="w-4 h-4 animate-spin" />
              Processing...
            </div>
          )}
        </div>
      ) : (
        <div className="max-w-[75%]">
          <div className="chat-bubble-user px-4 py-3">
            <p className="whitespace-pre-wrap">{message.content}</p>
          </div>
          <p className="text-xs text-slate-400 dark:text-slate-500 mt-1 text-right">
            {message.timestamp.toLocaleTimeString()}
          </p>
        </div>
      )}
    </div>
  );
});

ChatMessage.displayName = 'ChatMessage';
