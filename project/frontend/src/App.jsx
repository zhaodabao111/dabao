import { useCallback, useEffect, useState } from "react";

import { getHealth } from "./api";


const STATUS_COPY = {
  checking: "正在连接本地后端…",
  online: "后端服务连接正常",
  offline: "暂时无法连接后端，请确认服务已启动。",
};


export default function App() {
  const [backendStatus, setBackendStatus] = useState("checking");
  const [requestId, setRequestId] = useState("");

  const checkHealth = useCallback(async (signal) => {
    setBackendStatus("checking");
    setRequestId("");

    try {
      const payload = await getHealth({ signal });
      if (payload?.data?.status !== "ok") {
        throw new Error("Unexpected health response");
      }
      setRequestId(payload.request_id);
      setBackendStatus("online");
    } catch (error) {
      if (error.code !== "ERR_CANCELED") {
        setBackendStatus("offline");
      }
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    checkHealth(controller.signal);
    return () => controller.abort();
  }, [checkHealth]);

  return (
    <main className="page-shell">
      <section className="hero" aria-labelledby="page-title">
        <p className="eyebrow">VOICE MEETUP</p>
        <h1 id="page-title">语音约碰面地点</h1>
        <p className="intro">
          说出两个人所在的位置，我们会帮你寻找地理中点附近的碰面地点。
        </p>

        <div className="status-card">
          <div>
            <span
              className={`status-dot status-dot--${backendStatus}`}
              aria-hidden="true"
            />
            <span aria-live="polite">{STATUS_COPY[backendStatus]}</span>
          </div>
          {requestId && <code>request_id: {requestId}</code>}
          {backendStatus === "offline" && (
            <button type="button" onClick={() => checkHealth()}>
              重新检查
            </button>
          )}
        </div>

        <div className="placeholder" aria-label="后续功能说明">
          <span>第一阶段</span>
          <strong>基础页面已就绪</strong>
          <p>录音与地点推荐功能将在后续阶段逐步加入。</p>
        </div>
      </section>
    </main>
  );
}
