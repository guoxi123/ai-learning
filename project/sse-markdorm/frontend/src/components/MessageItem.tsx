import { memo } from "react";
import type { ChatMessage } from "../types";
import { Markdown } from "./Markdown";

interface Props {
  message: ChatMessage;
}

function MessageItemBase({ message }: Props) {
  const isUser = message.role === "user";

  return (
    <div className={`flex w-full ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[88%] rounded-2xl px-4 py-3 text-[15px] leading-relaxed ${
          isUser
            ? "bg-[var(--primary)] text-[var(--primary-foreground)]"
            : "bg-[var(--card)] text-[var(--card-foreground)] border border-[var(--border)]"
        }`}
      >
        <div className="mb-1 text-xs opacity-50">
          {isUser ? "你" : "助手"}
        </div>

        {isUser ? (
          <div className="whitespace-pre-wrap break-words">{message.content}</div>
        ) : message.content ? (
          <Markdown content={message.content} isStreaming={message.streaming} />
        ) : message.streaming ? (
          // 首字到达前的"思考中"呼吸点
          <div className="flex items-center gap-1 py-1">
            {[0, 150, 300].map((d) => (
              <span
                key={d}
                className="h-2 w-2 rounded-full bg-current opacity-40 animate-bounce"
                style={{ animationDelay: `${d}ms` }}
              />
            ))}
          </div>
        ) : null}

        {message.error && (
          <div className="mt-2 border-t border-red-400/30 pt-2 text-sm text-red-500">
            ⚠ {message.error}
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * memo：流式中只有正在生成的那条 message 引用会变，其余历史消息引用不变，
 * 会被 memo 跳过、不重渲染——避免「每 token 全树 diff」在长对话下越来越慢。
 */
export const MessageItem = memo(MessageItemBase);
