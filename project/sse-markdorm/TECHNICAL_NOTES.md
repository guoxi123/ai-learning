# LLM Markdown 表格流式渲染器 — 技术问题与解决方案

> 本文记录本项目开发过程中遇到的真实技术问题、根因分析与解决方案，按重要性排序。每个问题统一采用「**现象 → 根因 → 方案 → 代码位置**」结构。
>
> 结论先行：本项目的难点不在「调 LLM」或「渲染一张表格」，而在**流式过程中表格的稳定性**——token 逐个到达时，如何让表格边长边渲染、不闪烁、不乱码、对齐正确。

---

## 问题总览

| # | 问题 | 核心方案 |
|---|---|---|
| 1 | 浏览器无法直连 LLM API（CORS） | 后端代理，前端同源访问 |
| 2 | 流式表格闪烁（FOIM） | remend 修补未完成的 Markdown 块 |
| 3 | SSE 消息跨网络分片被拆行 | 跨 read 维护行缓冲 |
| 4 | 表格列宽 reflow 抖动 | `table-layout: fixed` |
| 5 | 选型踩坑：Streamdown 居中对齐 bug | 切回 react-markdown + remark-gfm |
| 6 | 中英文混排撑破单元格 | `overflow-wrap` / `word-break` |
| 7 | react-markdown 全文重解析性能 | 组件 `memo` 隔离旧消息 |
| 8 | 滚动跟随「抢」用户滚动 | 「近底部」才自动跟随 |
| 9 | 流式响应的错误处理分层 | 启动期 → HTTP 状态码，中途 → SSE error |
| 10 | 超时 / 停止 / 断线重试 | AbortController + 计时器 + 历史重发 |

---

## 1. 浏览器无法直连 LLM API（CORS）

**现象**：前端用 `fetch` 直接调用 `https://api.deepseek.com/v1/chat/completions`，请求被浏览器拦截，控制台报 CORS 错误。

**根因**：OpenAI、DeepSeek、通义千问三家的 API **响应都不带 `Access-Control-Allow-Origin` 头**，出于安全考虑禁止浏览器直连（避免在前端代码里暴露调用方式）。这与「能否用 SDK 加 `dangerouslyAllowBrowser`」无关——网络层就被拦了。

**方案**：加一层后端代理。前端只请求同源的 `/api/chat/stream`，由 FastAPI 后端转发给 LLM API。这同时解决两个问题：
- CORS：前端与后端同源，不存在跨域；
- API Key 安全：Key 只存在后端 `.env`，前端代码、浏览器 Network 面板里都看不到。

开发期还用 Vite 的 `server.proxy` 把 `/api` 转发到后端端口，前端代码里写相对路径即可。

**代码位置**：
- 后端代理与 LLM 调用：[backend/app/routes/chat.py](backend/app/routes/chat.py)、[backend/app/services/llm_service.py](backend/app/services/llm_service.py)
- 前端开发代理：[frontend/vite.config.ts](frontend/vite.config.ts)

---

## 2. 流式表格闪烁（FOIM）—— 本项目最核心的难点

**现象**：LLM 逐 token 输出一个 Markdown 表格时，先到达的是 `| 城市 | 房价 |`，此时它会被当成**普通段落文本**显示（原始的 `|` 管道符裸露）；等分隔行 `| --- |` 到达后，渲染器突然把它重新解析成 `<table>`，发生明显的结构跳变和视觉闪烁。

**根因**：
- `react-markdown` 在**每个 token 到达时重新解析整个 Markdown 字符串**；
- GFM 表格语法要求「表头行 + 分隔行 `| --- |` + 数据行」结构完整才识别为表格，分隔行出现前，`| 城市 | 房价 |` 不满足表格语法，被当作普通段落。

业界把这类问题统称为 **FOIM（Flash of Incomplete Markdown）**，在多家已上线的 AI 产品中都存在。

