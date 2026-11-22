import { useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode } from "react";
import { Navigate, useLocation, useNavigate, useSearchParams } from "react-router";
import { safeNext, signIn, useAuth } from "../../app/auth";
import { ThemeSwitch } from "../../components/layout/ThemeSwitch";
import { Icon } from "../../components/ui/icons";
import { ApiError } from "../../lib/api";
import { t } from "../../lib/i18n";
import { NetworkBackdrop } from "./NetworkBackdrop";

function BrandLockup() {
  return (
    <div className="brand auth__lockup">
      <span className="brand__mark" aria-hidden="true">
        <svg viewBox="0 0 24 24" width="20" height="20">
          <path d="M5 19V5l14 14V5" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
      <span className="brand__text">
        <span className="brand__name">{t("app.name")}</span>
        <span className="brand__team">{t("app.team")}</span>
      </span>
    </div>
  );
}

/** Shared frame for the sign-in screen and the session check, so there is no layout jump between them. */
function AuthFrame({ children }: { children: ReactNode }) {
  return (
    <div className="auth">
      <section className="auth__brand">
        <div className="auth__top">
          <BrandLockup />
          <span className="auth__theme">
            <ThemeSwitch />
          </span>
        </div>
        <div className="auth__hero">
          <h1 className="auth__headline" lang="en">
            {t("auth.brandHeadline")}
          </h1>
          <p className="auth__sub" lang="en">
            {t("auth.brandSubheading")}
          </p>
        </div>
        <div className="auth__viz">
          <NetworkBackdrop />
        </div>
        <ul className="auth__points">
          {(["auth.point.evidence", "auth.point.graph", "auth.point.analyst"] as const).map((k) => (
            <li key={k}>
              <Icon name="check" size={16} />
              {t(k)}
            </li>
          ))}
        </ul>
      </section>
      <main className="auth__side" id="main">
        {children}
      </main>
    </div>
  );
}

/** Shown while the server confirms whether the browser's cookie is a live session. */
export function AuthSplash() {
  return (
    <AuthFrame>
      <div className="auth__panel auth__panel--checking" role="status" aria-live="polite">
        <span className="auth__spinner" aria-hidden="true" />
        <span className="visually-hidden">{t("auth.checking")}</span>
      </div>
    </AuthFrame>
  );
}

