import { Link, Route, Routes } from "react-router-dom";

import AnalyticsPage from "./pages/AnalyticsPage";
import DealEditorPage from "./pages/DealEditorPage";
import DealLibraryPage from "./pages/DealLibraryPage";
import RunResultsPage from "./pages/RunResultsPage";

export default function App() {
  return (
    <div className="min-h-screen bg-slate-100">
      <header className="border-b border-slate-200 bg-white px-6 py-3">
        <Link to="/" className="text-lg font-semibold text-slate-800">
          ABS Structuring Tool
        </Link>
      </header>
      <main className="mx-auto max-w-7xl p-6">
        <Routes>
          <Route path="/" element={<DealLibraryPage />} />
          <Route path="/deals/:dealId" element={<DealEditorPage />} />
          <Route path="/deals/:dealId/results/:scenario" element={<RunResultsPage />} />
          <Route path="/deals/:dealId/analytics" element={<AnalyticsPage />} />
          <Route path="/deals/:dealId/analytics/:scenario" element={<AnalyticsPage />} />
        </Routes>
      </main>
    </div>
  );
}
