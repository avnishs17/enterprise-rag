export type MessageRole = "user" | "assistant";

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  thoughtProcess?: string[];
  sources?: string[];
}

export interface QueryRequest {
  q: string;
  thread_id: string;
}

export interface QueryResponse {
  question: string;
  answer: string;
  thought_process: string[];
  status: string;
  sources: string[];
}

export interface HealthResponse {
  status: string;
}
