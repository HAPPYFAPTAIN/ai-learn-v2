import { Link, Outlet } from "react-router-dom";

export default function App() {
  return (
    <div className="app">
      <header className="topbar">
        <Link to="/" className="brand">
          Learn Everything
        </Link>
        <span className="hint">多租户学习平台 · v2</span>
      </header>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
