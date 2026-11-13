# Truy vết chức năng, code và kiểm thử

Đối chiếu từng chức năng trong [FEATURES.md](FEATURES.md) với code hiện tại.
Tên hàm/test trong bảng là vị trí cần đọc trong file liên kết; test dùng fixture
không chứng minh chất lượng semantic. Xem [TEST_PLAN.md](TEST_PLAN.md),
[TEST_REPORT.md](TEST_REPORT.md) và [EVALUATION_REPORT.md](EVALUATION_REPORT.md).

## Biên bản có dẫn chứng

| ID | Chức năng theo FEATURES.md | Code | Test / bằng chứng và khoảng trống |
|---|---|---|---|
| BB-01 | Ý chính, quyết định, action item có `source_turn_ids` | [summarize.py](../src/meeting_asr/summarize.py): `validate_summary`, `Summarizer` | [test_summarize.py](../tests/test_summarize.py): `test_long_transcript_keeps_source_ids_and_decisions_across_chunks` |
| BB-02 | Chỉ nhận ID trong context; lấy timestamp/speaker từ transcript | [summarize.py](../src/meeting_asr/summarize.py): `_request`, `resolve_evidence` | [test_summarize.py](../tests/test_summarize.py): `test_unknown_or_empty_evidence_is_rejected_and_not_cached`, `test_evidence_timestamps_and_review_status_come_from_transcript` |
| BB-03 | Bấm nguồn mở lượt, xóa filter và nghe audio | [Minutes.tsx](../web/components/Minutes.tsx): `Sources`; [Workspace.tsx](../web/components/Workspace.tsx): `seek`; [Transcript.tsx](../web/components/Transcript.tsx): focus effect | [meeting.spec.ts](../web/tests/meeting.spec.ts): `evidence links jump to the source turn, clear search and play from it` |
| BB-04 | Nguồn flagged chưa soát có nhãn | [summarize.py](../src/meeting_asr/summarize.py): `resolve_evidence`; [Minutes.tsx](../web/components/Minutes.tsx): `Sources` | [test_summarize.py](../tests/test_summarize.py): evidence/review status; browser kiểm nhãn “Nguồn chưa rõ” |
| BB-05 | Nội dung chưa rõ cần xác nhận; owner/deadline chưa rõ để trống | [summarize.py](../src/meeting_asr/summarize.py): `PROMPT`, `validate_summary`; [Minutes.tsx](../web/components/Minutes.tsx): `ActionRow` | [test_summarize.py](../tests/test_summarize.py): `test_json_retry_and_cache_preserve_uncertain_action_items`; chưa có test xác nhận suy luận semantic của LLM thật |
| BB-06 | Mẫu project/standup/customer; tạo lại dùng transcript sửa | [summarize.py](../src/meeting_asr/summarize.py): `TEMPLATES`; [jobs.py](../src/meeting_asr/jobs.py): `JobWorker` | [test_jobs.py](../tests/test_jobs.py): `test_summary_worker_uses_corrected_turns_and_keeps_concurrent_edit_stale`; [meeting.spec.ts](../web/tests/meeting.spec.ts): templates; chưa có test riêng cho nội dung mẫu customer |
| BB-07 | Sửa text/speaker làm stale; export không dùng summary stale | [jobs.py](../src/meeting_asr/jobs.py): `edit`, `result`; [export.py](../src/meeting_asr/export.py): `export_markdown` | [test_jobs.py](../tests/test_jobs.py): edits/reassign; [test_export.py](../tests/test_export.py): `test_exports_use_reviewed_text_and_disclose_stale_summary` |
| BB-08 | Chia transcript dài, giữ ID trong mảnh và hợp nhất nguồn/quyết định/action | [summarize.py](../src/meeting_asr/summarize.py): `summarize` | [test_summarize.py](../tests/test_summarize.py): `test_long_transcript_keeps_source_ids_and_decisions_across_chunks` |
| BB-09 | Đọc biên bản cũ; không tự suy đoán dẫn chứng | [summarize.py](../src/meeting_asr/summarize.py): `validate_summary`, `resolve_evidence`; [jobs.py](../src/meeting_asr/jobs.py): `result` | [test_jobs.py](../tests/test_jobs.py): fixture summary cũ không có nguồn; [test_summarize.py](../tests/test_summarize.py): legacy JSON hợp lệ; chưa có test riêng cho không tự thêm nguồn vào biên bản cũ |
| BB-10 | Cấu hình provider/model/key và bật LLM | [summarize.py](../src/meeting_asr/summarize.py): `Summarizer.__init__`; [api.py](../src/meeting_asr/api.py): `regenerate` | [test_summarize.py](../tests/test_summarize.py): protocol/env; [test_acceptance.py](../tests/test_acceptance.py): `test_llm_check_does_not_expose_secrets_or_send_requests`; chưa có test chất lượng semantic provider thật |

