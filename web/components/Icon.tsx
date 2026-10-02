import type { SVGProps } from "react";

const paths = {
  audio: "M4 10v4m4-8v12m4-15v18m4-15v12m4-8v4",
  plus: "M12 5v14M5 12h14",
  library: "M4 4h6v16H4zM14 4h6v16h-6zM4 8h6m4 0h6",
  upload: "M12 16V4m-5 5 5-5 5 5M4 16v4h16v-4",
  search: "M21 21l-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0",
  check: "m5 12 4 4L19 6",
  flag: "M5 21V4m0 0h14l-3 5 3 5H5",
  play: "m8 5 11 7-11 7z",
  pause: "M8 5v14m8-14v14",
  back: "m11 5-7 7 7 7m-7-7h16",
  next: "m9 5 7 7-7 7",
  repeat:
    "m17 2 4 4-4 4M3 11V8a2 2 0 0 1 2-2h16M7 22l-4-4 4-4m14-1v3a2 2 0 0 1-2 2H3",
  users:
    "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2m20 0v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75M13 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0",
  note: "M5 3h14v18H5zM8 7h8M8 11h8m-8 4h5",
  timeline: "M4 5h16M4 12h16M4 19h16M7 3v4m7 3v4m-4 3v4",
  download: "M12 3v12m-5-5 5 5 5-5M5 17v4h14v-4",
  history: "M3 11a9 9 0 1 1 3 8M3 4v7h7m2-5v6l4 2",
  close: "m6 6 12 12M6 18 18 6",
  link: "m10 13 4-4m-5 7-2 2a4 4 0 0 1-6-6l4-4a4 4 0 0 1 6 0m2 0 2-2a4 4 0 0 1 6 6l-4 4a4 4 0 0 1-6 0",
  alert: "m12 3 10 18H2zM12 9v4m0 3v1",
  edit: "m16 3 5 5-12 12H4v-5zM13 6l5 5",
} as const;
export type IconName = keyof typeof paths;
export function Icon({
  name,
  ...props
}: SVGProps<SVGSVGElement> & { name: IconName }) {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      <path d={paths[name]} />
    </svg>
  );
}
