import { memo, useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remend from "remend";

interface MarkdownProps {
  content: string;
  isStreaming?: boolean;
}

function MarkdownBase({ content, isStreaming }: MarkdownProps) {
  // 流式过程中用 remend 修补未完成的 markdown 块（表格分隔行未到达、未闭合的
  // 代码围栏 / 加粗等），避免管道语法裸露造成的视觉跳变（FOIM）。
  // 完成态直接原样渲染，不引入额外改写。
  const processed = useMemo(() => {
    if (!content) return "";
    if (!isStreaming) return content;
    try {
      return remend(content);
    } catch {
      return content;
    }
  }, [content, isStreaming]);

  return (
    <div className="prose-assistant">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{processed}</ReactMarkdown>
    </div>
  );
}

/**
 * memo：多轮对话里 content 不变的旧消息不会因新消息流入而重渲染。
 */
export const Markdown = memo(MarkdownBase);
