"use client";

import { useEffect, useRef, useState } from "react";
import { date, duration, eta, Job, notifyDone, request } from "@/lib/api";
import type { Toast } from "./MeetingApp";
import { Icon } from "./Icon";
import { UploadDialog, useDropUpload } from "./ReviewControls";

export const STAGES: Record<string, string> = {
  queued: "Đang chờ xử lý",
  M1: "Đang chuẩn bị bản ghi",
  M2: "Đang phân biệt người nói",
  M3: "Đang chép lời",
  M4: "Đang sắp xếp lượt nói",
  M5: "Đang chọn đoạn cần nghe lại",
  M6: "Đang tạo biên bản",
  complete: "Xong",
  failed: "Xử lý chưa thành công",
};

type Filter = "all" | "todo" | "done";

/** What the user still has to do with a meeting, most urgent first. */
export function meetingStatus(job: Job): {
  label: string;
  tone: "warn" | "ok" | "plain" | "busy";
  todo: boolean;
} {
  if (job.status === "queued" || job.status === "running")
    return {
      label: STAGES[job.stage] || "Đang xử lý",
      tone: "busy",
      todo: false,
    };
  if (job.status === "failed")
    return { label: "Xử lý lỗi", tone: "warn", todo: true };
  const o = job.overview;
  if (job.finalized) return { label: "Đã chốt", tone: "ok", todo: false };
  if (!o) return { label: "Sẵn sàng", tone: "plain", todo: true };
  if (!o.has_minutes)
    return { label: "Chưa có biên bản", tone: "plain", todo: true };
  if (o.to_review)
    return {
      label: `${o.to_review} mục cần nghe lại`,
      tone: "warn",
      todo: true,
    };
  if (o.unnamed_speakers)
    return { label: "Chưa đặt tên người nói", tone: "plain", todo: true };
  if (o.summary_stale)
    return { label: "Biên bản cần tạo lại", tone: "warn", todo: true };
  return { label: "Sẵn sàng chốt", tone: "plain", todo: true };
}

function outcome(job: Job) {
  const o = job.overview;
  if (!o || !o.has_minutes) return null;
  const parts = [];
  if (o.decisions) parts.push(`${o.decisions} quyết định`);
  if (o.actions)
    parts.push(
      o.actions_done
        ? `${o.actions_done}/${o.actions} việc xong`
        : `${o.actions} việc`,
    );
  return parts.join(" · ") || "Không có việc";
}

