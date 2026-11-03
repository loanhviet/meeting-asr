"use client";

import { useEffect, useState } from "react";
import {
  Job,
  jsonBody,
  mentionedNames,
  request,
  ResultView,
  speakerClass,
  speakerId,
  speakerOrder,
} from "@/lib/api";
import { Icon } from "./Icon";
import type { Playback } from "./MeetingApp";

type Props = {
  jobId: string;
  view: ResultView;
  playback: Playback;
  onView: (view: ResultView) => void;
  onError: (error: string) => void;
};

function SpeakerCard({
  id,
  cls,
  share,
  suggestions,
  others,
  jobId,
  view,
  playback,
  onView,
  onError,
  onRenamed,
}: Props & {
  id: string;
  cls: string;
  share: number;
  suggestions: string[];
  others: string[];
  onRenamed: () => void;
}) {
  const turns = view.edited.turns.filter((t) => speakerId(t) === id);
  const sample = [...turns].sort(
    (a, b) => b.end - b.start - (a.end - a.start),
  )[0];
  const saved = view.speaker_names[id] || "";
  const [name, setName] = useState(saved);
  const [justSaved, setJustSaved] = useState(false);
  const [target, setTarget] = useState(others[0] || "");
  useEffect(() => setName(saved), [saved]);
  const playingHere =
    playback.playing &&
    !!sample &&
    playback.position >= sample.start &&
    playback.position <= sample.end;

  async function save(value = name) {
    const next = value.trim();
    if (!next || next === saved || !sample) return;
    try {
      onView(
        await request<ResultView>(
          `/api/jobs/${jobId}/turns/${sample.turn_id}`,
          jsonBody({
            speaker_name: next,
            reviewed: sample.reviewed,
            expected_revision: view.revision,
          }),
        ),
      );
      setJustSaved(true);
      onRenamed();
      setTimeout(() => setJustSaved(false), 1600);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Chưa đổi được tên.");
    }
  }
  async function merge() {
    try {
      onView(
        await request<ResultView>(
          `/api/jobs/${jobId}/speakers/merge`,
          jsonBody(
            {
              source_speaker: id,
              target_speaker: target,
              expected_revision: view.revision,
            },
            "POST",
          ),
        ),
      );
      onRenamed();
    } catch (err) {
      onError(err instanceof Error ? err.message : "Chưa gộp được người nói.");
    }
  }
  const label = (other: string) => view.speaker_names[other] || other;
  return (
    <article className={`speaker-card ${cls} ${playingHere ? "playing" : ""}`}>
      <div className="speaker-head">
        <button
          className="play small"
          disabled={!sample}
          aria-label={`Nghe thử giọng ${saved || id}`}
          onClick={() =>
            playingHere
              ? playback.toggle()
              : sample &&
                playback.play(
                  sample.start,
                  Math.min(sample.end, sample.start + 8),
                )
          }
        >
          <Icon
            name={playingHere ? "pause" : "play"}
            width="16"
            fill={playingHere ? "none" : "currentColor"}
            strokeWidth={playingHere ? 2.6 : 1.7}
          />
        </button>
        <div>
          <strong>{saved || id}</strong>
          <span className="eq" aria-hidden="true">
            <i />
            <i />
            <i />
            <i />
          </span>
          <small className="muted">
            {id} · nói{" "}
            {share.toLocaleString("vi-VN", { maximumFractionDigits: 1 })}% thời
            lượng · {turns.length} lượt
          </small>
        </div>
        {justSaved && (
          <span className="saved" role="status">
            <Icon name="check" width="14" strokeWidth="3" /> Đã lưu
          </span>
        )}
      </div>
      <div className="share" aria-hidden="true">
        <i style={{ width: `${Math.max(2, share)}%` }} />
      </div>
      {sample && <p className="quote-text">“{sample.text}”</p>}
      <form
        className="name-form"
        onSubmit={(e) => {
          e.preventDefault();
          void save();
        }}
      >
        <label htmlFor={`speaker-${id}`}>Tên hiển thị</label>
        <input
          id={`speaker-${id}`}
          value={name}
          maxLength={100}
          placeholder="Ví dụ: Thắng"
          onChange={(e) => setName(e.target.value)}
          onBlur={() => void save()}
        />
      </form>
      {!!suggestions.length && (
        <div className="suggest">
          <span className="muted">Được nhắc trong cuộc họp:</span>
          {suggestions.map((s) => (
            <button
              key={s}
              className="pill small"
              onClick={() => {
                setName(s);
                void save(s);
              }}
            >
              {s}
            </button>
          ))}
        </div>
      )}
      {!!others.length && (
        <details
          className={`merge ${share < 2 ? "hint" : ""}`}
          open={share < 2}
        >
          <summary>
            {share < 2
              ? "Giọng này rất ít lời, có thể bị tách nhầm. Gộp vào người khác?"
              : "Cùng một người với giọng khác?"}
          </summary>
          <div className="merge-row">
            <label className="sr-only" htmlFor={`merge-${id}`}>
              Gộp vào
            </label>
            <select
              id={`merge-${id}`}
              value={target}
              onChange={(e) => setTarget(e.target.value)}
            >
              {others.map((o) => (
                <option key={o} value={o}>
                  {label(o)}
                </option>
              ))}
            </select>
            <button className="btn small" onClick={() => void merge()}>
              Gộp {turns.length} lượt
            </button>
          </div>
        </details>
      )}
    </article>
  );
}

