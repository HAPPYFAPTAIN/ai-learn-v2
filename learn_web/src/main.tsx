import React, { lazy, Suspense } from "react";
import ReactDOM from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";
import {
  createBrowserRouter,
  Link,
  Navigate,
  RouterProvider,
  useParams,
} from "react-router-dom";
import App from "./App";
import SessionGate from "./session/SessionGate";
import { queryClient } from "./query";
import "./styles.css";
// Entry has already exchanged the ticket for a cookie. Never retain it in URLs.
const entryUrl = new URL(location.href);
if (entryUrl.searchParams.has("ticket")) {
  entryUrl.searchParams.delete("ticket");
  history.replaceState(history.state, "", entryUrl);
}
const Home = lazy(() => import("./pages/Home"));
const Workbench = lazy(() => import("./pages/Workbench"));
const Roadmap = lazy(() => import("./pages/Roadmap"));
const Chat = lazy(() => import("./pages/Chat"));
const Library = lazy(() => import("./pages/Library"));
const Review = lazy(() => import("./pages/Review"));
const Quiz = lazy(() => import("./pages/Quiz"));
const Dashboard = lazy(() => import("./pages/Dashboard"));
const Tools = lazy(() => import("./pages/Tools"));
const Models = lazy(() => import("./pages/Models"));
function OldProjectLink() {
  const { projectId } = useParams();
  return (
    <Navigate
      replace
      to={`/study?project=${encodeURIComponent(projectId || "")}`}
    />
  );
}
const basename = import.meta.env.BASE_URL.replace(/\/$/, "") || "/";
const router = createBrowserRouter(
  [
    {
      path: "/",
      element: <App />,
      errorElement: (
        <main className="gate">
          <h1>页面暂时无法打开</h1>
          <a href={basename}>返回学习首页</a>
        </main>
      ),
      children: [
        { index: true, element: <Home /> },
        { path: "study", element: <Workbench /> },
        { path: "roadmap", element: <Roadmap /> },
        { path: "chat", element: <Chat /> },
        { path: "library", element: <Library /> },
        { path: "review", element: <Review /> },
        { path: "quiz", element: <Quiz /> },
        { path: "dashboard", element: <Dashboard /> },
        { path: "tools", element: <Tools /> },
        { path: "models", element: <Models /> },
        { path: "p/:projectId", element: <OldProjectLink /> },
        {
          path: "*",
          element: (
            <div className="empty">
              <h1>页面不存在</h1>
              <Link to="/">返回学习首页</Link>
            </div>
          ),
        },
      ],
    },
  ],
  { basename },
);
async function start() {
  // This branch and demo code are removed from the production build.
  if (__DEMO__) {
    const { enableDemo } = await import("./demo/transport");
    enableDemo();
  }
  ReactDOM.createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
      <QueryClientProvider client={queryClient}>
        <SessionGate>
          <Suspense
            fallback={
              <p role="status" className="loading">
                正在打开页面…
              </p>
            }
          >
            <RouterProvider router={router} />
          </Suspense>
        </SessionGate>
      </QueryClientProvider>
    </React.StrictMode>,
  );
}
void start();
