import { useState } from "react";
import { CaseStatusBadge, ErrorState, Loading, Panel } from "../../components/ui";
import { api, ApiError } from "../../lib/api";
import { formatDateTime } from "../../lib/format";
import { t, tDynamic, type MessageKey } from "../../lib/i18n";
import type { AuditEvent, Case, CaseStatus } from "../../lib/types";
import { useApi } from "../../lib/useApi";

const REASON_REQUIRED: ReadonlySet<CaseStatus> = new Set(["escalated", "dismissed", "closed", "reopened"]);

export function CasePanel({ alertId, caseId, onCaseOpened }: { alertId: string; caseId: string | null; onCaseOpened: (id: string) => void }) {
  const [opening, setOpening] = useState(false);
  const [openError, setOpenError] = useState<ApiError | null>(null);

  if (!caseId) {
    return (
      <Panel title={t("case.title")} id="case">
        <div className="stack">
          <p className="muted">{t("case.noCase")}</p>
          {openError && <ErrorState error={openError} />}
          <div>
            <button
              type="button"
              className="btn btn--primary"
              disabled={opening}
              data-testid="open-case"
              onClick={async () => {
                setOpening(true);
                setOpenError(null);
                try {
                  const c = await api.post<Case>("/api/v1/cases", { alert_id: alertId });
                  onCaseOpened(c.id);
                } catch (e) {
                  setOpenError(e as ApiError);
                } finally {
                  setOpening(false);
                }
              }}
            >
              {opening ? t("case.opening") : t("case.open")}
            </button>
          </div>
        </div>
      </Panel>
    );
  }
  return <CaseWorkspace caseId={caseId} />;
}

function CaseWorkspace({ caseId }: { caseId: string }) {
  const kase = useApi(`case:${caseId}`, (s) => api.get<Case>(`/api/v1/cases/${caseId}`, undefined, s));
  const audit = useApi(`audit:${caseId}`, (s) => api.get<AuditEvent[]>(`/api/v1/cases/${caseId}/audit`, undefined, s));
  const [action, setAction] = useState<CaseStatus | "">("");
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState<"decision" | "note" | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [conflict, setConflict] = useState(false);

  const c = kase.data;
  const needsReason = action !== "" && REASON_REQUIRED.has(action);
  const canSubmit = action !== "" && (!needsReason || reason.trim().length > 0) && saving === null;

  function refreshAll() {
    kase.reload();
    audit.reload();
  }

  async function submitDecision() {
    if (!c || action === "") return;
    setSaving("decision");
    setError(null);
    setConflict(false);
    try {
      await api.post<Case>(`/api/v1/cases/${c.id}/decisions`, {
        to_status: action,
        expected_version: c.version,
        reason: reason.trim() || null,
      });
      setAction("");
      setReason("");
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
      refreshAll();
    } catch (e) {
      setError(e as ApiError);
    } finally {
      setSaving(null);
    }
  }

  return (
    <Panel
      title={t("case.title")}
      id="case"
      actions={c ? <CaseStatusBadge status={c.status} /> : undefined}
      hint={c ? `${t("case.version", { n: c.version })} · ${t("case.assigned")}: ${c.assigned_to ?? "—"}` : undefined}
    >
      {kase.loading && !c && <Loading rows={3} />}
      {kase.error && <ErrorState error={kase.error} onRetry={kase.reload} />}
      {c && (
        <div className="stack">
          <div className="stack stack--sm">
            <h3>{t("case.decision")}</h3>
            {c.decision ? (
              <p data-testid="case-decision">
                <strong>{tDynamic("cs.", c.decision)}</strong>
                {c.decision_reason && <span className="muted"> — {c.decision_reason}</span>}
              </p>
            ) : (
              <p className="muted">{t("case.noDecision")}</p>
            )}
          </div>
          {c.allowed_transitions.length > 0 && (
            <form
              className="stack stack--sm"
              onSubmit={(e) => {
                e.preventDefault();
                if (canSubmit) void submitDecision();
              }}
            >
              <label className="field">
                {t("case.action")}
                <select className="select" value={action} onChange={(e) => setAction(e.target.value as CaseStatus | "")} data-testid="case-action">
                  <option value="">—</option>
                  {c.allowed_transitions.map((s) => (
                    <option key={s} value={s}>
                      {t(`act.${s}` as MessageKey)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                {t("case.reason")}
                <textarea
                  className="textarea"
                  value={reason}
                  maxLength={2000}
                  onChange={(e) => setReason(e.target.value)}
                  aria-required={needsReason}
                  data-testid="case-reason"
                />
                {needsReason && !reason.trim() && <span className="subtle">{t("case.reasonRequired")}</span>}
              </label>
              <div>
                <button type="submit" className="btn btn--primary" disabled={!canSubmit} data-testid="case-submit">
                  {saving === "decision" ? t("case.saving") : t("case.submit")}
                </button>
              </div>
              <p className="subtle">{t("case.humanOnly")}</p>
            </form>
          )}
          {conflict && (
            <div className="callout callout--warn" role="alert">
              {t("case.conflict")}
            </div>
          )}
          {error && <ErrorState error={error} />}

          <div className="stack stack--sm">
            <h3>{t("case.notes")}</h3>
            {c.notes.length === 0 && <p className="subtle">{t("case.noNotes")}</p>}
            <ul className="timeline" data-testid="case-notes">
              {c.notes.map((n) => (
                <li key={n.id}>
                  <span className="timeline__dot" aria-hidden="true" />
                  <div>
                    {/* Rendered as text: React escapes it; notes are never injected as HTML. */}
                    <p style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{n.body}</p>
                    <span className="subtle">
                      {n.author} · {formatDateTime(n.created_at)}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
            <form
              className="stack stack--sm"
              onSubmit={(e) => {
                e.preventDefault();
                void submitNote();
              }}
            >
              <label className="field">
                <span className="visually-hidden">{t("case.notes")}</span>
                <textarea
                  className="textarea"
                  value={note}
                  maxLength={4000}
                  placeholder={t("case.notePlaceholder")}
                  onChange={(e) => setNote(e.target.value)}
                  data-testid="case-note-input"
                />
              </label>
              <div>
                <button type="submit" className="btn btn--sm" disabled={!note.trim() || saving !== null}>
                  {t("case.addNote")}
                </button>
              </div>
            </form>
          </div>

          <div className="stack stack--sm">
            <h3>{t("case.audit")}</h3>
            <p className="subtle">{t("case.auditHint")}</p>
            {audit.error && <ErrorState error={audit.error} onRetry={audit.reload} />}
            <ol className="timeline" data-testid="audit-log">
              {(audit.data ?? []).map((ev) => (
                <li key={ev.id}>
                  <span className="timeline__dot" aria-hidden="true" />
                  <div>
                    <strong>{tDynamic("audit.", ev.action, ev.action)}</strong>
                    {ev.reason && <span className="muted"> — {ev.reason}</span>}
                    <div className="subtle">
                      {ev.actor} · {formatDateTime(ev.created_at)} · <code className="mono">{ev.request_id}</code>
                    </div>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </div>
      )}
    </Panel>
  );
}
