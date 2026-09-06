import { useCallback, useEffect, useRef, useState } from "react";


export const AUDIO_MIME_TYPE = "audio/webm;codecs=opus";
export const MIN_DURATION_MS = 1_000;
export const MAX_DURATION_MS = 60_000;
export const MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024;
const AUTO_STOP_DELAY_MS = MAX_DURATION_MS - 250;


function getCapability() {
  if (
    !navigator.mediaDevices?.getUserMedia ||
    !window.MediaRecorder ||
    typeof MediaRecorder.isTypeSupported !== "function"
  ) {
    return {
      supported: false,
      message: "当前浏览器不支持网页录音，请更换支持 MediaRecorder 的浏览器。",
    };
  }

  if (!MediaRecorder.isTypeSupported(AUDIO_MIME_TYPE)) {
    return {
      supported: false,
      message: "当前浏览器不支持 WebM/Opus 录音，请更换浏览器。",
    };
  }

  return { supported: true, message: "支持 WebM/Opus 录音" };
}


function permissionErrorMessage(error) {
  if (error?.name === "NotAllowedError" || error?.name === "SecurityError") {
    return "麦克风权限被拒绝，请在浏览器设置中允许后重新录音。";
  }
  if (error?.name === "NotFoundError") {
    return "没有检测到可用麦克风，请连接麦克风后重试。";
  }
  if (error?.name === "NotReadableError" || error?.name === "AbortError") {
    return "麦克风暂时不可用，可能正被其他应用占用。";
  }
  return "无法启动录音，请检查麦克风和浏览器权限后重试。";
}


function makeFileName() {
  const timestamp = new Date()
    .toISOString()
    .replace(/[-:]/g, "")
    .replace("T", "-")
    .slice(0, 15);
  return `voice-meetup-${timestamp}.webm`;
}