export function Library({
  onOpen,
  onUpload,
  onError,
  onToast,
  themeButton,
}: {
  onOpen: (id: string) => void;
  onUpload: () => void;
  onError: (error: string) => void;
  onToast: (toast: Toast) => void;
  themeButton: React.ReactNode;
}) {
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [dropped, setDropped] = useState<File | null>(null);
  const [now, setNow] = useState(() => Date.now() / 1000);
  const seen = useRef(new Map<string, Job["status"]>());
  // Parent callbacks change identity every render; polling must not restart for that.
  const callbacks = useRef({ onToast, onOpen });
  callbacks.current = { onToast, onOpen };
  const busy = jobs?.some(
    (j) => j.status === "queued" || j.status === "running",
  );

  useEffect(() => {
    let active = true;
    const load = () =>
      request<Job[]>("/api/jobs")
        .then((list) => {
          if (!active) return;
          // Tell the user when a job they saw processing finishes.
          for (const job of list) {
            const before = seen.current.get(job.id);
            if (
              (before === "queued" || before === "running") &&
              (job.status === "complete" || job.status === "failed")
            ) {
              const ok = job.status === "complete";
              notifyDone(job.title, ok);
              callbacks.current.onToast({
                text: `${job.title}: ${ok ? "đã xử lý xong" : "xử lý chưa thành công"}`,
                actions: [
                  {
                    label: "Mở",
                    onClick: () => callbacks.current.onOpen(job.id),
                  },
                ],
              });
            }
            seen.current.set(job.id, job.status);
          }
          setJobs(list);
        })
        .catch(() => active && onError("Không tải được thư viện cuộc họp."));
    void load();
    const timer = setInterval(
      () => {
        setNow(Date.now() / 1000);
        void load();
      },
      busy ? 2000 : 15000,
    );
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [busy, onError]);

  const drop = useDropUpload(setDropped);
  const q = query.trim().toLocaleLowerCase("vi");
  const processing = (jobs || []).filter(
    (j) => j.status === "queued" || j.status === "running",
  );
  const rows = (jobs || [])
    .filter((j) => !processing.includes(j))
    .filter((j) => !q || j.title.toLocaleLowerCase("vi").includes(q))
    .filter((j) => {
      const s = meetingStatus(j);
      return filter === "all" || (filter === "todo" ? s.todo : !s.todo);
    });

  return (
    <div
      className={`library ${drop.dragging ? "dragging" : ""}`}
      {...drop.handlers}
    >
      <header className="library-bar">
        <div className="brand">
          <svg width="28" height="28" viewBox="0 0 28 28" aria-hidden="true">
            <rect width="28" height="28" rx="8" fill="var(--ink)" />
            <path
              d="M8 17v-6M12 20V8M16 16v-4M20 18v-8"
              stroke="var(--bg)"
              strokeWidth="2.2"
              strokeLinecap="round"
            />
          </svg>
          Meeting Notes
        </div>
        <label className="search">
          <Icon name="search" width="16" />
          <span className="sr-only">Tìm cuộc họp</span>
          <input
            type="search"
            placeholder="Tìm cuộc họp…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        {themeButton}
        <button className="btn primary" onClick={onUpload}>
          <Icon name="upload" width="18" />
          Tải bản ghi
        </button>
      </header>

      <main className="library-main">
        <h1>Cuộc họp</h1>
        <p className="lede">Mỗi cuộc họp cho biết còn gì cần bạn làm.</p>

        {jobs && !jobs.length && (
          <div className="onboarding">
            <button className="dropzone big" onClick={onUpload}>
              <Icon name="upload" width="30" height="30" />
              <strong>Kéo bản ghi cuộc họp vào đây</strong>
              <span>WAV, MP3, M4A · tối đa 200 MB</span>
            </button>
            <ol className="steps">
              <li>
                <b>Chép lời và phân biệt người nói</b>
                <span>Khoảng 6–7 phút cho cuộc họp 30 phút.</span>
              </li>
              <li>
                <b>Đặt tên người nói</b>
                <span>Nghe thử vài giây mỗi giọng.</span>
              </li>
              <li>
                <b>Chốt biên bản</b>
                <span>
                  Quyết định và việc cần làm có dẫn chứng để nghe lại.
                </span>
              </li>
            </ol>
          </div>
        )}

        {processing.map((job) => (
          <button
            key={job.id}
            className="processing-row"
            onClick={() => onOpen(job.id)}
          >
            <span className="row-title">{job.title}</span>
            <span className="muted">
              {STAGES[job.stage] || "Đang xử lý"} ·{" "}
              {eta(job.eta_sec) ||
                `đã chạy ${Math.max(0, Math.round((now - job.created) / 60))} phút`}
            </span>
            <span className="bar">
              <span style={{ width: `${Math.round(job.progress * 100)}%` }} />
            </span>
          </button>
        ))}

        {!!jobs?.length && (
          <div className="filters" role="group" aria-label="Lọc cuộc họp">
            {(
              [
                ["all", "Tất cả"],
                ["todo", "Cần xử lý"],
                ["done", "Đã chốt"],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                className={`pill ${filter === key ? "on" : ""}`}
                aria-pressed={filter === key}
                onClick={() => setFilter(key)}
              >
                {label}
              </button>
            ))}
          </div>
        )}

        <div className="meeting-list">
          {jobs === null && (
            <div className="skeleton-rows" aria-hidden="true" />
          )}
          {rows.map((job, index) => {
            const s = meetingStatus(job);
            const o = job.overview;
            return (
              <button
                key={job.id}
                className="meeting-row"
                style={{ animationDelay: `${Math.min(index, 8) * 30}ms` }}
                onClick={() => onOpen(job.id)}
              >
                <span className="row-main">
                  <span className="row-title">{job.title}</span>
                  <span className={`tag ${s.tone}`}>{s.label}</span>
                </span>
                <span className="row-meta">
                  <span>{date(job.created)}</span>
                  {o && <span>{duration(o.duration)}</span>}
                  {o && (
                    <span
                      className="dots"
                      aria-label={`${o.speakers} người nói`}
                    >
                      {Array.from(
                        { length: Math.min(o.speakers, 6) },
                        (_, i) => (
                          <i key={i} className={`sp${i}`} />
                        ),
                      )}
                      <span>{o.speakers} người</span>
                    </span>
                  )}
                  {outcome(job) && <span>{outcome(job)}</span>}
                </span>
                <Icon name="next" width="18" className="row-go" />
              </button>
            );
          })}
          {!!jobs?.length && !rows.length && !processing.length && (
            <p className="empty">Không có cuộc họp nào khớp.</p>
          )}
        </div>
      </main>
      {dropped && (
        <UploadDialog
          initialFile={dropped}
          onClose={() => setDropped(null)}
          onUploaded={(id) => {
            setDropped(null);
            onOpen(id);
          }}
        />
      )}
    </div>
  );
}
