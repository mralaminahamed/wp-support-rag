// Brand logo mark (inline SVG, scales with size). Author: Al Amin Ahamed.
export function Logo({ size = 24 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      role="img"
      aria-label="Support RAG"
      className="shrink-0"
    >
      <defs>
        <linearGradient id="logo-g" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#6366f1" />
          <stop offset="1" stopColor="#a855f7" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="8" fill="url(#logo-g)" />
      <path
        d="M9 7h13a4 4 0 0 1 4 4v6a4 4 0 0 1-4 4h-6l-5 4v-4H9a4 4 0 0 1-4-4v-6a4 4 0 0 1 4-4z"
        fill="#ffffff"
      />
      <circle cx="11.5" cy="14" r="1.6" fill="#6366f1" />
      <circle cx="16" cy="14" r="1.6" fill="#7c5cf0" />
      <circle cx="20.5" cy="14" r="1.6" fill="#a855f7" />
    </svg>
  );
}
