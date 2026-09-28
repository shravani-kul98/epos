import { forwardRef, useState } from "react";
import { Eye, EyeOff } from "lucide-react";

import { cn } from "@/lib/cn";
import { TextInput, type TextInputProps } from "@/components/ui/form";

/**
 * Password field with a visibility toggle. Long generated passwords are mistyped often enough
 * that hiding them unconditionally costs more than it protects.
 */
export const PasswordInput = forwardRef<HTMLInputElement, TextInputProps>(
  function PasswordInput({ className, ...props }, ref) {
    const [visible, setVisible] = useState(false);
    return (
      <div className="relative">
        <TextInput
          ref={ref}
          type={visible ? "text" : "password"}
          className={cn(
            "pr-12",
            className,
          )}
          {...props}
        />
        <button
          type="button"
          onClick={() => setVisible((value) => !value)}
          aria-label={visible ? "Hide password" : "Show password"}
          className="icon-button absolute right-1 top-1/2 z-10 -translate-y-1/2"
        >
          {visible ? (
            <EyeOff aria-hidden="true" className="h-4 w-4" />
          ) : (
            <Eye aria-hidden="true" className="h-4 w-4" />
          )}
        </button>
      </div>
    );
  },
);

interface Assessment {
  score: number;
  label: string;
  tone: string;
}

/** Rough guidance only. The backend remains the authority on what it will accept. */
export function assessPassword(value: string): Assessment {
  let score = 0;
  if (value.length >= 12) score += 1;
  if (value.length >= 16) score += 1;
  if (/[a-z]/.test(value) && /[A-Z]/.test(value)) score += 1;
  if (/\d/.test(value)) score += 1;
  if (/[^A-Za-z0-9]/.test(value)) score += 1;
  if (new Set(value).size < 5) score = Math.min(score, 1);

  if (value.length === 0) return { score: 0, label: "", tone: "bg-line" };
  if (score <= 2) return { score, label: "Too weak", tone: "bg-critical" };
  if (score === 3) return { score, label: "Acceptable", tone: "bg-warn" };
  if (score === 4) return { score, label: "Strong", tone: "bg-ok" };
  return { score, label: "Very strong", tone: "bg-ok" };
}

export function PasswordStrength({ value }: { value: string }): JSX.Element | null {
  const { score, label, tone } = assessPassword(value);
  if (!value) return null;
  return (
    <div className="mt-1.5">
      <div className="flex gap-1" aria-hidden="true">
        {[1, 2, 3, 4, 5].map((step) => (
          <span
            key={step}
            className={cn("h-1 flex-1 rounded-full", step <= score ? tone : "bg-line")}
          />
        ))}
      </div>
      <p className="mt-1 text-meta text-ink-muted" role="status">
        Password strength: {label}
      </p>
    </div>
  );
}
