"use client";

import { useEffect, useRef, useState } from "react";
import { ResultView, speakerClass, speakerId, time, Turn } from "@/lib/api";
import { Icon } from "./Icon";
import { TurnEditor } from "./ReviewControls";
import type { Focus } from "./Workspace";

export function Transcript({
  jobId,
  view,
  order,
  activeId,
  focus,
  follow,
  followOn,
  onFollow,
  onSeek,
  onView,
  onError,
}: {
  jobId: string;
  view: ResultView;
  order: string[];
  activeId: string | null;
  focus: Focus;
  follow: boolean;
  followOn: boolean;
  onFollow: (follow: boolean) => void;
  onSeek: (turn: Turn) => void;
  onView: (view: ResultView) => void;
  onError: (error: string) => void;
}) {
  const [search, setSearch] = useState("");
  const nodes = useRef(new Map<string, HTMLElement>());
  const review = new Set(view.review_turn_ids);
  const q = search.trim().toLocaleLowerCase("vi");
  const turns = view.edited.turns.filter(
    (t) => !q || `${t.text} ${t.speaker}`.toLocaleLowerCase("vi").includes(q),
  );

  function reveal(id: string) {
    requestAnimationFrame(() =>
      nodes.current
        .get(id)
        ?.scrollIntoView({ behavior: "smooth", block: "center" }),
    );
  }
  useEffect(() => {
    if (!focus) return;
    setSearch("");
    reveal(focus.id);
  }, [focus]);
  useEffect(() => {
    if (follow && activeId) reveal(activeId);
  }, [follow, activeId]);

  return (
    <section className="transcript" aria-label="Transcript">
      <div className="transcript-bar">
        <h2>Transcript</h2>
        <label className="search compact">
          <Icon name="search" width="15" />
          <span className="sr-only">Tìm trong transcript</span>
          <input
            type="search"
            placeholder="Tìm lời nói…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        <label className="toggle">
          <input
            type="checkbox"
            checked={followOn}
            onChange={(e) => onFollow(e.target.checked)}
          />
          Theo lời đang phát
        </label>
      </div>
      <div className="turns">
        {turns.map((turn) => {
          const cls = [
            "turn",
            speakerClass(order, speakerId(turn)),
            turn.backchannel ? "backchannel" : "",
            activeId === turn.turn_id ? "active" : "",
            focus?.id === turn.turn_id
              ? focus.n % 2
                ? "flash-a"
                : "flash-b"
              : "",
          ].join(" ");
          return (
            <article
              key={turn.turn_id}
              data-turn-id={turn.turn_id}
              className={cls}
              ref={(node) => {
                if (node) nodes.current.set(turn.turn_id, node);
                else nodes.current.delete(turn.turn_id);
              }}
            >
              <button
                className="turn-time"
                onClick={() => onSeek(turn)}
                aria-label={`Nghe lượt ${time(turn.start)}`}
              >
                {time(turn.start)}
              </button>
              <div className="turn-body">
                <div className="turn-who">
                  <i className="dot" />
                  <span>{turn.speaker}</span>
                  {turn.reviewed && (
                    <span className="heard" title="Đã nghe lại">
                      <Icon name="check" width="13" strokeWidth="2.6" /> đã nghe
                      lại
                    </span>
                  )}
                </div>
                <p className={review.has(turn.turn_id) ? "unsure" : ""}>
                  {turn.text || (
                    <span className="muted">Không có lời phiên âm.</span>
                  )}
                </p>
                <TurnEditor
                  jobId={jobId}
                  view={view}
                  turn={turn}
                  onView={onView}
                  onError={onError}
                />
              </div>
            </article>
          );
        })}
        {!turns.length && (
          <p className="empty">Không tìm thấy lượt nói. Thử từ khóa khác.</p>
        )}
      </div>
    </section>
  );
}
