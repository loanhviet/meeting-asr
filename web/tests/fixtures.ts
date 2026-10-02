import { Page } from "@playwright/test";
import { EditEvent, Job, MeetingAnswer, Minutes, ResultView } from "../lib/api";

export function audioFixture() {
  const samples = 120 * 8000;
  const buffer = Buffer.alloc(44 + samples * 2);
  buffer.write("RIFF");
  buffer.writeUInt32LE(buffer.length - 8, 4);
  buffer.write("WAVEfmt ", 8);
  buffer.writeUInt32LE(16, 16);
  buffer.writeUInt16LE(1, 20);
  buffer.writeUInt16LE(1, 22);
  buffer.writeUInt32LE(8000, 24);
  buffer.writeUInt32LE(16000, 28);
  buffer.writeUInt16LE(2, 32);
  buffer.writeUInt16LE(16, 34);
  buffer.write("data", 36);
  buffer.writeUInt32LE(samples * 2, 40);
  return buffer;
}
export async function installFixture(
  page: Page,
  options: { empty?: boolean; status?: Job["status"]; llm?: boolean } = {},
) {
  const job: Job = {
    id: "fixture",
    filename: "Họp tiến độ dự án.wav",
    status: options.status || "complete",
    stage:
      options.status === "running"
        ? "M3"
        : options.status === "failed"
          ? "failed"
          : "complete",
    progress: 0.55,
    error:
      options.status === "failed"
        ? "Không đọc được bản ghi. Vui lòng kiểm tra file."
        : null,
    created: 1790899200,
    revision: 0,
    summary_error: null,
  };
  const specs = [
    ["An", "A", "Chúng ta chốt bản thử nghiệm vào thứ Sáu.", 0, 8, false],
    [
      "Bình",
      "B",
      "Tôi nhận phần kiểm thử, gửi kết quả trước thứ Năm.",
      10,
      13,
      true,
    ],
    [
      "An",
      "A",
      "Cần xác nhận lại dữ liệu cho chức năng tìm kiếm.",
      25,
      35,
      false,
    ],
    [
      "Người nói 03",
      "C",
      "Tôi cũng là Bình, tôi sẽ gửi báo cáo kiểm thử.",
      40,
      48,
      true,
    ],
    [
      "An",
      "A",
      "Thống nhất cập nhật tiến độ trong cuộc họp tiếp theo.",
      60,
      70,
      false,
    ],
  ] as const;
  const minutes: Minutes = {
    audio_id: "fixture",
    duration: 120,
    num_speakers: 3,
    flagged_ratio: 0.2,
    turns: specs.map(([name, id, text, start, end, flagged], index) => ({
      turn_id: String(index),
      start,
      end,
      speaker: name,
      speaker_id: id,
      original_speaker: id,
      text,
      original_text: text,
      flagged,
      reviewed: false,
      confidence: flagged ? 0.2 : 0.9,
      flag_reasons: flagged
        ? ["Người nói chưa rõ", "Đoạn ngắn cần nghe lại"]
        : [],
    })),
    summary:
      "Nhóm chốt bản thử nghiệm vào thứ Sáu, cần kiểm thử và xác nhận dữ liệu.",
    topics: ["Tiến độ", "Kiểm thử", "Dữ liệu"],
    summary_points: [
      {
        text: "Bản thử nghiệm dự kiến hoàn thành vào thứ Sáu.",
        source_turn_ids: ["0"],
        uncertain: false,
      },
      {
        text: "Bình nhận kiểm thử và gửi kết quả trước thứ Năm.",
        source_turn_ids: ["1"],
        uncertain: true,
      },
    ],
    decisions: [
      {
        text: "Chốt bản thử nghiệm vào thứ Sáu.",
        source_turn_ids: ["0"],
        uncertain: false,
      },
    ],
    action_items: [
      {
        speaker: "Bình",
        task: "Kiểm thử và gửi báo cáo kết quả",
        deadline: "Thứ Năm",
        source_turn_ids: ["1", "3"],
        uncertain: true,
      },
    ],
  };
  const original = structuredClone(minutes);
  original.turns.forEach((t) => (t.speaker = t.original_speaker));
  const view: ResultView = {
    original,
    edited: minutes,
    revision: 0,
    summary_stale: false,
    summary_error: null,
    summary_revision: 0,
    summary_template: "project",
    summary_grounded: true,
    speaker_names: { A: "An", B: "Bình", C: "Người nói 03" },
  };
  const events: EditEvent[] = [];
  const answers: MeetingAnswer[] = [];
  let uploaded = !options.empty;
  await page.route("**/api/**", async (route) => {
    const req = route.request(),
      path = new URL(req.url()).pathname;
    if (path === "/api/health")
      return route.fulfill({ json: { llm_enabled: options.llm ?? true } });
    if (path === "/api/jobs" && req.method() === "POST") {
      uploaded = true;
      return route.fulfill({ status: 202, json: { job_id: job.id } });
    }
    if (path === "/api/jobs")
      return route.fulfill({ json: uploaded ? [job] : [] });
    if (path.endsWith("/audio")) {
      const audio = audioFixture();
      const range = /^bytes=(\d+)-(\d*)$/.exec(req.headers()["range"] || "");
      if (range) {
        const start = Number(range[1]);
        const end = range[2]
          ? Math.min(Number(range[2]), audio.length - 1)
          : audio.length - 1;
        return route.fulfill({
          status: 206,
          contentType: "audio/wav",
          body: audio.subarray(start, end + 1),
          headers: {
            "Accept-Ranges": "bytes",
            "Content-Range": `bytes ${start}-${end}/${audio.length}`,
          },
        });
      }
      return route.fulfill({
        contentType: "audio/wav",
        body: audio,
        headers: { "Accept-Ranges": "bytes" },
      });
    }
    if (path.endsWith("/result")) {
      if (options.status && options.status !== "complete")
        return route.fulfill({
          status: 409,
          json: { detail: "Result is not ready" },
        });
      return route.fulfill({ json: view });
    }
    if (path.endsWith("/history"))
      return route.fulfill({ json: [...events].reverse() });
    if (path.endsWith("/questions")) {
      if (req.method() === "GET")
        return route.fulfill({
          json: [...answers].reverse().map((answer) => ({
            ...answer,
            stale: answer.revision !== view.revision,
          })),
        });
      const body = req.postDataJSON();
      if (body.expected_revision !== view.revision)
        return route.fulfill({
          status: 409,
          json: { detail: "transcript changed; reload before asking" },
        });
      if (options.llm === false)
        return route.fulfill({
          status: 409,
          json: { detail: "Configure and enable LLM" },
        });
      const cached = answers.find(
        (answer) =>
          answer.question === body.question &&
          answer.revision === view.revision,
      );
      if (cached) {
        cached.created = Date.now() / 1000;
        return route.fulfill({ json: cached });
      }
      const found = /kiểm thử|deadline|thời hạn|thứ/i.test(body.question);
      const source = minutes.turns[1];
      const answer: MeetingAnswer = {
        id: answers.length + 1,
        question: body.question,
        revision: view.revision,
        created: Date.now() / 1000,
        stale: false,
        status: found ? "found" : "not_found",
        answer_points: found
          ? [
              {
                text: `${source.speaker} nhận kiểm thử; thời hạn được nêu trong nguồn.`,
                source_turn_ids: [source.turn_id],
                uncertain: source.flagged && !source.reviewed,
                needs_review: source.flagged && !source.reviewed,
                sources: [source],
              },
            ]
          : [],
      };
      answers.push(answer);
      return route.fulfill({ json: answer });
    }
    if (path.includes("/turns/")) {
      const update = req.postDataJSON();
      if (update.expected_revision !== view.revision)
        return route.fulfill({
          status: 409,
          json: { detail: "transcript changed; reload before saving" },
        });
      const turn = minutes.turns.find(
        (t) => t.turn_id === path.split("/").at(-1),
      )!;
      const before = {
        text: turn.text,
        speaker_id: turn.speaker_id!,
        reviewed: turn.reviewed,
      };
      if (update.text !== undefined) turn.text = update.text;
      if (update.speaker_id) turn.speaker_id = update.speaker_id;
      if (update.speaker_name)
        view.speaker_names[turn.speaker_id!] = update.speaker_name;
      minutes.turns.forEach(
        (t) => (t.speaker = view.speaker_names[t.speaker_id!] || t.speaker_id!),
      );
      turn.reviewed = update.reviewed;
      view.revision++;
      job.revision = view.revision;
      if (
        before.text !== turn.text ||
        before.speaker_id !== turn.speaker_id ||
        update.speaker_name
      )
        view.summary_stale = true;
      if (!view.summary_stale) view.summary_revision = view.revision;
      events.push({
        id: events.length + 1,
        kind: "turn_edit",
        revision: view.revision,
        created: job.created,
        changes: {
          turn_id: turn.turn_id,
          before,
          after: {
            text: turn.text,
            speaker_id: turn.speaker_id!,
            reviewed: turn.reviewed,
          },
        },
      });
      minutes.num_speakers = new Set(
        minutes.turns.map((t) => t.speaker_id),
      ).size;
      return route.fulfill({ json: view });
    }
    if (path.endsWith("/speakers/merge")) {
      const update = req.postDataJSON();
      if (update.expected_revision !== view.revision)
        return route.fulfill({
          status: 409,
          json: { detail: "transcript changed" },
        });
      const turns = minutes.turns.filter(
        (t) => t.speaker_id === update.source_speaker,
      );
      turns.forEach((t) => {
        t.speaker_id = update.target_speaker;
        t.speaker = view.speaker_names[update.target_speaker];
      });
      view.revision++;
      job.revision = view.revision;
      view.summary_stale = true;
      minutes.num_speakers = new Set(
        minutes.turns.map((t) => t.speaker_id),
      ).size;
      events.push({
        id: events.length + 1,
        kind: "speaker_merge",
        revision: view.revision,
        created: job.created,
        changes: {
          source_speaker: update.source_speaker,
          target_speaker: update.target_speaker,
          turn_ids: turns.map((t) => t.turn_id),
        },
      });
      return route.fulfill({ json: view });
    }
    if (path.endsWith("/summary")) {
      view.summary_template = req.postDataJSON()?.template || "project";
      view.summary_stale = false;
      view.summary_revision = view.revision;
      return route.fulfill({ status: 202, json: { job_id: job.id } });
    }
    if (path.endsWith("/retry")) {
      job.status = "running";
      job.stage = "M3";
      return route.fulfill({ status: 202, json: { job_id: job.id } });
    }
    if (path.endsWith("/export"))
      return route.fulfill({
        body: minutes.turns.map((t) => t.text).join("\n"),
        headers: { "Content-Disposition": 'attachment; filename="meeting.md"' },
      });
    return route.fulfill({ json: job });
  });
  return { job, view, minutes, events, answers };
}
