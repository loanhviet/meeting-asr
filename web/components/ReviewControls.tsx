"use client";

import { useEffect, useRef, useState } from "react";
import {
  askNotifyPermission,
  EditEvent,
  jsonBody,
  request,
  ResultView,
  speakerId,
  speakerOrder,
  Turn,
} from "@/lib/api";
import { Icon } from "./Icon";

type Props = {
  jobId: string;
  view: ResultView;
  onView: (view: ResultView) => void;
  onError: (error: string) => void;
};

/** Inline correction for one turn; actions appear on hover or keyboard focus. */
export function TurnEditor({
  jobId,
  view,
  turn,
  onView,
  onError,
}: Props & { turn: Turn }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(turn.text);
  const [draftRevision, setDraftRevision] = useState(view.revision);
  const [speaker, setSpeaker] = useState(speakerId(turn));
  const [saving, setSaving] = useState(false);
  const speakers = speakerOrder(view.original.turns);
  useEffect(() => {
    if (!editing) {
      setDraft(turn.text);
      setSpeaker(speakerId(turn));
    }
  }, [turn, editing]);
  async function save(reviewed = true) {
    if (saving) return;
    setSaving(true);
    try {
      onView(
        await request<ResultView>(
          `/api/jobs/${jobId}/turns/${turn.turn_id}`,
          jsonBody({
            text: editing ? draft : turn.text,
            speaker_id: editing ? speaker : speakerId(turn),
            reviewed,
            expected_revision: editing ? draftRevision : view.revision,
          }),
        ),
      );
      setEditing(false);
    } catch (error) {
      onError(
        error instanceof Error ? error.message : "Chưa lưu được nội dung.",
      );
    } finally {
      setSaving(false);
    }
  }
  const changed =
    turn.original_text !== turn.text ||
    speakerId(turn) !== turn.original_speaker;
  if (editing)
    return (
      <div
        className="turn-editor"
        onKeyDown={(event) => {
          if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
            event.preventDefault();
            void save();
          }
          if (event.key === "Escape") setEditing(false);
        }}
      >
        <label htmlFor={`edit-${turn.turn_id}`} className="sr-only">
          Chỉnh sửa nội dung lượt nói
        </label>
        <textarea
          id={`edit-${turn.turn_id}`}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          rows={3}
          maxLength={50000}
          autoFocus
        />
        <div className="editor-row">
          <label>
            Người nói
            <select
              value={speaker}
              onChange={(e) => setSpeaker(e.target.value)}
            >
              {speakers.map((id) => (
                <option key={id} value={id}>
                  {view.speaker_names[id] || id}
                </option>
              ))}
            </select>
          </label>
          <button
            className="btn primary small"
            disabled={saving}
            onClick={() => void save()}
          >
            {saving ? "Đang lưu…" : "Lưu"}
          </button>
          <button
            className="btn small"
            disabled={saving}
            onClick={() => setEditing(false)}
          >
            Hủy
          </button>
          <small className="muted">Ctrl / ⌘ + Enter</small>
        </div>
      </div>
    );
  return (
    <div className="turn-actions">
      <button
        className="link"
        onClick={() => {
          setDraftRevision(view.revision);
          setEditing(true);
        }}
      >
        <Icon name="edit" width="13" /> Sửa
      </button>
      <button
        className="link"
        disabled={saving}
        onClick={() => void save(!turn.reviewed)}
      >
        <Icon name="check" width="13" />
        {turn.reviewed ? "Bỏ đánh dấu đã nghe" : "Đúng, đã nghe lại"}
      </button>
      {changed && (
        <details className="original">
          <summary>Bản ban đầu</summary>
          <p>
            {turn.original_speaker}: {turn.original_text}
          </p>
        </details>
      )}
    </div>
  );
}

export function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    ref.current?.showModal();
  }, []);
  return (
    <dialog
      ref={ref}
      className="modal"
      onCancel={onClose}
      onClick={(event) => {
        if (event.target === ref.current) {
          const r = ref.current.getBoundingClientRect();
          if (
            event.clientX < r.left ||
            event.clientX > r.right ||
            event.clientY < r.top ||
            event.clientY > r.bottom
          )
            onClose();
        }
      }}
      aria-label={title}
    >
      <div className="modal-head">
        <h2>{title}</h2>
        <button className="icon-button" aria-label="Đóng" onClick={onClose}>
          <Icon name="close" />
        </button>
      </div>
      {children}
    </dialog>
  );
}

