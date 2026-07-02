import { useEffect, useState } from "react";
import { Bell, Database, Link2, Server, Settings2 } from "lucide-react";
import SyncMonitor, { SYNC_API_URL } from "./SyncMonitor.jsx";
import SyncSetup from "./SyncSetup.jsx";

export default function App() {
  const [activeMode, setActiveMode] = useState("setup");
  const [setupTab, setSetupTab] = useState("jobs");
  const [setupNotice, setSetupNotice] = useState("");
  const [setupFocusJob, setSetupFocusJob] = useState(null);
  const [setupAddJobToken, setSetupAddJobToken] = useState(0);
  const [apiOnline, setApiOnline] = useState(null);

  useEffect(() => {
    let alive = true;

    async function ping() {
      try {
        const controller = new AbortController();
        const timer = window.setTimeout(() => controller.abort(), 3000);
        await fetch(`${SYNC_API_URL}/api/health`, { signal: controller.signal });
        window.clearTimeout(timer);
        if (alive) setApiOnline(true);
      } catch {
        if (alive) setApiOnline(false);
      }
    }

    ping();
    const timer = window.setInterval(ping, 15000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, []);

  function editSyncJob(name) {
    setSetupFocusJob({ name, token: Date.now() });
    setSetupTab("jobs");
    setActiveMode("setup");
  }

  function addSyncJobFromMonitor() {
    setSetupTab("jobs");
    setActiveMode("setup");
    setSetupAddJobToken(Date.now());
  }

  return (
    <div className="app">
      <header className="appHeader">
        <div className="appBrand" title="PowerBI Data DTL">
          <Database size={22} aria-hidden="true" />
        </div>

        <nav className="appNav" aria-label="Điều hướng chính">
          <button type="button" className={activeMode === "setup" && setupTab === "jobs" ? "active" : ""} onClick={() => { setActiveMode("setup"); setSetupTab("jobs"); }}>
            <Link2 size={16} aria-hidden="true" />
            Tác vụ
          </button>
          <button type="button" className={activeMode === "setup" && setupTab === "system" ? "active" : ""} onClick={() => { setActiveMode("setup"); setSetupTab("system"); }}>
            <Settings2 size={16} aria-hidden="true" />
            Hệ thống
          </button>
          <button type="button" className={activeMode === "setup" && setupTab === "notify" ? "active" : ""} onClick={() => { setActiveMode("setup"); setSetupTab("notify"); }}>
            <Bell size={16} aria-hidden="true" />
            Thông báo
          </button>
          <button type="button" className={activeMode === "sync" ? "active" : ""} onClick={() => setActiveMode("sync")}>
            <Server size={16} aria-hidden="true" />
            Giám sát
          </button>
        </nav>

        <div className="appStatus">
          <div
            className={`statusDot ${apiOnline === true ? "online" : apiOnline === false ? "offline" : ""}`}
            role="img"
            aria-label={apiOnline === true ? "Hệ thống hoạt động" : apiOnline === false ? "Mất kết nối" : "Đang kiểm tra kết nối"}
          />
          <span>{apiOnline === true ? "Hệ thống hoạt động" : apiOnline === false ? "Mất kết nối" : "Đang kiểm tra..."}</span>
        </div>
      </header>

      <section className="workspace">
        {activeMode === "setup" ? (
          <SyncSetup
            notice={setupNotice}
            focusJobName={setupFocusJob?.name}
            focusToken={setupFocusJob?.token}
            addJobToken={setupAddJobToken}
            setupTab={setupTab}
            onSetupTabChange={setSetupTab}
          />
        ) : (
          <SyncMonitor onEditJob={editSyncJob} onAddJob={addSyncJobFromMonitor} />
        )}
      </section>
    </div>
  );
}
