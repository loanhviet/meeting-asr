"use client";

import { useEffect, useRef, useState } from "react";
import {
  API,
  Job,
  request,
  ResultView,
  speakerId,
  time,
  Turn,
} from "@/lib/api";
import { Icon } from "./Icon";
import { MinutesPanel } from "./MinutesPanel";
import { MeetingPlayer } from "./MeetingPlayer";
import { AskMeetingPanel } from "./AskMeetingPanel";
import {
  HistoryDialog,
  Modal,
  SpeakersDialog,
  TurnEditor,
} from "./ReviewControls";

const stages: Record<string, string> = {
  queued: "Đang chờ xử lý",
  M1: "Chuẩn hóa bản ghi",
  M2: "Phân biệt người nói",
  M3: "Phiên âm nội dung",
  M4: "Sắp xếp lượt nói",
  M5: "Chọn đoạn cần soát",
  M6: "Tạo biên bản",
  complete: "Đã xử lý",
  failed: "Xử lý chưa thành công",
};
const date = (created: number) =>
  new Date(created * 1000).toLocaleDateString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
export default function MeetingApp() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [view, setView] = useState<ResultView | null>(null);
  const [error, setError] = useState("");
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [tab, setTab] = useState("transcript");
  const [onlyFlagged, setOnlyFlagged] = useState(false);
  const [search, setSearch] = useState("");
  const [librarySearch, setLibrarySearch] = useState("");
  const [llmEnabled, setLlmEnabled] = useState(false);
  const [askEnabled, setAskEnabled] = useState(false);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [loop, setLoop] = useState(false);
  const [dialog, setDialog] = useState<
    "upload" | "speakers" | "history" | null
  >(null);
  const audio = useRef<HTMLAudioElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const turnNodes = useRef(new Map<string, HTMLElement>());
  const refreshResult = useRef(false);
  const seekTarget = useRef<number | null>(null);

  useEffect(() => {
    const id =
      new URLSearchParams(window.location.search).get("job") ||
      localStorage.getItem("meetingJobId");
    if (id) setSelected(id);
    request<Job[]>("/api/jobs")
      .then(setJobs)
      .catch(() => setError("Chưa kết nối được dịch vụ xử lý."));
    request<{ llm_enabled: boolean; ask_enabled?: boolean }>("/api/health")
      .then((health) => {
        setLlmEnabled(health.llm_enabled);
        setAskEnabled(health.ask_enabled ?? health.llm_enabled);
      })
      .catch(() => {});
  }, []);
  useEffect(() => {
    if (!selected) return;
    const controller = new AbortController();
    let active = true,
      pending = false,
      lastRevision = -1,
      lastStatus = "";
    setView(null);
    setJob(null);
    setError("");
    setSearch("");
    setActiveId(null);
    setLoop(false);
    seekTarget.current = null;
    setOnlyFlagged(false);
    setTab("transcript");
    async function poll() {
      if (pending) return;
      pending = true;
      try {
        const current = await request<Job>(`/api/jobs/${selected}`, {
          signal: controller.signal,
        });
        if (!active) return;
        setJob(current);
        if (
          (current.status === "complete" || current.status === "failed") &&
          (current.revision !== lastRevision ||
            current.status !== lastStatus ||
            refreshResult.current)
        ) {
          const result = await request<ResultView>(
            `/api/jobs/${selected}/result`,
            { signal: controller.signal },
          ).catch(() => null);
          if (active && result) {
            setView((previous) =>
              !previous || result.revision >= previous.revision
                ? result
                : previous,
            );
            lastRevision = result.revision;
            refreshResult.current = false;
          }
        }
        lastStatus = current.status;
        const list = await request<Job[]>("/api/jobs", {
          signal: controller.signal,
        });
        if (active) setJobs(list);
      } catch (err) {
        if (active)
          setError(
            err instanceof Error ? err.message : "Không tải được cuộc họp.",
          );
      } finally {
        pending = false;
      }
    }
    void poll();
    const timer = setInterval(poll, 1500);
    return () => {
      active = false;
      controller.abort();
      clearInterval(timer);
    };
  }, [selected]);
  const minutes = view?.edited;
  const allTurns = minutes?.turns || [];
  const pendingTurns = allTurns
    .filter((t) => t.flagged && !t.reviewed)
    .sort(
      (a, b) =>
        (a.confidence ?? 1) - (b.confidence ?? 1) ||
        a.turn_id.localeCompare(b.turn_id),
    );
  const turns = (onlyFlagged ? pendingTurns : allTurns).filter((t) =>
    `${t.text} ${t.speaker}`
      .toLocaleLowerCase("vi")
      .includes(search.toLocaleLowerCase("vi")),
  );
  const speakers = [...new Set(allTurns.map(speakerId))];
  const activeTurn = allTurns.find((t) => t.turn_id === activeId);
  const reviewed = allTurns.filter((t) => t.reviewed).length;
  const busy = job?.status === "queued" || job?.status === "running";

  function choose(id: string) {
    audio.current?.pause();
    localStorage.setItem("meetingJobId", id);
    const url = new URL(window.location.href);
    url.searchParams.set("job", id);
    window.history.replaceState(null, "", url);
    setDialog(null);
    setSelected(id);
  }
  function library() {
    audio.current?.pause();
    localStorage.removeItem("meetingJobId");
    const url = new URL(window.location.href);
    url.searchParams.delete("job");
    window.history.replaceState(null, "", url);
    setSelected(null);
    setView(null);
    setJob(null);
    setError("");
    setDialog(null);
    request<Job[]>("/api/jobs")
      .then(setJobs)
      .catch(() => setError("Không tải được thư viện cuộc họp."));
  }
  async function upload(file?: File) {
    if (!file || uploading) return;
    if (!/\.(wav|mp3|m4a)$/i.test(file.name)) {
      setError("Hãy chọn file WAV, MP3 hoặc M4A.");
      return;
    }
    if (file.size > 200 * 1024 * 1024) {
      setError("File cần nhỏ hơn 200 MB.");
      return;
    }
    setUploading(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      const result = await request<{ job_id: string }>("/api/jobs", {
        method: "POST",
        body: form,
      });
      choose(result.job_id);
      setTab("transcript");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tải file lên được.");
    } finally {
      setUploading(false);
      if (input.current) input.current.value = "";
    }
  }
  function seek(turn: Turn, source = false) {
    setActiveId(turn.turn_id);
    if (source) {
      setOnlyFlagged(false);
      setSearch("");
      setTab("transcript");
      requestAnimationFrame(() =>
        requestAnimationFrame(() =>
          turnNodes.current
            .get(turn.turn_id)
            ?.scrollIntoView({ behavior: "smooth", block: "center" }),
        ),
      );
    }
    const player = audio.current;
    if (player) {
      seekTarget.current = turn.start;
      const play = () => {
        if (audio.current !== player || seekTarget.current !== turn.start)
          return;
        player.currentTime = turn.start;
        void player.play().catch(() => {});
      };
      if (player.readyState >= 1) play();
      else player.addEventListener("loadedmetadata", play, { once: true });
    }
  }
  function nextPending() {
    if (!pendingTurns.length) return;
    const i = pendingTurns.findIndex((t) => t.turn_id === activeId);
    seek(pendingTurns[(i + 1) % pendingTurns.length], true);
  }
  useEffect(() => {
    function keyboard(event: KeyboardEvent) {
      const target = event.target as HTMLElement;
      if (
        !selected ||
        !view ||
        document.querySelector("dialog[open]") ||
        target.closest("input,textarea,select,button,a,[contenteditable=true]")
      )
        return;
      const player = audio.current;
      if (event.code === "Space" && player) {
        event.preventDefault();
        if (player.paused) void player.play().catch(() => {});
        else player.pause();
      }
      if (event.key.toLowerCase() === "j" && player)
        player.currentTime = Math.max(0, player.currentTime - 5);
      if (event.key.toLowerCase() === "l" && player)
        player.currentTime = Math.min(
          minutes?.duration || 0,
          player.currentTime + 5,
        );
      if (event.key.toLowerCase() === "n") {
        event.preventDefault();
        nextPending();
      }
      if (event.key.toLowerCase() === "r" && activeTurn) {
        event.preventDefault();
        setLoop((value) => !value);
      }
    }
    window.addEventListener("keydown", keyboard);
    return () => window.removeEventListener("keydown", keyboard);
  });
  async function retry() {
    if (!selected) return;
    try {
      await request(`/api/jobs/${selected}/retry`, { method: "POST" });
      setError("");
      setJob((j) =>
        j ? { ...j, status: "queued", stage: "queued", progress: 0 } : j,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không thử lại được.");
    }
  }
  function onView(updated: ResultView) {
    setView(updated);
    setError("");
  }
  function onQueued() {
    refreshResult.current = true;
    setJob((j) => (j ? { ...j, status: "queued", stage: "M6" } : j));
  }
  const dropzone = (
    <div
      className={`dropzone ${dragging ? "dragging" : ""}`}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        void upload(e.dataTransfer.files[0]);
      }}
    >
      <span className="upload-symbol">
        <Icon name="upload" width="28" height="28" />
      </span>
      <h3>Kéo bản ghi vào đây</h3>
      <p>Hoặc chọn file từ máy tính của bạn</p>
      <button
        className="button primary"
        disabled={uploading}
        onClick={() => input.current?.click()}
      >
        {uploading ? "Đang tải lên…" : "Chọn bản ghi"}
      </button>
      <small>WAV, MP3, M4A · tối đa 200 MB</small>
    </div>
  );

  return (
    <div className={`workspace ${view ? "with-player" : ""}`}>
      <input
        ref={input}
        type="file"
        accept=".wav,.mp3,.m4a"
        aria-label="Chọn bản ghi cuộc họp"
        className="sr-only"
        onChange={(e) => void upload(e.target.files?.[0])}
      />
      <aside className="sidebar">
        <button className="brand" onClick={library}>
          <span className="brand-mark">
            <Icon name="audio" width="25" height="25" />
          </span>
          <span>
            Meeting Notes<small>Không gian cuộc họp</small>
          </span>
        </button>
        <button
          className="button primary new-meeting"
          onClick={() => setDialog("upload")}
          disabled={uploading}
        >
          <Icon name="plus" />
          Cuộc họp mới
        </button>
        <button
          className={`sidebar-nav ${!selected ? "active" : ""}`}
          onClick={library}
        >
          <Icon name="library" />
          Thư viện cuộc họp<span>{jobs.length}</span>
        </button>
        <div className="sidebar-title">GẦN ĐÂY</div>
        <nav aria-label="Cuộc họp gần đây" className="job-list">
          {jobs.slice(0, 12).map((item) => (
            <button
              key={item.id}
              className={`job-link ${selected === item.id ? "active" : ""}`}
              onClick={() => choose(item.id)}
            >
              <Icon name="audio" width="17" />
              <span>
                <strong>{item.filename}</strong>
                <small>{date(item.created)}</small>
              </span>
              <span className={`status-dot ${item.status}`} />
            </button>
          ))}
          {!jobs.length && (
            <p className="sidebar-empty">Bản ghi của bạn sẽ xuất hiện ở đây.</p>
          )}
        </nav>
        <div className="sidebar-bottom">
          <span className="local-dot" />
          <div>
            Lưu trong không gian của bạn
            <small>Nghe, kiểm tra và giữ bản gốc</small>
          </div>
        </div>
      </aside>
      <main className="main-content">
        <header className="topbar">
          <div className="breadcrumb">
            <button onClick={library}>Thư viện</button>
            {selected && (
              <>
                <Icon name="next" width="14" />
                <span>Chi tiết cuộc họp</span>
              </>
            )}
          </div>
          <span className="topbar-label">TRỢ LÝ CUỘC HỌP TIẾNG VIỆT</span>
        </header>
        {error && !dialog && (
          <div className="alert" role="alert">
            <Icon name="alert" />
            <span>{error}</span>
            <button
              aria-label="Đóng thông báo"
              className="icon-button"
              onClick={() => setError("")}
            >
              <Icon name="close" />
            </button>
          </div>
        )}
        {!selected ? (
          <div className="library-page">
            <div className="page-heading">
              <div>
                <span className="eyebrow">KHÔNG BỎ LỠ ĐIỀU QUAN TRỌNG</span>
                <h1>
                  {jobs.length
                    ? "Thư viện cuộc họp"
                    : "Ghi lại những điều quan trọng."}
                </h1>
                <p>
                  Nghe lại, soát nội dung và biến cuộc họp thành những bước tiếp
                  theo.
                </p>
              </div>
              {!!jobs.length && (
                <button
                  className="button primary"
                  onClick={() => setDialog("upload")}
                >
                  <Icon name="upload" />
                  Tải bản ghi
                </button>
              )}
            </div>
            {jobs.length ? (
              <>
                <div className="library-stats">
                  <div>
                    <Icon name="audio" />
                    <span>
                      <strong>{jobs.length}</strong> bản ghi
                    </span>
                  </div>
                  <div>
                    <Icon name="check" />
                    <span>
                      <strong>
                        {jobs.filter((j) => j.status === "complete").length}
                      </strong>{" "}
                      đã xử lý
                    </span>
                  </div>
                  <div>
                    <Icon name="history" />
                    <span>
                      <strong>
                        {
                          jobs.filter((j) =>
                            ["queued", "running"].includes(j.status),
                          ).length
                        }
                      </strong>{" "}
                      đang xử lý
                    </span>
                  </div>
                </div>
                <div className="library-list-heading">
                  <h2>Tất cả bản ghi</h2>
                  <label className="search-field">
                    <Icon name="search" width="17" />
                    <input
                      aria-label="Tìm cuộc họp"
                      placeholder="Tìm tên cuộc họp…"
                      value={librarySearch}
                      onChange={(e) => setLibrarySearch(e.target.value)}
                    />
                  </label>
                </div>
                <div className="meeting-table">
                  <div className="meeting-table-head">
                    <span>CUỘC HỌP</span>
                    <span>NGÀY TẢI</span>
                    <span>TRẠNG THÁI</span>
                    <span />
                  </div>
                  {jobs
                    .filter((j) =>
                      j.filename
                        .toLocaleLowerCase("vi")
                        .includes(librarySearch.toLocaleLowerCase("vi")),
                    )
                    .map((item) => (
                      <button
                        className="meeting-row"
                        key={item.id}
                        onClick={() => choose(item.id)}
                      >
                        <span className="meeting-name">
                          <span className="record-icon">
                            <Icon name="audio" />
                          </span>
                          <span>
                            <strong>{item.filename}</strong>
                            <small>Bản ghi tiếng Việt</small>
                          </span>
                        </span>
                        <span className="meeting-date">
                          {date(item.created)}
                        </span>
                        <span
                          className={`badge ${item.status === "failed" ? "warning" : item.status === "complete" ? "success" : "neutral"}`}
                        >
                          {stages[item.stage] || item.stage}
                        </span>
                        <Icon name="next" width="17" />
                      </button>
                    ))}
                  {!jobs.some((j) =>
                    j.filename
                      .toLocaleLowerCase("vi")
                      .includes(librarySearch.toLocaleLowerCase("vi")),
                  ) && (
                    <p className="panel-empty">
                      Không tìm thấy cuộc họp phù hợp.
                    </p>
                  )}
                </div>
              </>
            ) : (
              <div className="onboarding-grid">
                {dropzone}
                <div className="onboarding-notes">
                  <span className="eyebrow">TỪ BẢN GHI ĐẾN BIÊN BẢN</span>
                  {[
                    [
                      "01",
                      "Nghe và kiểm tra",
                      "Transcript có người nói và mốc thời gian; ưu tiên đoạn cần soát.",
                    ],
                    [
                      "02",
                      "Giữ đúng nội dung",
                      "Sửa lời nói, xác nhận người nói và giữ lại bản model ban đầu.",
                    ],
                    [
                      "03",
                      "Theo dõi quyết định",
                      "Biên bản có dẫn chứng để đọc nhanh và nghe lại khi cần.",
                    ],
                  ].map(([n, title, desc]) => (
                    <div className="onboarding-step" key={n}>
                      <span>{n}</span>
                      <div>
                        <h3>{title}</h3>
                        <p>{desc}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="meeting-page">
            <div className="page-heading meeting-heading">
              <div>
                <div className="meeting-kicker">
                  <span className="eyebrow">BẢN GHI CUỘC HỌP</span>
                  <span
                    className={`badge ${job?.status === "complete" ? "success" : job?.status === "failed" ? "warning" : "neutral"}`}
                  >
                    {job ? stages[job.stage] || job.stage : "Đang tải…"}
                  </span>
                </div>
                <h1>{job?.filename || "Đang mở cuộc họp…"}</h1>
                <p>
                  {job && date(job.created)}
                  {minutes && (
                    <>
                      {" "}
                      · {time(minutes.duration)} · {minutes.num_speakers} người
                      nói
                    </>
                  )}
                </p>
              </div>
              {view && (
                <div className="header-actions">
                  <button
                    className="button secondary"
                    onClick={() => setDialog("history")}
                  >
                    <Icon name="history" />
                    Lịch sử
                  </button>
                  <details className="export-menu">
                    <summary className="button primary">
                      <Icon name="download" />
                      Xuất biên bản
                    </summary>
                    <div>
                      {["md", "srt", "pdf"].map((fmt) => (
                        <a
                          key={fmt}
                          href={`${API}/api/jobs/${selected}/export?fmt=${fmt}`}
                          download
                        >
                          {fmt === "md" ? "Markdown" : fmt.toUpperCase()} ↗
                        </a>
                      ))}
                    </div>
                  </details>
                </div>
              )}
            </div>
            {busy && (
              <div
                className={`processing ${view ? "compact" : ""}`}
                role="status"
              >
                <span className="processing-symbol">
                  <Icon name="audio" width="30" height="30" />
                </span>
                <div>
                  <h2>{stages[job?.stage || "queued"]}</h2>
                  <p>
                    {job?.stage === "M6"
                      ? "Đang tạo biên bản từ transcript hiện tại."
                      : "Bạn có thể mở cuộc họp khác; bản ghi vẫn tiếp tục được xử lý."}
                  </p>
                  <progress
                    aria-label="Tiến độ xử lý"
                    max="1"
                    value={job?.progress || 0}
                  />
                  <div className="processing-stages">
                    {["M1", "M2", "M3", "M4", "M5"].map((s) => (
                      <span
                        key={s}
                        className={job?.stage === s ? "current" : ""}
                      >
                        {stages[s]}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            )}
            {job?.status === "failed" && (
              <div className="failure-state" role="status">
                <Icon name="alert" width="30" height="30" />
                <div>
                  <h2>
                    {view
                      ? "Chưa tạo được biên bản"
                      : "Chưa xử lý được bản ghi"}
                  </h2>
                  <p>{job.error || "Vui lòng thử lại."}</p>
                  <button
                    className="button primary"
                    onClick={() => void retry()}
                  >
                    Thử lại
                  </button>
                </div>
              </div>
            )}
            {!job && !error && (
              <div className="panel-empty" role="status">
                Đang tải cuộc họp…
              </div>
            )}
            {job?.status === "complete" && !view && (
              <div className="notice warning">
                Chưa tải được kết quả. Hãy mở lại cuộc họp từ thư viện.
              </div>
            )}
            {view && minutes && (
              <>
                <div className="review-overview">
                  <div className="review-progress">
                    <span className="review-icon">
                      <Icon name="check" />
                    </span>
                    <div>
                      <strong>
                        {reviewed}/{allTurns.length} lượt đã soát
                      </strong>
                      <progress
                        aria-label="Tiến độ soát transcript"
                        value={reviewed}
                        max={Math.max(allTurns.length, 1)}
                      />
                    </div>
                  </div>
                  <div className="review-remaining">
                    <span className="badge warning">
                      {pendingTurns.length} đoạn cần soát
                    </span>
                    <span className="subtle">Ưu tiên đoạn có tín hiệu lỗi</span>
                  </div>
                  <button
                    className="button secondary small"
                    onClick={nextPending}
                    disabled={!pendingTurns.length}
                  >
                    Đoạn cần soát tiếp <Icon name="next" width="15" />
                  </button>
                </div>
                <div className="workspace-toolbar">
                  <div
                    role="tablist"
                    aria-label="Nội dung cuộc họp"
                    className="tabs"
                  >
                    {[
                      ["transcript", "Transcript", "note"],
                      ["timeline", "Timeline", "timeline"],
                      ["summary", "Tóm tắt & công việc", "check"],
                      ["ask", "Hỏi đáp", "chat"],
                    ].map(([key, label, icon]) => (
                      <button
                        key={key}
                        role="tab"
                        aria-selected={tab === key}
                        aria-controls={`panel-${key}`}
                        id={`tab-${key}`}
                        onClick={() => setTab(key)}
                      >
                        <Icon
                          name={icon as "note" | "timeline" | "check" | "chat"}
                          width="17"
                        />
                        {label}
                      </button>
                    ))}
                  </div>
                  <button
                    className="button quiet small"
                    onClick={() => setDialog("speakers")}
                  >
                    <Icon name="users" width="17" />
                    Người nói
                  </button>
                </div>
                {tab === "ask" ? (
                  <AskMeetingPanel
                    key={selected}
                    jobId={selected}
                    view={view}
                    enabled={askEnabled}
                    busy={!!busy}
                    onSource={(turn) => seek(turn, true)}
                  />
                ) : (
                  <div className={`review-grid tab-${tab}`}>
                    <section
                      className="transcript-panel"
                      id={`panel-${tab === "summary" ? "transcript" : tab}`}
                      aria-label={
                        tab === "timeline"
                          ? "Timeline người nói"
                          : "Transcript cuộc họp"
                      }
                    >
                      {tab === "timeline" ? (
                        <>
                          <div className="panel-heading">
                            <div>
                              <span className="eyebrow">
                                AI NÓI, VÀO LÚC NÀO
                              </span>
                              <h2>Timeline người nói</h2>
                            </div>
                            <span className="subtle">
                              {time(minutes.duration)}
                            </span>
                          </div>
                          <div className="timeline-axis">
                            <span>00:00</span>
                            <span>{time(minutes.duration / 2)}</span>
                            <span>{time(minutes.duration)}</span>
                          </div>
                          {speakers.map((id, i) => (
                            <div className="timeline-row" key={id}>
                              <span className={`speaker-avatar color-${i % 6}`}>
                                {(view.speaker_names[id] || id)
                                  .slice(0, 1)
                                  .toUpperCase()}
                              </span>
                              <strong>{view.speaker_names[id] || id}</strong>
                              <div className="timeline-track">
                                {allTurns
                                  .filter((t) => speakerId(t) === id)
                                  .map((turn) => (
                                    <button
                                      key={turn.turn_id}
                                      className={`timeline-segment color-${i % 6} ${activeId === turn.turn_id ? "active" : ""}`}
                                      style={{
                                        left: `${(turn.start / Math.max(minutes.duration, 1)) * 100}%`,
                                        width: `${Math.max(0.4, ((turn.end - turn.start) / Math.max(minutes.duration, 1)) * 100)}%`,
                                      }}
                                      aria-label={`${turn.speaker}, ${time(turn.start)}: ${turn.text}`}
                                      title={`${time(turn.start)}–${time(turn.end)} · ${turn.text}`}
                                      onClick={() => seek(turn)}
                                    />
                                  ))}
                              </div>
                            </div>
                          ))}
                          <p className="hint timeline-hint">
                            Chọn một lượt để nghe. Các lượt chồng lấn có thể
                            xuất hiện trên nhiều hàng.
                          </p>
                        </>
                      ) : (
                        <>
                          <div className="transcript-toolbar">
                            <label className="search-field">
                              <Icon name="search" width="16" />
                              <input
                                type="search"
                                aria-label="Tìm trong transcript"
                                placeholder="Tìm nội dung, người nói…"
                                value={search}
                                onChange={(e) => setSearch(e.target.value)}
                              />
                            </label>
                            <button
                              className={`filter-button ${onlyFlagged ? "active" : ""}`}
                              aria-pressed={onlyFlagged}
                              onClick={() => setOnlyFlagged(!onlyFlagged)}
                            >
                              <Icon name="flag" width="15" />
                              Cần soát <span>{pendingTurns.length}</span>
                            </button>
                          </div>
                          <div className="transcript-caption">
                            <span>
                              {turns.length} lượt nói
                              {onlyFlagged
                                ? " · ưu tiên theo độ tin cậy"
                                : " · theo thời gian"}
                            </span>
                            <span>
                              <kbd>N</kbd> đoạn cần soát tiếp
                            </span>
                          </div>
                          <div className="turn-list">
                            {turns.map((turn) => (
                              <article
                                key={turn.turn_id}
                                ref={(node) => {
                                  if (node)
                                    turnNodes.current.set(turn.turn_id, node);
                                  else turnNodes.current.delete(turn.turn_id);
                                }}
                                className={`turn ${turn.flagged && !turn.reviewed ? "flagged" : ""} ${activeId === turn.turn_id ? "selected" : ""}`}
                                data-turn-id={turn.turn_id}
                              >
                                <div className="turn-meta">
                                  <span
                                    className={`speaker-avatar color-${Math.max(0, speakers.indexOf(speakerId(turn))) % 6}`}
                                  >
                                    {turn.speaker.slice(0, 1).toUpperCase()}
                                  </span>
                                  <strong>{turn.speaker}</strong>
                                  <button
                                    className="turn-time"
                                    onClick={() => seek(turn)}
                                    aria-label={`Nghe lượt ${time(turn.start)}`}
                                  >
                                    {time(turn.start)}–{time(turn.end)}
                                  </button>
                                  {turn.reviewed ? (
                                    <span className="badge success review-label">
                                      ✓ Đã soát
                                    </span>
                                  ) : turn.flagged ? (
                                    <span className="badge warning review-label">
                                      Cần soát
                                    </span>
                                  ) : null}
                                  <button
                                    className="icon-button turn-play"
                                    onClick={() => seek(turn)}
                                    aria-label={`Phát lượt ${time(turn.start)}`}
                                  >
                                    <Icon name="play" width="15" />
                                  </button>
                                </div>
                                <p className="turn-text">
                                  {turn.text || (
                                    <span className="subtle">
                                      Không có lời phiên âm.
                                    </span>
                                  )}
                                </p>
                                {turn.flagged && !turn.reviewed && (
                                  <p className="flag-reasons">
                                    <Icon name="alert" width="13" />
                                    {turn.flag_reasons.join(" · ") ||
                                      "Cần nghe lại để xác nhận nội dung và người nói"}
                                  </p>
                                )}
                                <TurnEditor
                                  jobId={selected}
                                  view={view}
                                  turn={turn}
                                  onView={onView}
                                  onError={setError}
                                />
                              </article>
                            ))}
                            {!turns.length && (
                              <div className="panel-empty">
                                <Icon
                                  name={onlyFlagged ? "check" : "search"}
                                  width="28"
                                  height="28"
                                />
                                <h3>
                                  {onlyFlagged && !search
                                    ? "Đã soát hết các đoạn được gắn cờ"
                                    : "Không tìm thấy lượt nói"}
                                </h3>
                                <p>
                                  {onlyFlagged
                                    ? "Bạn vẫn có thể kiểm tra các lượt còn lại trong transcript."
                                    : "Thử từ khóa khác hoặc bỏ bộ lọc."}
                                </p>
                              </div>
                            )}
                          </div>
                        </>
                      )}
                    </section>
                    <div className="minutes-column" id="panel-summary">
                      <MinutesPanel
                        key={selected}
                        jobId={selected}
                        view={view}
                        enabled={llmEnabled}
                        busy={!!busy}
                        onSource={(turn) => seek(turn, true)}
                        onQueued={onQueued}
                        onError={setError}
                      />
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </main>
      {view && minutes && selected && (
        <MeetingPlayer
          key={selected}
          jobId={selected}
          duration={minutes.duration}
          audioRef={audio}
          activeTurn={activeTurn}
          loop={loop}
          onLoop={setLoop}
          onTime={(position) => {
            if (seekTarget.current !== null) {
              if (Math.abs(position - seekTarget.current) > 1) return;
              seekTarget.current = null;
            }
            if (!loop) {
              const turn = allTurns.find(
                (t) => position >= t.start && position < t.end,
              );
              if (turn) setActiveId(turn.turn_id);
            }
          }}
          onError={setError}
        />
      )}
      {dialog === "upload" && (
        <Modal title="Tải bản ghi cuộc họp" onClose={() => setDialog(null)}>
          <p className="dialog-intro">
            Chọn bản ghi để phiên âm, phân người nói và tạo biên bản.
          </p>
          {error && (
            <div role="alert" className="alert">
              {error}
            </div>
          )}
          {dropzone}
        </Modal>
      )}
      {dialog === "speakers" && view && selected && (
        <SpeakersDialog
          jobId={selected}
          view={view}
          onView={onView}
          onError={setError}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === "history" && view && selected && (
        <HistoryDialog
          jobId={selected}
          view={view}
          onClose={() => setDialog(null)}
        />
      )}
    </div>
  );
}
