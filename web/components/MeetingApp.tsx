"use client";

import { useEffect, useRef, useState } from "react";
import { API, Job, request, ResultView, time } from "@/lib/api";
import {
  ReviewControls,
  SummaryButton,
  TurnEditor,
} from "@/components/ReviewControls";

const stages: Record<string, string> = {
  queued: "Đang chờ xử lý",
  M1: "Chuẩn hóa bản ghi",
  M2: "Phân biệt người nói",
  M3: "Phiên âm nội dung",
  M4: "Sắp xếp lượt nói",
  M5: "Chọn đoạn cần soát",
  M6: "Tạo tóm tắt",
  complete: "Đã xử lý",
  failed: "Xử lý chưa thành công",
};

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
  const [llmEnabled, setLlmEnabled] = useState(false);
  const audio = useRef<HTMLAudioElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const refreshResult = useRef(false);

  useEffect(() => {
    const id =
      new URLSearchParams(window.location.search).get("job") ||
      localStorage.getItem("meetingJobId");
    if (id) setSelected(id);
    request<Job[]>("/api/jobs")
      .then(setJobs)
      .catch(() => setError("Chưa kết nối được dịch vụ xử lý."));
    request<{ llm_enabled: boolean }>("/api/health")
      .then((health) => setLlmEnabled(health.llm_enabled))
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
    const poll = async () => {
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
            setView(result);
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
    };
    void poll();
    const timer = setInterval(poll, 1800);
    return () => {
      active = false;
      controller.abort();
      clearInterval(timer);
    };
  }, [selected]);

  function choose(id: string) {
    localStorage.setItem("meetingJobId", id);
    setSelected(id);
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

  function seek(start: number) {
    if (audio.current) {
      audio.current.currentTime = start;
      void audio.current.play().catch(() => {});
    }
  }

  async function retry() {
    if (!selected) return;
    try {
      await request(`/api/jobs/${selected}/retry`, { method: "POST" });
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không thử lại được.");
    }
  }

  const minutes = view?.edited;
  const turns =
    minutes?.turns.filter(
      (t) =>
        (!onlyFlagged || (t.flagged && !t.reviewed)) &&
        `${t.text} ${t.speaker}`
          .toLocaleLowerCase("vi")
          .includes(search.toLocaleLowerCase("vi")),
    ) || [];
  const speakers = [
    ...new Set(minutes?.turns.map((t) => t.original_speaker) || []),
  ];

  return (
    <div className="workspace">
      <aside className="sidebar">
        <a className="brand" href="/">
          <span className="brand-mark">≋</span>
          <span>
            Meeting<span className="brand-light"> Notes</span>
          </span>
        </a>
        <p className="sidebar-label">KHÔNG GIAN LÀM VIỆC</p>
        <button
          className="new-meeting"
          onClick={() => input.current?.click()}
          disabled={uploading}
        >
          ＋ Cuộc họp mới
        </button>
        <div className="sidebar-title">
          Bản ghi gần đây <span>{jobs.length}</span>
        </div>
        <nav aria-label="Cuộc họp gần đây" className="job-list">
          {jobs.map((item) => (
            <button
              key={item.id}
              className={`job-link ${selected === item.id ? "active" : ""}`}
              onClick={() => choose(item.id)}
            >
              <span className={`status-dot ${item.status}`} />
              <span>
                <strong>{item.filename}</strong>
                <small>
                  {new Date(item.created * 1000).toLocaleDateString("vi-VN")} ·{" "}
                  {stages[item.stage] || item.stage}
                </small>
              </span>
            </button>
          ))}
          {!jobs.length && (
            <p className="muted sidebar-empty">
              Các bản ghi của bạn sẽ xuất hiện ở đây.
            </p>
          )}
        </nav>
        <div className="sidebar-footer">
          <span className="avatar">VI</span>
          <div>
            <strong>Biên bản tiếng Việt</strong>
            <small>Không gian cá nhân</small>
          </div>
        </div>
      </aside>
      <main>
        <header className="topbar">
          <span>
            Không gian làm việc <span className="muted">/</span>{" "}
            <strong>{job ? "Chi tiết cuộc họp" : "Tổng quan"}</strong>
          </span>
          <span className="local-badge">● Bản demo local</span>
        </header>
        <div className="content">
          <div className="page-heading">
            <div>
              <p className="eyebrow">TỪ CUỘC TRÒ CHUYỆN ĐẾN HÀNH ĐỘNG</p>
              <h1>{job?.filename || "Ghi lại những điều quan trọng."}</h1>
              <p className="muted">
                Phiên âm theo người nói, soát lại nội dung và lưu biên bản của
                bạn.
              </p>
            </div>
          </div>
          {error && (
            <div className="alert error" role="alert">
              {error}
              <button aria-label="Đóng thông báo" onClick={() => setError("")}>
                ×
              </button>
            </div>
          )}
          <input
            ref={input}
            type="file"
            accept=".wav,.mp3,.m4a"
            className="hidden-input"
            aria-label="Chọn bản ghi cuộc họp"
            onChange={(event) => void upload(event.target.files?.[0])}
          />
          {!selected && (
            <>
              <section
                className={`dropzone ${dragging ? "dragging" : ""}`}
                onDragOver={(event) => {
                  event.preventDefault();
                  setDragging(true);
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={(event) => {
                  event.preventDefault();
                  setDragging(false);
                  void upload(event.dataTransfer.files[0]);
                }}
              >
                <div className="upload-symbol">↥</div>
                <h2>Bắt đầu với một bản ghi</h2>
                <p>Kéo thả file vào đây hoặc chọn từ máy của bạn.</p>
                <button
                  className="primary"
                  onClick={() => input.current?.click()}
                  disabled={uploading}
                >
                  {uploading ? "Đang tải lên…" : "Chọn bản ghi"}
                </button>
                <small>WAV, MP3, M4A · Tối đa 200 MB</small>
              </section>
              <div className="feature-grid">
                {[
                  [
                    "01",
                    "Lắng nghe",
                    "Nội dung được phiên âm kèm người nói và thời gian.",
                  ],
                  [
                    "02",
                    "Soát lại",
                    "Tập trung vào những đoạn cần bạn kiểm tra.",
                  ],
                  [
                    "03",
                    "Lưu biên bản",
                    "Chỉnh sửa và xuất nội dung để chia sẻ.",
                  ],
                ].map(([n, title, text]) => (
                  <div className="feature" key={n}>
                    <span>{n}</span>
                    <h3>{title}</h3>
                    <p>{text}</p>
                  </div>
                ))}
              </div>
            </>
          )}
          {selected && !job && (
            <div className="card empty-state">Đang tải cuộc họp…</div>
          )}
          {job && (job.status === "queued" || job.status === "running") && (
            <section className="card processing" aria-live="polite">
              <div className="processing-title">
                <span className="spinner" />
                <h2>{stages[job.stage] || "Đang xử lý"}</h2>
                <span>{Math.round(job.progress * 100)}%</span>
              </div>
              <div className="progress-track">
                <div style={{ width: `${job.progress * 100}%` }} />
              </div>
              <p className="muted">
                Bạn có thể rời trang. Kết quả sẽ được lưu khi xử lý xong.
              </p>
            </section>
          )}
          {job?.status === "failed" && (
            <div className="alert error">
              <div>
                <strong>Xử lý chưa thành công</strong>
                <p>{job.error}</p>
              </div>
              <button onClick={() => void retry()}>Thử lại</button>
            </div>
          )}
          {minutes && view && job && (
            <>
              <div className="stats">
                <div>
                  <small>THỜI LƯỢNG BẢN GHI</small>
                  <strong>{time(minutes.duration)}</strong>
                </div>
                <div>
                  <small>NGƯỜI NÓI</small>
                  <strong>
                    {minutes.num_speakers.toString().padStart(2, "0")}
                  </strong>
                </div>
                <div>
                  <small>LƯỢT NÓI</small>
                  <strong>{minutes.turns.length}</strong>
                </div>
                <div>
                  <small>LƯỢT CẦN SOÁT</small>
                  <strong className="amber">
                    {
                      minutes.turns.filter((t) => t.flagged && !t.reviewed)
                        .length
                    }
                  </strong>
                </div>
              </div>
              <section className="card result-card">
                <ReviewControls
                  jobId={job.id}
                  view={view}
                  onView={setView}
                  onError={setError}
                />
                <div className="player">
                  <span className="audio-icon">♫</span>
                  <div>
                    <strong>Bản ghi gốc</strong>
                    <small>Chọn mốc thời gian để nghe lại.</small>
                  </div>
                  <audio
                    ref={audio}
                    controls
                    preload="metadata"
                    src={`${API}/api/jobs/${job.id}/audio`}
                  />
                </div>
                <div
                  className="tabs"
                  role="tablist"
                  aria-label="Nội dung cuộc họp"
                >
                  {[
                    ["transcript", "Nội dung"],
                    ["timeline", "Timeline"],
                    ["summary", "Tóm tắt & công việc"],
                  ].map(([id, label]) => (
                    <button
                      role="tab"
                      aria-selected={tab === id}
                      key={id}
                      onClick={() => setTab(id)}
                      className={tab === id ? "selected" : ""}
                    >
                      {label}
                    </button>
                  ))}
                </div>
                {tab === "transcript" && (
                  <>
                    <div className="transcript-tools">
                      <input
                        type="search"
                        aria-label="Tìm trong transcript"
                        placeholder="Tìm trong nội dung…"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                      />
                      <label>
                        <input
                          type="checkbox"
                          checked={onlyFlagged}
                          onChange={(e) => setOnlyFlagged(e.target.checked)}
                        />{" "}
                        Chỉ đoạn cần soát
                      </label>
                    </div>
                    <div className="transcript-list">
                      {turns.map((turn) => (
                        <article
                          className={`turn ${turn.flagged && !turn.reviewed ? "flagged" : ""}`}
                          key={turn.turn_id}
                        >
                          <button
                            className="timestamp"
                            onClick={() => seek(turn.start)}
                            aria-label={`Nghe từ ${time(turn.start)}`}
                          >
                            ▷ {time(turn.start)}
                          </button>
                          <div className="turn-body">
                            <div className="turn-meta">
                              <span
                                className={`speaker color-${speakers.indexOf(turn.original_speaker) % 6}`}
                              >
                                {turn.speaker}
                              </span>
                              {turn.flagged && (
                                <span
                                  className={`review-label ${turn.reviewed ? "reviewed" : ""}`}
                                  title={turn.flag_reasons.join(" · ")}
                                >
                                  {turn.reviewed ? "✓ Đã soát" : "◉ Cần soát"}
                                </span>
                              )}
                            </div>
                            <p>
                              {turn.text || (
                                <em className="muted">
                                  Không nhận dạng được lời nói.
                                </em>
                              )}
                            </p>
                            {turn.flagged && !turn.reviewed && (
                              <small className="flag-reasons">
                                {turn.flag_reasons.join(" · ") ||
                                  "Được ưu tiên soát lại theo điểm tin cậy."}
                              </small>
                            )}
                            <TurnEditor
                              key={`${job.id}-${turn.turn_id}`}
                              jobId={job.id}
                              view={view}
                              turn={turn}
                              onView={setView}
                              onError={setError}
                            />
                          </div>
                        </article>
                      ))}
                      {!turns.length && (
                        <div className="empty-state">
                          Không có lượt nói phù hợp.
                        </div>
                      )}
                    </div>
                  </>
                )}
                {tab === "timeline" && (
                  <div className="timeline">
                    <p className="muted">
                      Các lượt nói chồng lấn có thể xuất hiện cùng thời điểm.
                    </p>
                    {speakers.map((speaker, i) => (
                      <div key={speaker} className="timeline-row">
                        <strong>
                          {view.speaker_names[speaker] || speaker}
                        </strong>
                        <div className="timeline-track">
                          {minutes.turns
                            .filter((t) => t.original_speaker === speaker)
                            .map((turn) => (
                              <button
                                key={turn.turn_id}
                                aria-label={`${turn.speaker}, ${time(turn.start)}: ${turn.text}`}
                                title={`${time(turn.start)}–${time(turn.end)} · ${turn.text}`}
                                className={`color-${i % 6}`}
                                style={{
                                  left: `${(turn.start / minutes.duration) * 100}%`,
                                  width: `${((turn.end - turn.start) / minutes.duration) * 100}%`,
                                }}
                                onClick={() => seek(turn.start)}
                              />
                            ))}
                        </div>
                      </div>
                    ))}
                    <div className="timeline-scale">
                      <span>00:00</span>
                      <span>{time(minutes.duration)}</span>
                    </div>
                  </div>
                )}
                {tab === "summary" && (
                  <div className="summary-content">
                    {llmEnabled && (
                      <SummaryButton
                        jobId={job.id}
                        disabled={
                          job.status === "queued" || job.status === "running"
                        }
                        onError={setError}
                        onQueued={() => {
                          refreshResult.current = true;
                          setJob({
                            ...job,
                            status: "queued",
                            stage: "queued",
                            progress: 0,
                          });
                        }}
                      />
                    )}
                    {view.summary_stale && (
                      <div className="alert warning">
                        Nội dung đã thay đổi. Tóm tắt và việc cần làm dưới đây
                        cần được tạo lại.
                      </div>
                    )}
                    {view.summary_error && (
                      <div className="alert warning">
                        Chưa tạo được tóm tắt: {view.summary_error}
                      </div>
                    )}
                    {minutes.summary ? (
                      <>
                        <h2>Tóm tắt cuộc họp</h2>
                        <p className="summary-text">{minutes.summary}</p>
                        <div className="topic-tags">
                          {minutes.topics.map((topic) => (
                            <span key={topic}>{topic}</span>
                          ))}
                        </div>
                        <h2>Việc cần làm</h2>
                        {minutes.action_items.length ? (
                          minutes.action_items.map((item, i) => (
                            <div className="action-item" key={i}>
                              <span className="action-check">□</span>
                              <div>
                                <strong>{item.task}</strong>
                                <p>
                                  {item.speaker} ·{" "}
                                  {item.deadline || "Chưa nêu thời hạn"}
                                  {item.uncertain ? " · Cần xác nhận" : ""}
                                </p>
                              </div>
                            </div>
                          ))
                        ) : (
                          <p className="muted">
                            Không có việc cần làm được nêu rõ.
                          </p>
                        )}
                      </>
                    ) : (
                      <div className="empty-state">
                        Cuộc họp này chưa có tóm tắt.
                      </div>
                    )}
                  </div>
                )}
              </section>
              <p className="footnote">
                Các đoạn cần soát chiếm{" "}
                {(minutes.flagged_ratio * 100).toFixed(1)}% tổng thời lượng lượt
                nói. Hãy nghe lại trước khi sử dụng nội dung quan trọng.
              </p>
            </>
          )}
        </div>
      </main>
    </div>
  );
}
