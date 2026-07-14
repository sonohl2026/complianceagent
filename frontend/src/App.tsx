import { Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { AnalysesList } from "./pages/AnalysesList";
import { AnalysisDetail } from "./pages/AnalysisDetail";
import { Chat } from "./pages/Chat";
import { ClaimsRegister } from "./pages/ClaimsRegister";
import { Dashboard } from "./pages/Dashboard";
import { Monitoring } from "./pages/Monitoring";
import { NewAnalysis } from "./pages/NewAnalysis";
import { ProjectDetail } from "./pages/ProjectDetail";
import { Settings } from "./pages/Settings";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="new-analysis" element={<NewAnalysis />} />
        <Route path="projects/:projectId" element={<ProjectDetail />} />
        <Route path="analyses/:analysisId" element={<AnalysisDetail />} />
        <Route path="analyses" element={<AnalysesList />} />
        <Route path="claims-register" element={<ClaimsRegister />} />
        <Route path="chat" element={<Chat />} />
        <Route path="monitoring" element={<Monitoring />} />
        <Route path="settings" element={<Settings />} />
      </Route>
    </Routes>
  );
}
