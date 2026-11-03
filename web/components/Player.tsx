"use client";

import { useState } from "react";
import { Minutes, speakerClass, speakerId, time, Turn } from "@/lib/api";
import { Icon } from "./Icon";
import type { Playback } from "./MeetingApp";

export function Player({
  playback,
  duration,
  minutes,
  order,
  activeTurn,
  loop,
  onLoop,
}: {
  playback: Playback;
  duration: number;
  minutes: Minutes;
  order: string[];
  activeTurn?: Turn;
  loop: boolean;
  onLoop: (loop: boolean) => void;
}) {
  const [rate, setRate] = useState("1");
  const total = Math.max(duration, 1);
  const pct = (t: number) => `${Math.min(100, (t / total) * 100)}%`;
  const starts = new Map(minutes.turns.map((t) => [t.turn_id, t.start]));
  const marks = [
    ...(minutes.decisions || []).map((d) => ({
      ids: d.source_turn_ids,
      label: "Quyết định",
    })),
    ...minutes.action_items.map((a) => ({
      ids: a.source_turn_ids,
      label: "Việc cần làm",
    })),
  ]
    .map((m) => ({ at: starts.get(m.ids?.[0] ?? ""), label: m.label }))
    .filter((m): m is { at: number; label: string } => m.at !== undefined);
  function seek(value: number) {
    const player = playback.audio.current;
    if (player) player.currentTime = Math.max(0, Math.min(duration, value));
  }
  return (
    <div className="player" aria-label="Trình phát bản ghi">
      <button
        className="play"
        aria-label={playback.playing ? "Tạm dừng audio" : "Phát audio"}
        onClick={playback.toggle}
      >
        <Icon
          name={playback.playing ? "pause" : "play"}
          fill={playback.playing ? "none" : "currentColor"}
          strokeWidth={playback.playing ? 2.6 : 1.7}
        />
      </button>
      <span className="clock">
        {time(playback.position)}
        <span className="muted"> / {time(duration)}</span>
      </span>
      <div className="track-wrap">
        <span className="now-speaking">
          {activeTurn ? activeTurn.speaker : "Bản ghi cuộc họp"}
        </span>
        <div
          className="track"
          onClick={(e) => {
            const r = e.currentTarget.getBoundingClientRect();
            seek(((e.clientX - r.left) / r.width) * total);
          }}
          aria-hidden="true"
        >
          {minutes.turns.map((t) => (
            <i
              key={t.turn_id}
              className={`seg ${speakerClass(order, speakerId(t))}`}
              style={{
                left: pct(t.start),
                width: `max(2px, ${pct(t.end - t.start)})`,
              }}
            />
          ))}
          {marks.map((m, i) => (
            <b
              key={i}
              className="mark"
              style={{ left: pct(m.at) }}
              title={`${m.label} · ${time(m.at)}`}
            />
          ))}
          <span className="head" style={{ left: pct(playback.position) }} />
        </div>
        <input
          className="sr-only"
          aria-label="Vị trí phát audio"
          type="range"
          min="0"
          max={duration}
          step="0.1"
          value={Math.min(playback.position, duration)}
          onChange={(e) => seek(Number(e.target.value))}
        />
      </div>
      <button
        className={`icon-button ${loop ? "on" : ""}`}
        aria-pressed={loop}
        disabled={!activeTurn && !loop}
        onClick={() => onLoop(!loop)}
        title="Lặp lượt đang nghe · R"
        aria-label="Lặp đoạn"
      >
        <Icon name="repeat" width="18" />
      </button>
      <label className="sr-only" htmlFor="playback-rate">
        Tốc độ phát
      </label>
      <select
        id="playback-rate"
        className="rate"
        value={rate}
        onChange={(e) => {
          setRate(e.target.value);
          if (playback.audio.current)
            playback.audio.current.playbackRate = Number(e.target.value);
        }}
      >
        {[0.75, 1, 1.25, 1.5, 2].map((r) => (
          <option key={r} value={r}>
            {r}×
          </option>
        ))}
      </select>
    </div>
  );
}
