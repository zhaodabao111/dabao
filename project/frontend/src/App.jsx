import { useCallback, useEffect, useRef, useState } from "react";

import { getHealth } from "./api";
import {
  MAX_FILE_SIZE_BYTES,
  useAudioRecorder,
} from "./hooks/useAudioRecorder";


const STATUS_COPY = {
  checking: "正在连接本地后端…",
  online: "后端服务连接正常",
  offline: "暂时无法连接后端，请确认服务已启动。",
};


function formatBytes(bytes) {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}


function isInsideElement(event, element) {
  if (!element) {
    return false;
  }
  const bounds = element.getBoundingClientRect();
  return (
    event.clientX >= bounds.left &&
    event.clientX <= bounds.right &&
    event.clientY >= bounds.top &&
    event.clientY <= bounds.bottom
  );
}


export default function App() {
  const [backendStatus, setBackendStatus] = useState("checking");
  const [requestId, setRequestId] = useState("");
  const [city, setCity] = useState("杭州");
  const activePointerRef = useRef(null);
  const cancelZoneRef = useRef(null);
  const {
    beginRecording,
    cancelRecording,
    capability,
    elapsedMs,
    finishRecording,
    message,
    phase,
    recording,
  } = useAudioRecorder();

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

  useEffect(() => {
    const finishActivePointer = (event) => {
      if (
        activePointerRef.current !== null &&
        (event.pointerId === undefined ||
          event.pointerId === activePointerRef.current)
      ) {
        activePointerRef.current = null;
        if (isInsideElement(event, cancelZoneRef.current)) {
          cancelRecording();
        } else {
          finishRecording();
        }
      }
    };
    const cancelActivePointer = (event) => {
      if (
        activePointerRef.current !== null &&
        (event.pointerId === undefined ||
          event.pointerId === activePointerRef.current)
      ) {
        activePointerRef.current = null;
        cancelRecording();
      }
    };

    window.addEventListener("pointerup", finishActivePointer);
    window.addEventListener("pointercancel", cancelActivePointer);
    return () => {
      window.removeEventListener("pointerup", finishActivePointer);
      window.removeEventListener("pointercancel", cancelActivePointer);
    };
  }, [cancelRecording, finishRecording]);

  const handlePointerDown = (event) => {
    if (!event.isPrimary || event.button !== 0) {
      return;
    }
    event.preventDefault();
    activePointerRef.current = event.pointerId;
    event.currentTarget.setPointerCapture?.(event.pointerId);
    beginRecording();
  };

  const handlePointerUp = (event) => {
    if (activePointerRef.current !== event.pointerId) {
      return;
    }
    activePointerRef.current = null;
    if (isInsideElement(event, cancelZoneRef.current)) {
      cancelRecording();
    } else {
      finishRecording();
    }
  };

  const handlePointerCancel = (event) => {
    if (activePointerRef.current !== event.pointerId) {
      return;
    }
    activePointerRef.current = null;
    cancelRecording();
  };

  const handleKeyDown = (event) => {
    if (
      !event.repeat &&
      (event.key === " " || event.key === "Enter")
    ) {
      event.preventDefault();
      beginRecording();
    }
  };

  const handleKeyUp = (event) => {
    if (event.key === " " || event.key === "Enter") {
      event.preventDefault();
      finishRecording();
    }
  };

  const isBusy = ["requesting", "recording", "processing"].includes(phase);
  const elapsedSeconds = (elapsedMs / 1000).toFixed(1);

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

        <section className="recorder-card" aria-labelledby="recorder-title">
          <div className="field-row">
            <label htmlFor="city">当前城市</label>
            <input
              id="city"
              list="city-options"
              value={city}
              onChange={(event) => setCity(event.target.value)}
              disabled={isBusy}
            />
            <datalist id="city-options">
              <option value="杭州" />
              <option value="上海" />
              <option value="北京" />
              <option value="广州" />
              <option value="深圳" />
            </datalist>
          </div>

          <div className="recorder-copy">
            <p className="section-label">本地录音</p>
            <h2 id="recorder-title">按住说出碰面需求</h2>
            <p>录音限制为1—60秒、最多5MB，仅支持 WebM/Opus。</p>
          </div>

          <div className="record-control">
            <button
              className={`record-button record-button--${phase}`}
              type="button"
              disabled={!capability.supported || phase === "processing"}
              onContextMenu={(event) => event.preventDefault()}
              onKeyDown={handleKeyDown}
              onKeyUp={handleKeyUp}
              onLostPointerCapture={handlePointerUp}
              onPointerCancel={handlePointerCancel}
              onPointerDown={handlePointerDown}
              onPointerUp={handlePointerUp}
              aria-label="按住录音，松开结束"
            >
              <span className="record-icon" aria-hidden="true" />
              <strong>
                {phase === "recording"
                  ? `${elapsedSeconds} 秒`
                  : phase === "requesting"
                    ? "等待授权"
                    : phase === "processing"
                      ? "处理中"
                      : "按住录音"}
              </strong>
            </button>
            {phase === "recording" && (
              <button
                ref={cancelZoneRef}
                className="cancel-button"
                type="button"
                onClick={cancelRecording}
              >
                移到这里松开取消
              </button>
            )}
          </div>

          <p
            className={`recorder-message recorder-message--${phase}`}
            aria-live="polite"
          >
            {message}
          </p>

          {recording && (
            <div className="preview-card">
              <div className="preview-heading">
                <div>
                  <span>录音已就绪</span>
                  <strong>{recording.fileName}</strong>
                </div>
                <a href={recording.url} download={recording.fileName}>
                  下载录音文件
                </a>
              </div>
              <audio controls preload="metadata" src={recording.url}>
                当前浏览器不支持音频播放。
              </audio>
              <dl className="recording-meta">
                <div>
                  <dt>城市</dt>
                  <dd>{city || "未填写"}</dd>
                </div>
                <div>
                  <dt>格式</dt>
                  <dd>{recording.mimeType}</dd>
                </div>
                <div>
                  <dt>时长</dt>
                  <dd>{(recording.durationMs / 1000).toFixed(1)} 秒</dd>
                </div>
                <div>
                  <dt>大小</dt>
                  <dd>{formatBytes(recording.size)}</dd>
                </div>
              </dl>
              <progress
                max={MAX_FILE_SIZE_BYTES}
                value={recording.size}
                aria-label="录音文件大小"
              />
            </div>
          )}

          {!recording && (
            <div className="empty-result">
              录音完成后，这里只显示本地试听和下载入口。
            </div>
          )}
        </section>

        <div className="placeholder" aria-label="后续功能说明">
          <span>暂未接入</span>
          <strong>识别与地点推荐</strong>
          <p>本阶段不会上传录音，也不会生成识别文字或店铺结果。</p>
        </div>
      </section>
    </main>
  );
}
