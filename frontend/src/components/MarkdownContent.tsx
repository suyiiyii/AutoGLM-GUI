import ReactMarkdown from 'react-markdown';
import remarkBreaks from 'remark-breaks';
import remarkGfm from 'remark-gfm';
import type { Components } from 'react-markdown';

interface MarkdownContentProps {
  content: string;
  className?: string;
  prose?: boolean;
}

export function MarkdownContent({
  content,
  className = '',
  prose = true,
}: MarkdownContentProps) {
  const rootClassName = [
    'min-w-0 w-full max-w-full break-words',
    prose
      ? 'prose dark:prose-invert max-w-none prose-pre:text-sm prose-code:text-sm [&_ol:first-child]:mt-0 [&_ol:last-child]:mb-0 [&_p:first-child]:mt-0 [&_p:last-child]:mb-0 [&_pre:first-child]:mt-0 [&_pre:last-child]:mb-0 [&_ul:first-child]:mt-0 [&_ul:last-child]:mb-0'
      : 'whitespace-pre-wrap text-current [&_a]:text-current [&_a]:underline [&_ol]:list-decimal [&_ol]:pl-5 [&_p]:m-0 [&_strong]:text-current [&_ul]:list-disc [&_ul]:pl-5',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm, remarkBreaks]}
      className={rootClassName}
      components={
        {
          table: ({ node: _node, ...props }) => (
            <div className="my-2 min-w-0 max-w-full overflow-x-auto">
              <table {...props} />
            </div>
          ),
          pre: ({ node: _node, className, ...props }) => (
            <pre
              className={`overflow-x-auto whitespace-pre-wrap ${className ?? ''}`}
              {...props}
            />
          ),
          code: ({ node: _node, ...props }) => <code {...props} />,
        } as Components
      }
    >
      {content}
    </ReactMarkdown>
  );
}
