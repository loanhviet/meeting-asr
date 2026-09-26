export const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export type Job = {
  id: string;
  filename: string;
  status: "queued" | "running" | "complete" | "failed";
  stage: string;
  progress: number;
  error: string | null;
  created: number;
  revision: number;
  summary_error: string | null;
};
export type Turn = {
  turn_id: string;
  start: number;
  end: number;
  speaker: string;
  text: string;
  confidence: number | null;
  flagged: boolean;
  flag_reasons: string[];
  reviewed: boolean;
  original_text: string;
  original_speaker: string;
};
export type Minutes = {
  audio_id: string;
  duration: number;
  num_speakers: number;
  flagged_ratio: number;
  turns: Turn[];
  summary: string | null;
  topics: string[];
  action_items: {
    speaker: string;
    task: string;
    deadline: string | null;
    uncertain: boolean;
  }[];
};
export type ResultView = {
  original: Minutes;
  edited: Minutes;
  revision: number;
  summary_stale: boolean;
  summary_error: string | null;
  speaker_names: Record<string, string>;
};

export async function request<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const response = await fetch(API + path, { cache: "no-store", ...options });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const detail =
      typeof payload.detail === "string"
        ? payload.detail
        : "Yêu cầu không thành công.";
    throw new Error(
      detail.includes("transcript changed")
        ? "Nội dung đã thay đổi ở phiên khác. Hãy tải lại trước khi lưu."
        : detail,
    );
  }
  return response.json() as Promise<T>;
}

export function time(seconds: number) {
  const value = Math.max(0, Math.floor(seconds));
  return `${Math.floor(value / 60)
    .toString()
    .padStart(2, "0")}:${(value % 60).toString().padStart(2, "0")}`;
}
