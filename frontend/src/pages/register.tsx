import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { BriefcaseBusiness, LoaderCircle, LockKeyhole, Mail, UserRound } from "lucide-react";

import { AuthLayout } from "@/components/layout/auth-layout";
import { Button } from "@/components/ui/button";
import { Field, TextInput } from "@/components/ui/form";
import { PasswordInput, PasswordStrength, assessPassword } from "@/components/ui/password-input";
import { ApiError, useAuth } from "@/lib/auth";

interface FormState {
  full_name: string;
  email: string;
  job_title: string;
  password: string;
  confirm: string;
}

const EMPTY: FormState = { full_name: "", email: "", job_title: "", password: "", confirm: "" };

export function RegisterPage(): JSX.Element {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const invitationCode = searchParams.get("invite") || null;
  const invitedEmail = invitationCode ? (searchParams.get("email") ?? "").trim() : "";
  // An invitation is bound to one address, so the address it names cannot be edited here.
  const emailLocked = invitedEmail !== "";
  const [form, setForm] = useState<FormState>(() => ({ ...EMPTY, email: invitedEmail }));
  const [errors, setErrors] = useState<Partial<Record<keyof FormState, string>>>({});
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function update<K extends keyof FormState>(key: K, value: FormState[K]): void {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function validate(): boolean {
    const next: Partial<Record<keyof FormState, string>> = {};
    if (form.full_name.trim().length < 2) next.full_name = "Enter your full name.";
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(form.email.trim())) {
      next.email = "Enter a valid work email address.";
    }
    if (form.password.length < 12) {
      next.password = "Use at least 12 characters.";
    } else if (assessPassword(form.password).score <= 2) {
      next.password = "Add more variety, such as mixed case, a number or a symbol.";
    }
    if (form.confirm !== form.password) next.confirm = "Both passwords must match.";
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  async function onSubmit(event: React.FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setSubmitError(null);
    if (!validate()) return;

    setSubmitting(true);
    try {
      // Entered values are deliberately preserved; only navigation clears the form.
      await register({
        full_name: form.full_name.trim(),
        email: form.email.trim(),
        password: form.password,
        job_title: form.job_title.trim() || null,
        ...(invitationCode ? { invitation_code: invitationCode } : {}),
      });
      navigate("/welcome", { replace: true });
    } catch (caught) {
      // A duplicate never confirms the address is registered, and limits explain what to do next.
      setSubmitError(
        caught instanceof ApiError && caught.status === 403
          ? "Sign-up is not open for this address. Ask a workspace administrator for an account."
          : caught instanceof ApiError && [409, 422, 429].includes(caught.status)
            ? caught.message
            : "Your account could not be created. Try again.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout
      title="Create your account"
      description={
        invitationCode
          ? "Your invitation sets the role you join with. Complete your details to finish."
          : "You will join as a workspace member. An administrator can extend your access later."
      }
      footer={
        <>
          Already have an account?{" "}
          <Link to="/login" className="font-medium text-accent hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      <form className="mt-6 space-y-4" onSubmit={onSubmit} noValidate>
        {invitationCode ? (
          <p className="rounded-control border border-accent/25 bg-accent-tint px-3 py-2 text-meta text-ink">
            You were invited to this workspace by an administrator, who chose your role.
          </p>
        ) : null}

        <Field label="Full name" htmlFor="full_name" {...(errors.full_name ? { error: errors.full_name } : {})}>
          <TextInput
            enhanced
            leadingIcon={<UserRound size={17} />}
            id="full_name"
            autoComplete="name"
            autoFocus
            value={form.full_name}
            onChange={(event) => update("full_name", event.target.value)}
          />
        </Field>

        <Field
          label="Work email"
          htmlFor="email"
          {...(emailLocked ? { hint: "Set by your invitation." } : {})}
          {...(errors.email ? { error: errors.email } : {})}
        >
          <TextInput
            enhanced
            leadingIcon={<Mail size={17} />}
            id="email"
            type="email"
            autoComplete="username"
            readOnly={emailLocked}
            value={form.email}
            onChange={(event) => update("email", event.target.value)}
          />
        </Field>

        <Field label="Job title" htmlFor="job_title" hint="Optional. Helps colleagues identify you.">
          <TextInput
            enhanced
            leadingIcon={<BriefcaseBusiness size={17} />}
            id="job_title"
            value={form.job_title}
            onChange={(event) => update("job_title", event.target.value)}
          />
        </Field>

        <div>
          <Field
            label="Password"
            htmlFor="password"
            hint="At least 12 characters."
            {...(errors.password ? { error: errors.password } : {})}
          >
            <PasswordInput
              enhanced
              leadingIcon={<LockKeyhole size={17} />}
              id="password"
              autoComplete="new-password"
              value={form.password}
              onChange={(event) => update("password", event.target.value)}
            />
          </Field>
          <PasswordStrength value={form.password} />
        </div>

        <Field label="Confirm password" htmlFor="confirm" {...(errors.confirm ? { error: errors.confirm } : {})}>
          <PasswordInput
            enhanced
            leadingIcon={<LockKeyhole size={17} />}
            id="confirm"
            autoComplete="new-password"
            value={form.confirm}
            onChange={(event) => update("confirm", event.target.value)}
          />
        </Field>

        {submitError ? (
          <p
            className="rounded-control border border-critical/25 bg-critical-tint px-3 py-2 text-meta text-critical"
            role="alert"
          >
            {submitError}
          </p>
        ) : null}

        <Button type="submit" variant="primary" className="w-full" disabled={submitting} aria-busy={submitting}>
          {submitting ? <LoaderCircle size={17} className="godui-spinner" aria-hidden="true" /> : null}
          {submitting ? "Creating your account" : "Create account"}
        </Button>
      </form>
    </AuthLayout>
  );
}
