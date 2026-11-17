import { useState } from "react";
import { CaseStatusBadge, ErrorState, Icon, Loading } from "../../components/ui";
import { api, ApiError } from "../../lib/api";
import { formatDateTime } from "../../lib/format";
import { t, tDynamic, type MessageKey } from "../../lib/i18n";
import type { AuditEvent, Case, CaseStatus } from "../../lib/types";
import { useApi } from "../../lib/useApi";

const REASON_REQUIRED: ReadonlySet<CaseStatus> = new Set(["escalated", "dismissed", "closed", "reopened"]);
/** Decisions that end the investigation get an explicit second confirmation. */
const FINAL: ReadonlySet<CaseStatus> = new Set(["dismissed", "closed"]);

/** Open a case for an alert. The only write the header exposes; decisions live in CaseWorkspace. */
export function useOpenCase(alertId: string, onOpened: (id: string) => void) {
  const [opening, setOpening] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  async function open() {
    setOpening(true);
    setError(null);
    try {
      const c = await api.post<Case>("/api/v1/cases", { alert_id: alertId });
      onOpened(c.id);
    } catch (e) {
      setError(e as ApiError);
    } finally {
      setOpening(false);
    }
  }
  return { open, opening, error };
}

export function CasePanel({ caseId, onOpen, opening, onChanged }: { caseId: string | null; onOpen: () => void; opening: boolean; onChanged?: () => void }) {
  if (!caseId) {
    return (
      <section className="panel decision" id="case" aria-labelledby="case-title">
        <div className="panel__head">
          <div className="panel__titles">
            <h2 id="case-title">{t("case.title")}</h2>
            <p className="panel__hint">{t("case.noCase")}</p>
          </div>
        </div>
        <div className="panel__body">
          <button type="button" className="btn btn--block" onClick={onOpen} disabled={opening}>
            {opening ? t("case.opening") : t("case.open")}
          </button>
          <p className="decision__note">{t("case.humanOnly")}</p>
        </div>
      </section>
    );
  }
  return <CaseWorkspace caseId={caseId} onChanged={onChanged} />;
}

