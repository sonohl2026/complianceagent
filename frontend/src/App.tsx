import { Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { AnalysesList } from "./pages/AnalysesList";
import { AnalysisDetail } from "./pages/AnalysisDetail";
import { ProductResults } from "./pages/ProductResults";
import { ProductsList } from "./pages/ProductsList";
import { RunRedirect } from "./pages/RunRedirect";
import { Settings } from "./pages/Settings";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<ProductsList />} />
        <Route path="products/:productId" element={<ProductResults />} />
        <Route path="runs/:runId" element={<RunRedirect />} />
        <Route path="settings" element={<Settings />} />
        {/* Legacy FULL_COMPLIANCE_ANALYSIS data -- not part of the MVP's
            3-deliverable product and dropped from primary nav, but not
            deleted: still reachable by direct URL. See Step 4 report for
            the recommendation to remove these once confirmed unneeded. */}
        <Route path="analyses/:analysisId" element={<AnalysisDetail />} />
        <Route path="analyses" element={<AnalysesList />} />
      </Route>
    </Routes>
  );
}