**方案**：在把内容交给渲染器之前，先做一道「**修补未完成块**」的预处理。流式过程中调用 `remend(content)`，它会自动补全未闭合的代码围栏、未闭合的加粗 / 斜体、未完成的表格等，让残缺的 Markdown 也能被正确解析，从而避免管道语法裸露。完成态则原样渲染，不引入改写。

```tsx
const processed = useMemo(() => {
  if (!content) return "";
  if (!isStreaming) return content;      // 完成态不改写
  try { return remend(content); }        // 流式态：修补未完成块
  catch { return content; }
}, [content, isStreaming]);
```

**代码位置**：[frontend/src/components/Markdown.tsx](frontend/src/components/Markdown.tsx)

> 详见下文第 5 节：为什么没有直接用封装好此能力的 Streamdown。

---

## 3. SSE 消息跨网络分片被拆行

**现象**：照抄常见教程的「拿到一个 chunk 就按 `\n` 切分并立即 `JSON.parse`」写法，偶发 `JSON.parse` 失败、内容丢字。

**根因**：一条完整的 SSE 数据行 `data: {"content":"hello"}\n\n` 在传输时，**可能被 TCP 分片拆到两次（甚至多次）网络 `read` 里**。如果在单次 `read` 的边界上切行，切出来的可能是半行（如 `data: {"content":"hel`），`JSON.parse` 自然失败，这一段内容就丢了。

**方案**：维护一个 `buffer` 字符串，每次 `read` 解码后追加进去；只取出以 `\n` 结尾的**完整行**来处理，末尾那截不完整的残行留在 `buffer` 里等下一次 `read` 拼上来。

```ts
let buffer = "";
while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  buffer += decoder.decode(value, { stream: true });
  let nl = buffer.indexOf("\n");
  while (nl >= 0) {                 // 只处理完整行
    const line = buffer.slice(0, nl).trim();
    buffer = buffer.slice(nl + 1);  // 残行留在 buffer
    nl = buffer.indexOf("\n");
    // ...解析 data: 行
  }
}
```

**代码位置**：[frontend/src/lib/sse.ts](frontend/src/lib/sse.ts)

---

## 4. 表格列宽 reflow 抖动

**现象**：表格每多长出一行数据，所有列的宽度都在重新计算、跳动，表格整体宽度抖动，观感很不稳定。

**根因**：浏览器默认 `table-layout: auto`，列宽由**所有行的内容**共同决定。流式时数据行逐行到达，每行都可能改变列宽，于是不断触发 reflow（回流）。

**方案**：设 `table-layout: fixed`。此模式下**列宽只由第一行（表头）决定**，后续数据行到达时不再重算列宽，彻底消除抖动。

附带收益：`overflow-wrap` / `word-break` 这些换行属性，**只有在 `table-layout: fixed` 下才会对单元格内容生效**（这是第 6 节的前提）。

```css
.prose-assistant table {
  table-layout: fixed;     /* 列宽只由首行决定，后续行不 reflow */
  width: 100%;
  border-collapse: collapse;
}
```

**代码位置**：[frontend/src/index.css](frontend/src/index.css)

---

## 5. 选型踩坑：Streamdown 居中对齐 bug

**现象**：最初按调研结论选用了 Vercel 的 **Streamdown**（一个为流式而生的 react-markdown 替代库，内置未完成块修补 + 块级 memo）。但它渲染表格时，`:---:`（居中）列被显示成了**左对齐**，而 `---:`（右对齐）、`:---`（左对齐）都正确。

**排查过程**：
1. 先怀疑是后端发的分隔行写错——打印后端原始输出，确认第 5 列就是标准 `:---:`，无误；
2. 再怀疑渲染层 CSS 覆盖——读 DOM 的 `inline style`，发现表头的 `text-align` 在**解析阶段就已经是 `left`**，不是 CSS 覆盖；
3. 顺 React Fiber 往上找，读到 `node.properties.align`，发现 Streamdown 的 table 解析器把第 5 列解析成了 `'left'`；
4. 写独立脚本用标准 `remark-gfm` 解析同样的分隔行，得到 `["left","right","center"]`——**证明标准解析是 center，是 Streamdown 的 bug**。

