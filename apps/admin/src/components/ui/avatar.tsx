// Gravatar avatar with initials fallback. Author: Al Amin Ahamed.
import { useEffect, useState } from "react";
import { gravatarUrl, initials } from "@/lib/profile";
import { cn } from "@/lib/utils";

export function Avatar({
  name,
  email,
  size = 32,
  className,
}: {
  name: string;
  email: string;
  size?: number;
  className?: string;
}) {
  const [failed, setFailed] = useState(false);
  // Retry the image when the email changes.
  useEffect(() => setFailed(false), [email]);

  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-primary/10 text-xs font-semibold text-primary",
        className,
      )}
      style={{ width: size, height: size }}
      aria-label={name}
      title={name}
    >
      {failed || !email.trim() ? (
        initials(name)
      ) : (
        <img
          src={gravatarUrl(email, size * 2)}
          alt={name}
          width={size}
          height={size}
          className="size-full object-cover"
          onError={() => setFailed(true)}
        />
      )}
    </span>
  );
}
