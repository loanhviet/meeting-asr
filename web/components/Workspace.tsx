"use client";

import { useEffect, useRef, useState } from "react";
import {
  API,
  date,
  duration,
  Job,
  jsonBody,
  request,
  ResultView,
  speakerOrder,
  Turn,
} from "@/lib/api";
import { Icon } from "./Icon";
import type { Playback, Screen, Toast } from "./MeetingApp";
import { STAGES } from "./Library";
import { Minutes } from "./Minutes";
import { Transcript } from "./Transcript";
import { Player } from "./Player";
import { AskDrawer } from "./AskDrawer";
import { HistoryDialog } from "./ReviewControls";

export type Focus = { id: string; n: number } | null;

export function Workspace({
  jobId,
  job,
  view,
  llmEnabled,
  askEnabled,
  playback,
  themeButton,
  onView,
  onJob,
  onQueued,
  onRetry,
  onError,
  onToast,
  onLibrary,
  onScreen,
}: {
  jobId: string;
  job: Job | null;
  view: ResultView | null;
  llmEnabled: boolean;
  askEnabled: boolean;
  playback: Playback;
  themeButton: React.ReactNode;
  onView: (view: ResultView) => void;
  onJob: (job: Job) => void;
  onQueued: () => void;
  onRetry: () => void;
  onError: (error: string) => void;
  onToast: (toast: Toast) => void;
  onLibrary: () => void;
  onScreen: (screen: Screen) => void;
}) {
  const [focus, setFocus] = useState<Focus>(null);
  const [follow, setFollow] = useState(true);
  const [loop, setLoop] = useState(false);
  const [askOpen, setAskOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [titleDraft, setTitleDraft] = useState<string | null>(null);
  const [template, setTemplate] = useState("project");
  const [pending, setPending] = useState(false);
  const menu = useRef<HTMLDetailsElement>(null);
  const busy = job?.status === "queued" || job?.status === "running";
  const minutes = view?.edited;
  const turns = minutes?.turns || [];
  const order = speakerOrder(turns);
  const position = playback.position;
  const activeTurn =
    turns.find(
      (t) => !t.backchannel && position >= t.start && position < t.end,
    ) || turns.find((t) => position >= t.start && position < t.end);
  const loopTurn = loop
    ? turns.find((t) => t.turn_id === (focus?.id ?? activeTurn?.turn_id))
    : undefined;

  useEffect(() => {
    if (view?.summary_template) setTemplate(view.summary_template);
  }, [view?.summary_template]);
  useEffect(() => {
    if (loopTurn && playback.playing && position >= loopTurn.end)
      playback.play(loopTurn.start);
  }, [loopTurn, position, playback]);

  function seek(turn: Turn) {
    setFocus((f) => ({ id: turn.turn_id, n: (f?.n || 0) + 1 }));
    playback.play(turn.start);
  }
  useEffect(() => {
    function keyboard(event: KeyboardEvent) {
      const target = event.target as HTMLElement;
      if (
        !view ||
        document.querySelector("dialog[open]") ||
        target.closest(
          "input,textarea,select,button,a,summary,[contenteditable=true]",
        )
      )
        return;
      const player = playback.audio.current;
      const key = event.key.toLowerCase();
      if (event.code === "Space" && player) {
        event.preventDefault();
        playback.toggle();
      } else if (key === "j" && player)
        player.currentTime = Math.max(0, player.currentTime - 5);
      else if (key === "l" && player)
        player.currentTime = Math.min(
          minutes?.duration || 0,
          player.currentTime + 5,
        );
      else if (key === "r" && (focus || activeTurn)) {
        event.preventDefault();
        setLoop((value) => !value);
      }
    }
    window.addEventListener("keydown", keyboard);
    return () => window.removeEventListener("keydown", keyboard);
  });

  async function saveTitle() {
    const title = titleDraft?.trim();
    setTitleDraft(null);
    if (!title || title === (job?.title || view?.title)) return;
    try {
      onJob(await request<Job>(`/api/jobs/${jobId}`, jsonBody({ title })));
      if (view) onView({ ...view, title });
    } catch (err) {
      onError(err instanceof Error ? err.message : "Chưa đổi được tên.");
    }
  }
  async function finalize(next: boolean) {
    try {
      const updated = await request<Job>(
        `/api/jobs/${jobId}`,
        jsonBody({ finalized: next }),
      );
      onJob(updated);
      if (view) onView({ ...view, finalized: updated.finalized });
      if (next)
        onToast({
          text: "Đã chốt biên bản.",
          links: [
            {
              label: "Xuất PDF",
              href: `${API}/api/jobs/${jobId}/export?fmt=pdf`,
            },
            {
              label: "Markdown",
              href: `${API}/api/jobs/${jobId}/export?fmt=md`,
            },
          ],
        });
    } catch (err) {
      onError(err instanceof Error ? err.message : "Chưa chốt được biên bản.");
    }
  }
  async function regenerate() {
    menu.current?.removeAttribute("open");
    setPending(true);
    try {
      await request(
        `/api/jobs/${jobId}/summary`,
        jsonBody({ template }, "POST"),
      );
      onQueued();
    } catch (err) {
      onError(err instanceof Error ? err.message : "Chưa tạo được biên bản.");
    } finally {
      setPending(false);
    }
  }

  const title = view?.title || job?.title || "Đang mở cuộc họp…";
  const unnamed = order.filter((id) => !view?.speaker_names[id]).length;
  const finalized = job?.finalized ?? view?.finalized ?? false;

  return (
    <div className={`workspace ${askOpen ? "asking" : ""}`}>
      <header className="meeting-bar">
        <button className="btn ghost" onClick={onLibrary} aria-label="Thư viện">
          <Icon name="back" width="18" />
          <span className="hide-sm">Thư viện</span>
        </button>
        <div className="meeting-title">
          {titleDraft !== null ? (
            <input
              aria-label="Tên cuộc họp"
              className="title-input"
              value={titleDraft}
              autoFocus
              maxLength={200}
              onChange={(e) => setTitleDraft(e.target.value)}
              onBlur={() => void saveTitle()}
              onKeyDown={(e) => {
                if (e.key === "Enter") void saveTitle();
                if (e.key === "Escape") setTitleDraft(null);
              }}
            />
          ) : (
            <h1>
              <button
                className="title-button"
                title="Đổi tên cuộc họp"
                onClick={() => setTitleDraft(title)}
                disabled={!job}
              >
                {title}
              </button>
            </h1>
          )}
          <p>
            {job && date(job.created)}
            {minutes &&
              ` · ${duration(minutes.duration)} · ${order.length} người nói`}
          </p>
        </div>
        {view && (
          <div className="bar-actions">
            <button
              className="btn"
              onClick={() => onScreen("speakers")}
              aria-label={`Người nói${unnamed ? `, ${unnamed} chưa có tên` : ""}`}
            >
              <Icon name="users" width="18" />
              <span className="hide-sm">Người nói</span>
              {!!unnamed && (
                <span className="count warn">{unnamed} chưa có tên</span>
              )}
            </button>
            <button
              className="btn"
              aria-expanded={askOpen}
              aria-label="Hỏi cuộc họp"
              onClick={() => setAskOpen((v) => !v)}
            >
              <Icon name="chat" width="18" />
              <span className="hide-sm">Hỏi cuộc họp</span>
            </button>
            <button
              className={`btn ${finalized ? "done" : "primary"}`}
              onClick={() => void finalize(!finalized)}
              aria-pressed={finalized}
            >
              <Icon name="check" width="18" />
              {finalized ? "Đã chốt" : "Chốt biên bản"}
            </button>
            <details className="menu" ref={menu}>
              <summary className="icon-button" aria-label="Thêm thao tác">
                <Icon name="more" strokeWidth="3" />
              </summary>
              <div className="menu-panel">
                <span className="menu-label">Xuất</span>
                {(["pdf", "md", "srt"] as const).map((fmt) => (
                  <a
                    key={fmt}
                    href={`${API}/api/jobs/${jobId}/export?fmt=${fmt}`}
                    download
                  >
                    <Icon name="download" width="16" />
                    {fmt === "md"
                      ? "Markdown"
                      : fmt === "pdf"
                        ? "PDF"
                        : "Phụ đề SRT"}
                  </a>
                ))}
                <span className="menu-label">Biên bản</span>
                <label className="menu-field">
                  Mẫu
                  <select
                    value={template}
                    onChange={(e) => setTemplate(e.target.value)}
                  >
                    <option value="project">Họp dự án</option>
                    <option value="standup">Standup</option>
                    <option value="customer">Họp khách hàng</option>
                  </select>
                </label>
                <button
                  disabled={!llmEnabled || busy || pending}
                  onClick={() => void regenerate()}
                >
                  <Icon name="repeat" width="16" />
                  {minutes?.summary ? "Tạo lại biên bản" : "Tạo biên bản"}
                </button>
                <button
                  onClick={() => {
                    menu.current?.removeAttribute("open");
                    setHistoryOpen(true);
                  }}
                >
                  <Icon name="history" width="16" />
                  Lịch sử chỉnh sửa
                </button>
              </div>
            </details>
          </div>
        )}
        {!view && themeButton}
      </header>

      {busy && (
        <section
          className={`processing ${view ? "compact" : ""}`}
          role="status"
        >
          <div className="processing-head">
            <h2>{STAGES[job?.stage || "queued"]}</h2>
            <span className="muted">
              {job?.stage === "M6"
                ? "Đang tạo biên bản từ transcript hiện tại."
                : "Có thể quay lại thư viện; bản ghi vẫn tiếp tục được xử lý."}
            </span>
          </div>
          <progress
            aria-label="Tiến độ xử lý"
            max="1"
            value={job?.progress || 0}
          />
          {!view && (
            <ol className="stages">
              {["M1", "M2", "M3", "M4", "M5", "M6"].map((s) => {
                const stages = ["queued", "M1", "M2", "M3", "M4", "M5", "M6"];
                const now = stages.indexOf(job?.stage || "queued");
                const at = stages.indexOf(s);
                return (
                  <li
                    key={s}
                    className={at < now ? "done" : at === now ? "now" : ""}
                  >
                    {STAGES[s].replace("Đang ", "")}
                  </li>
                );
              })}
            </ol>
          )}
        </section>
      )}
      {job?.status === "failed" && (
        <section className="failure" role="status">
          <Icon name="alert" width="24" />
          <div>
            <h2>
              {view ? "Chưa tạo được biên bản" : "Chưa xử lý được bản ghi"}
            </h2>
            <p>{job.error || "Vui lòng thử lại."}</p>
          </div>
          <button className="btn primary" onClick={onRetry}>
            Thử lại
          </button>
        </section>
      )}
      {!job && (
        <div className="loading" role="status">
          Đang tải cuộc họp…
        </div>
      )}

      {view && minutes && (
        <div className="columns">
          <Minutes
            jobId={jobId}
            view={view}
            order={order}
            llmEnabled={llmEnabled}
            busy={busy}
            pending={pending}
            onSource={seek}
            onView={onView}
            onError={onError}
            onReview={() => onScreen("review")}
            onRegenerate={() => void regenerate()}
          />
          <Transcript
            jobId={jobId}
            view={view}
            order={order}
            activeId={activeTurn?.turn_id || null}
            focus={focus}
            follow={follow && playback.playing}
            onFollow={setFollow}
            followOn={follow}
            onSeek={seek}
            onView={onView}
            onError={onError}
          />
        </div>
      )}
      {view && minutes && (
        <Player
          playback={playback}
          duration={minutes.duration}
          minutes={minutes}
          order={order}
          activeTurn={activeTurn}
          loop={loop}
          onLoop={setLoop}
        />
      )}
      {view && (
        <AskDrawer
          jobId={jobId}
          view={view}
          enabled={askEnabled}
          busy={busy}
          open={askOpen}
          onClose={() => setAskOpen(false)}
          onSource={seek}
        />
      )}
      {historyOpen && view && (
        <HistoryDialog
          jobId={jobId}
          view={view}
          onClose={() => setHistoryOpen(false)}
        />
      )}
    </div>
  );
}