**方案**：居中对齐是验收硬指标，果断切回 **`react-markdown + remark-gfm + remend`** 组合——`remark-gfm` 的对齐完全正确，`remend` 负责流式时修补未完成块（能力等同于 Streamdown 的卖点）。

> 教训：第三方「开箱即用」的库能省事，但对关键能力（这里是 GFM 表格对齐）一定要用真实数据跑一遍验证，不能只看 README 的宣传。

**代码位置**：选型最终落点 [frontend/src/components/Markdown.tsx](frontend/src/components/Markdown.tsx)

---

## 6. 中英文混排撑破单元格

**现象**：表格里出现长英文串、URL 或一长串不带空格的字符时，会把单元格撑破、顶乱整个表格布局。

**根因**：默认情况下，浏览器只在「空白 / 连字符」处换行，遇到不可断的长串就溢出。

**方案**：给单元格强制换行。注意这依赖第 4 节的 `table-layout: fixed`——没有它，这些换行属性对单元格常常不生效。

```css
.prose-assistant th,
.prose-assistant td {
  overflow-wrap: break-word;
  word-break: break-word;
}
```

宽表则在外层容器加 `overflow-x: auto`，让它横向滚动而不撑破消息气泡。中文与英文混排（如「北京 Beijing」）渲染后不存在错位问题——浏览器按盒模型对齐，所谓「错位」只发生在查看 Markdown **源码**时全角字符宽度为 2 导致的视觉不齐，不影响渲染结果。

**代码位置**：[frontend/src/index.css](frontend/src/index.css)

---

## 7. react-markdown 全文重解析的性能

**现象**：`react-markdown` 每来一个 token 就重新解析整段 Markdown，长内容（1000+ token）下重渲染开销明显。

**根因**：没有做内容粒度的隔离，任何一次 `messages` 状态变更都会让所有历史消息重新走一遍解析。

**方案**：用 `React.memo` 包裹消息渲染组件。多轮对话中，**content 没有变化的旧消息不会因新消息流入而重渲染**，只有正在流式生成的那条会频繁更新。对本项目的内容长度，配合 `table-layout: fixed` 已足够流畅；如果内容更长，可进一步做「按块 memo」（把 Markdown 切成稳定块，只重渲染变化的块）。

**代码位置**：[frontend/src/components/Markdown.tsx](frontend/src/components/Markdown.tsx)（`export const Markdown = memo(MarkdownBase)`）

---

## 8. 滚动跟随「抢」用户滚动

**现象**：流式时自动滚动到底部，但用户想上滚查看历史内容时，被自动滚动一次次「拉」回底部，体验很差。

**根因**：无脑地在每次更新时 `scrollIntoView`。

**方案**：记录「是否贴底」状态——只有当用户处于「近底部」（距底部 < 80px）时才自动跟随；一旦用户主动上滚，就停止跟随，把滚动控制权还给用户。

```ts
const onScroll = () => {
  const el = containerRef.current;
  if (!el) return;
  const dist = el.scrollHeight - el.scrollTop - el.clientHeight;
  stick.current = dist < 80;   // 近底部才跟随
};
```

**代码位置**：[frontend/src/components/MessageList.tsx](frontend/src/components/MessageList.tsx)

---

## 9. 流式响应的错误处理分层

**现象**：流式接口的错误来源多样——API Key 失效、限流、超时、网络中断、服务端内部错误。如果都混在一起，前端无法给出准确提示，验收要求的「Key 失效返回 401」也无法满足。

**根因**：SSE 响应一旦以 200 开始流式输出，中途的错误就不再能用普通 HTTP 状态码表达了，需要区分「流开始前」和「流进行中」两个阶段。

