# SSE vs WebSocket 选型文档

> 服务端需要把数据实时推送到浏览器时，两种主流方案的选择。
> 本文结合本仓库 [sse-markdorm](../project/sse-markdorm)（LLM 流式渲染）的实际实现给出判断。

---

## 1. TL;DR

| 一句话结论 | |
|---|---|
| **绝大多数「服务端 → 客户端」单向推送，选 SSE** | 实现简单、基于 HTTP、穿透代理/防火墙无障碍、可复用 HTTP 鉴权与状态码语义 |
| **需要「客户端 ↔ 服务端」高频双向通信，才选 WebSocket** | 全双工、低延迟、可传二进制，代价是自己实现重连/心跳/鉴权/协议语义 |
| **LLM 流式输出，几乎一定选 SSE** | OpenAI / Anthropic / DeepSeek 的流式 API 本身就是 `text/event-stream`，SSE 是事实标准 |

**最快决策**：只需服务端推、客户端只发一次请求 → **SSE**；客户端要持续发消息、或双方都要高频推 → **WebSocket**。

---

## 2. 两种技术是什么

### 2.1 SSE（Server-Sent Events）

- **本质**：一次**长连接的 HTTP 响应**，`Content-Type: text/event-stream`，服务端持续写出以 `\n\n` 分隔的事件块。
- **方向**：**单向**（服务端 → 客户端）。客户端想发数据，得另外发普通 HTTP 请求。
- **数据格式**：纯文本，约定 `data: <payload>\n\n`，可带 `event:` / `id:` / `retry:` 字段。
- **二进制**：不原生支持（需 base64 编码，通常用 SSE 传文本/JSON）。
- **浏览器 API**：两种用法——
  - 原生 `EventSource`（简单，但**只能 GET、不能自定义请求头/带 body、内置自动重连**）；
  - `fetch` + `ReadableStream` 手动解析（**支持 POST / 自定义头 / body**，重连要自己写）。
- **重连**：`EventSource` 自动重连，并通过 `Last-Event-ID` 请求头告诉服务端从哪续；`fetch` 方案需自行实现。

### 2.2 WebSocket

- **本质**：先借 HTTP 做一次 `Upgrade` 握手，随后**切换为独立的 ws/wss 双工协议**，不再走 HTTP 语义。
- **方向**：**全双工双向**，两端随时互发。
- **数据格式**：文本帧或二进制帧均可。
- **浏览器 API**：原生 `WebSocket`。
- **重连 / 心跳**：协议不提供，需应用层自行实现（ping/pong 保活 + 指数退避重连）。
- **鉴权**：没有 HTTP 状态码那一套，通常在握手 URL 带 token，或握手后第一帧做鉴权。

---

## 3. 核心对比

| 维度 | SSE | WebSocket |
|---|---|---|
| 通信方向 | 单向（S→C） | 全双工（C↔S） |
| 底层协议 | HTTP（长响应） | 独立协议（HTTP 升级后） |
| 数据格式 | 文本（`data:` 文本/JSON） | 文本 + 二进制 |
| 二进制 | ❌ 需 base64 | ✅ 原生 |
| 浏览器内置自动重连 | ✅（仅 `EventSource`） | ❌ 需自行实现 |
| 断点续传 | ✅ `Last-Event-ID` 头 | ❌ 需自行设计 |
| 鉴权 | 复用 HTTP（Cookie / Header / 状态码） | 握手 URL token 或首帧鉴权 |
| HTTP 状态码语义 | ✅ 流前错误可返回 401/429/504 等 | ❌ 握手后无状态码概念 |
| 代理 / 防火墙穿透 | ✅ 就是 HTTP，几乎无障碍 | ⚠️ 部分代理会拦截 `Upgrade` |
| HTTP/2 友好度 | ✅ 原生（每路一个 stream） | ⚠️ 需走 h2 的 WebSocket 扩展（RFC 8441），支持不普遍 |
| 连接数限制（HTTP/1.1） | ⚠️ 浏览器同域 ~6 条 | ✅ 不受此限 |
| 服务端实现成本 | 低（一个流式响应） | 中（需 WS 服务、连接管理） |
| 客户端实现成本 | 低（`EventSource`）/ 中（`fetch` 手解析） | 中（重连/心跳/消息分发） |
| 典型库支持 | 各 Web 框架内置流式响应 | 各框架内置 WS / Socket.IO 等 |

