import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Shell } from "../components/layout/Shell";
import { Loading } from "../components/ui";
import { AlertsQueue } from "../features/alerts/AlertsQueue";
import { CasesList } from "../features/cases/CasesList";
import { CommandCenter } from "../features/command-center/CommandCenter";
import { FraudLab } from "../features/fraud-lab/FraudLab";
import { DatasetProvider } from "./dataset";

// Graph screens pull in Cytoscape; load them only when visited.
const Investigation = lazy(() => import("../features/investigation/Investigation").then((m) => ({ default: m.Investigation })));
const NetworkExplorer = lazy(() => import("../features/network/NetworkExplorer").then((m) => ({ default: m.NetworkExplorer })));

export function App() {
  return (
    <BrowserRouter>
      <DatasetProvider>
        <Suspense fallback={<Loading rows={6} />}>
          <Routes>
            <Route element={<Shell />}>
              <Route index element={<CommandCenter />} />
              <Route path="alerts" element={<AlertsQueue />} />
              <Route path="alerts/:alertId" element={<Investigation />} />
              <Route path="cases" element={<CasesList />} />
              <Route path="network" element={<NetworkExplorer />} />
              <Route path="lab" element={<FraudLab />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </Suspense>
      </DatasetProvider>
    </BrowserRouter>
  );
}
