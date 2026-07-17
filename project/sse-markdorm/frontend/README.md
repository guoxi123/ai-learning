# Frontend — React + Vite + TypeScript

LLM Markdown 表格流式渲染器的前端。

## 启动

```bash
pnpm install
pnpm dev   # http://localhost:5173
```

开发期 `/api/*` 经 Vite proxy 转发到 `http://localhost:8000`（见 `vite.config.ts`），前端同源访问、无 CORS。需先启动后端（见 `../backend`）。

## 关键实现

- `src/lib/sse.ts` — **跨 read 行缓冲**的 SSE 解析。一条 `data:{...}` 行可能被拆到两次网络读里，这里把每次解码内容追加到 buffer，只处理以换行结尾的完整行，残行留到下次拼，避免 `JSON.parse` 失败。
- `src/hooks/useStreamChat.ts` — 消息状态、流式 fetch、`AbortController` 停止、60s 无数据超时、断线重试、多轮上下文拼接。
- `src/components/Markdown.tsx` — `react-markdown + remark-gfm` 渲染；流式时用 **remend** 修补未完成的 markdown 块（表格分隔行未到达、未闭合的代码围栏 / 加粗等），避免管道语法裸露（FOIM）。
- `src/components/MessageList.tsx` — 智能滚动跟随：仅当用户处于「近底部」时自动跟随，手动上滚浏览历史时不抢滚动。
- `src/index.css` — `table-layout: fixed` 防抖、三种对齐（remark-gfm 的 `:---:` 等输出内联 `text-align` 自动生效）、`overflow-wrap / word-break` 中英文不断串、明暗主题令牌（CSS 变量 + Tailwind `darkMode: 'class'`）。

## 依赖

`react-markdown` · `remark-gfm` · `remend` · `tailwindcss` v4（`@tailwindcss/vite`）

## 构建

```bash
pnpm build   # tsc -b && vite build
```
