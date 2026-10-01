import { useCallback, useState } from "react";
import type { CameraStreamStatus } from "../types";
import type { NoticeHandler } from "../uiNotice";

export function useCameraController({ cameraStreams, announce }: {
  cameraStreams: CameraStreamStatus[];
  announce: NoticeHandler;
}) {
  const [selectedCameraId, setSelectedCameraId] = useState("");
  const [streamRevision, setStreamRevision] = useState(0);
  const [showLiveStream, setShowLiveStream] = useState(false);

  const selectCamera = useCallback((cameraId: string) => {
    setSelectedCameraId(cameraId);
  }, []);

  const openCamera = useCallback((cameraId: string) => {
    setSelectedCameraId(cameraId);
    setStreamRevision(Date.now());
  }, []);

  const showLiveStreamNow = () => {
    setStreamRevision(Date.now());
    setShowLiveStream(true);
    const connected = cameraStreams.find(
      (status) => status.camera?.camera_id === selectedCameraId,
    )?.connected ?? false;
    announce(
      connected
        ? `ライブ映像を表示しました: ${selectedCameraId}`
        : "カメラの自動再接続を待っています",
      connected ? "success" : "warning",
    );
  };

  const stopLiveStream = useCallback(() => {
    setShowLiveStream(false);
  }, []);

  const hideLiveStream = () => {
    stopLiveStream();
    announce("ライブ映像を非表示にしました。カメラ接続は維持されます");
  };

  return {
    selectedCameraId,
    selectCamera,
    openCamera,
    streamRevision,
    showLiveStream,
    showLiveStreamNow,
    hideLiveStream,
    stopLiveStream,
  };
}
