import { Children, createContext, forwardRef, isValidElement, useContext } from "react";
import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";

import { cn } from "@/lib/cn";
import { MagicInput } from "@/components/godui/magic-input";

const FieldContext = createContext<{ htmlFor?: string; describedBy?: string; invalid?: boolean }>({});

function describedBy(explicit?: string, field?: string): string | undefined {
  return [explicit, field].filter(Boolean).join(" ") || undefined;
}

export function Field({
  label,
  htmlFor,
  hint,
  error,
  children,
  required,
}: {
  label: string;
  htmlFor: string;
  hint?: string;
  error?: string;
  children: ReactNode;
  required?: boolean;
}): JSX.Element {
  const isRequired = required ?? Children.toArray(children).some(
    (child) => isValidElement<{ required?: boolean }>(child) && child.props.required,
  );
  const description = [hint ? `${htmlFor}-hint` : "", error ? `${htmlFor}-error` : ""].filter(Boolean).join(" ");
  return (
    <FieldContext.Provider value={{ htmlFor, describedBy: description || undefined, invalid: Boolean(error) }}>
    <div className="space-y-1.5">
      <div className="flex gap-1 text-meta font-medium text-ink">
        <label htmlFor={htmlFor}>{label}</label>
        {isRequired ? <span className="text-critical" aria-hidden="true">*</span> : null}
      </div>
      {children}
      {hint ? <p id={`${htmlFor}-hint`} className="text-meta text-ink-secondary">{hint}</p> : null}
      {error ? (
        <p id={`${htmlFor}-error`} className="text-meta text-critical" role="alert">
          {error}
        </p>
      ) : null}
    </div>
    </FieldContext.Provider>
  );
}

export interface TextInputProps extends InputHTMLAttributes<HTMLInputElement> {
  leadingIcon?: ReactNode;
  enhanced?: boolean;
}

export const TextInput = forwardRef<HTMLInputElement, TextInputProps>(
  function TextInput({ className, enhanced = true, leadingIcon, ...props }, ref) {
    const field = useContext(FieldContext);
    if (enhanced) {
      const { size, onSubmit, style, ...inputProps } = props;
      return <MagicInput ref={ref} id={field.htmlFor} {...inputProps} nativeSize={size} nativeOnSubmit={onSubmit}
        leadingIcon={leadingIcon} size={leadingIcon ? "md" : "sm"} rainbow={false} inputClassName={className} inputStyle={style}
        aria-invalid={props["aria-invalid"] ?? (field.invalid || undefined)}
        aria-describedby={describedBy(props["aria-describedby"], field.describedBy)} />;
    }
    return <input ref={ref} id={field.htmlFor} {...props} aria-invalid={props["aria-invalid"] ?? (field.invalid || undefined)} aria-describedby={describedBy(props["aria-describedby"], field.describedBy)} className={cn("control min-h-10", className)} />;
  },
);

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(
  function Select({ className, ...props }, ref) {
    const field = useContext(FieldContext);
    return <select ref={ref} id={field.htmlFor} {...props} aria-invalid={props["aria-invalid"] ?? (field.invalid || undefined)} aria-describedby={describedBy(props["aria-describedby"], field.describedBy)} className={cn("control min-h-10", className)} />;
  },
);

export const TextArea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function TextArea({ className, ...props }, ref) {
    const field = useContext(FieldContext);
    return <textarea ref={ref} id={field.htmlFor} {...props} aria-invalid={props["aria-invalid"] ?? (field.invalid || undefined)} aria-describedby={describedBy(props["aria-describedby"], field.describedBy)} className={cn("control py-2", className)} />;
  },
);

/** A labelled checkbox with an explanation of what ticking it changes. */
export function CheckboxField({ id, label, hint, checked, onChange, disabled }: {
  id: string;
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}): JSX.Element {
  return (
    <div className="flex items-start gap-2.5">
      <input id={id} type="checkbox" className="mt-1 h-4 w-4 shrink-0 accent-accent" checked={checked} disabled={disabled}
        aria-describedby={hint ? `${id}-hint` : undefined} onChange={event => onChange(event.target.checked)} />
      <div>
        <label htmlFor={id} className="text-body font-medium text-ink">{label}</label>
        {hint ? <p id={`${id}-hint`} className="text-meta text-ink-secondary">{hint}</p> : null}
      </div>
    </div>
  );
}
