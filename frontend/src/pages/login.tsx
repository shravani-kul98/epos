import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { LoaderCircle, LockKeyhole, Mail } from "lucide-react";

import { AuthLayout } from "@/components/layout/auth-layout";
import { Button } from "@/components/ui/button";
import { Field, TextInput } from "@/components/ui/form";
import { PasswordInput } from "@/components/ui/password-input";
import { ApiError, useAuth } from "@/lib/auth";

interface LocationState {
  from?: string;
}

export function LoginPage(): JSX.Element {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setError(null);

    if (!email.trim() || !password) {
      setError("Enter your email address and password.");
      return;
    }

    setSubmitting(true);
    try {
      await signIn(email.trim(), password);
      const target = (location.state as LocationState | null)?.from ?? "/";
      navigate(target, { replace: true });
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 429) {
        setError("Too many attempts. Wait a moment before trying again.");
      } else if (caught instanceof ApiError && caught.status === 0) {
        setError("EPOS could not be reached. Check your connection and try again.");
      } else if (caught instanceof ApiError && caught.status === 403) {
        // Sign-in refuses a disabled account only after the password was verified.
        setError("This account has been disabled. Contact your workspace administrator.");
      } else if (caught instanceof ApiError && caught.status >= 500) {
        setError(caught.message);
      } else {
        // Never reveal whether the address exists.
        setError("Email or password is incorrect.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout
      title="Sign in"
      description="Your role determines what you can see and change."
      footer={
        <>
          New to this workspace?{" "}
          <Link to="/register" className="font-medium text-accent hover:underline">
            Create an account
          </Link>
        </>
      }
    >
      <form className="mt-6 space-y-4" onSubmit={onSubmit} noValidate>
        <Field label="Work email" htmlFor="email">
          <TextInput
            enhanced
            leadingIcon={<Mail size={17} />}
            id="email"
            name="email"
            type="email"
            autoComplete="username"
            autoFocus
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </Field>

        <Field label="Password" htmlFor="password">
          <PasswordInput
            enhanced
            leadingIcon={<LockKeyhole size={17} />}
            id="password"
            name="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </Field>

        {error ? (
          <p
            className="rounded-control border border-critical/25 bg-critical-tint px-3 py-2 text-meta text-critical"
            role="alert"
          >
            {error}
          </p>
        ) : null}

        <Button type="submit" variant="primary" className="w-full" disabled={submitting} aria-busy={submitting}>
          {submitting ? <LoaderCircle size={17} className="godui-spinner" aria-hidden="true" /> : null}
          {submitting ? "Signing in" : "Sign in"}
        </Button>

        <p className="text-center text-meta text-ink-muted">
          Contact your workspace administrator for account recovery.
        </p>
      </form>
    </AuthLayout>
  );
}