function CaseWorkspace({ caseId, onChanged }: { caseId: string; onChanged?: () => void }) {
  const kase = useApi(`case:${caseId}`, (s) => api.get<Case>(`/api/v1/cases/${caseId}`, undefined, s));
  const audit = useApi(`audit:${caseId}`, (s) => api.get<AuditEvent[]>(`/api/v1/cases/${caseId}/audit`, undefined, s));
  const [action, setAction] = useState<CaseStatus | "">("");
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState<"decision" | "note" | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [saved, setSaved] = useState<{ kind: "decision" | "note"; label: string } | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [conflict, setConflict] = useState(false);

  const c = kase.data;
  const needsReason = action !== "" && REASON_REQUIRED.has(action);
  const canSubmit = action !== "" && (!needsReason || reason.trim().length > 0) && saving === null;

  function refreshAll() {
    kase.reload();
    audit.reload();
    onChanged?.();
  }

  function choose(next: CaseStatus) {
    setAction(next);
    setConfirming(false);
    setSaved(null);
  }

  async function submitDecision() {
    if (!c || action === "") return;
    if (FINAL.has(action) && !confirming) {
      setConfirming(true);
      return;
    }
    setSaving("decision");
    setError(null);
    setConflict(false);
    try {
      await api.post<Case>(`/api/v1/cases/${c.id}/decisions`, {
        to_status: action,
        expected_version: c.version,
        reason: reason.trim() || null,
      });
      setSaved({ kind: "decision", label: tDynamic("cs.", action) });
      setAction("");
      setReason("");
      setConfirming(false);
      refreshAll();
    } catch (e) {
      const err = e as ApiError;
      if (err.code === "CASE_VERSION_CONFLICT") {
        setConflict(true);
        refreshAll();
      } else setError(err);
    } finally {
      setSaving(null);
    }
  }

  async function submitNote() {
    if (!c || !note.trim()) return;
    setSaving("note");
    setError(null);
    try {
      await api.post<Case>(`/api/v1/cases/${c.id}/notes`, { body: note });
      setNote("");
      setSaved({ kind: "note", label: t("case.noteSaved") });
      refreshAll();
    } catch (e) {
      setError(e as ApiError);
    } finally {
      setSaving(null);
    }
  }

  return (
    <section className="panel decision" id="case" aria-labelledby="case-title">
      <div className="panel__head">
        <div className="panel__titles">
          <h2 id="case-title">{t("case.title")}</h2>
          {c && <p className="panel__hint">{t("case.meta", { n: c.version, who: c.assigned_to ?? "—" })}</p>}
        </div>
        {c && <CaseStatusBadge status={c.status} />}
      </div>
      <div className="panel__body">
        {kase.loading && !c && <Loading rows={3} />}
        {kase.error && <ErrorState error={kase.error} onRetry={kase.reload} />}
        {c && (
          <div className="decision__stack">
            <div className="decision__current">
              <span className="ctx__label">{t("case.decision")}</span>
              {c.decision ? (
                <p data-testid="case-decision">
                  <strong>{tDynamic("cs.", c.decision)}</strong>
                  {c.decision_reason && <span className="decision__reason">{c.decision_reason}</span>}
                </p>
              ) : (
                <p className="ctx__note">{t("case.noDecision")}</p>
              )}
            </div>

            {saved && (
              <div className="callout callout--ok" role="status">
                <Icon name="supported" size={16} />
                {saved.kind === "decision" ? t("case.savedDecision", { label: saved.label }) : saved.label}
              </div>
            )}

            {c.allowed_transitions.length > 0 && (
              <form
                className="decision__form"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (canSubmit) void submitDecision();
                }}
              >
                <fieldset className="choice-group" data-testid="case-action">
                  <legend className="ctx__label">{t("case.action")}</legend>
                  {c.allowed_transitions.map((s) => (
                    <label key={s} className="choice" data-final={FINAL.has(s) ? "true" : undefined}>
                      <input type="radio" name="case-action" value={s} checked={action === s} onChange={() => choose(s)} />
                      <span className="choice__text">
                        <span className="choice__label">{t(`act.${s}` as MessageKey)}</span>
                        <span className="choice__hint">{t(`act.${s}.hint` as MessageKey)}</span>
                      </span>
                    </label>
                  ))}
                </fieldset>
                <label className="field">
                  <span>
                    {t("case.reason")}
                    {needsReason && <span className="field__req"> · {t("case.required")}</span>}
                  </span>
                  <textarea
                    className="textarea"
                    value={reason}
                    maxLength={2000}
                    onChange={(e) => setReason(e.target.value)}
                    aria-required={needsReason}
                    aria-describedby={needsReason && !reason.trim() ? "reason-help" : undefined}
                    data-testid="case-reason"
                  />
                  {needsReason && !reason.trim() && (
                    <span className="field__help" id="reason-help">
                      {t("case.reasonRequired")}
                    </span>
                  )}
                </label>
                {confirming && action !== "" ? (
                  <div className="confirm" role="alertdialog" aria-labelledby="confirm-text">
                    <p id="confirm-text">{t("case.confirm", { label: t(`act.${action}` as MessageKey) })}</p>
                    <div className="confirm__actions">
                      <button type="submit" className="btn btn--primary" disabled={!canSubmit} data-testid="case-submit" autoFocus>
                        {saving === "decision" ? t("case.saving") : t("case.confirmYes")}
                      </button>
                      <button type="button" className="btn btn--ghost" onClick={() => setConfirming(false)}>
                        {t("common.cancel")}
                      </button>
                    </div>
                  </div>
                ) : (
                  <button type="submit" className="btn btn--primary btn--block" disabled={!canSubmit} data-testid="case-submit">
                    {saving === "decision" ? t("case.saving") : t("case.submit")}
                  </button>
                )}
                <p className="decision__note">{t("case.humanOnly")}</p>
              </form>
            )}
            {conflict && (
              <div className="callout callout--warn" role="alert">
                {t("case.conflict")}
              </div>
            )}
            {error && <ErrorState error={error} />}

            <div className="decision__block">
              <h3 className="ctx__label">{t("case.notes")}</h3>
              {c.notes.length === 0 && <p className="ctx__note">{t("case.noNotes")}</p>}
              <ul className="timeline" data-testid="case-notes">
                {c.notes.map((n) => (
                  <li key={n.id}>
                    <span className="timeline__dot" aria-hidden="true" />
                    <div>
                      {/* Rendered as text: React escapes it; notes are never injected as HTML. */}
                      <p className="timeline__text">{n.body}</p>
                      <span className="cell-note">
                        {n.author} · {formatDateTime(n.created_at)}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
              <form
                className="note-form"
                onSubmit={(e) => {
                  e.preventDefault();
                  void submitNote();
                }}
              >
                <label className="field">
                  <span className="visually-hidden">{t("case.notes")}</span>
                  <textarea
                    className="textarea textarea--sm"
                    value={note}
                    maxLength={4000}
                    placeholder={t("case.notePlaceholder")}
                    onChange={(e) => setNote(e.target.value)}
                    data-testid="case-note-input"
                  />
                </label>
                <button type="submit" className="btn btn--sm" disabled={!note.trim() || saving !== null}>
                  {t("case.addNote")}
                </button>
              </form>
            </div>

            <div className="decision__block">
              <h3 className="ctx__label">{t("case.audit")}</h3>
              <p className="ctx__note">{t("case.auditHint")}</p>
              {audit.error && <ErrorState error={audit.error} onRetry={audit.reload} />}
              <ol className="timeline timeline--audit" data-testid="audit-log">
                {(audit.data ?? []).map((ev) => (
                  <li key={ev.id}>
                    <span className="timeline__dot" aria-hidden="true" />
                    <div>
                      <strong>{tDynamic("audit.", ev.action, ev.action)}</strong>
                      {ev.reason && <span className="decision__reason">{ev.reason}</span>}
                      <div className="cell-note">
                        {ev.actor} · {formatDateTime(ev.created_at)} · <code className="mono">{ev.request_id}</code>
                      </div>
                    </div>
                  </li>
                ))}
              </ol>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
