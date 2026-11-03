"use client";

import { useState } from "react";
import {
  ActionItem,
  Claim,
  jsonBody,
  request,
  ResultView,
  time,
  Turn,
} from "@/lib/api";
import { Icon } from "./Icon";

function Sources({
  item,
  view,
  onSource,
}: {
  item: Claim | ActionItem;
  view: ResultView;
  onSource: (turn: Turn) => void;
}) {
  const turns = (item.source_turn_ids || [])
    .map((id) => view.edited.turns.find((t) => t.turn_id === id))
    .filter((t): t is Turn => !!t);
  const unsure = turns.some((t) => view.review_turn_ids.includes(t.turn_id));
  return (
    <span className="sources">
      {turns.map((turn) => (
        <button
          key={turn.turn_id}
          className="source"
          onClick={() => onSource(turn)}
          aria-label={`Nghe dẫn chứng ${time(turn.start)} ${turn.speaker}`}
        >
          <Icon name="play" width="11" height="11" fill="currentColor" />
          {time(turn.start)}
        </button>
      ))}
      {!turns.length && <span className="muted">Chưa có dẫn chứng</span>}
      {unsure && <span className="tag warn">Nguồn chưa rõ</span>}
    </span>
  );
}

function ActionRow({
  item,
  index,
  jobId,
  view,
  owners,
  onSource,
  onView,
  onError,
}: {
  item: ActionItem;
  index: number;
  jobId: string;
  view: ResultView;
  owners: string[];
  onSource: (turn: Turn) => void;
  onView: (view: ResultView) => void;
  onError: (error: string) => void;
}) {
  const [deadline, setDeadline] = useState(item.deadline || "");
  async function save(fields: Partial<ActionItem>) {
    try {
      onView(
        await request<ResultView>(
          `/api/jobs/${jobId}/actions/${index}`,
          jsonBody(fields),
        ),
      );
    } catch (err) {
      onError(
        err instanceof Error ? err.message : "Chưa lưu được việc cần làm.",
      );
    }
  }
  const options = [
    ...new Set([...owners, "Cả nhóm", item.speaker || ""]),
  ].filter(Boolean);
  return (
    <li className={`action ${item.done ? "done" : ""}`}>
      <button
        className="check"
        aria-pressed={!!item.done}
        aria-label={`${item.done ? "Bỏ đánh dấu" : "Đánh dấu"} hoàn thành: ${item.task}`}
        onClick={() => void save({ done: !item.done })}
      >
        <Icon name="check" width="14" strokeWidth="3" />
      </button>
      <div>
        <p className="task">{item.task}</p>
        <div className="action-meta">
          <label className={`chip-field ${item.speaker ? "" : "missing"}`}>
            <span className="sr-only">Người làm</span>
            <Icon name="users" width="14" />
            <select
              value={item.speaker || ""}
              onChange={(e) => void save({ speaker: e.target.value || null })}
            >
              <option value="">Chọn người làm…</option>
              {options.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <label className={`chip-field ${item.deadline ? "" : "missing"}`}>
            <span className="sr-only">Hạn chót</span>
            <Icon name="calendar" width="14" />
            <input
              value={deadline}
              placeholder="Thêm hạn"
              maxLength={100}
              size={Math.max(8, deadline.length + 1)}
              onChange={(e) => setDeadline(e.target.value)}
              onBlur={() => {
                if (deadline.trim() !== (item.deadline || ""))
                  void save({ deadline: deadline.trim() || null });
              }}
              onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
            />
          </label>
          <Sources item={item} view={view} onSource={onSource} />
        </div>
      </div>
    </li>
  );
}

export function Minutes({
  jobId,
  view,
  order,
  llmEnabled,
  busy,
  pending,
  onSource,
  onView,
  onError,
  onReview,
  onRegenerate,
}: {
  jobId: string;
  view: ResultView;
  order: string[];
  llmEnabled: boolean;
  busy: boolean;
  pending: boolean;
  onSource: (turn: Turn) => void;
  onView: (view: ResultView) => void;
  onError: (error: string) => void;
  onReview: () => void;
  onRegenerate: () => void;
}) {
  const minutes = view.edited;
  const decisions = minutes.decisions || [];
  const actions = minutes.action_items;
  const toReview = view.review_turn_ids.length;
  const owners = [
    ...(view.participants || []),
    ...order.map((id) => view.speaker_names[id]).filter(Boolean),
  ];
  const done = actions.filter((a) => a.done).length;

  return (
    <section className="minutes" aria-label="Biên bản">
      {toReview > 0 && (
        <button className="callout warn" onClick={onReview}>
          <Icon name="audio" width="18" />
          <span>
            <b>{toReview} mục</b>{" "}
            {minutes.summary
              ? "trong biên bản dựa trên đoạn nghe chưa rõ."
              : "có tín hiệu nhận dạng sai."}{" "}
            Nghe lại để chắc chắn.
          </span>
          <strong>Soát ngay →</strong>
        </button>
      )}
      {view.summary_stale && (
        <div className="callout" role="status">
          <Icon name="alert" width="18" />
          <span>Transcript đã sửa sau khi tạo biên bản.</span>
          <button
            className="btn small"
            disabled={!llmEnabled || busy || pending}
            onClick={onRegenerate}
          >
            Tạo lại
          </button>
        </div>
      )}
      {view.summary_error && (
        <p className="callout warn" role="alert">
          Chưa tạo được biên bản: {view.summary_error}
        </p>
      )}

      {!minutes.summary ? (
        <div className="minutes-empty">
          <Icon name="note" width="28" height="28" />
          <h2>Chưa có biên bản</h2>
          <p>
            Quyết định và việc cần làm sẽ có liên kết về đoạn nói gốc để nghe
            lại.
          </p>
          {llmEnabled ? (
            <button
              className="btn primary"
              disabled={busy || pending}
              onClick={onRegenerate}
            >
              Tạo biên bản
            </button>
          ) : (
            <p className="muted">Bật dịch vụ LLM để tạo biên bản.</p>
          )}
        </div>
      ) : (
        <>
          <h2>
            Quyết định <span className="muted">{decisions.length}</span>
          </h2>
          {decisions.length ? (
            <ul className="claims">
              {decisions.map((item, i) => (
                <li key={i} className="decision">
                  <Icon
                    name="check"
                    width="18"
                    className="ok"
                    strokeWidth="2.4"
                  />
                  <div>
                    <p>{item.text}</p>
                    <Sources item={item} view={view} onSource={onSource} />
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted none">Không có quyết định được chốt rõ.</p>
          )}

          <h2>
            Việc cần làm{" "}
            <span className="muted">
              {actions.length ? `${done}/${actions.length} xong` : 0}
            </span>
          </h2>
          {actions.length ? (
            <ul className="claims">
              {actions.map((item, i) => (
                <ActionRow
                  key={`${i}-${item.task}`}
                  item={item}
                  index={i}
                  jobId={jobId}
                  view={view}
                  owners={owners}
                  onSource={onSource}
                  onView={onView}
                  onError={onError}
                />
              ))}
            </ul>
          ) : (
            <p className="muted none">Chưa có việc được giao rõ ràng.</p>
          )}

          <details
            className="summary"
            open={!decisions.length && !actions.length}
          >
            <summary>Tóm tắt nội dung</summary>
            {minutes.summary_points?.length ? (
              <ul>
                {minutes.summary_points.map((item, i) => (
                  <li key={i}>
                    {item.text}{" "}
                    <Sources item={item} view={view} onSource={onSource} />
                  </li>
                ))}
              </ul>
            ) : (
              <p>{minutes.summary}</p>
            )}
          </details>
        </>
      )}
    </section>
  );
}
