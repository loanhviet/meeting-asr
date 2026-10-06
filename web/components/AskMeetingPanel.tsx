"use client";

import { useEffect, useRef, useState } from "react";
import { MeetingAnswer, request, ResultView, time, Turn } from "@/lib/api";
import { Icon } from "./Icon";

export function AskMeetingPanel({
  jobId,
  view,
  enabled,
  busy,
  onSource,
}: {
  jobId: string;
  view: ResultView;
  enabled: boolean;
  busy: boolean;
  onSource: (turn: Turn) => void;
}) {
  const [answers, setAnswers] = useState<MeetingAnswer[]>([]);
  const [question, setQuestion] = useState("");
  const [pending, setPending] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const input = useRef<HTMLTextAreaElement>(null);
  const submission = useRef<AbortController | null>(null);
  const inFlight = useRef(false);
  useEffect(() => {
    const controller = new AbortController();
    request<MeetingAnswer[]>(`/api/jobs/${jobId}/questions`, {
      signal: controller.signal,
    })
      .then((history) => {
        if (!controller.signal.aborted)
          setAnswers((previous) =>
            [
              ...history,
              ...previous.filter(
                (answer) => !history.some((item) => item.id === answer.id),
              ),
            ]
              .sort((a, b) => b.created - a.created || b.id - a.id)
              .slice(0, 20),
          );
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setError("Chưa tải được lịch sử hỏi đáp. Hãy mở lại tab.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [jobId, view.revision]);
  useEffect(() => () => submission.current?.abort(), []);

  async function ask() {
    const text = question.trim();
    if (!text || inFlight.current || !enabled || busy) return;
    inFlight.current = true;
    const controller = new AbortController();
    submission.current = controller;
    setPending(true);
    setError("");
    try {
      const answer = await request<MeetingAnswer>(
        `/api/jobs/${jobId}/questions`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            question: text,
            expected_revision: view.revision,
          }),
          signal: controller.signal,
        },
      );
      if (!controller.signal.aborted) {
        setAnswers((previous) =>
          [answer, ...previous.filter((item) => item.id !== answer.id)]
            .sort((a, b) => b.created - a.created || b.id - a.id)
            .slice(0, 20),
        );
        setQuestion("");
      }
    } catch (err) {
      if (!controller.signal.aborted)
        setError(
          err instanceof Error
            ? err.message
            : "Chưa trả lời được. Hãy thử lại.",
        );
    } finally {
      inFlight.current = false;
      if (!controller.signal.aborted) setPending(false);
    }
  }
  return (
    <section
      className="ask-panel"
      id="panel-ask"
      role="tabpanel"
      aria-labelledby="tab-ask"
    >
      <div className="panel-heading">
        <div>
          <span className="eyebrow">TÌM LẠI NỘI DUNG CUỘC HỌP</span>
          <h2>Hỏi đáp có dẫn chứng</h2>
          <p className="subtle">
            Câu trả lời dựa trên các đoạn transcript liên quan. Bấm nguồn để
            nghe và kiểm tra.
          </p>
        </div>
        <span className="ask-mark">
          <Icon name="chat" width="24" height="24" />
        </span>
      </div>
      <div className="ask-compose">
        {!enabled && (
          <p className="notice warning">
            Bật dịch vụ LLM để hỏi đáp về cuộc họp. Lịch sử đã lưu vẫn xem được.
          </p>
        )}
        <div className="ask-suggestions" aria-label="Câu hỏi gợi ý">
          {[
            "Ai nhận phần kiểm thử?",
            "Deadline đã chốt chưa?",
            "Còn vấn đề nào cần giải quyết?",
          ].map((text) => (
            <button
              key={text}
              className="button secondary small"
              disabled={!enabled || pending || busy}
              onClick={() => {
                setQuestion(text);
                input.current?.focus();
              }}
            >
              {text}
            </button>
          ))}
        </div>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void ask();
          }}
        >
          <label htmlFor="meeting-question">Câu hỏi của bạn</label>
          <textarea
            ref={input}
            id="meeting-question"
            placeholder="Ví dụ: Nhóm đã thống nhất thời hạn nào?"
            value={question}
            maxLength={1000}
            rows={3}
            disabled={!enabled || pending || busy}
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={(event) => {
              if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
                event.preventDefault();
                void ask();
              }
            }}
          />
          <div className="ask-compose-actions">
            <small className="subtle">
              {question.length}/1000 · Ctrl / ⌘ + Enter để gửi
            </small>
            <button
              type="submit"
              className="button primary"
              disabled={!question.trim() || !enabled || pending || busy}
            >
              <Icon name="chat" width="16" />
              {pending ? "Đang tìm câu trả lời…" : "Gửi câu hỏi"}
            </button>
          </div>
        </form>
        {error && (
          <p className="notice warning" role="alert">
            {error}
          </p>
        )}
        {pending && (
          <p className="ask-pending" role="status">
            Đang tìm đoạn liên quan và kiểm tra dẫn chứng…
          </p>
        )}
      </div>
      <div className="ask-history" aria-live="polite" aria-busy={pending}>
        <div className="ask-history-heading">
          <h3>Lịch sử hỏi đáp</h3>
          <span className="subtle">20 câu hỏi gần nhất</span>
        </div>
        {loading ? (
          <p className="panel-empty">Đang tải lịch sử…</p>
        ) : !answers.length ? (
          <div className="ask-empty">
            <Icon name="chat" width="32" height="32" />
            <h3>Bạn muốn tìm lại điều gì?</h3>
            <p>
              Hỏi về quyết định, người phụ trách hoặc thời hạn trong cuộc họp
              này.
            </p>
          </div>
        ) : null}
        {answers.map((answer) => {
          const stale = answer.stale || answer.revision !== view.revision;
          return (
            <article className="ask-answer" key={answer.id}>
              <div className="ask-question">
                <Icon name="users" width="18" />
                <h3>{answer.question}</h3>
              </div>
              <div className="ask-answer-body">
                <div className="ask-answer-meta">
                  <span className={`badge ${stale ? "warning" : "neutral"}`}>
                    {stale ? "Transcript đã thay đổi" : "Dựa trên transcript"}
                  </span>
                  <small className="subtle">Phiên bản {answer.revision}</small>
                </div>
                {stale && (
                  <p className="hint">
                    Câu trả lời và trích đoạn thuộc phiên bản trước. Hỏi lại để
                    dùng nội dung đã chỉnh sửa.
                  </p>
                )}
                {answer.status === "not_found" && (
                  <div className="ask-no-answer">
                    <strong>Chưa tìm thấy câu trả lời có dẫn chứng.</strong>
                    <p>
                      Thử hỏi cụ thể hơn hoặc kiểm tra lại transcript. Nội dung
                      được truy xuất chưa đủ để trả lời câu hỏi này.
                    </p>
                  </div>
                )}
                {answer.answer_points.map((point, index) => (
                  <div className="ask-point" key={index}>
                    <p>{point.text}</p>
                    {point.uncertain && (
                      <span className="badge warning">Cần xác nhận</span>
                    )}
                    {point.sources.map((source) => {
                      const current = view.edited.turns.find(
                        (turn) => turn.turn_id === source.turn_id,
                      );
                      return (
                        <div className="ask-evidence" key={source.turn_id}>
                          <div>
                            <button
                              className="source-link"
                              disabled={!current}
                              aria-label={`Nghe nguồn hỏi đáp ${time(source.start)} ${source.speaker}`}
                              onClick={() => current && onSource(current)}
                            >
                              <Icon name="play" width="12" height="12" />
                              {time(source.start)}–{time(source.end)}
                            </button>
                            <strong>{source.speaker}</strong>
                            {source.flagged && !source.reviewed && (
                              <span className="badge warning">
                                Nguồn cần soát
                              </span>
                            )}
                          </div>
                          <blockquote>{source.text}</blockquote>
                        </div>
                      );
                    })}
                  </div>
                ))}
                {stale && (
                  <button
                    className="text-button"
                    disabled={!enabled || pending || busy}
                    onClick={() => {
                      setQuestion(answer.question);
                      input.current?.focus();
                      input.current?.scrollIntoView({
                        behavior: "smooth",
                        block: "center",
                      });
                    }}
                  >
                    Hỏi lại với transcript hiện tại{" "}
                    <Icon name="next" width="14" />
                  </button>
                )}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
