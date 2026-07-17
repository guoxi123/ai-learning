import { useCallback, useRef, useState } from "react";
import type { ApiMessage, ChatMessage } from "../types";
import { consumeSSE } from "../lib/sse";

// 开发期走 Vite proxy（/api → :8000）；生产可经 VITE_API_BASE 指向后端
const API_URL = `${import.meta.env.VITE_API_BASE ?? ""}/api/chat/stream`;
// 无数据超时：连续 60s 收不到任何 token 则自动断开
const NO_DATA_TIMEOUT = 60_000;

let idCounter = 0;
const genId = () => `m-${Date.now()}-${idCounter++}`;

const NO_DATA_REASON = "no-data-timeout";

export function useStreamChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  // 用 ref 镜像最新 messages，供 send / retry 读取历史，避免闭包陈旧
  const messagesRef = useRef<ChatMessage[]>([]);
  messagesRef.current = messages;

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setIsStreaming(false);
    setMessages((prev) => {
      if (!prev.length) return prev;
      const last = prev[prev.length - 1];
      if (last.role === "assistant" && last.streaming) {
        return [...prev.slice(0, -1), { ...last, streaming: false }];
      }
      return prev;
    });
  }, []);

  /** 发起一次流式请求，把增量写入指定 assistant 消息 */
  const sendStream = useCallback(
    async (apiMessages: ApiMessage[], assistantId: string) => {
      const controller = new AbortController();
      abortRef.current = controller;
      setIsStreaming(true);
      setError(null);

      let timer: ReturnType<typeof setTimeout> | null = null;
      const resetTimer = () => {
        if (timer) clearTimeout(timer);
        timer = setTimeout(
          () => controller.abort(NO_DATA_REASON),
          NO_DATA_TIMEOUT,
        );
      };
      resetTimer();

      const patch = (updater: (m: ChatMessage) => ChatMessage) =>
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantId ? updater(m) : m)),
        );

      // 用 requestAnimationFrame 节流：token 先累积到 pending，每帧最多 flush 一次
      // setMessages，把「每 token 一次重渲染」降到「每帧一次」，显著减少长对话 /
      // 长回答下的卡顿。60fps 仍是流畅的逐字效果，人眼无法分辨帧内批量。
      let pending = "";
      let rafId: number | null = null;
      const flushNow = () => {
        if (rafId !== null) {
          cancelAnimationFrame(rafId);
          rafId = null;
        }
        if (pending) {
          const delta = pending;
          pending = "";
          patch((m) => ({ ...m, content: m.content + delta }));
        }
      };

      try {
        const resp = await fetch(API_URL, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            messages: apiMessages,
            temperature: 0.3,
          }),
          signal: controller.signal,
        });

        if (!resp.ok) {
          let msg = `请求失败（HTTP ${resp.status}）`;
          try {
            const data = (await resp.json()) as { error?: string };
            if (data?.error) msg = data.error;
          } catch {
            /* 忽略非 JSON 错误体 */
          }
          patch((m) => ({ ...m, streaming: false, error: msg }));
          setError(msg);
          return;
        }

        await consumeSSE(resp, {
          onContent: (text) => {
            resetTimer();
            pending += text;
            if (rafId === null) {
              rafId = requestAnimationFrame(flushNow);
            }
          },
          onDone: () => {
            flushNow(); // 流结束前把残余 token 落盘，再标记完成
            patch((m) => ({ ...m, streaming: false }));
          },
          onError: ({ error: errMsg }) => {
            patch((m) => ({ ...m, streaming: false, error: errMsg }));
            setError(errMsg);
          },
        });
        patch((m) => ({ ...m, streaming: false }));
      } catch (e) {
        const err = e as Error;
        // 用 signal 状态而非 err.name 判断：某些环境下 abort 流式 fetch 抛出的
        // 异常并非 AbortError（如 TypeError "Load failed"），但 signal.aborted 必为 true。
        if (controller.signal.aborted) {
          patch((m) => ({ ...m, streaming: false }));
          if (controller.signal.reason === NO_DATA_REASON) {
            setError(
              `连续 ${NO_DATA_TIMEOUT / 1000} 秒未收到数据，已自动断开。`,
            );
          }
        } else {
          const msg = `网络错误：${err.message || "连接中断"}`;
          patch((m) => ({ ...m, streaming: false, error: msg }));
          setError(msg);
        }
      } finally {
        if (rafId !== null) cancelAnimationFrame(rafId);
        rafId = null;
        if (timer) clearTimeout(timer);
        abortRef.current = null;
        setIsStreaming(false);
      }
    },
    [],
  );

  const send = useCallback(
    async (text: string) => {
      const content = text.trim();
      if (!content || isStreaming) return;

      const userMsg: ChatMessage = { id: genId(), role: "user", content };
      const assistantMsg: ChatMessage = {
        id: genId(),
        role: "assistant",
        content: "",
        streaming: true,
      };

      // 历史对话 + 本次提问，跳过出错的消息，发给后端做多轮上下文
      const history: ApiMessage[] = [...messagesRef.current, userMsg]
        .filter((m) => m.role === "user" || m.role === "assistant")
        .filter((m) => !m.error)
        .map((m) => ({ role: m.role, content: m.content }));

      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      await sendStream(history, assistantMsg.id);
    },
    [isStreaming, sendStream],
  );

  const retry = useCallback(async () => {
    const prev = messagesRef.current;
    if (!prev.length || isStreaming) return;

    // 截到最后一条 user，丢弃其后失败/空的 assistant
    let lastUserIdx = -1;
    for (let i = prev.length - 1; i >= 0; i--) {
      if (prev[i].role === "user") {
        lastUserIdx = i;
        break;
      }
    }
    if (lastUserIdx < 0) return;

    const trimmed = prev.slice(0, lastUserIdx + 1);
    const assistantMsg: ChatMessage = {
      id: genId(),
      role: "assistant",
      content: "",
      streaming: true,
    };
    setMessages([...trimmed, assistantMsg]);

    const history: ApiMessage[] = trimmed
      .filter((m) => !m.error)
      .map((m) => ({ role: m.role, content: m.content }));

    setError(null);
    await sendStream(history, assistantMsg.id);
  }, [isStreaming, sendStream]);

  const newChat = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setMessages([]);
    setError(null);
    setIsStreaming(false);
  }, []);

  return { messages, isStreaming, error, send, stop, retry, newChat };
}
