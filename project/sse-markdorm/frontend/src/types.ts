export type Role = "user" | "assistant";

export interface ChatMessage {
  id: string;
  role: Role;
  content: string;
  /** 该条消息生成过程中是否出错 */
  error?: string;
  /** 是否仍在流式生成 */
  streaming?: boolean;
}

/** 发给后端 /api/chat/stream 的消息格式（OpenAI 兼容） */
export interface ApiMessage {
  role: "system" | "user" | "assistant";
  content: string;
}
