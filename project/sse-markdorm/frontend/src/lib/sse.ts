/**
 * SSE 解析：跨网络 read 维护行缓冲。
 *
 * 关键防坑：一条 `data: {...}` 行可能被拆到两次（甚至多次）网络读里，
 * 不能"拿到 chunk 就按 \n 切并立刻 JSON.parse"。这里把每次解码的内容
 * 追加到 buffer，只处理以换行结尾的完整行，末尾不完整的残行留到下次拼。
 */

interface SSEHandlers {
  onContent: (text: string) => void;
  onDone: () => void;
  onError?: (info: { error: string; code?: number }) => void;
}

export async function consumeSSE(
  response: Response,
  handlers: SSEHandlers,
): Promise<void> {
  if (!response.body) {
    handlers.onError?.({ error: "响应没有可读的内容流" });
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // 处理所有"完整行"（以 \n 结尾），残行留在 buffer
      let nl = buffer.indexOf("\n");
      while (nl >= 0) {
        const rawLine = buffer.slice(0, nl);
        buffer = buffer.slice(nl + 1);
        nl = buffer.indexOf("\n");

        const line = rawLine.trim();
        if (!line || !line.startsWith("data:")) continue;

        const data = line.slice(5).trim();
        if (data === "[DONE]") {
          handlers.onDone();
          return;
        }

        try {
          const parsed = JSON.parse(data) as {
            content?: string;
            error?: string;
            code?: number;
          };
          if (parsed.error) {
            handlers.onError?.({ error: parsed.error, code: parsed.code });
          } else if (typeof parsed.content === "string") {
            handlers.onContent(parsed.content);
          }
        } catch {
          // 单行 JSON 解析失败（心跳/注释等），忽略
        }
      }
    }
    // 连接自然结束但未收到 [DONE]，视为完成
    handlers.onDone();
  } finally {
    reader.releaseLock();
  }
}
