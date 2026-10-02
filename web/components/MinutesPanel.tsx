"use client";

import { useState } from "react";
import { ActionItem, Claim, request, ResultView, time, Turn } from "@/lib/api";
import { Icon } from "./Icon";

type Props = {
  jobId: string;
  view: ResultView;
  enabled: boolean;
  busy: boolean;
  onSource: (turn: Turn) => void;
  onQueued: () => void;
  onError: (error: string) => void;
};
function Sources({
  item,
  view,
  onSource,
}: {
  item: Claim | ActionItem;
  view: ResultView;
  onSource: Props["onSource"];
}) {
  const turns = (item.source_turn_ids || [])
    .map((id) => view.edited.turns.find((t) => t.turn_id === id))
    .filter((t): t is Turn => !!t);
  return (
    <div className="evidence">
      {turns.map((turn) => (
        <button
          className="source-link"
          key={turn.turn_id}
          onClick={() => onSource(turn)}
          aria-label={`Nghe dẫn chứng ${time(turn.start)} ${turn.speaker}`}
        >
          <Icon name="play" width="12" height="12" />
          {time(turn.start)}–{time(turn.end)}
        </button>
      ))}
      {!turns.length && <span className="subtle">Chưa có dẫn chứng</span>}
      {turns.some((t) => t.flagged && !t.reviewed) && (
        <span className="badge warning">Nguồn cần soát</span>
      )}
      {item.uncertain && <span className="subtle">Cần xác nhận</span>}
    </div>
  );
}
export function MinutesPanel({
  jobId,
  view,
  enabled,
  busy,
  onSource,
  onQueued,
  onError,
}: Props) {
  const [template, setTemplate] = useState(view.summary_template || "project");
  const [pending, setPending] = useState(false);
  const minutes = view.edited;
  async function generate() {
    setPending(true);
    try {
      await request(`/api/jobs/${jobId}/summary`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ template }),
      });
      onQueued();
    } catch (error) {
      onError(
        error instanceof Error ? error.message : "Chưa tạo được biên bản.",
      );
    } finally {
      setPending(false);
    }
  }
  return (
    <aside className="minutes-panel" aria-label="Biên bản cuộc họp">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">SAU CUỘC HỌP</span>
          <h2>Biên bản có dẫn chứng</h2>
        </div>
        <Icon name="note" />
      </div>
      <div className="minutes-toolbar">
        <label htmlFor="minutes-template" className="sr-only">
          Mẫu biên bản
        </label>
        <select
          id="minutes-template"
          value={template}
          onChange={(e) => setTemplate(e.target.value)}
        >
          <option value="project">Họp dự án</option>
          <option value="standup">Standup</option>
          <option value="customer">Họp khách hàng</option>
        </select>
        <button
          className="button primary small"
          disabled={!enabled || busy || pending}
          onClick={() => void generate()}
        >
          {pending ? "Đang gửi…" : minutes.summary ? "Tạo lại" : "Tạo biên bản"}
        </button>
      </div>
      {!enabled && (
        <p className="hint">
          Bật dịch vụ tóm tắt để tạo biên bản từ transcript đã soát.
        </p>
      )}
      {view.summary_stale && (
        <div role="status" className="notice warning">
          <Icon name="alert" />
          <p>
            Nội dung đã thay đổi. Biên bản và dẫn chứng dưới đây thuộc bản
            trước; hãy tạo lại.
          </p>
        </div>
      )}
      {view.summary_error && (
        <p className="notice warning">
          Chưa tạo được biên bản: {view.summary_error}
        </p>
      )}
      {minutes.summary ? (
        <>
          <div className="summary-meta">
            <span className="badge neutral">
              {view.summary_grounded || minutes.summary_points?.length
                ? "Có nguồn transcript"
                : "Biên bản cũ"}
            </span>
            <span className="subtle">
              Phiên bản {view.summary_revision ?? view.revision}
            </span>
          </div>
          <section className="minutes-section">
            <h3>Tóm tắt</h3>
            {minutes.summary_points?.length ? (
              minutes.summary_points.map((item, i) => (
                <article className="claim" key={i}>
                  <p>{item.text}</p>
                  <Sources item={item} view={view} onSource={onSource} />
                </article>
              ))
            ) : (
              <p className="legacy-summary">{minutes.summary}</p>
            )}
          </section>
          {!!minutes.topics.length && (
            <div className="topic-tags">
              {minutes.topics.map((topic, i) => (
                <span key={i}>{topic}</span>
              ))}
            </div>
          )}
          <section className="minutes-section">
            <h3>
              <Icon name="check" width="16" />
              Quyết định <span>{minutes.decisions?.length || 0}</span>
            </h3>
            {minutes.decisions?.length ? (
              minutes.decisions.map((item, i) => (
                <article className="claim decision" key={i}>
                  <p>{item.text}</p>
                  <Sources item={item} view={view} onSource={onSource} />
                </article>
              ))
            ) : (
              <p className="subtle">Chưa trích xuất quyết định.</p>
            )}
          </section>
          <section className="minutes-section">
            <h3>
              <Icon name="flag" width="16" />
              Việc cần làm <span>{minutes.action_items.length}</span>
            </h3>
            {minutes.action_items.length ? (
              minutes.action_items.map((item, i) => (
                <article className="claim action-item" key={i}>
                  <p>{item.task}</p>
                  <div className="action-owner">
                    <span>{item.speaker || "Chưa rõ người phụ trách"}</span>
                    <span>{item.deadline || "Chưa nêu hạn"}</span>
                  </div>
                  <Sources item={item} view={view} onSource={onSource} />
                </article>
              ))
            ) : (
              <p className="subtle">Chưa có việc được giao rõ ràng.</p>
            )}
          </section>
        </>
      ) : (
        <div className="panel-empty">
          <span className="empty-icon">
            <Icon name="note" width="28" height="28" />
          </span>
          <h3>Từ lời nói đến việc cần làm</h3>
          <p>
            Tóm tắt, quyết định và công việc sẽ có liên kết về đoạn nói nguồn để
            bạn kiểm tra.
          </p>
        </div>
      )}
    </aside>
  );
}