> **关于连接数限制**：老资料常说「SSE 受 HTTP/1.1 每域 6 连接限制」。这在 **HTTP/2 下不成立**——每个 SSE 在 H2 里只是一个 stream，可并发很多路。现代部署（H2 普及）这个顾虑已基本消除。

---

## 4. 关键概念澄清（最容易踩的坑）

### 4.1 SSE 协议 ≠ `EventSource` API

这是混淆最多的一点：

- **SSE 是一个传输协议**（`text/event-stream` 的长连接 HTTP 响应）。
- **`EventSource` 是浏览器内置的一种 SSE 客户端实现**，它加了三个限制：**只能 GET、不能设自定义请求头、不能带 body**。

一旦你需要 **POST 请求体**（比如把多轮对话历史发给 LLM）或**自定义头**，就必须**放弃 `EventSource`，改用 `fetch` + `ReadableStream` 手动解析**。

> 本仓库 [sse-markdorm](../project/sse-markdorm/frontend/src/lib/sse.ts) 正是后者——它要把消息历史以 JSON body POST 给 `/api/chat/stream`，所以用 `fetch` 手解析，而不是 `new EventSource()`。

### 4.2 SSE 的「行」可能被网络层拆碎

一条 `data: {...}\n\n` 在传输时**可能被拆到两次甚至多次网络 read 里**。正确做法是**维护一个行缓冲（buffer）**：每次 read 追加到 buffer，只取出以 `\n` 结尾的完整行处理，残行留到下次拼接。直接「拿到 chunk 就 split('\n') 并 JSON.parse」会在数据量大时偶发解析失败。

> 见 [sse.ts](../project/sse-markdorm/frontend/src/lib/sse.ts) 的 `buffer += decoder.decode(...)` 与「只处理完整行」循环。

### 4.3 反向代理会缓冲你的流

nginx 等默认会**缓冲**响应体再整批发给客户端，这会让 SSE 的「逐字」退化成「攒一批才发」。必须显式禁用：

- 响应头 `X-Accel-Buffering: no`（nginx 专用）；
- `Cache-Control: no-cache`；
- `Connection: keep-alive`。

> 见 [chat.py](../project/sse-markdorm/backend/app/routes/chat.py) 的 `_SSE_HEADERS`。

### 4.4 错误分两层：HTTP 状态码 vs 流内事件

SSE 的错误处理天然分两层，要刻意设计：

- **流启动前的错误**（鉴权失败、限流、连不上 LLM、超时）：**进入流之前**抛出，映射成标准 HTTP 状态码（401/429/502/504），前端走 `!resp.ok` 分支。
- **流中途的错误**（生成到一半 LLM 报错）：已经 200 开始流式了，只能**把错误作为一条 SSE 事件** `data: {"error": ...}` 下发，前端在 `onError` 里处理。

> 见 [chat.py](../project/sse-markdorm/backend/app/routes/chat.py)：预检阶段返回 JSONResponse + 状态码；`_stream_sse` 内部用 `try/except` 把异常转成 SSE error 事件。

---

## 5. 选型决策框架

```
                需要服务端实时推数据给客户端？
                          │
              ┌──── 否 ────┴──── 是 ────┐
        普通 HTTP 轮询/响应               │
                          客户端需要频繁向服务端发消息？
                          │
                ┌── 否 ──┴── 是 ──┐
                │                  │
            单向推送            双向高频
            ★ 选 SSE           ★ 选 WebSocket
```

