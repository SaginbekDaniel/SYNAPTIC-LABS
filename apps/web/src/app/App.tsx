import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router-dom";
import { Shell } from "../components/layout/Shell";
import { Loading } from "../components/ui";
import { AlertsQueue } from "../features/alerts/AlertsQueue";
import { CasesList } from "../features/cases/CasesList";
import { CommandCenter } from "../features/command-center/CommandCenter";
import { DatasetProvider } from "./dataset";

// Graph screens pull in Cytoscape; secondary screens are visited rarely. Load them on demand.
const Investigation = lazy(() => import("../features/investigation/Investigation").then((m) => ({ default: m.Investigation })));
const NetworkExplorer = lazy(() => import("../features/network/NetworkExplorer").then((m) => ({ default: m.NetworkExplorer })));
const Analytics = lazy(() => import("../features/analytics/Analytics").then((m) => ({ default: m.Analytics })));
const Evaluation = lazy(() => import("../features/evaluation/Evaluation").then((m) => ({ default: m.Evaluation })));
const FraudLab = lazy(() => import("../features/fraud-lab/FraudLab").then((m) => ({ default: m.FraudLab })));

export function App() {
  return (
    <BrowserRouter>
      <DatasetProvider>
        <Routes>
          <Route element={<Shell />}>
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
              <Route path="network" element={<NetworkExplorer />} />
              <Route path="lab" element={<FraudLab />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Route>
        </Routes>
      </DatasetProvider>
    </BrowserRouter>
  );
}

// Suspense sits inside the shell so navigation chrome stays visible while a screen chunk loads.
function RouteOutlet() {
  return <Outlet />;
}