export function HistoryDialog({
  jobId,
  onClose,
  view,
}: {
  jobId: string;
  onClose: () => void;
  view: ResultView;
}) {
  const [events, setEvents] = useState<EditEvent[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const c = new AbortController();
    request<EditEvent[]>(`/api/jobs/${jobId}/history`, { signal: c.signal })
      .then(setEvents)
      .catch((e) => {
        if (!c.signal.aborted) setError(e.message);
      });
    return () => c.abort();
  }, [jobId, view.revision]);
  const name = (id?: string) => (id ? view.speaker_names[id] || id : "");
  return (
    <Modal title="Lịch sử chỉnh sửa" onClose={onClose}>
      <p className="muted">
        Bản gốc của mô hình luôn được giữ. Hiển thị 100 thay đổi gần nhất.
      </p>
      {error && (
        <p role="alert" className="callout warn">
          {error}
        </p>
      )}
      {events === null && !error && <p className="muted">Đang tải lịch sử…</p>}
      {events?.length === 0 && <p className="empty">Chưa có chỉnh sửa.</p>}
      <ol className="history">
        {events?.map((event) => (
          <li key={event.id}>
            <div className="history-head">
              <strong>
                {event.kind === "speaker_merge"
                  ? "Gộp người nói"
                  : "Sửa lượt nói"}
              </strong>
              <small className="muted">
                Phiên bản {event.revision} ·{" "}
                {new Date(event.created * 1000).toLocaleString("vi-VN")}
              </small>
            </div>
            {event.kind === "speaker_merge" ? (
              <p>
                {name(event.changes.source_speaker)} →{" "}
                {name(event.changes.target_speaker)} ·{" "}
                {event.changes.turn_ids?.length} lượt
              </p>
            ) : (
              <>
                {event.changes.before?.speaker_id !==
                  event.changes.after?.speaker_id && (
                  <p>
                    {name(event.changes.before?.speaker_id)} →{" "}
                    {name(event.changes.after?.speaker_id)}
                  </p>
                )}
                {event.changes.before?.text !== event.changes.after?.text && (
                  <div className="diff">
                    <del>{event.changes.before?.text}</del>
                    <ins>{event.changes.after?.text}</ins>
                  </div>
                )}
                {event.changes.speaker_name && (
                  <p>
                    Đổi tên: {event.changes.speaker_name.before} →{" "}
                    {event.changes.speaker_name.after}
                  </p>
                )}
                {event.changes.after?.reviewed &&
                  !event.changes.before?.reviewed && (
                    <p className="muted">Đánh dấu đã nghe lại</p>
                  )}
              </>
            )}
          </li>
        ))}
      </ol>
    </Modal>
  );
}

export function useDropUpload(onFile: (file: File) => void) {
  const [dragging, setDragging] = useState(false);
  return {
    dragging,
    handlers: {
      onDragOver: (e: React.DragEvent) => {
        e.preventDefault();
        setDragging(true);
      },
      onDragLeave: (e: React.DragEvent) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node))
          setDragging(false);
      },
      onDrop: (e: React.DragEvent) => {
        e.preventDefault();
        setDragging(false);
        const file = e.dataTransfer.files[0];
        if (file) onFile(file);
      },
    },
  };
}

export function UploadDialog({
  onClose,
  onUploaded,
  initialFile,
}: {
  onClose: () => void;
  onUploaded: (id: string) => void;
  initialFile?: File;
}) {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const started = useRef(false);
  async function upload(file?: File) {
    if (!file || uploading) return;
    if (!/\.(wav|mp3|m4a)$/i.test(file.name))
      return setError("Hãy chọn file WAV, MP3 hoặc M4A.");
    if (file.size > 200 * 1024 * 1024)
      return setError("File cần nhỏ hơn 200 MB.");
    setUploading(true);
    setError("");
    askNotifyPermission();
    try {
      const form = new FormData();
      form.append("file", file);
      const result = await request<{ job_id: string }>("/api/jobs", {
        method: "POST",
        body: form,
      });
      onUploaded(result.job_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tải file lên được.");
    } finally {
      setUploading(false);
      if (input.current) input.current.value = "";
    }
  }
  useEffect(() => {
    if (initialFile && !started.current) {
      started.current = true;
      void upload(initialFile);
    }
    // Upload a dropped file once, on open.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const drop = useDropUpload((file) => void upload(file));
  return (
    <Modal title="Tải bản ghi cuộc họp" onClose={onClose}>
      <input
        ref={input}
        type="file"
        accept=".wav,.mp3,.m4a"
        aria-label="Chọn bản ghi cuộc họp"
        className="sr-only"
        onChange={(e) => void upload(e.target.files?.[0])}
      />
      <div
        className={`dropzone ${drop.dragging ? "dragging" : ""}`}
        {...drop.handlers}
      >
        <Icon name="upload" width="28" height="28" />
        <p>
          <strong>Kéo bản ghi vào đây</strong> hoặc chọn từ máy
        </p>
        <button
          className="btn primary"
          disabled={uploading}
          onClick={() => input.current?.click()}
        >
          {uploading ? "Đang tải lên…" : "Chọn bản ghi"}
        </button>
        <small className="muted">WAV, MP3, M4A · tối đa 200 MB</small>
      </div>
      {error && (
        <p role="alert" className="callout warn">
          {error}
        </p>
      )}
    </Modal>
  );
}
