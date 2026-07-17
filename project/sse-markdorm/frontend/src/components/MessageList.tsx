import { useEffect, useRef } from "react";
import type { ChatMessage } from "../types";
import { MessageItem } from "./MessageItem";

interface Props {
  messages: ChatMessage[];
}

export function MessageList({ messages }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  // 仅当用户处于"近底部"时才自动跟随，手动上滚浏览历史时不抢滚动
  const stick = useRef(true);

  const onScroll = () => {
    const el = containerRef.current;
    if (!el) return;
    const dist = el.scrollHeight - el.scrollTop - el.clientHeight;
    stick.current = dist < 80;
  };

  useEffect(() => {
    if (stick.current) {
      bottomRef.current?.scrollIntoView();
    }
  });

  if (!messages.length) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center px-6 text-center text-[var(--muted-foreground)]">
        <div className="mb-4 text-5xl">📊</div>
        <div className="mb-1 text-lg font-medium text-[var(--foreground)]">
          LLM 表格助手
        </div>
        <p className="max-w-md text-sm">
          输入包含「对比 / 汇总 / 列表」含义的问题，AI 会用 Markdown 表格流式作答。
        </p>
        <p className="mt-3 rounded-lg bg-[var(--muted)] px-3 py-1.5 text-xs">
          试试：对比北京、上海、深圳的房价和薪资
        </p>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      onScroll={onScroll}
      className="flex-1 space-y-4 overflow-y-auto px-4 py-6"
    >
      {messages.map((m) => (
        <MessageItem key={m.id} message={m} />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
