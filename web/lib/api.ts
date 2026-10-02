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
  speaker_id?: string;
  text: string;
  confidence: number | null;
  flagged: boolean;
  flag_reasons: string[];
  reviewed: boolean;
  original_text: string;
  original_speaker: string;
};
export type EvidenceSource = Pick<
  Turn,
  "turn_id" | "start" | "end" | "speaker" | "flagged" | "reviewed"
>;
export type Claim = {
  text: string;
  source_turn_ids: string[];
  uncertain: boolean;
  sources?: EvidenceSource[];
  needs_review?: boolean;
  evidence_missing?: boolean;
};
export type ActionItem = Omit<Claim, "text"> & {
  speaker: string | null;
  task: string;
  deadline: string | null;
};
export type Minutes = {
  audio_id: string;
  duration: number;
  num_speakers: number;
  flagged_ratio: number;
  turns: Turn[];
  summary: string | null;
  topics: string[];
  summary_points?: Claim[];
  decisions?: Claim[];
  action_items: ActionItem[];
};
export type ResultView = {
  original: Minutes;
  edited: Minutes;
  revision: number;
  summary_stale: boolean;
  summary_error: string | null;
  speaker_names: Record<string, string>;
  summary_revision?: number | null;
  summary_template?: string;
  summary_grounded?: boolean;
};
export type EditEvent = {
  id: number;
  revision: number;
  kind: "turn_edit" | "speaker_merge";
  created: number;
  changes: {
    turn_id?: string;
    source_speaker?: string;
    target_speaker?: string;
    turn_ids?: string[];
    before?: { text: string; speaker_id: string; reviewed: boolean };
    after?: { text: string; speaker_id: string; reviewed: boolean };
    speaker_name?: { speaker_id: string; before: string; after: string };
  };
};
export type MeetingAnswer = {
  id: number;
  question: string;
  revision: number;
  created: number;
  stale: boolean;
  status: "found" | "not_found";
  answer_points: (Omit<Claim, "sources"> & {
    sources: (EvidenceSource & { text: string })[];
  })[];
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
        ? "Nội dung đã thay đổi ở phiên khác. Hãy mở lại cuộc họp trước khi gửi yêu cầu."
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
export const speakerId = (turn: Turn) =>
  turn.speaker_id || turn.original_speaker;