## Soát sửa và người nói

| ID | Chức năng theo FEATURES.md | Code | Test / bằng chứng và khoảng trống |
|---|---|---|---|
| SS-01 | Xác nhận đúng hoặc sửa text/speaker từng lượt | [ReviewControls.tsx](../web/components/ReviewControls.tsx): `TurnEditor`; [jobs.py](../src/meeting_asr/jobs.py): `edit` | [test_api.py](../tests/test_api.py): `test_speaker_review_api_and_template_validation`; [meeting.spec.ts](../web/tests/meeting.spec.ts): upload/edit và review mode |
| SS-02 | Hàng đợi soát: lượt gắn cờ, chưa soát, được biên bản dẫn hoặc lặp decode, theo thứ tự transcript | [jobs.py](../src/meeting_asr/jobs.py): `review_turn_ids`; [ReviewMode.tsx](../web/components/ReviewMode.tsx): queue | [meeting.spec.ts](../web/tests/meeting.spec.ts): `review mode walks only the items behind the minutes`; **chưa có test** đơn vị riêng cho `review_turn_ids` |
| SS-03 | Đổi tên/gộp speaker, tính cả lượt đã gán lại | [SpeakersStep.tsx](../web/components/SpeakersStep.tsx); [jobs.py](../src/meeting_asr/jobs.py): `edit`, `merge_speakers` | [test_jobs.py](../tests/test_jobs.py): `test_reassign_merge_history_and_revision_conflicts_persist`; [meeting.spec.ts](../web/tests/meeting.spec.ts): speaker step |
| SS-04 | Giữ file gốc; SQLite lưu sửa/history và migration | [jobs.py](../src/meeting_asr/jobs.py): `JobStore.__init__`, `edit`, `history` | [test_jobs.py](../tests/test_jobs.py): `test_edits_persist_without_overwriting_original_and_mark_summary_stale`, `test_legacy_database_migration_preserves_jobs` |
| SS-05 | Revision và editor giữ revision lúc mở draft | [ReviewControls.tsx](../web/components/ReviewControls.tsx): `draftRevision`; [jobs.py](../src/meeting_asr/jobs.py): `RevisionConflict` | [test_jobs.py](../tests/test_jobs.py): revision conflicts; [meeting.spec.ts](../web/tests/meeting.spec.ts): templates/revision conflict khi draft đang mở |
| SS-06 | Review-only không làm stale hoặc xóa trạng thái stale cũ | [jobs.py](../src/meeting_asr/jobs.py): `edit` | [test_jobs.py](../tests/test_jobs.py): `test_review_only_edit_updates_evidence_without_invalidating_summary` |
| SS-07 | Tiến độ theo mục trong hàng đợi (Mục i / n), đến mục tiếp theo | [ReviewMode.tsx](../web/components/ReviewMode.tsx): `index`, `decide`, `results` | [meeting.spec.ts](../web/tests/meeting.spec.ts): `review mode walks only the items behind the minutes` |
| SS-08 | Tốc độ phát và loop lượt chọn | [Player.tsx](../web/components/Player.tsx): `playbackRate`; [Workspace.tsx](../web/components/Workspace.tsx): loop effect | [meeting.spec.ts](../web/tests/meeting.spec.ts): loop replay; **chưa có test** thay tốc độ phát |
| SS-09 | Space phát/tạm dừng | [Workspace.tsx](../web/components/Workspace.tsx): `keyboard` | **chưa có test** nhấn Space trực tiếp; test hiện dùng nút phát |
| SS-10 | J/L lùi/tiến audio | [Workspace.tsx](../web/components/Workspace.tsx): `keyboard` | **chưa có test** nhấn J/L để kiểm tra seek |
| SS-11 | Màn soát: Enter xác nhận, E sửa, ↓ bỏ qua, Space nghe đoạn | [ReviewMode.tsx](../web/components/ReviewMode.tsx): `keyboard` | [meeting.spec.ts](../web/tests/meeting.spec.ts): review mode dùng Control+Enter; **chưa có test** riêng cho Enter/E/↓/Space |
| SS-12 | R bật/tắt loop | [Workspace.tsx](../web/components/Workspace.tsx): `keyboard` | **chưa có test** nhấn R; browser chỉ test nút “Lặp đoạn” |
| SS-13 | Ctrl/⌘+Enter lưu và đánh dấu đã soát | [ReviewControls.tsx](../web/components/ReviewControls.tsx): `onKeyDown`; [ReviewMode.tsx](../web/components/ReviewMode.tsx) | [meeting.spec.ts](../web/tests/meeting.spec.ts): upload/edit và review mode dùng Control+Enter; **chưa có test** Meta+Enter |
| SS-14 | Phím audio bỏ qua input, button/link, dialog | [Workspace.tsx](../web/components/Workspace.tsx): `target.closest`, dialog guard | [meeting.spec.ts](../web/tests/meeting.spec.ts): `loop replays the turn and shortcuts ignore text inputs`; **chưa có test** riêng cho button/link/dialog |