**倾向 SSE 的信号**：
- LLM / RAG 流式输出、Token 逐字下发
- 通知、消息提醒、状态变更推送
- 行情、日志尾随、构建进度、部署状态
- 任何「客户端发起一次请求，服务端持续回吐结果」的模式

**倾向 WebSocket 的信号**：
- 多人协作编辑、共享白板、实时位置
- 多人游戏、需要低延迟双向指令
- 客户端要持续高频上报（传感器、遥测）
- 需要二进制流（音视频、文件分片）

---

## 6. 典型场景对照

| 场景 | 推荐 | 理由 |
|---|---|---|
| ChatGPT 式流式回答 | **SSE** | 单向、复用 HTTP、与 LLM API 的 `text/event-stream` 一致 |
| 股票/币价行情 | **SSE** | 服务端单向广播，SSE 足够且更简单 |
| 系统通知 / Webhook 回显 | **SSE** | 低频单向推送 |
| 多人在线协作文档 | WebSocket | 双向高频，双方都在改 |
| 多人实时游戏 | WebSocket | 低延迟双向 + 二进制 |
| 直播弹幕 / 聊天室 | WebSocket（或 SSE 下发 + HTTP 上行） | 用户双向互动密集 |
| 日志/构建流水线 tail | **SSE** | 单向流 |
| IoT 遥测上报 | WebSocket / MQTT | 客户端持续上报 |

---

## 7. 本项目案例：sse-markdorm 为什么选 SSE

[sse-markdorm](../project/sse-markdorm) 是「自然语言提问 → 后端调 LLM → 前端逐字流式渲染 Markdown 表格」的应用。选型判断如下。

**为什么选 SSE**：
1. **通信本质是单向**——客户端发一次提问，服务端持续回吐 token，客户端无需在生成过程中再发消息。SSE 的单向模型天然契合。
2. **基于 HTTP，穿透简单**——就是普通 HTTP 响应，开发期 Vite proxy、生产期反向代理都无需特殊配置（WebSocket 的 `Upgrade` 偶尔被代理拦截）。
3. **服务端实现成本极低**——FastAPI 的 `StreamingResponse(..., media_type="text/event-stream")` 一行搞定，直接把 LLM 的异步迭代器转成 SSE。
4. **复用 HTTP 语义**——鉴权失败可返回 401、限流 429、超时 504，前端用熟悉的 `resp.ok` / 状态码分支处理，无需另设协议层。
5. **与 LLM API 对齐**——DeepSeek / OpenAI 的 SDK 流式本身就是事件流，后端只是「转封装」而非「转协议」。

**为什么用 `fetch` 而不是 `EventSource`**：
- 需要把**多轮对话历史**以 JSON body **POST** 给后端，`EventSource`（仅 GET、无 body）做不到，故用 `fetch` + `ReadableStream` 手解析（见 [sse.ts](../project/sse-markdorm/frontend/src/lib/sse.ts)）。

**实现中的工程细节**（都是 SSE 实战必踩的点）：
- 行缓冲防拆包；`X-Accel-Buffering: no` 禁代理缓冲；错误分 HTTP / SSE 两层；
- 客户端 60s 无数据超时（`AbortController`）+ `requestAnimationFrame` 节流（把「每 token 一次重渲染」降为「每帧一次」）；
- 用 `signal.aborted` 而非 `err.name === 'AbortError'` 判断中断（跨环境更稳）。

> 详见 [sse-markdorm/README.md](../project/sse-markdorm/README.md) 的「关键技术点」一节。

---

## 8. 代码示例（最小可用）

### 8.1 SSE

**服务端（FastAPI）**——对应 [chat.py](../project/sse-markdorm/backend/app/routes/chat.py) 的简化版：

```python
import json
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

app = FastAPI()

async def event_stream():
    for word in ["Hello", " ", "World"]:
        yield f"data: {json.dumps({'content': word})}\n\n"
    yield "data: [DONE]\n\n"

@app.post("/stream")
def stream():
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # 禁用 nginx 缓冲，token 即时下发
            "Connection": "keep-alive",
        },
    )
```

