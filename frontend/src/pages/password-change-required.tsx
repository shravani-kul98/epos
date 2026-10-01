import { useState } from "react";
import type { FormEvent } from "react";
import { KeyRound, LoaderCircle, LockKeyhole } from "lucide-react";

import { AuthLayout } from "@/components/layout/auth-layout";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/form";
import { PasswordInput, PasswordStrength } from "@/components/ui/password-input";
import { ApiError, useAuth } from "@/lib/auth";
import { useChangePassword } from "@/lib/queries";

const MIN_PASSWORD_LENGTH = 12;

/**
 * Shown instead of the workspace after an administrator reset. The API refuses every other
 * request until the temporary password is replaced, so this is the only way forward.
 */
export function PasswordChangeRequiredPage(): JSX.Element {
  const { user, signIn, signOut } = useAuth();
  const changePassword = useChangePassword();
  const [temporary, setTemporary] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setError(null);
    if (!user) return;
    if (!temporary || next.length < MIN_PASSWORD_LENGTH) {
      setError(`Enter the temporary password and a new one of at least ${MIN_PASSWORD_LENGTH} characters.`);
      return;
    }
    if (next !== confirm) {
      setError("Both new passwords must match.");
      return;
    }
    if (next === temporary) {
      setError("Choose a password different from the temporary one.");
      return;
    }
    setSubmitting(true);
    try {
      await changePassword.mutateAsync({ current_password: temporary, new_password: next });
    } catch (caught) {
      setError(
        caught instanceof ApiError && caught.status === 403
          ? "The temporary password is not correct."
          : caught instanceof ApiError
            ? caught.message
            : "Your password could not be changed.",
      );
      setSubmitting(false);
      return;
    }
    // The change ends every session, this one included, so sign straight back in with the new one.
    try {
      await signIn(user.email, next);
    } catch {
      await signOut();
    }
    setSubmitting(false);
  }

  return (
    <AuthLayout
      title="Choose a new password"
      description="Your administrator issued a temporary password. Replace it with one only you know to open your workspace."
      footer={<button type="button" className="font-medium text-accent hover:underline" onClick={() => void signOut()}>Sign out instead</button>}
    >
      <form className="mt-6 space-y-4" onSubmit={(event) => void submit(event)} noValidate>
        {user ? <p className="text-meta text-ink-secondary">Signed in as {user.email}</p> : null}
        <Field label="Temporary password" htmlFor="temporary-password">
          <PasswordInput enhanced leadingIcon={<KeyRound size={17} />} id="temporary-password" autoComplete="current-password" autoFocus required
            value={temporary} onChange={(event) => setTemporary(event.target.value)} />
        </Field>
        <Field label="New password" htmlFor="new-password" hint={`At least ${MIN_PASSWORD_LENGTH} characters, with some variety.`}>
          <PasswordInput enhanced leadingIcon={<LockKeyhole size={17} />} id="new-password" autoComplete="new-password" required
            value={next} onChange={(event) => setNext(event.target.value)} />
        </Field>
        <PasswordStrength value={next} />
        <Field label="Confirm new password" htmlFor="confirm-new-password">
          <PasswordInput enhanced leadingIcon={<LockKeyhole size={17} />} id="confirm-new-password" autoComplete="new-password" required
            value={confirm} onChange={(event) => setConfirm(event.target.value)} />
        </Field>
        {error ? (
          <p className="rounded-control border border-critical/25 bg-critical-tint px-3 py-2 text-meta text-critical" role="alert">{error}</p>
        ) : null}
        <Button type="submit" variant="primary" className="w-full" disabled={submitting} aria-busy={submitting}>
          {submitting ? <LoaderCircle size={17} className="godui-spinner" aria-hidden="true" /> : null}
          {submitting ? "Saving new password" : "Save and continue"}
        </Button>
        <p className="text-center text-meta text-ink-muted">Every other session on this account ends when the password changes.</p>
      </form>
    </AuthLayout>
  );
}