## Hỏi đáp trong cuộc họp

| ID | Chức năng theo FEATURES.md | Code | Test / bằng chứng và khoảng trống |
|---|---|---|---|
| HD-01 | Câu trả lời dẫn transcript/audio | [ask.py](../src/meeting_asr/ask.py): `AskMeeting`, `validate_answer`; [AskDrawer.tsx](../web/components/AskDrawer.tsx) | [test_ask.py](../tests/test_ask.py): `test_reject_ungrounded_answers`; [ask.spec.ts](../web/tests/ask.spec.ts): ask cites audio |
| HD-02 | Lịch sử lưu bền vững | [jobs.py](../src/meeting_asr/jobs.py): `ask_answers`; [AskDrawer.tsx](../web/components/AskDrawer.tsx): history | [test_ask.py](../tests/test_ask.py): `test_api_answers_review_sources_history_persistence_cache_and_edit`; browser reload dùng fixture |
| HD-03 | Revision, đánh dấu câu trả lời cũ và hỏi lại | [api.py](../src/meeting_asr/api.py): questions; [jobs.py](../src/meeting_asr/jobs.py); [AskDrawer.tsx](../web/components/AskDrawer.tsx) | [test_ask.py](../tests/test_ask.py): concurrent edit; [ask.spec.ts](../web/tests/ask.spec.ts): stale answers, conflicts |
| HD-04 | Phản hồi khi thiếu bằng chứng | [ask.py](../src/meeting_asr/ask.py): `validate_answer`; [AskDrawer.tsx](../web/components/AskDrawer.tsx) | [test_ask.py](../tests/test_ask.py): `test_api_missing_answers_and_invalid_retry`; [ask.spec.ts](../web/tests/ask.spec.ts): missing evidence abstains |

## API bổ sung

| ID | Chức năng theo FEATURES.md | Code | Test / bằng chứng và khoảng trống |
|---|---|---|---|
| API-01 | PATCH turns có speaker/text/reviewed/expected_revision | [api.py](../src/meeting_asr/api.py): `TurnEdit`, route turns | [test_api.py](../tests/test_api.py): upload/edit/conflict và speaker review |
| API-02 | POST speakers/merge có source/target/revision | [api.py](../src/meeting_asr/api.py): `SpeakerMerge`, `merge` | [test_api.py](../tests/test_api.py): `test_speaker_review_api_and_template_validation` |
| API-03 | GET history tối đa 100 thay đổi mới nhất | [api.py](../src/meeting_asr/api.py): `history`; [jobs.py](../src/meeting_asr/jobs.py): `history`, SQL LIMIT | [test_jobs.py](../tests/test_jobs.py): thứ tự/history persistence; **chưa có test** vượt giới hạn 100 |
| API-04 | POST summary body tùy chọn, ba template | [api.py](../src/meeting_asr/api.py): `SummaryRequest`, `regenerate` | [test_api.py](../tests/test_api.py): template sai; [meeting.spec.ts](../web/tests/meeting.spec.ts): standup; **chưa có test** API trực tiếp cho body rỗng và từng template hợp lệ |
| API-05 | Result có speaker sửa, nguồn/time/review, template/summary revision | [jobs.py](../src/meeting_asr/jobs.py): `result`; [summarize.py](../src/meeting_asr/summarize.py): `resolve_evidence` | [test_jobs.py](../tests/test_jobs.py): review-only và concurrent summary; [test_summarize.py](../tests/test_summarize.py): evidence timestamps |

## Khoảng trống cần xử lý

- Các mô tả trong FEATURES.md về hàng đợi soát, tiến độ soát và phím tắt đã được sửa
  cho khớp code (không có phím N, không sắp theo confidence).
- TODO: bổ sung các test được đánh dấu “chưa có test” (phím Space/J/L/R, tốc độ phát,
  giới hạn 100 lịch sử, body rỗng và từng template của API summary).
- TODO: nghiệm thu semantic summary/QA bằng reference đã nghe rà trên cuộc họp thật.
