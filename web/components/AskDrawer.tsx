"use client";

import { useEffect, useRef, useState } from "react";
import { MeetingAnswer, request, ResultView, time, Turn } from "@/lib/api";
import { Icon } from "./Icon";

const short = (text: string) =>
  text.length > 42 ? text.slice(0, 40).trimEnd() + "…" : text;

/** Questions this meeting can actually answer, taken from its own minutes. */
function suggestions(view: ResultView) {
  const actions = view.edited.action_items;
  const list = ["Nhóm đã chốt những gì?"];
  const noOwner = actions.find((a) => !a.speaker);
  const noDeadline = actions.find((a) => !a.deadline);
  if (noOwner) list.push(`Ai làm “${short(noOwner.task)}”?`);
  if (noDeadline) list.push(`Hạn của “${short(noDeadline.task)}” là khi nào?`);
  list.push("Còn vấn đề nào chưa giải quyết?");
  return list.slice(0, 3);
}

export function AskDrawer({
  jobId,
  view,
  enabled,
  busy,
  open,
  onClose,
  onSource,
}: {
  jobId: string;
  view: ResultView;
  enabled: boolean;
  busy: boolean;
  open: boolean;
  onClose: () => void;
  onSource: (turn: Turn) => void;
}) {
  const [answers, setAnswers] = useState<MeetingAnswer[]>([]);
  const [question, setQuestion] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const input = useRef<HTMLTextAreaElement>(null);
  const end = useRef<HTMLDivElement>(null);
  const inFlight = useRef(false);
  const submission = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    request<MeetingAnswer[]>(`/api/jobs/${jobId}/questions`, {
      signal: controller.signal,
    })
      .then((history) => {
        if (!controller.signal.aborted)
          setAnswers((previous) =>
            [
              ...history,
              ...previous.filter((a) => !history.some((h) => h.id === a.id)),
            ].sort((a, b) => a.created - b.created || a.id - b.id),
          );
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setError("Chưa tải được lịch sử hỏi đáp.");
      });
    setTimeout(() => input.current?.focus(), 350);
    return () => controller.abort();
  }, [jobId, view.revision, open]);
  useEffect(() => () => submission.current?.abort(), []);
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [answers.length, pending]);

  async function ask(text = question.trim()) {
    if (!text || inFlight.current || !enabled || busy) return;
    inFlight.current = true;
    const controller = new AbortController();
    submission.current = controller;
    setPending(true);
    setError("");
    setQuestion(text);
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
        setAnswers((previous) => [
          ...previous.filter((a) => a.id !== answer.id),
          answer,
        ]);
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
    <aside
      className={`drawer ${open ? "open" : ""}`}
      aria-label="Hỏi cuộc họp"
      aria-hidden={!open}
      inert={!open}
    >
      <header>
        <h2>Hỏi cuộc họp</h2>
        <button
          className="icon-button"
          aria-label="Đóng hỏi đáp"
          onClick={onClose}
        >
          <Icon name="close" width="18" />
        </button>
      </header>
      <div className="chat" aria-live="polite" aria-busy={pending}>
        {!enabled && (
          <p className="callout warn">
            Bật dịch vụ LLM để hỏi đáp. Lịch sử đã lưu vẫn xem được.
          </p>
        )}
        {!answers.length && (
          <p className="chat-empty">
            Hỏi về quyết định, người làm hoặc hạn chót. Mỗi câu trả lời có nguồn
            để nghe lại.
          </p>
        )}
        {answers.map((answer) => {
          const stale = answer.stale || answer.revision !== view.revision;
          return (
            <div className="exchange" key={answer.id}>
              <p className="q">{answer.question}</p>
              <div className="a">
                {stale && (
                  <p className="tag warn">
                    Transcript đã thay đổi sau câu trả lời này
                  </p>
                )}
                {answer.status === "not_found" && (
                  <p>
                    <strong>Chưa tìm thấy câu trả lời có dẫn chứng.</strong> Thử
                    hỏi cụ thể hơn hoặc kiểm tra lại transcript.
                  </p>
                )}
                {answer.answer_points.map((point, i) => (
                  <div key={i} className="point">
                    <p>
                      {point.text}
                      {point.uncertain && (
                        <span className="tag warn">Cần xác nhận</span>
                      )}
                    </p>
                    {point.sources.map((source) => {
                      const current = view.edited.turns.find(
                        (t) => t.turn_id === source.turn_id,
                      );
                      return (
                        <button
                          key={source.turn_id}
                          className="source quote"
                          disabled={!current}
                          aria-label={`Nghe nguồn hỏi đáp ${time(source.start)} ${source.speaker}`}
                          onClick={() => current && onSource(current)}
                        >
                          <span>
                            <Icon
                              name="play"
                              width="11"
                              height="11"
                              fill="currentColor"
                            />
                            {time(source.start)} · {source.speaker}
                          </span>
                          <q>{source.text}</q>
                        </button>
                      );
                    })}
                  </div>
                ))}
                {stale && (
                  <button
                    className="link"
                    disabled={!enabled || pending || busy}
                    onClick={() => void ask(answer.question)}
                  >
                    Hỏi lại với transcript hiện tại →
                  </button>
                )}
              </div>
            </div>
          );
        })}
        {pending && (
          <div className="exchange">
            <p className="q">{question}</p>
            <p className="a typing" role="status">
              <i />
              <i />
              <i />
              <span className="sr-only">Đang tìm câu trả lời…</span>
            </p>
          </div>
        )}
        <div ref={end} />
      </div>
      <div className="suggestions" aria-label="Câu hỏi gợi ý">
        {suggestions(view)
          .filter((s) => !answers.some((a) => a.question === s))
          .map((text) => (
            <button
              key={text}
              className="pill"
              disabled={!enabled || pending || busy}
              onClick={() => void ask(text)}
            >
              {text}
            </button>
          ))}
      </div>
      {error && (
        <p className="callout warn" role="alert">
          {error}
        </p>
      )}
      <form
        className="composer"
        onSubmit={(event) => {
          event.preventDefault();
          void ask();
        }}
      >
        <label htmlFor="meeting-question" className="sr-only">
          Câu hỏi của bạn
        </label>
        <textarea
          ref={input}
          id="meeting-question"
          placeholder="Hỏi về nội dung cuộc họp…"
          value={question}
          maxLength={1000}
          rows={2}
          disabled={!enabled || pending || busy}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void ask();
            }
          }}
        />
        <button
          type="submit"
          className="btn primary"
          disabled={!question.trim() || !enabled || pending || busy}
        >
          {pending ? "Đang hỏi…" : "Hỏi"}
        </button>
      </form>
    </aside>
  );
}
