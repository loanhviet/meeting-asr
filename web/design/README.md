# Meeting Notes: complete UI redesign

Figma: [Meeting ASR — Review & Grounded Minutes](https://www.figma.com/design/wxI9RqXMlKkz49Mygb90mz?node-id=23-2).

The file contains editable text, frames and SVG vectors, using Arial to match the application. It covers the complete existing frontend and the new evidence/review flows. Screens use synthetic meeting fixtures; no user recording or transcript is uploaded to Figma.

| Screen                         | Figma node                                                               |
| ------------------------------ | ------------------------------------------------------------------------ |
| Desktop meeting library        | [23:2](https://www.figma.com/design/wxI9RqXMlKkz49Mygb90mz?node-id=23-2) |
| Upload dialog                  | [24:2](https://www.figma.com/design/wxI9RqXMlKkz49Mygb90mz?node-id=24-2) |
| Transcript, player and minutes | [25:2](https://www.figma.com/design/wxI9RqXMlKkz49Mygb90mz?node-id=25-2) |
| Turn text/speaker editor       | [26:2](https://www.figma.com/design/wxI9RqXMlKkz49Mygb90mz?node-id=26-2) |
| Speaker timeline               | [27:2](https://www.figma.com/design/wxI9RqXMlKkz49Mygb90mz?node-id=27-2) |
| Grounded minutes               | [28:2](https://www.figma.com/design/wxI9RqXMlKkz49Mygb90mz?node-id=28-2) |
| Speaker naming and merging     | [29:2](https://www.figma.com/design/wxI9RqXMlKkz49Mygb90mz?node-id=29-2) |
| Edit history                   | [30:2](https://www.figma.com/design/wxI9RqXMlKkz49Mygb90mz?node-id=30-2) |
| Stale minutes                  | [31:2](https://www.figma.com/design/wxI9RqXMlKkz49Mygb90mz?node-id=31-2) |
| Export menu                    | [32:2](https://www.figma.com/design/wxI9RqXMlKkz49Mygb90mz?node-id=32-2) |
| Processing                     | [33:2](https://www.figma.com/design/wxI9RqXMlKkz49Mygb90mz?node-id=33-2) |
| Processing failure and retry   | [34:2](https://www.figma.com/design/wxI9RqXMlKkz49Mygb90mz?node-id=34-2) |
| Empty library/onboarding       | [35:2](https://www.figma.com/design/wxI9RqXMlKkz49Mygb90mz?node-id=35-2) |
| Mobile library                 | [36:2](https://www.figma.com/design/wxI9RqXMlKkz49Mygb90mz?node-id=36-2) |
| Mobile transcript/player       | [37:2](https://www.figma.com/design/wxI9RqXMlKkz49Mygb90mz?node-id=37-2) |
| Mobile minutes                 | [38:2](https://www.figma.com/design/wxI9RqXMlKkz49Mygb90mz?node-id=38-2) |
| Mobile speaker management      | [39:2](https://www.figma.com/design/wxI9RqXMlKkz49Mygb90mz?node-id=39-2) |

## Layout and interaction

- Desktop: meeting sidebar, transcript/timeline, evidence panel and fixed audio player. A dedicated minutes tab gives the summary more room.
- Tablet/mobile: compact navigation, single content panel, tabs for transcript/timeline/minutes, fixed player and native modal dialogs.
- Indigo primary actions, dark navy navigation, white content panels. Amber marks items needing review; green marks reviewed turns.
- Stable speaker IDs determine grouping and colors; display names can be changed separately.
- Evidence opens the source turn, clears search/review filters and seeks the audio. Stale minutes disclose the source revision.
- Source confidence is shown as review status, not as a probability of correctness.

## Reproduce local design artifacts

With dependencies installed, start `npm run dev` in `web/`. In another terminal:

```bash
cd web
node scripts/capture-design.mjs
```

The script renders 17 states from `tests/fixtures.ts`, checks for browser exceptions and writes PNGs, self-contained HTML and SVG source metadata to `results/ui-redesign/`. These generated files remain local. `MEETING_WEB_URL` and `MEETING_CAPTURE_DIR` override the server and output directory.

The Figma file was created with the Figma MCP HTML conversion, then its icons were restored from the exact app SVGs. Native select chevrons remain native layers. The audio dock uses an opaque white fill in Figma to avoid translucency artifacts. The deliverable is a screen collection with editable layers; component libraries and interactive prototype wiring can be added separately.
