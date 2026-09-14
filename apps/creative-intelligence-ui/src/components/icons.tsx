/** Compact inline SVG icon set (stroke style, 18px default). */
const PATHS: Record<string, React.ReactNode> = {
  dashboard: <path d="M3 10.5 12 3l9 7.5M5 9.5V21h5v-6h4v6h5V9.5" />,
  campaign: (
    <>
      <path d="M3 11v9h9l9-9-4.5-4.5L7 11H3Z" />
      <circle cx="15.5" cy="8.5" r="1.4" />
    </>
  ),
  creatives: (
    <>
      <rect x="3" y="3" width="18" height="18" rx="3" />
      <circle cx="9" cy="9" r="1.6" />
      <path d="m5.5 18 5-5 3 3 2.5-2.5 2.5 2.5" />
    </>
  ),
  compare: (
    <>
      <path d="M9 3H4v18h5M15 3h5v18h-5" />
      <path d="M9 8H6.5M9 12H6.5M17.5 8H15M17.5 12H15" />
    </>
  ),
  book: (
    <>
      <path d="M4 19V5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2Zm0 0a2 2 0 0 0 2 2h13" />
      <path d="M9 7h6" />
    </>
  ),
  bookmark: <path d="M6 3h12v18l-6-4.5L6 21V3Z" />,
  report: (
    <>
      <path d="M6 2h9l4 4v16H6V2Z" />
      <path d="M14 2v5h5M9 13h6M9 17h6" />
    </>
  ),
  workbook: (
    <>
      <rect x="4" y="3" width="16" height="18" rx="2" />
      <path d="M8 3v18M8 8h2M8 12h2M8 16h2M13 9h4M13 13h4" />
    </>
  ),
  chat: <path d="M4 5h16v11H9l-5 4V5Z" />,
  send: <path d="M22 2 11 13M22 2l-7 20-4-9-9-4 20-7Z" />,
  spark: <path d="M12 2v6m0 0 2.5-2.5M12 8 9.5 5.5M4 20l4.5-4.5M20 20l-4.5-4.5M12 8c-3 0-5 2.5-5 6l-1 4 4-1c.8.2 1.4.2 2 .2 3 0 5-2.5 5-6" />,
  moon: <path d="M20 13.5A8 8 0 0 1 10.5 4 6.8 6.8 0 1 0 20 13.5Z" />,
  users: (
    <>
      <circle cx="9" cy="8" r="3.2" />
      <path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6M16 4.5a3.2 3.2 0 0 1 0 6.2M18 14.3c2 .8 3.5 2.7 3.5 5" />
    </>
  ),
  user: (
    <>
      <circle cx="12" cy="8" r="3.5" />
      <path d="M5 20c0-3.9 3.1-7 7-7s7 3.1 7 7" />
    </>
  ),
  gear: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M19.1 4.9 17 7M7 17l-2.1 2.1" />
    </>
  ),
  bell: <path d="M6 9a6 6 0 0 1 12 0c0 5 2 6 2 6H4s2-1 2-6M10 20a2.2 2.2 0 0 0 4 0" />,
  search: (
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.8-3.8" />
    </>
  ),
  reset: <path d="M3 12a9 9 0 1 0 3-6.7M3 4v5h5" />,
  calendar: (
    <>
      <rect x="3" y="5" width="18" height="16" rx="2" />
      <path d="M8 3v4M16 3v4M3 10h18" />
    </>
  ),
  dots: (
    <g fill="currentColor" stroke="none">
      <circle cx="12" cy="5" r="1.6" />
      <circle cx="12" cy="12" r="1.6" />
      <circle cx="12" cy="19" r="1.6" />
    </g>
  ),
  check: <path d="m4 12.5 5 5L20 6.5" />,
  info: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v5" />
      <circle cx="12" cy="8" r=".5" />
    </>
  ),
  /* Pointer hand with a click burst above the fingertip: reads as
   * "click" at 12–20px everywhere the Total Clicks metric appears. */
  click: (
    <>
      <path d="M12 3.5v2.6M7.6 5.2l1.3 2.2M16.4 5.2l-1.3 2.2" />
      <path d="M10.2 11.2V6.8a1.4 1.4 0 0 1 2.8 0v3.4m0-2.6a1.4 1.4 0 0 1 2.8 0v3.2m0-2a1.4 1.4 0 0 1 2.8 0v4.4c0 3.2-2.2 5.8-5.4 5.8-2 0-3.2-.9-4.3-2.6l-2.1-3.3c-.6-1 .1-2.2 1.2-2.2h2.2" />
    </>
  ),
  coin: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v10M15 9.5c-.8-1-2-1.5-3-1.5-1.7 0-3 .9-3 2.2 0 2.9 6 1.4 6 4.3 0 1.3-1.3 2.2-3 2.2-1 0-2.2-.5-3-1.5" />
    </>
  ),
  bars: <path d="M5 20V10M12 20V4M19 20v-7" />,
  trend: <path d="m3 17 6-6 4 4 8-8M15 7h6v6" />,
  play: (
    <>
      <rect x="3" y="5" width="18" height="14" rx="3" />
      <path d="m10 9 5 3-5 3V9Z" />
    </>
  ),
  tiktok: <path d="M9 8v8.5a3.5 3.5 0 1 0 3.5-3.5M9 8V4c.5 2.5 2.5 4 5 4" />,
  meta: <path d="M12 12c-1.8-2.4-4.2-3.8-6.8-3.8a4.3 4.3 0 1 0 0 8.6c2.6 0 5-1.4 6.8-3.8Zm0 0c1.8 2.4 4.2 3.8 6.8 3.8a4.3 4.3 0 1 0 0-8.6c-2.6 0-5 1.4-6.8 3.8Z" />,
  menu: <path d="M4 7h16M4 12h16M4 17h16" />,
  chev: <path d="m9 6 6 6-6 6" />,
  x: <path d="M6 6l12 12M18 6 6 18" />,
  lock: (
    <>
      <rect x="5" y="11" width="14" height="9" rx="2" />
      <path d="M8 11V8a4 4 0 0 1 8 0v3" />
    </>
  ),
  mail: (
    <>
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <path d="m3 7 9 6 9-6" />
    </>
  ),
  eye: (
    <>
      <path d="M2 12s3.5-6.5 10-6.5S22 12 22 12s-3.5 6.5-10 6.5S2 12 2 12Z" />
      <circle cx="12" cy="12" r="2.8" />
    </>
  ),
  google: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M8.5 12a3.5 3.5 0 0 1 6.8-1.2H12v2.4h3.4A3.5 3.5 0 0 1 8.5 12Z" />
    </>
  ),
  plus: <path d="M12 5v14M5 12h14" />,
  download: <path d="M12 3v12m0 0 4-4m-4 4-4-4M4 17v4h16v-4" />,
  clock: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3.5 2" />
    </>
  ),
  megaphone: (
    <>
      <path d="M3 11v3l4 1 2 5h2.5L10 15l9 3.5V6L4 10l-1 1Z" />
      <path d="M19 6v12.5" />
    </>
  ),
  target: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <circle cx="12" cy="12" r="4.8" />
      <circle cx="12" cy="12" r="1.4" />
    </>
  ),
  list: <path d="M8 6h13M8 12h13M8 18h13M3.5 6h.5M3.5 12h.5M3.5 18h.5" />,
  copy: (
    <>
      <rect x="9" y="9" width="11" height="11" rx="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </>
  ),
  grid: (
    <>
      <rect x="4" y="4" width="7" height="7" rx="1.5" />
      <rect x="13" y="4" width="7" height="7" rx="1.5" />
      <rect x="4" y="13" width="7" height="7" rx="1.5" />
      <rect x="13" y="13" width="7" height="7" rx="1.5" />
    </>
  ),
  expand: <path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" />,
  compress: <path d="M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5" />,
};

export function Icon({ name, size = 18 }: { name: string; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {PATHS[name] ?? PATHS.info}
    </svg>
  );
}