/** Route guard: every application screen requires a session the server has accepted. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const location = useLocation();
  if (auth.status === "checking") return <AuthSplash />;
  if (auth.status !== "authenticated") {
    const query = new URLSearchParams();
    const here = `${location.pathname}${location.search}${location.hash}`;
    // After an explicit sign-out the next user starts at the overview; after expiry, where they were.
    if (auth.status !== "signed_out" && here !== "/") query.set("next", here);
    if (auth.status === "expired" || auth.status === "signed_out") query.set("reason", auth.status);
    const qs = query.toString();
    return <Navigate to={qs ? `/login?${qs}` : "/login"} replace />;
  }
  return <>{children}</>;
}

type FieldErrors = { username?: string; password?: string };

function describeFailure(error: unknown): { message: string; credentials: boolean } {
  if (error instanceof ApiError) {
    if (error.status === 401 || error.status === 422) return { message: t("auth.invalid"), credentials: true };
    if (error.status === 429) {
      const seconds = Number(error.details.retry_after_seconds) || 60;
      return { message: t("auth.throttled", { minutes: Math.max(1, Math.ceil(seconds / 60)) }), credentials: false };
    }
    if (error.status === 0) return { message: t("auth.network"), credentials: false };
  }
  return { message: t("auth.failed"), credentials: false };
}

export function LoginPage() {
  const auth = useAuth();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const next = safeNext(params.get("next"));
  const reason = params.get("reason");

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [reveal, setReveal] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [capsLock, setCapsLock] = useState(false);
  const inFlight = useRef(false);
  const userRef = useRef<HTMLInputElement>(null);
  const passRef = useRef<HTMLInputElement>(null);
  const ids = useId();
  const userErrId = `${ids}-user-error`;
  const passErrId = `${ids}-pass-error`;
  const capsId = `${ids}-caps`;

  // Focus the first field on devices with a precise pointer once the form is actually shown (the
  // session check renders a splash first). On touch devices focusing would open the on-screen
  // keyboard and cover the screen before the user has seen it.
  const formShown = auth.status !== "checking";
  useEffect(() => {
    if (formShown && window.matchMedia("(pointer: fine)").matches) userRef.current?.focus({ preventScroll: true });
  }, [formShown]);

  if (auth.status === "checking") return <AuthSplash />;
  if (auth.status === "authenticated" && !submitting) return <Navigate to={next} replace />;

  const notice = formError ? null : reason === "expired" ? t("auth.expired") : reason === "signed_out" ? t("auth.signedOut") : null;

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (inFlight.current) return; // double submit (Enter + click, repeated taps)
    const errors: FieldErrors = {};
    if (!username.trim()) errors.username = t("auth.usernameRequired");
    if (!password) errors.password = t("auth.passwordRequired");
    setFieldErrors(errors);
    setFormError(null);
    if (errors.username) return userRef.current?.focus();
    if (errors.password) return passRef.current?.focus();

    inFlight.current = true;
    setSubmitting(true);
    try {
      await signIn(username.trim(), password);
      setPassword("");
      navigate(next, { replace: true });
    } catch (err) {
      const failure = describeFailure(err);
      setFormError(failure.message);
      if (failure.credentials) {
        setPassword("");
        passRef.current?.focus();
      }
    } finally {
      inFlight.current = false;
      setSubmitting(false);
    }
  }

  const onPasswordKey = (e: KeyboardEvent<HTMLInputElement>) => setCapsLock(e.getModifierState?.("CapsLock") ?? false);

  return (
    <AuthFrame>
      <div className="auth__panel" data-testid="login-panel">
        <header className="auth__head">
          <h2 className="auth__title">{t("auth.title")}</h2>
          <p className="auth__subtitle">{t("auth.subtitle")}</p>
        </header>

        {notice && (
          <div className="callout auth__notice" role="status" data-testid="login-notice">
            <Icon name="info" size={16} />
            {notice}
          </div>
        )}
        <div aria-live="assertive" className="auth__error-slot">
          {formError && (
            <div className="callout callout--error auth__error" role="alert" data-testid="login-error">
              <Icon name="contradicted" size={16} />
              {formError}
            </div>
          )}
        </div>

        <form className="auth__form" onSubmit={onSubmit} noValidate aria-busy={submitting} aria-label={t("auth.subtitle")}>
          <label className="field">
            <span>{t("auth.username")}</span>
            <input
              ref={userRef}
              className="input auth__input"
              name="username"
              type="text"
              autoComplete="username"
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              inputMode="text"
              enterKeyHint="next"
              maxLength={256}
              value={username}
              readOnly={submitting}
              onChange={(e) => {
                setUsername(e.target.value);
                if (fieldErrors.username) setFieldErrors((f) => ({ ...f, username: undefined }));
              }}
              aria-invalid={fieldErrors.username ? true : undefined}
              aria-describedby={fieldErrors.username ? userErrId : undefined}
              data-testid="login-username"
            />
            {fieldErrors.username && (
              <span className="field__error" id={userErrId}>
                {fieldErrors.username}
              </span>
            )}
          </label>

          <div className="field">
            <label htmlFor={`${ids}-password`}>{t("auth.password")}</label>
            <div className="auth__password">
              <input
                ref={passRef}
                id={`${ids}-password`}
                className="input auth__input"
                name="password"
                type={reveal ? "text" : "password"}
                autoComplete="current-password"
                autoCapitalize="none"
                autoCorrect="off"
                spellCheck={false}
                enterKeyHint="go"
                maxLength={1024}
                value={password}
                readOnly={submitting}
                onChange={(e) => {
                  setPassword(e.target.value);
                  if (fieldErrors.password) setFieldErrors((f) => ({ ...f, password: undefined }));
                }}
                onKeyDown={onPasswordKey}
                onKeyUp={onPasswordKey}
                onBlur={() => setCapsLock(false)}
                aria-invalid={fieldErrors.password ? true : undefined}
                aria-describedby={[fieldErrors.password && passErrId, capsLock && capsId].filter(Boolean).join(" ") || undefined}
                data-testid="login-password"
              />
              <button
                type="button"
                className="auth__reveal"
                onClick={() => setReveal((r) => !r)}
                aria-pressed={reveal}
                aria-controls={`${ids}-password`}
                aria-label={reveal ? t("auth.hidePassword") : t("auth.showPassword")}
                title={reveal ? t("auth.hidePassword") : t("auth.showPassword")}
                data-testid="login-reveal"
              >
                <Icon name={reveal ? "eyeOff" : "eye"} size={18} />
              </button>
            </div>
            {fieldErrors.password && (
              <span className="field__error" id={passErrId}>
                {fieldErrors.password}
              </span>
            )}
            {capsLock && (
              <span className="field__help auth__caps" id={capsId}>
                {t("auth.capsLock")}
              </span>
            )}
          </div>

          <button type="submit" className="btn btn--primary btn--lg btn--block auth__submit" disabled={submitting} data-testid="login-submit">
            {submitting && <span className="auth__spinner auth__spinner--inline" aria-hidden="true" />}
            {submitting ? t("auth.submitting") : t("auth.submit")}
          </button>
        </form>

        <p className="auth__footer">
          <Icon name="shield" size={16} />
          {t("auth.footer")}
        </p>
      </div>
    </AuthFrame>
  );
}