export function useAudioRecorder() {
  const capability = useRef(getCapability()).current;
  const initialPhase = capability.supported ? "idle" : "unsupported";
  const [phase, setPhase] = useState(initialPhase);
  const [message, setMessage] = useState(capability.message);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [recording, setRecording] = useState(null);

  const phaseRef = useRef(initialPhase);
  const mountedRef = useRef(true);
  const holdActiveRef = useRef(false);
  const sessionRef = useRef(0);
  const recorderRef = useRef(null);
  const streamRef = useRef(null);
  const chunksRef = useRef([]);
  const startedAtRef = useRef(0);
  const finalDurationRef = useRef(0);
  const cancelledRef = useRef(false);
  const failedRef = useRef(false);
  const reachedLimitRef = useRef(false);
  const recordedSizeRef = useRef(0);
  const previewUrlRef = useRef("");
  const stopTimeoutRef = useRef(null);
  const progressIntervalRef = useRef(null);
  const stopRecorderRef = useRef(() => {});

  const updatePhase = useCallback((nextPhase) => {
    phaseRef.current = nextPhase;
    if (mountedRef.current) {
      setPhase(nextPhase);
    }
  }, []);

  const clearTimers = useCallback(() => {
    if (stopTimeoutRef.current !== null) {
      window.clearTimeout(stopTimeoutRef.current);
      stopTimeoutRef.current = null;
    }
    if (progressIntervalRef.current !== null) {
      window.clearInterval(progressIntervalRef.current);
      progressIntervalRef.current = null;
    }
  }, []);

  const releaseStream = useCallback((stream = streamRef.current) => {
    stream?.getTracks().forEach((track) => track.stop());
    if (stream === streamRef.current) {
      streamRef.current = null;
    }
  }, []);

  const clearRecording = useCallback(() => {
    if (previewUrlRef.current) {
      URL.revokeObjectURL(previewUrlRef.current);
      previewUrlRef.current = "";
    }
    if (mountedRef.current) {
      setRecording(null);
    }
  }, []);

  const reportRecorderFailure = useCallback(
    (failureMessage = "录制失败，请重新尝试。") => {
      failedRef.current = true;
      holdActiveRef.current = false;
      clearTimers();

      const recorder = recorderRef.current;
      if (recorder?.state && recorder.state !== "inactive") {
        try {
          recorder.stop();
        } catch {
          recorderRef.current = null;
        }
      }

      releaseStream();
      updatePhase("error");
      if (mountedRef.current) {
        setMessage(failureMessage);
        setElapsedMs(0);
      }
    },
    [clearTimers, releaseStream, updatePhase],
  );

  const stopRecorder = useCallback(
    ({ cancelled = false, reachedLimit = false } = {}) => {
      holdActiveRef.current = false;

      if (phaseRef.current === "requesting") {
        if (cancelled) {
          sessionRef.current += 1;
          updatePhase("idle");
          setMessage("录音已取消，麦克风将在授权请求结束后释放。");
        }
        return;
      }

      const recorder = recorderRef.current;
      if (phaseRef.current !== "recording" || !recorder) {
        return;
      }

      cancelledRef.current = cancelled;
      reachedLimitRef.current = reachedLimit;
      finalDurationRef.current = Math.min(
        performance.now() - startedAtRef.current,
        MAX_DURATION_MS,
      );

      clearTimers();
      updatePhase("processing");
      setElapsedMs(finalDurationRef.current);

      try {
        recorder.stop();
      } catch {
        reportRecorderFailure();
        return;
      }
      releaseStream();
    },
    [clearTimers, releaseStream, reportRecorderFailure, updatePhase],
  );

  stopRecorderRef.current = stopRecorder;

  const beginRecording = useCallback(async () => {
    if (!capability.supported) {
      updatePhase("unsupported");
      setMessage(capability.message);
      return;
    }

    if (["requesting", "recording", "processing"].includes(phaseRef.current)) {
      return;
    }

    holdActiveRef.current = true;
    const sessionId = sessionRef.current + 1;
    sessionRef.current = sessionId;
    clearRecording();
    clearTimers();
    setElapsedMs(0);
    setMessage("正在请求麦克风权限…");
    updatePhase("requesting");

    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          autoGainControl: true,
          echoCancellation: true,
          noiseSuppression: true,
        },
        video: false,
      });
    } catch (error) {
      if (sessionId !== sessionRef.current || !mountedRef.current) {
        return;
      }
      holdActiveRef.current = false;
      updatePhase("error");
      setMessage(permissionErrorMessage(error));
      return;
    }

    if (
      sessionId !== sessionRef.current ||
      !mountedRef.current ||
      !holdActiveRef.current
    ) {
      releaseStream(stream);
      if (mountedRef.current && sessionId === sessionRef.current) {
        updatePhase("idle");
        setMessage("麦克风已授权，请重新按住按钮开始录音。");
      }
      return;
    }

    streamRef.current = stream;
    chunksRef.current = [];
    recordedSizeRef.current = 0;
    cancelledRef.current = false;
    failedRef.current = false;
    reachedLimitRef.current = false;

    let recorder;
    try {
      recorder = new MediaRecorder(stream, { mimeType: AUDIO_MIME_TYPE });
    } catch {
      reportRecorderFailure("浏览器无法创建 WebM/Opus 录音，请更换浏览器。");
      return;
    }

    recorderRef.current = recorder;
    recorder.ondataavailable = (event) => {
      if (event.data?.size > 0) {
        chunksRef.current.push(event.data);
        recordedSizeRef.current += event.data.size;
        if (
          recordedSizeRef.current > MAX_FILE_SIZE_BYTES &&
          phaseRef.current === "recording"
        ) {
          reportRecorderFailure("录音文件超过5MB，请缩短内容后重新录制。");
        }
      }
    };
    recorder.onerror = () => {
      reportRecorderFailure();
    };
    recorder.onstop = () => {
      recorderRef.current = null;
      releaseStream();

      if (!mountedRef.current || sessionId !== sessionRef.current) {
        return;
      }
      if (failedRef.current) {
        chunksRef.current = [];
        recordedSizeRef.current = 0;
        return;
      }
      if (cancelledRef.current) {
        chunksRef.current = [];
        setElapsedMs(0);
        updatePhase("idle");
        setMessage("录音已取消，麦克风已释放。");
        return;
      }

      const durationMs = finalDurationRef.current;
      const mimeType = recorder.mimeType || AUDIO_MIME_TYPE;
      const blob = new Blob(chunksRef.current, { type: mimeType });
      chunksRef.current = [];
      recordedSizeRef.current = 0;

      if (durationMs < MIN_DURATION_MS) {
        updatePhase("error");
        setMessage("录音不能少于1秒，请按住按钮说完后再松开。");
        setElapsedMs(0);
        return;
      }
      if (blob.size === 0) {
        updatePhase("error");
        setMessage("没有录到有效音频，请检查麦克风后重试。");
        setElapsedMs(0);
        return;
      }
      if (blob.size > MAX_FILE_SIZE_BYTES) {
        updatePhase("error");
        setMessage("录音文件超过5MB，请缩短内容后重新录制。");
        setElapsedMs(0);
        return;
      }

      const url = URL.createObjectURL(blob);
      previewUrlRef.current = url;
      setRecording({
        blob,
        durationMs,
        fileName: makeFileName(),
        mimeType,
        size: blob.size,
        url,
      });
      updatePhase("ready");
      setMessage(
        reachedLimitRef.current
          ? "已达到60秒上限，录音已自动结束。"
          : "录音完成，可以试听或下载文件。",
      );
    };

    try {
      recorder.start(250);
    } catch {
      reportRecorderFailure();
      return;
    }

    startedAtRef.current = performance.now();
    finalDurationRef.current = 0;
    updatePhase("recording");
    setMessage("正在录音，松开按钮结束；按 Esc 取消。");

    progressIntervalRef.current = window.setInterval(() => {
      if (mountedRef.current) {
        setElapsedMs(
          Math.min(performance.now() - startedAtRef.current, MAX_DURATION_MS),
        );
      }
    }, 100);
    stopTimeoutRef.current = window.setTimeout(() => {
      stopRecorderRef.current({ reachedLimit: true });
    }, AUTO_STOP_DELAY_MS);
  }, [
    capability.message,
    capability.supported,
    clearRecording,
    clearTimers,
    releaseStream,
    reportRecorderFailure,
    updatePhase,
  ]);

  const finishRecording = useCallback(() => {
    stopRecorder({ cancelled: false });
  }, [stopRecorder]);

  const cancelRecording = useCallback(() => {
    stopRecorder({ cancelled: true });
  }, [stopRecorder]);

  useEffect(() => {
    const handleEscape = (event) => {
      if (event.key === "Escape") {
        cancelRecording();
      }
    };
    const handleWindowBlur = () => {
      if (phaseRef.current === "recording") {
        cancelRecording();
      }
    };
    const handleVisibilityChange = () => {
      if (document.hidden) {
        cancelRecording();
      }
    };

    window.addEventListener("keydown", handleEscape);
    window.addEventListener("blur", handleWindowBlur);
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      window.removeEventListener("keydown", handleEscape);
      window.removeEventListener("blur", handleWindowBlur);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [cancelRecording]);

  useEffect(
    () => () => {
      mountedRef.current = false;
      sessionRef.current += 1;
      clearTimers();
      const recorder = recorderRef.current;
      if (recorder?.state && recorder.state !== "inactive") {
        try {
          recorder.stop();
        } catch {
          // The stream is still released below.
        }
      }
      releaseStream();
      if (previewUrlRef.current) {
        URL.revokeObjectURL(previewUrlRef.current);
        previewUrlRef.current = "";
      }
    },
    [clearTimers, releaseStream],
  );

  return {
    beginRecording,
    cancelRecording,
    capability,
    elapsedMs,
    finishRecording,
    phase,
    recording,
    message,
  };
}
