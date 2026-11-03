export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

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
  title: string;
  finalized: boolean;
  overview?: Overview | null;
  participants?: string[];
  duration?: number | null;
  /** Seconds left, estimated from this machine's measured speed; null when unknown. */
  eta_sec?: number | null;
};
export type Overview = {
  duration: number;
  speakers: number;
  unnamed_speakers: number;
  decisions: number;
  actions: number;
  actions_done: number;
  to_review: number;
  has_minutes: boolean;
  summary_stale: boolean;
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
  backchannel?: boolean;
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
  done?: boolean;
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
  title: string;
  finalized: boolean;
  review_turn_ids: string[];
  participants?: string[];
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

export const jsonBody = (body: unknown, method = "PATCH"): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});
export const date = (created: number) =>
  new Date(created * 1000).toLocaleDateString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
export function duration(seconds: number) {
  const minutes = Math.round(seconds / 60);
  return minutes < 1 ? `${Math.round(seconds)} giây` : `${minutes} phút`;
}
/** Stable speaker order (first appearance) drives the speaker colour. */
export function speakerOrder(turns: Turn[]) {
  return [...new Set(turns.map(speakerId))];
}
export const speakerClass = (order: string[], id: string) =>
  `sp${Math.max(0, order.indexOf(id)) % 8}`;
const NOT_NAMES = new Set(
  (
    "ấy ơi à ạ nhé nhá thì là có không cũng nói làm gửi đã sẽ ta mình hay và với cho này kia đó " +
    "nghĩ thấy biết muốn phải xem hỏi hiểu cần đi thích nhầm tạo thằng ấy bảo đang vẫn chưa"
  ).split(" "),
);
/** Names called out in the meeting ("anh Thắng", "chị Phương"): naming hints, never labels.
 *  ASR text is lower case, so a word counts only if it mostly follows a form of address;
 *  "em" is left out because it is also "I" ("em nghĩ"). */
export function mentionedNames(turns: Turn[]) {
  const after = new Map<string, number>();
  const total = new Map<string, number>();
  const kin = new Set("anh chị bạn cô thầy ông bà".split(" "));
  for (const turn of turns) {
    const words = turn.text
      .toLocaleLowerCase("vi")
      .split(/[^\p{L}]+/u)
      .filter(Boolean);
    words.forEach((word, i) => {
      total.set(word, (total.get(word) || 0) + 1);
      if (i && kin.has(words[i - 1]) && word.length > 1 && !NOT_NAMES.has(word))
        after.set(word, (after.get(word) || 0) + 1);
    });
  }
  return [...after]
    .filter(([w, n]) => n >= 2 && n / (total.get(w) || n) >= 0.6)
    .sort((a, b) => b[1] - a[1])
    .map(([w]) => w[0].toLocaleUpperCase("vi") + w.slice(1));
}
/** Minutes items (decisions and actions) citing a turn, for review context. */
export function claimsFor(minutes: Minutes, turnId: string) {
  return [
    ...(minutes.decisions || []).map((d) => ({
      kind: "Quyết định",
      text: d.text,
      ids: d.source_turn_ids,
    })),
    ...minutes.action_items.map((a) => ({
      kind: "Việc cần làm",
      text: a.task,
      ids: a.source_turn_ids,
    })),
    ...(minutes.summary_points || []).map((p) => ({
      kind: "Tóm tắt",
      text: p.text,
      ids: p.source_turn_ids,
    })),
  ].filter((c) => c.ids?.includes(turnId));
}

export function eta(seconds?: number | null) {
  if (seconds === null || seconds === undefined) return null;
  if (seconds < 45) return "sắp xong";
  return `còn khoảng ${Math.ceil(seconds / 60)} phút`;
}
/** Plain-text action list to paste into chat or email. */
export function actionListText(view: ResultView) {
  const items = view.edited.action_items;
  if (!items.length) return `${view.title}: không có việc cần làm.`;
  return [
    `Việc cần làm — ${view.title}`,
    ...items.map(
      (a) =>
        `${a.done ? "☑" : "☐"} ${a.task}` +
        ` — ${a.speaker || "chưa rõ người làm"}` +
        (a.deadline ? ` — hạn: ${a.deadline}` : ""),
    ),
  ].join("\n");
}
/** Ask once, from a user action, so the browser can tell when a long job finishes. */
export function askNotifyPermission() {
  if ("Notification" in window && Notification.permission === "default")
    void Notification.requestPermission();
}
export function notifyDone(title: string, ok: boolean) {
  if (!("Notification" in window) || Notification.permission !== "granted")
    return;
  if (!document.hidden) return;
  new Notification(ok ? "Đã xử lý xong" : "Xử lý chưa thành công", {
    body: title,
  });
}
