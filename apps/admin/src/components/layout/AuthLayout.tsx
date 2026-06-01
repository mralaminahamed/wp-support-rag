// Shared split-screen shell for all auth pages. Author: Al Amin Ahamed.
import type { ReactNode } from "react";
import { Logo } from "@/components/Logo";

interface AuthLayoutProps {
  children: ReactNode;
  title: string;
  description?: string;
}

export function AuthLayout({ children, title, description }: AuthLayoutProps) {
  return (
    <div className="flex min-h-screen bg-background">
      {/* Brand panel — desktop only */}
      <div
        className="hidden lg:flex lg:w-[420px] shrink-0 flex-col justify-between p-12 relative overflow-hidden"
        style={{ backgroundColor: "var(--nav)" }}
      >
        {/* Subtle grid */}
        <div
          className="pointer-events-none absolute inset-0"
          style={{
            backgroundImage:
              "linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px)",
            backgroundSize: "40px 40px",
          }}
        />
        {/* Glow */}
        <div
          className="pointer-events-none absolute top-0 right-0 w-64 h-64 rounded-full"
          style={{
            background:
              "radial-gradient(circle at 80% 20%, rgba(99,102,241,0.25) 0%, transparent 65%)",
          }}
        />
        <div
          className="pointer-events-none absolute bottom-0 left-0 w-80 h-64 rounded-full"
          style={{
            background:
              "radial-gradient(circle at 20% 80%, rgba(99,102,241,0.12) 0%, transparent 65%)",
          }}
        />

        {/* Logo */}
        <div className="relative z-10 flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center bg-primary/20 ring-1 ring-primary/30">
            <Logo size={18} />
          </div>
          <span className="text-sm font-semibold text-[#e0eaf8]">Support RAG</span>
        </div>

        {/* Center content */}
        <div className="relative z-10 space-y-8">
          <div>
            <h1 className="text-2xl font-bold text-white leading-tight">
              WordPress support,<br />powered by AI
            </h1>
            <p className="mt-3 text-sm text-[#4b6284] leading-relaxed">
              Instant, grounded answers from your plugin documentation.
            </p>
          </div>

          <ul className="space-y-3">
            {[
              { icon: "ti-file-search", text: "RAG over plugin docs & GitHub READMEs" },
              { icon: "ti-chart-bar", text: "Deflection metrics & query analytics" },
              { icon: "ti-brand-wordpress", text: "WordPress.org registry integration" },
            ].map((item) => (
              <li key={item.icon} className="flex items-center gap-3">
                <span className="w-7 h-7 rounded-md flex items-center justify-center shrink-0 bg-white/5 ring-1 ring-white/8">
                  <i className={`ti ${item.icon} text-[13px] text-primary`} />
                </span>
                <span className="text-[13px] text-[#4b6284]">{item.text}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* Footer */}
        <p className="relative z-10 text-[11px] text-[#2d3f5c]">
          Admin console · WP Support RAG
        </p>
      </div>

      {/* Form panel */}
      <div className="flex flex-1 items-center justify-center p-6 sm:p-12">
        <div className="w-full max-w-[400px] space-y-7">
          {/* Mobile logo */}
          <div className="flex items-center gap-2.5 lg:hidden">
            <div className="w-8 h-8 rounded-lg flex items-center justify-center bg-primary/10">
              <Logo size={18} />
            </div>
            <span className="text-sm font-semibold">Support RAG</span>
          </div>

          {/* Heading */}
          <div className="space-y-1.5">
            <h2 className="text-xl font-bold tracking-tight text-foreground">{title}</h2>
            {description && (
              <p className="text-sm text-text-3 leading-relaxed">{description}</p>
            )}
          </div>

          {/* Form content */}
          <div>{children}</div>
        </div>
      </div>
    </div>
  );
}
