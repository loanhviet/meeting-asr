"use client";

import { useEffect, useState } from "react";
import { API, request, ResultView, Turn } from "@/lib/api";

type Props = {
  jobId: string;
  view: ResultView;
  onView: (view: ResultView) => void;
  onError: (error: string) => void;
};

export function TurnEditor({
  jobId,
  view,
  turn,
  onView,
  onError,
}: Props & { turn: Turn }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(turn.text);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    if (!editing) setDraft(turn.text);
  }, [turn.text, editing]);

  async function save() {
    setSaving(true);
    try {
      const updated = await request<ResultView>(
        `/api/jobs/${jobId}/turns/${turn.turn_id}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            text: draft,
            reviewed: true,
            expected_revision: view.revision,
          }),
        },
      );
      onView(updated);
      setEditing(false);
    } catch (error) {
      onError(
        error instanceof Error ? error.message : "Chưa lưu được nội dung.",
      );
    } finally {
      setSaving(false);
    }
  }

  if (!editing)
    return (
      <div className="edit-controls">
        <button onClick={() => setEditing(true)}>
          {turn.reviewed ? "Sửa lại" : "Sửa & xác nhận"}
        </button>
        {turn.original_text !== turn.text && (
          <details>
            <summary>Xem bản ban đầu</summary>
            <p>{turn.original_text}</p>
          </details>
        )}
      </div>
    );
  return (
    <div className="turn-editor">
      <label htmlFor={`edit-${turn.turn_id}`}>
        Chỉnh sửa nội dung lượt nói
      </label>
      <textarea
        id={`edit-${turn.turn_id}`}
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        rows={3}
        maxLength={50000}
      />
      <div>
        <button
          className="primary"
          onClick={() => void save()}
          disabled={saving}
        >
          {saving ? "Đang lưu…" : "Lưu & đánh dấu đã soát"}
        </button>
        <button
          className="secondary"
          onClick={() => {
            setEditing(false);
            setDraft(turn.text);
          }}
          disabled={saving}
        >
          Hủy
        </button>
      </div>
    </div>
  );
}

function SpeakerName({
  speaker,
  turn,
  jobId,
  view,
  onView,
  onError,
}: Props & { speaker: string; turn: Turn }) {
  const savedName = view.speaker_names[speaker] || speaker;
  const [name, setName] = useState(savedName);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    setName(savedName);
  }, [savedName]);
  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    try {
      onView(
        await request<ResultView>(`/api/jobs/${jobId}/turns/${turn.turn_id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            speaker_name: name.trim(),
            reviewed: turn.reviewed,
            expected_revision: view.revision,
          }),
        }),
      );
    } catch (error) {
      onError(error instanceof Error ? error.message : "Chưa đổi được tên.");
    } finally {
      setSaving(false);
    }
  }
  return (
    <form className="speaker-form" onSubmit={save}>
      <label htmlFor={`speaker-${speaker}`}>{speaker}</label>
      <input
        id={`speaker-${speaker}`}
        value={name}
        onChange={(event) => setName(event.target.value)}
        maxLength={100}
        required
      />
      <button
        disabled={saving || name === (view.speaker_names[speaker] || speaker)}
        type="submit"
      >
        {saving ? "…" : "Lưu tên"}
      </button>
    </form>
  );
}

export function ReviewControls(props: Props) {
  const speakers = [
    ...new Set(props.view.edited.turns.map((turn) => turn.original_speaker)),
  ];
  return (
    <div className="review-controls">
      <details className="speaker-settings">
        <summary>Đặt tên người nói</summary>
        <div>
          {speakers.map((speaker) => (
            <SpeakerName
              key={speaker}
              speaker={speaker}
              {...props}
              turn={props.view.edited.turns.find(
                (turn) => turn.original_speaker === speaker,
              )!}
            />
          ))}
        </div>
      </details>
      <div className="export-buttons">
        <span>Xuất biên bản</span>
        {["md", "srt", "pdf"].map((fmt) => (
          <a
            key={fmt}
            href={`${API}/api/jobs/${props.jobId}/export?fmt=${fmt}`}
            download
          >
            {fmt === "md" ? "Markdown" : fmt.toUpperCase()} ↗
          </a>
        ))}
      </div>
    </div>
  );
}

export function SummaryButton({
  jobId,
  disabled,
  onQueued,
  onError,
}: {
  jobId: string;
  disabled: boolean;
  onQueued: () => void;
  onError: (error: string) => void;
}) {
  const [pending, setPending] = useState(false);
  async function regenerate() {
    setPending(true);
    try {
      await request(`/api/jobs/${jobId}/summary`, { method: "POST" });
      onQueued();
    } catch (error) {
      onError(
        error instanceof Error ? error.message : "Chưa tạo được tóm tắt.",
      );
    } finally {
      setPending(false);
    }
  }
  return (
    <button
      className="secondary summary-button"
      onClick={() => void regenerate()}
      disabled={disabled || pending}
    >
      {pending ? "Đang gửi yêu cầu…" : "Tạo lại tóm tắt"}
    </button>
  );
}
