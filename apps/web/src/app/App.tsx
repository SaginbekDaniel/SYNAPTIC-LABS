import { lazy, Suspense, useEffect } from "react";
import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router";
import { Shell } from "../components/layout/Shell";
import { Loading } from "../components/ui";
import { AlertsQueue } from "../features/alerts/AlertsQueue";
import { CasesList } from "../features/cases/CasesList";
import { CommandCenter } from "../features/command-center/CommandCenter";
import { LoginPage, RequireAuth } from "../features/auth/LoginPage";
import { restoreSession } from "./auth";
import { DatasetProvider } from "./dataset";

// Graph screens pull in Cytoscape; secondary screens are visited rarely. Load them on demand.
const Investigation = lazy(() => import("../features/investigation/Investigation").then((m) => ({ default: m.Investigation })));
const GraphWorkspace = lazy(() => import("../features/graph/GraphWorkspace").then((m) => ({ default: m.GraphWorkspace })));
const Analytics = lazy(() => import("../features/analytics/Analytics").then((m) => ({ default: m.Analytics })));
const Evaluation = lazy(() => import("../features/evaluation/Evaluation").then((m) => ({ default: m.Evaluation })));
const FraudLab = lazy(() => import("../features/fraud-lab/FraudLab").then((m) => ({ default: m.FraudLab })));

let restoring = false;

export function App() {
  useEffect(() => {
    if (restoring) return; // StrictMode runs effects twice in development
    restoring = true;
    void restoreSession();
  }, []);

  return (
    <BrowserRouter>
      <Routes>
        <Route path="login" element={<LoginPage />} />
        {/* Everything else needs a session the server accepted. Data providers mount only then. */}
        <Route
          element={
            <RequireAuth>
              <DatasetProvider>
                <Shell />
              </DatasetProvider>
            </RequireAuth>
          }
        >
          <Route
            element={
              <Suspense fallback={<Loading rows={6} />}>
                <RouteOutlet />
              </Suspense>
            }
          >
            <Route index element={<CommandCenter />} />
            <Route path="alerts" element={<AlertsQueue />} />
            <Route path="alerts/:alertId" element={<Investigation />} />
            <Route path="cases" element={<CasesList />} />
            <Route path="analytics" element={<Analytics />} />
            <Route path="analytics/benchmark" element={<Evaluation />} />
            <Route path="evaluation" element={<Navigate to="/analytics/benchmark" replace />} />
            <Route path="network" element={<GraphWorkspace />} />
            <Route path="lab" element={<FraudLab />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

// Suspense sits inside the shell so navigation chrome stays visible while a screen chunk loads.
function RouteOutlet() {
  return <Outlet />;
}
