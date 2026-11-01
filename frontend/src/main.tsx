import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Layout } from "./components/Layout";
import { Queue } from "./pages/Queue";
import { PaperReview } from "./pages/PaperReview";
import { Rules } from "./pages/Rules";
import { Offline } from "./pages/Offline";
import { System } from "./pages/System";
import { ReviewByItem } from "./pages/ReviewByItem";
import "./style.css";
import "./m11.css";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1 } },
});
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Queue />} />
            <Route path="review/:runId/:entryId" element={<PaperReview />} />
            <Route path="rules" element={<Rules />} />
            <Route path="system" element={<System />} />
            <Route path="offline" element={<Offline />} />
            <Route path="items" element={<ReviewByItem />} />
            <Route
              path="*"
              element={
                <p>
                  Page not found. Use the navigation to return to the workspace.
                </p>
              }
            />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
