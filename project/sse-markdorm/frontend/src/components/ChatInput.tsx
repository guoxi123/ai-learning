import { useState, type KeyboardEvent } from "react";

interface Props {
  onSend: (text: string) => void;
  onStop: () => void;
  onNewChat: () => void;
  isStreaming: boolean;
}

export function ChatInput({ onSend, onStop, onNewChat, isStreaming }: Props) {
  const [text, setText] = useState("");

  const submit = () => {
    const t = text.trim();
    if (!t || isStreaming) return;
    onSend(t);
    setText("");
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="border-t border-[var(--border)] bg-[var(--background)] p-3">
      <div className="flex items-end gap-2">
        <button
          onClick={onNewChat}
          className="shrink-0 rounded-lg border border-[var(--border)] px-3 py-2 text-sm transition hover:bg-[var(--muted)]"
          title="新建对话（清空历史）"
        >
          新建
        </button>

        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          rows={2}
          placeholder="输入问题，Enter 发送 · Shift+Enter 换行"
          className="max-h-40 flex-1 resize-none rounded-lg border border-[var(--border)] bg-[var(--card)] px-3 py-2 text-[15px] outline-none focus:border-[var(--primary)]"
        />

        {isStreaming ? (
          <button
            onClick={onStop}
            className="shrink-0 rounded-lg bg-red-500 px-4 py-2 text-sm text-white transition hover:bg-red-600"
          >
            停止
          </button>
        ) : (
          <button
            onClick={submit}
            disabled={!text.trim()}
            className="shrink-0 rounded-lg bg-[var(--primary)] px-4 py-2 text-sm text-[var(--primary-foreground)] transition hover:opacity-90 disabled:opacity-40"
          >
            发送
          </button>
        )}
      </div>
    </div>
  );
}
