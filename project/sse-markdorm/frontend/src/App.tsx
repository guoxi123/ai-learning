import { useEffect, useState } from "react";
import { useStreamChat } from "./hooks/useStreamChat";
import { MessageList } from "./components/MessageList";
import { ChatInput } from "./components/ChatInput";

const THEME_KEY = "table-assistant-theme";

export default function App() {
  const { messages, isStreaming, error, send, stop, retry, newChat } =
    useStreamChat();
  const [dark, setDark] = useState(false);

  // 初始化主题：localStorage > 系统偏好
  useEffect(() => {
    const saved = localStorage.getItem(THEME_KEY);
    const prefersDark = window.matchMedia(
      "(prefers-color-scheme: dark)",
    ).matches;
    setDark(saved ? saved === "dark" : prefersDark);
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    localStorage.setItem(THEME_KEY, dark ? "dark" : "light");
  }, [dark]);

  return (
    <div className="flex h-[100svh] flex-col bg-[var(--background)] text-[var(--foreground)]">
      <header className="flex items-center justify-between border-b border-[var(--border)] px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="text-xl">🤖</span>
          <h1 className="text-base font-semibold">LLM 表格助手</h1>
        </div>
        <button
          onClick={() => setDark((d) => !d)}
          className="rounded-lg border border-[var(--border)] px-2.5 py-1 text-sm transition hover:bg-[var(--muted)]"
          title="切换明暗主题"
        >
          {dark ? "🌙" : "☀️"}
        </button>
      </header>

      {error && (
        <div className="mx-4 mt-3 flex items-center justify-between gap-2 rounded-lg border border-red-400/40 bg-red-50 px-3 py-2 text-sm text-red-600 dark:bg-red-950/40 dark:text-red-300">
          <span className="break-all">⚠ {error}</span>
          <button
            onClick={retry}
            disabled={isStreaming}
            className="shrink-0 underline disabled:opacity-40"
          >
            重试
          </button>
        </div>
      )}

      <MessageList messages={messages} />

      <ChatInput
        onSend={send}
        onStop={stop}
        onNewChat={newChat}
        isStreaming={isStreaming}
      />
    </div>
  );
}
