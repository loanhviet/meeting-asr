"use client";

import { useEffect, useRef, useState } from "react";
import {
  claimsFor,
  jsonBody,
  request,
  ResultView,
  speakerClass,
  speakerId,
  speakerOrder,
  time,
} from "@/lib/api";
import { Icon } from "./Icon";
import type { Playback } from "./MeetingApp";

type Result = "ok" | "edit" | "skip";

export function ReviewMode({
  jobId,
  view,
  playback,
  llmEnabled,
  onView,
  onError,
  onDone,
  onQueued,
}: {
  jobId: string;
  view: ResultView;
  playback: Playback;
  llmEnabled: boolean;
  onView: (view: ResultView) => void;
  onError: (error: string) => void;
  onDone: () => void;
  onQueued: () => void;
}) {
  // Freeze the queue on entry: reviewing a turn removes it from review_turn_ids.
  const [queue] = useState(() =>
    view.edited.turns
      .filter((t) => view.review_turn_ids.includes(t.turn_id))
      .map((t) => t.turn_id),
  );
  const [index, setIndex] = useState(0);
  const [results, setResults] = useState<Result[]>([]);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const turns = view.edited.turns;
  const order = speakerOrder(turns);
  const turn = turns.find((t) => t.turn_id === queue[index]);
  const at = turn ? turns.indexOf(turn) : -1;
  const before = turns
    .slice(0, Math.max(0, at))
    .filter((t) => !t.backchannel)
    .at(-1);
  const after = turns.slice(at + 1).find((t) => !t.backchannel);
  const claims = turn ? claimsFor(view.edited, turn.turn_id) : [];
  const finished = index >= queue.length;
  const clip = turn
    ? { from: Math.max(0, turn.start - 1), to: turn.end + 1 }
    : null;
  const progress = clip
    ? Math.min(
        1,
        Math.max(0, (playback.position - clip.from) / (clip.to - clip.from)),
      )
    : 0;

  useEffect(() => {
    if (clip) playback.play(clip.from, clip.to);
    // Replay only when moving to another item.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [index]);

  async function decide(result: Result) {
    if (!turn || saving) return;
    if (result !== "skip") {
      setSaving(true);
      try {
        onView(
          await request<ResultView>(
            `/api/jobs/${jobId}/turns/${turn.turn_id}`,
            jsonBody({
              text: result === "edit" ? draft : turn.text,
              speaker_id: speakerId(turn),
              reviewed: true,
              expected_revision: view.revision,
            }),
          ),
        );
      } catch (err) {
        onError(err instanceof Error ? err.message : "Chưa lưu được.");
        setSaving(false);
        return;
      }
      setSaving(false);
    }
    setResults((r) => [...r, result]);
    setEditing(false);
    setIndex((i) => i + 1);
  }
  function startEdit() {
    if (!turn) return;
    setDraft(turn.text);
    setEditing(true);
    setTimeout(() => textarea.current?.focus(), 0);
  }
  useEffect(() => {
    function keyboard(event: KeyboardEvent) {
      if (finished || document.querySelector("dialog[open]")) return;
      const typing = (event.target as HTMLElement).closest(
        "textarea,input,select",
      );
      if (typing) {
        if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
          event.preventDefault();
          void decide("edit");
        } else if (event.key === "Escape") setEditing(false);
        return;
      }
      if ((event.target as HTMLElement).closest("button,a")) return;
      if (event.key === "Enter") {
        event.preventDefault();
        void decide("ok");
      } else if (event.key.toLowerCase() === "e") {
        event.preventDefault();
        startEdit();
      } else if (event.key === "ArrowDown") {
        event.preventDefault();
        void decide("skip");
      } else if (event.code === "Space") {
        event.preventDefault();
        if (clip) playback.play(clip.from, clip.to);
      }
    }
    window.addEventListener("keydown", keyboard);
    return () => window.removeEventListener("keydown", keyboard);
  });

  const count = (r: Result) => results.filter((x) => x === r).length;
  return (
    <div className="step review">
      <div className="review-top">
        <button className="btn ghost" onClick={onDone}>
          <Icon name="back" width="18" /> Về biên bản
        </button>
        <div className="progress-dots" aria-hidden="true">
          {queue.map((id, i) => (
            <i
              key={id}
              className={i < index ? "done" : i === index ? "now" : ""}
            />
          ))}
        </div>
        <span className="muted">
          {finished ? "Hoàn tất" : `Mục ${index + 1} / ${queue.length}`}
        </span>
      </div>

      {!queue.length && (
        <div className="review-done">
          <h1>Không có mục nào cần nghe lại</h1>
          <button className="btn primary" onClick={onDone}>
            Về biên bản
          </button>
        </div>
      )}

      {turn && !finished && (
        <div className="review-card" key={turn.turn_id}>
          {claims.length ? (
            <div className="callout warn">
              <span>
                Ảnh hưởng tới <b>{claims[0].kind.toLowerCase()}</b>: “
                {claims[0].text}”
                {claims.length > 1 && ` và ${claims.length - 1} mục khác`}
              </span>
            </div>
          ) : (
            <div className="callout warn">
              <span>
                {turn.flag_reasons.join(" · ") ||
                  "Đoạn có tín hiệu nhận dạng sai."}
              </span>
            </div>
          )}
          <div className={`clip ${speakerClass(order, speakerId(turn))}`}>
            <div className="clip-head">
              <button
                className="play"
                aria-label={playback.playing ? "Tạm dừng" : "Phát lại đoạn này"}
                onClick={() =>
                  playback.playing
                    ? playback.toggle()
                    : clip && playback.play(clip.from, clip.to)
                }
              >
                <Icon
                  name={playback.playing ? "pause" : "play"}
                  fill={playback.playing ? "none" : "currentColor"}
                  strokeWidth={playback.playing ? 2.6 : 1.7}
                />
              </button>
              <div>
                <strong className="who">
                  <i className="dot" /> {turn.speaker}
                </strong>
                <small className="muted">
                  {time(turn.start)} – {time(turn.end)} · phát kèm 1 giây trước
                  và sau
                </small>
              </div>
            </div>
            <div className="wave" aria-hidden="true">
              {Array.from({ length: 64 }, (_, k) => (
                <i
                  key={k}
                  className={k / 64 < progress ? "past" : ""}
                  style={{
                    height: `${20 + Math.abs(Math.sin(k * 1.7 + at) * 60) + (k % 7 ? 0 : 12)}%`,
                  }}
                />
              ))}
            </div>
            {before && <p className="context">… {before.text}</p>}
            {editing ? (
              <label className="edit">
                <span className="sr-only">Sửa lời nói</span>
                <textarea
                  ref={textarea}
                  value={draft}
                  rows={3}
                  maxLength={50000}
                  onChange={(e) => setDraft(e.target.value)}
                />
              </label>
            ) : (
              <p className="spoken">{turn.text}</p>
            )}
            {after && <p className="context">{after.text} …</p>}
          </div>
          <div className="review-actions">
            {editing ? (
              <>
                <button
                  className="btn primary"
                  disabled={saving}
                  onClick={() => void decide("edit")}
                >
                  Lưu và tiếp <kbd>Ctrl</kbd>
                  <kbd>Enter</kbd>
                </button>
                <button className="btn" onClick={() => setEditing(false)}>
                  Hủy <kbd>Esc</kbd>
                </button>
              </>
            ) : (
              <>
                <button
                  className="btn primary"
                  disabled={saving}
                  onClick={() => void decide("ok")}
                >
                  Đúng rồi <kbd>Enter</kbd>
                </button>
                <button className="btn" onClick={startEdit}>
                  Sửa lời <kbd>E</kbd>
                </button>
              </>
            )}
            <button
              className="btn ghost push"
              onClick={() => void decide("skip")}
            >
              Bỏ qua <kbd>↓</kbd>
            </button>
          </div>
        </div>
      )}

      {finished && !!queue.length && (
        <div className="review-done">
          <svg width="64" height="64" viewBox="0 0 64 64" aria-hidden="true">
            <circle
              className="draw"
              cx="32"
              cy="32"
              r="22"
              fill="none"
              stroke="var(--ok)"
              strokeWidth="4"
            />
            <path
              className="draw"
              d="M22 33l7 7 14-15"
              fill="none"
              stroke="var(--ok)"
              strokeWidth="4"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <h1>Đã soát xong</h1>
          <p className="muted">
            {count("ok")} đúng · {count("edit")} đã sửa · {count("skip")} bỏ qua
          </p>
          <div className="row">
            {!!count("edit") && llmEnabled && view.edited.summary && (
              <button
                className="btn primary"
                onClick={async () => {
                  try {
                    await request(
                      `/api/jobs/${jobId}/summary`,
                      jsonBody(
                        { template: view.summary_template || "project" },
                        "POST",
                      ),
                    );
                    onQueued();
                  } catch (err) {
                    onError(
                      err instanceof Error
                        ? err.message
                        : "Chưa tạo lại được biên bản.",
                    );
                  }
                  onDone();
                }}
              >
                Cập nhật biên bản theo bản sửa
              </button>
            )}
            <button
              className={`btn ${count("edit") ? "" : "primary"}`}
              onClick={onDone}
            >
              Về biên bản
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
