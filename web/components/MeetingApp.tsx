"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { API, Job, notifyDone, request, ResultView } from "@/lib/api";
import { Icon } from "./Icon";
import { Library } from "./Library";
import { Workspace } from "./Workspace";
import { SpeakersStep } from "./SpeakersStep";
import { ReviewMode } from "./ReviewMode";
import { UploadDialog } from "./ReviewControls";

export type Screen = "workspace" | "speakers" | "review";
export type Playback = {
  audio: React.RefObject<HTMLAudioElement | null>;
  position: number;
  playing: boolean;
  /** Seek and play; with `until`, pause there (snippets and review clips). */
  play: (from: number, until?: number) => void;
  toggle: () => void;
};
export type Toast = {
  text: string;
  links?: { label: string; href: string }[];
  actions?: { label: string; onClick: () => void }[];
};

function readUrl() {
  const params = new URLSearchParams(window.location.search);
  const screen = params.get("view");
  return {
    id: params.get("job"),
    screen: (screen === "speakers" || screen === "review"
      ? screen
      : "workspace") as Screen,
  };
}

export default function MeetingApp() {
  const [selected, setSelected] = useState<string | null>(null);
  const [screen, setScreen] = useState<Screen>("workspace");
  const [job, setJob] = useState<Job | null>(null);
  const [view, setView] = useState<ResultView | null>(null);
  const [error, setError] = useState("");
  const [llmEnabled, setLlmEnabled] = useState(false);
  const [askEnabled, setAskEnabled] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [toast, setToast] = useState<Toast | null>(null);
  const [theme, setTheme] = useState<"light" | "dark" | null>(null);
  const [systemDark, setSystemDark] = useState(false);
  const refreshResult = useRef(false);

  const audio = useRef<HTMLAudioElement>(null);
  const stopAt = useRef<number | null>(null);
  const [position, setPosition] = useState(0);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    const { id, screen } = readUrl();
    setSelected(id);
    setScreen(screen);
    const saved = localStorage.getItem("meetingTheme");
    if (saved === "light" || saved === "dark") setTheme(saved);
    setSystemDark(
      !!window.matchMedia?.("(prefers-color-scheme: dark)").matches,
    );
    request<{ llm_enabled: boolean; ask_enabled?: boolean }>("/api/health")
      .then((health) => {
        setLlmEnabled(health.llm_enabled);
        setAskEnabled(health.ask_enabled ?? health.llm_enabled);
      })
      .catch(() => setError("Chưa kết nối được dịch vụ xử lý."));
    const onPop = () => {
      const next = readUrl();
      setSelected(next.id);
      setScreen(next.screen);
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  useEffect(() => {
    if (theme) document.documentElement.dataset.theme = theme;
  }, [theme]);

  const navigate = useCallback(
    (id: string | null, next: Screen = "workspace") => {
      const url = new URL(window.location.href);
      url.searchParams.delete("job");
      url.searchParams.delete("view");
      if (id) url.searchParams.set("job", id);
      if (id && next !== "workspace") url.searchParams.set("view", next);
      window.history.pushState(null, "", url);
      setSelected(id);
      setScreen(next);
      setError("");
      window.scrollTo({ top: 0 });
    },
    [],
  );

  useEffect(() => {
    if (!selected) return;
    const controller = new AbortController();
    let active = true,
      pending = false,
      lastRevision = -1,
      lastStatus = "";
    setView(null);
    setJob(null);
    async function poll() {
      if (pending) return;
      pending = true;
      try {
        const current = await request<Job>(`/api/jobs/${selected}`, {
          signal: controller.signal,
        });
        if (!active) return;
        if (
          (lastStatus === "queued" || lastStatus === "running") &&
          (current.status === "complete" || current.status === "failed")
        )
          notifyDone(current.title, current.status === "complete");
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
      audio.current?.pause();
      setPosition(0);
    };
  }, [selected]);

  const play = useCallback((from: number, until?: number) => {
    const player = audio.current;
    if (!player) return;
    stopAt.current = until ?? null;
    const go = () => {
      player.currentTime = Math.max(0, from);
      void player.play().catch(() => {});
    };
    if (player.readyState >= 1) go();
    else player.addEventListener("loadedmetadata", go, { once: true });
  }, []);
  const toggle = useCallback(() => {
    const player = audio.current;
    if (!player) return;
    stopAt.current = null;
    if (player.paused)
      void player
        .play()
        .catch(() =>
          setError("Chưa phát được audio. Kiểm tra bản ghi hoặc thử lại."),
        );
    else player.pause();
  }, []);
  const playback: Playback = { audio, position, playing, play, toggle };

  function showToast(next: Toast) {
    setToast(next);
    window.setTimeout(
      () => setToast((current) => (current === next ? null : current)),
      6000,
    );
  }
  function onQueued() {
    refreshResult.current = true;
    setJob((j) => (j ? { ...j, status: "queued", stage: "M6" } : j));
  }
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
  const dark = theme ? theme === "dark" : systemDark;
  const themeButton = (
    <button
      className="icon-button"
      aria-label={dark ? "Dùng giao diện sáng" : "Dùng giao diện tối"}
      onClick={() => {
        const next = dark ? "light" : "dark";
        localStorage.setItem("meetingTheme", next);
        setTheme(next);
      }}
    >
      <Icon name={dark ? "sun" : "moon"} />
    </button>
  );

  return (
    <div className="app">
      {error && !uploadOpen && (
        <div className="banner error" role="alert">
          <Icon name="alert" width="18" />
          <span>{error}</span>
          <button
            className="icon-button"
            aria-label="Đóng thông báo"
            onClick={() => setError("")}
          >
            <Icon name="close" width="18" />
          </button>
        </div>
      )}
      {!selected ? (
        <Library
          onOpen={(id) => navigate(id)}
          onUpload={() => setUploadOpen(true)}
          onError={setError}
          onToast={showToast}
          themeButton={themeButton}
        />
      ) : (
        <>
          {
            <audio
              ref={audio}
              src={`${API}/api/jobs/${selected}/audio`}
              preload="metadata"
              onPlay={() => setPlaying(true)}
              onPause={() => setPlaying(false)}
              onEnded={() => setPlaying(false)}
              onTimeUpdate={(e) => {
                const t = e.currentTarget.currentTime;
                setPosition(t);
                if (stopAt.current !== null && t >= stopAt.current) {
                  stopAt.current = null;
                  e.currentTarget.pause();
                }
              }}
              onError={() => setError("Không tải được audio của cuộc họp.")}
            />
          }
          {screen === "speakers" && view ? (
            <SpeakersStep
              jobId={selected}
              view={view}
              llmEnabled={llmEnabled}
              playback={playback}
              onView={setView}
              onQueued={onQueued}
              onError={setError}
              onDone={() => navigate(selected)}
            />
          ) : screen === "review" && view ? (
            <ReviewMode
              jobId={selected}
              view={view}
              playback={playback}
              onView={setView}
              onError={setError}
              onDone={() => navigate(selected)}
              onQueued={onQueued}
              llmEnabled={llmEnabled}
            />
          ) : (
            <Workspace
              jobId={selected}
              job={job}
              view={view}
              llmEnabled={llmEnabled}
              askEnabled={askEnabled}
              playback={playback}
              themeButton={themeButton}
              onView={setView}
              onJob={setJob}
              onQueued={onQueued}
              onRetry={() => void retry()}
              onError={setError}
              onToast={showToast}
              onLibrary={() => navigate(null)}
              onScreen={(next) => navigate(selected, next)}
            />
          )}
        </>
      )}
      {uploadOpen && (
        <UploadDialog
          onClose={() => setUploadOpen(false)}
          onUploaded={(id) => {
            setUploadOpen(false);
            navigate(id);
          }}
        />
      )}
      <div className={`toast ${toast ? "show" : ""}`} role="status">
        {toast && (
          <>
            <span>{toast.text}</span>
            {toast.links?.map((link) => (
              <a key={link.href} href={link.href} download>
                {link.label}
              </a>
            ))}
            {toast.actions?.map((action) => (
              <button key={action.label} onClick={action.onClick}>
                {action.label}
              </button>
            ))}
          </>
        )}
      </div>
    </div>
  );
}