**客户端 A：`EventSource`（仅 GET、无需 body 的简单场景）**

```ts
const es = new EventSource("/stream?topic=foo");  // 只能 GET
es.onmessage = (e) => {
  if (e.data === "[DONE]") { es.close(); return; }
  console.log(JSON.parse(e.data));
};
es.onerror = () => { /* EventSource 会自动重连 */ };
```

**客户端 B：`fetch` 手解析（需 POST / 自定义头，本项目采用）**

```ts
async function streamPost(messages: unknown[]) {
  const resp = await fetch("/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages }),
  });
  const reader = resp.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let nl = buffer.indexOf("\n");
    while (nl >= 0) {                       // 只处理完整行，残行留 buffer
      const line = buffer.slice(0, nl).trim();
      buffer = buffer.slice(nl + 1);
      nl = buffer.indexOf("\n");
      if (!line.startsWith("data:")) continue;
      const data = line.slice(5).trim();
      if (data === "[DONE]") return;
      console.log(JSON.parse(data));
    }
  }
}
```

### 8.2 WebSocket

**服务端（FastAPI / Starlette）**：

```python
from fastapi import FastAPI, WebSocket

app = FastAPI()

@app.websocket("/ws")
async def ws(endpoint: WebSocket):
    await endpoint.accept()
    try:
        while True:
            msg = await endpoint.receive_text()      # 收（双向）
            await endpoint.send_text(f"echo: {msg}")  # 发
    except Exception:
        await endpoint.close()
```

**客户端**：

```ts
const ws = new WebSocket("wss://host/ws");
ws.onopen = () => ws.send("hello");
ws.onmessage = (e) => console.log(e.data);
ws.onclose = () => { /* 需自行实现指数退避重连 */ };
// 心跳：定时 ws.send("ping")，服务端 pong 或用协议级 ping/pong
```

> 同样是「echo」，WebSocket 两端代码量与 SSE 接近，但一旦涉及**重连、心跳、鉴权、消息路由、断线补偿**，WebSocket 的应用层工作量会明显超过 SSE。

---

## 9. 常见陷阱与对策

| 陷阱 | 对策 |
|---|---|
| `EventSource` 无法 POST / 带自定义头 | 改用 `fetch` + `ReadableStream` 手解析 |
| 一条 SSE 事件被拆到多次 read | 维护行缓冲，只处理以 `\n` 结尾的完整行 |
| 反向代理缓冲导致「批量到达」 | 响应头 `X-Accel-Buffering: no` + `Cache-Control: no-cache` |
| HTTP/1.1 同域连接数上限（~6） | 部署 HTTP/2；或域名分片 |
| 连接闲置被中间网络断开 | SSE：定期发注释行心跳 `: ping\n\n`；WebSocket：ping/pong |
| 重连风暴 | 指数退避 + 抖动；`EventSource` 用 `retry:` 字段调间隔 |
| 流中途报错无法用状态码 | 设计 SSE 错误事件（`{"error": ..., "code": ...}`），前端 `onError` 处理 |
| 中断判断在 Safari 上不是 `AbortError` | 用 `signal.aborted` 判断，而非 `err.name` |
| 高频 token 撑爆 React 重渲染 | `requestAnimationFrame` 节流，每帧最多 flush 一次 |

---

## 10. 结论

- **默认偏 SSE**：它是 HTTP 的自然延伸，简单、稳、好调试，覆盖了绝大多数实时推送需求。LLM 流式场景几乎只有这一个合理选择。
- **只在真正需要双向时上 WebSocket**：当客户端也要持续高频发消息、或需要二进制 / 极低延迟时，WebSocket 的全双工能力才物有所值，且要接受重连/心跳/鉴权都要自己写。
- **别为了「实时」二字就用 WebSocket**——单向推送用 WebSocket 是过度设计；反之，协作/游戏用 SSE 会处处别扭。

> 一句话：**SSE 是「服务端说话、客户端听着」的最优解；WebSocket 是「两边都要抢话筒」时的必要解。**