**方案**：分两层处理。
- **流开始前**：在进入 `StreamingResponse` 之前先发起一次连接建立（`create_stream`），把鉴权、限流、连接、超时类错误映射成标准 HTTP 状态码（401 / 429 / 502 / 504），前端走错误分支直接读取；
- **流进行中**：用统一的 SSE 生成器把中途异常包装成 `data: {"error": "...", "code": ...}` 事件下发，前端在 SSE 解析里识别 `error` 字段并提示。

```python
# 流开始前：预检连接，错误 → HTTP 状态码
try:
    stream = await llm_service.create_stream(...)
except openai.AuthenticationError:
    return JSONResponse(status_code=401, content={"error": "LLM_API_KEY 失效。"})
except openai.RateLimitError:
    return JSONResponse(status_code=429, ...)
# ...

# 流进行中：中途异常 → SSE error 事件
async def _stream_sse(source):
    try:
        async for content in source:
            yield _sse({"content": content})
        yield _sse("[DONE]")
    except openai.APITimeoutError:
        yield _sse({"error": "LLM 响应超时。", "code": 504})
    # ...
```

**代码位置**：[backend/app/routes/chat.py](backend/app/routes/chat.py)；前端识别 [frontend/src/lib/sse.ts](frontend/src/lib/sse.ts) 与 [frontend/src/hooks/useStreamChat.ts](frontend/src/hooks/useStreamChat.ts)

---

## 10. 超时 / 停止 / 断线重试

**现象**：需要支持「用户主动停止生成」「长时间无响应自动断开」「网络中断后重试」。

**方案**（全部在前端 `useStreamChat` 中实现）：
- **停止**：每个请求持有一个 `AbortController`，点「停止」时 `abort()`，`fetch` 和 `reader.read()` 会随之中断；
- **超时**：维护一个「无数据超时」计时器，每收到一个 token 就重置；连续 60s 收不到任何数据则 `abort("no-data-timeout")`，并在 `catch` 里识别该 reason 给出对应提示；
- **重试**：失败后截取到最后一条 user 消息（丢弃其后失败 / 空的 assistant），重建一条空 assistant，用历史上下文重新发起流式请求。

**代码位置**：[frontend/src/hooks/useStreamChat.ts](frontend/src/hooks/useStreamChat.ts)

---

## 附：技术栈选型对照

| 关注点 | 选型 | 理由 |
|---|---|---|
| 后端 | Python + FastAPI + uv | `StreamingResponse` + async generator 做流式 SSE 极简洁；uv 依赖管理快 |
| LLM 调用 | `openai` SDK `stream=True` | DeepSeek / OpenAI / 通义都兼容 OpenAI 的 `/chat/completions`，一套代码切换厂商 |
| 前端框架 | React 19 + Vite + TypeScript | 生态成熟、HMR 快、类型安全 |
| Markdown 渲染 | react-markdown + remark-gfm | GFM 表格对齐完全正确（见第 5 节） |
| 流式稳定 | remend | 修补未完成的 Markdown 块，避免 FOIM |
| 样式 | Tailwind v4 + CSS 变量 | 主题令牌 + `table-layout: fixed` 防抖 |
| 通信 | SSE（fetch + ReadableStream） | 比 EventSource 更可控（支持 POST、自定义 header、abort） |

---

## 小结

把上面 10 个问题归类，其实只围绕三件事：

1. **安全与连通性**（1、9）：后端代理，顺带把错误处理分层；
2. **流式表格的稳定性**（2、3、4、5、6、7）：这是本项目真正的技术含量——从 SSE 分片解析、未完成块修补、列宽防抖、对齐正确性到换行与性能，每一环都可能在流式下单独翻车；
3. **交互体验**（8、10）：滚动跟随、停止、超时、重试，让流式对话「好用」。

其中最值得记住的两条经验：一是**流式解析必须做跨 read 行缓冲**（第 3 节），这是几乎所有流式教程都省略、却必然踩的坑；二是**第三方「流式优化」库要对关键能力做实测验证**（第 5 节），不要被 README 的宣传带偏。
