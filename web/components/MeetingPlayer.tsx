"use client";

import { RefObject, useEffect, useState } from "react";
import { API, time, Turn } from "@/lib/api";
import { Icon } from "./Icon";

export function MeetingPlayer({
  jobId,
  duration,
  audioRef,
  activeTurn,
  loop,
  onLoop,
  onTime,
  onError,
}: {
  jobId: string;
  duration: number;
  audioRef: RefObject<HTMLAudioElement | null>;
  activeTurn?: Turn;
  loop: boolean;
  onLoop: (loop: boolean) => void;
  onTime: (time: number) => void;
  onError: (error: string) => void;
}) {
  const [position, setPosition] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [rate, setRate] = useState("1");
  useEffect(() => {
    setPosition(0);
    setPlaying(false);
    setRate("1");
  }, [jobId]);
  useEffect(() => {
    const player = audioRef.current;
    if (!player) return;
    let frame = 0;
    const tick = () => {
      if (
        loop &&
        activeTurn &&
        (player.currentTime < activeTurn.start ||
          player.currentTime >= activeTurn.end)
      ) {
        player.currentTime = activeTurn.start;
        void player.play().catch(() => {});
      }
      if (!player.paused) frame = requestAnimationFrame(tick);
    };
    const start = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(tick);
    };
    player.addEventListener("play", start);
    if (!player.paused) start();
    return () => {
      cancelAnimationFrame(frame);
      player.removeEventListener("play", start);
    };
  }, [loop, activeTurn, audioRef]);
  async function toggle() {
    const player = audioRef.current;
    if (!player) return;
    if (player.paused) {
      try {
        if (
          loop &&
          activeTurn &&
          (player.currentTime < activeTurn.start ||
            player.currentTime >= activeTurn.end)
        )
          player.currentTime = activeTurn.start;
        await player.play();
      } catch {
        onError("Chưa phát được audio. Kiểm tra bản ghi hoặc thử lại.");
      }
    } else player.pause();
  }
  function seek(value: number) {
    if (audioRef.current) {
      audioRef.current.currentTime = value;
      setPosition(value);
      onTime(value);
    }
  }
  return (
    <div className="player-dock" aria-label="Trình phát bản ghi">
      <audio
        ref={audioRef}
        src={`${API}/api/jobs/${jobId}/audio`}
        preload="metadata"
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
        onTimeUpdate={(e) => {
          setPosition(e.currentTarget.currentTime);
          onTime(e.currentTarget.currentTime);
        }}
        onError={() => onError("Không tải được audio của cuộc họp.")}
      />
      <button
        className="player-play"
        aria-label={playing ? "Tạm dừng audio" : "Phát audio"}
        onClick={() => void toggle()}
      >
        <Icon name={playing ? "pause" : "play"} />
      </button>
      <div className="player-track">
        <div className="player-track-meta">
          <strong>
            {activeTurn
              ? `Đang nghe · ${activeTurn.speaker}`
              : "Bản ghi cuộc họp"}
          </strong>
          <span>
            {time(position)} <span className="subtle">/ {time(duration)}</span>
          </span>
        </div>
        <input
          aria-label="Vị trí phát audio"
          type="range"
          min="0"
          max={duration}
          step="0.1"
          value={Math.min(position, duration)}
          onChange={(e) => seek(Number(e.target.value))}
        />
      </div>
      <button
        className="button quiet small loop-button"
        aria-pressed={loop}
        disabled={!activeTurn}
        onClick={() => onLoop(!loop)}
        title="Lặp lượt đang chọn · R"
      >
        <Icon name="repeat" width="17" />
        Lặp đoạn
      </button>
      <label className="sr-only" htmlFor="playback-rate">
        Tốc độ phát
      </label>
      <select
        id="playback-rate"
        value={rate}
        onChange={(e) => {
          setRate(e.target.value);
          if (audioRef.current)
            audioRef.current.playbackRate = Number(e.target.value);
        }}
      >
        {[0.75, 1, 1.25, 1.5, 2].map((r) => (
          <option key={r} value={r}>
            {r}×
          </option>
        ))}
      </select>
      <span className="player-shortcut">
        <kbd>Space</kbd> phát / dừng
      </span>
    </div>
  );
}
