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
import "./misans.css";
import "./learning-skin.css";
// Entry has already exchanged the ticket for a cookie. Never retain it in URLs.
const entryUrl = new URL(location.href);
if (entryUrl.searchParams.has("ticket")) {
  entryUrl.searchParams.delete("ticket");
  history.replaceState(history.state, "", entryUrl);
}
const pageChunks = {
  home: () => import("./pages/Home"),
  workbench: () => import("./pages/Workbench"),
  roadmap: () => import("./pages/Roadmap"),
  chat: () => import("./pages/Chat"),
  library: () => import("./pages/Library"),
  review: () => import("./pages/Review"),
  quiz: () => import("./pages/Quiz"),
  dashboard: () => import("./pages/Dashboard"),
  tools: () => import("./pages/Tools"),
  models: () => import("./pages/Models"),
};
const Home = lazy(pageChunks.home);
const Workbench = lazy(pageChunks.workbench);
const Roadmap = lazy(pageChunks.roadmap);
const Chat = lazy(pageChunks.chat);
const Library = lazy(pageChunks.library);
const Review = lazy(pageChunks.review);
const Quiz = lazy(pageChunks.quiz);
const Dashboard = lazy(pageChunks.dashboard);
const Tools = lazy(pageChunks.tools);
const Models = lazy(pageChunks.models);
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
// Fetch the other pages once the first one is on screen, so the next link
// pressed opens without a wait. Lesson text is what most sessions open
// first, and its renderer is the one piece that is slow to arrive.
const whenIdle =
  window.requestIdleCallback ?? ((task: () => void) => setTimeout(task, 300));
whenIdle(() => {
  for (const load of Object.values(pageChunks)) void load();
  void import("./components/Markdown");
});
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
            {/* A link keeps the current page on screen until the next one is
                ready, instead of blanking the whole app to a loading line. */}
            <RouterProvider
              router={router}
              future={{ v7_startTransition: true }}
            />
          </Suspense>
        </SessionGate>
      </QueryClientProvider>
    </React.StrictMode>,
  );
}
void start();
