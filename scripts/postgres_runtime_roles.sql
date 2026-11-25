-- Run as the database and schema owner after Alembic, on a dedicated NEXORA database.
-- Group roles have no login. Provision separate service login roles outside this file.
BEGIN;

DO $roles$
DECLARE
    role_name text;
BEGIN
    FOREACH role_name IN ARRAY ARRAY[
        'nexora_api_runtime', 'nexora_worker_runtime', 'nexora_reporting', 'nexora_audit_appender'
    ] LOOP
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = role_name) THEN
            EXECUTE format('CREATE ROLE %I NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS', role_name);
        ELSIF EXISTS (
            SELECT FROM pg_roles WHERE rolname = role_name
              AND (rolcanlogin OR rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls)
        ) THEN
            RAISE EXCEPTION 'Runtime group % has elevated privileges', role_name;
        END IF;
    END LOOP;
END
$roles$;

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO nexora_api_runtime, nexora_worker_runtime, nexora_reporting, nexora_audit_appender;
GRANT SELECT ON public.alembic_version TO nexora_api_runtime;
GRANT SELECT ON public.datasets, public.import_batches, public.transactions,
    public.graph_snapshots, public.formations, public.evidence, public.evidence_transactions,
    public.fraud_signals, public.risk_assessments, public.alerts, public.cases, public.case_notes,
    public.audit_events, public.analysis_jobs, public.csv_import_requests, public.csv_import_jobs,
    public.transfer_assessments, public.transfer_action_events TO nexora_api_runtime;
GRANT INSERT ON public.datasets, public.import_batches, public.transactions, public.analysis_jobs,
    public.csv_import_requests, public.csv_import_jobs, public.cases, public.case_notes,
    public.transfer_assessments TO nexora_api_runtime;
GRANT UPDATE (result) ON public.csv_import_requests TO nexora_api_runtime;
GRANT UPDATE (status, content) ON public.csv_import_jobs TO nexora_api_runtime;
GRANT UPDATE ON public.cases TO nexora_api_runtime;
GRANT UPDATE (status) ON public.alerts TO nexora_api_runtime;
GRANT UPDATE (accepted, duplicate, quarantined, rejected, report, status, completed_at)
    ON public.import_batches TO nexora_api_runtime, nexora_worker_runtime;
-- The runtime can advance sandbox status; the original assessment remains immutable.
REVOKE UPDATE (id) ON public.transfer_assessments FROM nexora_api_runtime;
GRANT UPDATE (status) ON public.transfer_assessments TO nexora_api_runtime;

GRANT SELECT ON public.datasets, public.import_batches, public.transactions, public.csv_import_requests,
    public.csv_import_jobs, public.analysis_jobs, public.graph_snapshots, public.alerts TO nexora_worker_runtime;
GRANT INSERT ON public.datasets, public.import_batches, public.transactions, public.csv_import_requests,
    public.graph_snapshots, public.formations, public.evidence, public.evidence_transactions,
    public.fraud_signals, public.risk_assessments, public.alerts TO nexora_worker_runtime;
GRANT UPDATE (result) ON public.csv_import_requests TO nexora_worker_runtime;
GRANT UPDATE ON public.csv_import_jobs, public.analysis_jobs, public.alerts TO nexora_worker_runtime;
GRANT USAGE ON SEQUENCE public.transactions_ingest_seq_seq TO nexora_api_runtime, nexora_worker_runtime;

GRANT INSERT ON public.audit_events, public.transfer_action_events TO nexora_audit_appender;
GRANT nexora_audit_appender TO nexora_api_runtime;

CREATE OR REPLACE VIEW public.nexora_operational_totals AS
SELECT status, count(*) AS jobs FROM public.analysis_jobs GROUP BY status;
GRANT SELECT ON public.nexora_operational_totals TO nexora_reporting;

COMMIT;
