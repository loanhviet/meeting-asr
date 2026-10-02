"use client";

import { useEffect, useRef, useState } from "react";
import { EditEvent, request, ResultView, speakerId, Turn } from "@/lib/api";
import { Icon } from "./Icon";

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
  const [draftRevision, setDraftRevision] = useState(view.revision);
  const [speaker, setSpeaker] = useState(speakerId(turn));
  const [saving, setSaving] = useState(false);
  const speakers = [...new Set(view.original.turns.map((t) => t.speaker))];
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
        await request<ResultView>(`/api/jobs/${jobId}/turns/${turn.turn_id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            text: editing ? draft : turn.text,
            speaker_id: editing ? speaker : speakerId(turn),
            reviewed,
            expected_revision: editing ? draftRevision : view.revision,
          }),
        }),
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
  return (
    <div className="edit-controls">
      {editing ? (
        <div
          className="turn-editor"
          onKeyDown={(event) => {
            if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
              event.preventDefault();
              void save();
            }
          }}
        >
          <label htmlFor={`edit-${turn.turn_id}`}>
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
          <label htmlFor={`assign-${turn.turn_id}`}>
            Người nói của lượt này
          </label>
          <select
            id={`assign-${turn.turn_id}`}
            value={speaker}
            onChange={(e) => setSpeaker(e.target.value)}
          >
            {speakers.map((id) => (
              <option key={id} value={id}>
                {view.speaker_names[id] || id}
              </option>
            ))}
          </select>
          <div className="editor-actions">
            <button
              className="button primary small"
              disabled={saving}
              onClick={() => void save()}
            >
              {saving ? "Đang lưu…" : "Lưu & đánh dấu đã soát"}
            </button>
            <button
              className="button quiet small"
              disabled={saving}
              onClick={() => setEditing(false)}
            >
              Hủy
            </button>
            <small className="subtle">Ctrl / ⌘ + Enter để lưu</small>
          </div>
        </div>
      ) : (
        <>
          <button
            className="text-button"
            onClick={() => {
              setDraftRevision(view.revision);
              setEditing(true);
            }}
          >
            <Icon name="edit" width="14" height="14" />
            {turn.reviewed ? "Sửa lại" : "Sửa & xác nhận"}
          </button>
          <button
            className="text-button"
            disabled={saving}
            onClick={() => void save(!turn.reviewed)}
          >
            <Icon name="check" width="14" height="14" />
            {turn.reviewed ? "Bỏ đánh dấu đã soát" : "Đúng, đánh dấu đã soát"}
          </button>
          {(turn.original_text !== turn.text ||
            speakerId(turn) !== turn.original_speaker) && (
            <details className="original-turn">
              <summary>Xem bản ban đầu</summary>
              <p>
                {turn.original_speaker}: {turn.original_text}
              </p>
            </details>
          )}
        </>
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
      <div className="modal-heading">
        <div>
          <span className="eyebrow">MEETING NOTES</span>
          <h2>{title}</h2>
        </div>
        <button className="icon-button" aria-label="Đóng" onClick={onClose}>
          <Icon name="close" />
        </button>
      </div>
      {children}
    </dialog>
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
    if (!name.trim() || saving) return;
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
        className="button secondary small"
        disabled={saving || name.trim() === savedName}
        type="submit"
      >
        {saving ? "Đang lưu…" : "Lưu tên"}
      </button>
    </form>
  );
}
export function SpeakersDialog(props: Props & { onClose: () => void }) {
  const speakers = [...new Set(props.view.edited.turns.map(speakerId))];
  const [source, setSource] = useState(speakers[0] || "");
  const [target, setTarget] = useState(speakers[1] || "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const count = props.view.edited.turns.filter(
    (t) => speakerId(t) === source,
  ).length;
  async function merge() {
    if (saving) return;
    setSaving(true);
    setError("");
    try {
      props.onView(
        await request<ResultView>(`/api/jobs/${props.jobId}/speakers/merge`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            source_speaker: source,
            target_speaker: target,
            expected_revision: props.view.revision,
          }),
        }),
      );
      props.onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Chưa gộp được người nói.");
    } finally {
      setSaving(false);
    }
  }
  return (
    <Modal title="Quản lý người nói" onClose={props.onClose}>
      <p className="dialog-intro">
        Đặt tên để dễ theo dõi. Nếu một người bị chia thành nhiều nhóm, bạn có
        thể gộp các lượt nói của họ.
      </p>
      <h3>Đặt tên người nói</h3>
      <div className="speaker-list">
        {speakers.map((id) => (
          <SpeakerName
            key={id}
            {...props}
            onError={setError}
            speaker={id}
            turn={props.view.edited.turns.find((t) => speakerId(t) === id)!}
          />
        ))}
      </div>
      <section className="merge-section">
        <h3>Gộp nhóm người nói</h3>
        {speakers.length < 2 ? (
          <p className="subtle">Cuộc họp hiện có một nhóm người nói.</p>
        ) : (
          <>
            <div className="merge-selects">
              <label>
                Nhóm cần gộp
                <select
                  aria-label="Nhóm cần gộp"
                  value={source}
                  onChange={(e) => setSource(e.target.value)}
                >
                  {speakers.map((id) => (
                    <option key={id} value={id}>
                      {props.view.speaker_names[id] || id}
                    </option>
                  ))}
                </select>
              </label>
              <Icon name="next" />
              <label>
                Gộp vào
                <select
                  aria-label="Gộp vào"
                  value={target}
                  onChange={(e) => setTarget(e.target.value)}
                >
                  {speakers.map((id) => (
                    <option key={id} value={id}>
                      {props.view.speaker_names[id] || id}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <p className="hint">
              {count} lượt sẽ chuyển nhóm. Nội dung, thời gian và bản model gốc
              vẫn được giữ; biên bản cần tạo lại.
            </p>
            <button
              className="button primary"
              disabled={source === target || saving}
              onClick={() => void merge()}
            >
              {saving ? "Đang gộp…" : `Gộp ${count} lượt nói`}
            </button>
          </>
        )}
        {error && (
          <p className="notice warning" role="alert">
            {error}
          </p>
        )}
      </section>
    </Modal>
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
  return (
    <Modal title="Lịch sử chỉnh sửa" onClose={onClose}>
      <p className="dialog-intro">
        Bản model gốc được giữ riêng. Hiển thị tối đa 100 thay đổi gần nhất.
      </p>
      {error && (
        <p role="alert" className="notice warning">
          {error}
        </p>
      )}
      {events === null && !error && <p className="subtle">Đang tải lịch sử…</p>}
      {events?.length === 0 && (
        <p className="panel-empty">Chưa có chỉnh sửa.</p>
      )}
      <ol className="history-list">
        {events?.map((event) => (
          <li key={event.id}>
            <div>
              <strong>
                {event.kind === "speaker_merge"
                  ? "Gộp nhóm người nói"
                  : "Chỉnh sửa lượt nói"}
              </strong>
              <small>
                Phiên bản {event.revision} ·{" "}
                {new Date(event.created * 1000).toLocaleString("vi-VN")}
              </small>
            </div>
            {event.kind === "speaker_merge" ? (
              <p>
                {event.changes.source_speaker} → {event.changes.target_speaker}{" "}
                · {event.changes.turn_ids?.length} lượt
              </p>
            ) : (
              <>
                <p>
                  {event.changes.before?.speaker_id} →{" "}
                  {event.changes.after?.speaker_id}
                  {event.changes.after?.reviewed
                    ? " · đã soát"
                    : " · chưa soát"}
                </p>
                {event.changes.before?.text !== event.changes.after?.text && (
                  <div className="history-diff">
                    <del>{event.changes.before?.text}</del>
                    <p>{event.changes.after?.text}</p>
                  </div>
                )}
                {event.changes.speaker_name && (
                  <p>
                    Đổi tên: {event.changes.speaker_name.before} →{" "}
                    {event.changes.speaker_name.after}
                  </p>
                )}
              </>
            )}
          </li>
        ))}
      </ol>
    </Modal>
  );
}
