import React from "react";
import ReactDOM from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";

import App from "./App";
import Project from "./pages/Project";
import Projects from "./pages/Projects";
import "./styles.css";

// 构建时 base 可能是 /app/ 或 /official/learn-everything/app/，路由要跟着走。
const basename = import.meta.env.BASE_URL.replace(/\/$/, "") || "/";

const router = createBrowserRouter([
  {
    path: "/",
    element: <App />,
    children: [
      { index: true, element: <Projects /> },
      { path: "p/:projectId", element: <Project /> },
    ],
  },
], { basename });

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>,
);