export function SpeakersStep(
  props: Props & {
    llmEnabled: boolean;
    onQueued: () => void;
    onDone: () => void;
  },
) {
  const { view } = props;
  const [changed, setChanged] = useState(false);
  const order = speakerOrder(view.edited.turns);
  const total =
    view.edited.turns.reduce((s, t) => s + (t.end - t.start), 0) || 1;
  const shares = new Map(
    order.map((id) => [
      id,
      (view.edited.turns
        .filter((t) => speakerId(t) === id)
        .reduce((s, t) => s + (t.end - t.start), 0) /
        total) *
        100,
    ]),
  );
  const used = new Set(Object.values(view.speaker_names));
  const participants = view.participants || [];
  const [draft, setDraft] = useState(participants.join(", "));
  const suggestions = [
    ...new Set([...participants, ...mentionedNames(view.edited.turns)]),
  ]
    .filter((n) => !used.has(n))
    .slice(0, 5);
  async function saveParticipants(event: React.FormEvent) {
    event.preventDefault();
    const names = draft
      .split(/[,;\n]/)
      .map((n) => n.trim())
      .filter(Boolean)
      .slice(0, 30);
    try {
      const job = await request<Job>(
        `/api/jobs/${props.jobId}`,
        jsonBody({ participants: names }),
      );
      props.onView({ ...view, participants: job.participants || [] });
      setDraft((job.participants || []).join(", "));
    } catch (err) {
      props.onError(
        err instanceof Error
          ? err.message
          : "Chưa lưu được danh sách người dự.",
      );
    }
  }
  const named = order.filter((id) => view.speaker_names[id]).length;
  const sorted = [...order].sort(
    (a, b) => (shares.get(b) || 0) - (shares.get(a) || 0),
  );

  async function finish() {
    if (changed && props.llmEnabled && view.edited.summary) {
      try {
        await request(
          `/api/jobs/${props.jobId}/summary`,
          jsonBody({ template: view.summary_template || "project" }, "POST"),
        );
        props.onQueued();
      } catch (err) {
        props.onError(
          err instanceof Error ? err.message : "Chưa tạo lại được biên bản.",
        );
      }
    }
    props.onDone();
  }

  return (
    <div className="step">
      <button className="btn ghost" onClick={props.onDone}>
        <Icon name="back" width="18" /> {view.title}
      </button>
      <div className="step-head">
        <div>
          <h1>Ai đang nói?</h1>
          <p className="lede">
            Nghe vài giây mỗi giọng rồi đặt tên. Biên bản sẽ ghi đúng người nhận
            việc thay vì “SPEAKER_00”.
          </p>
        </div>
        <span className="muted">
          <b>{named}</b> / {order.length} giọng đã có tên
        </span>
      </div>
      <section className="participants" aria-label="Người dự họp">
        <form onSubmit={(e) => void saveParticipants(e)}>
          <label htmlFor="participants" className="sr-only">
            Người dự họp
          </label>
          <input
            id="participants"
            value={draft}
            placeholder="Người dự họp, cách nhau bằng dấu phẩy: Đạt, Trung, Hải…"
            onChange={(e) => setDraft(e.target.value)}
          />
          <button className="btn" type="submit">
            Lưu danh sách
          </button>
        </form>
        <p className="muted">
          Dùng để gợi ý tên và chọn người làm. Máy có thể nghe sai tên riêng (ví
          dụ “Chung” thay vì “Trung”); danh sách giúp bạn sửa bằng một lần chọn.
        </p>
      </section>
      <div className="speaker-grid">
        {sorted.map((id) => (
          <SpeakerCard
            key={id}
            {...props}
            id={id}
            cls={speakerClass(order, id)}
            share={shares.get(id) || 0}
            suggestions={suggestions}
            others={order.filter((o) => o !== id)}
            onRenamed={() => setChanged(true)}
          />
        ))}
      </div>
      <div className="step-actions">
        <button className="btn" onClick={props.onDone}>
          Để sau
        </button>
        <button className="btn primary" onClick={() => void finish()}>
          {changed && props.llmEnabled && view.edited.summary
            ? "Xong, cập nhật biên bản"
            : "Xong"}
        </button>
      </div>
    </div>
  );
}
