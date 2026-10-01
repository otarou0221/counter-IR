import { useState, type PointerEvent as ReactPointerEvent } from "react";
import { roiFromDrag, type NormalizedPoint, type NormalizedRoi } from "./roi";
import type { NoticeHandler } from "./uiNotice";

export type ImageRectangle = {
  id: string;
  label: string;
  roi: NormalizedRoi;
  className: string;
  muted?: boolean;
};

type Props = {
  imageUrl: string;
  disabled: boolean;
  rectangles: ImageRectangle[];
  activeRectangle: ImageRectangle;
  onChange: (roi: NormalizedRoi) => void;
  onMessage: NoticeHandler;
};

function Rectangle({ rectangle, draft = false }: { rectangle: ImageRectangle; draft?: boolean }) {
  const [left, top, right, bottom] = rectangle.roi;
  return <div className={`roi-rectangle ${rectangle.className} ${rectangle.muted ? "muted" : ""} ${draft ? "draft" : ""}`}
    style={{ left: `${left * 100}%`, top: `${top * 100}%`, width: `${(right - left) * 100}%`, height: `${(bottom - top) * 100}%` }}>
    <span>{rectangle.label}</span>
  </div>;
}

export default function StaticImageRectangleEditor({ imageUrl, disabled, rectangles, activeRectangle, onChange, onMessage }: Props) {
  const [dragStart, setDragStart] = useState<NormalizedPoint | null>(null);
  const [draftRoi, setDraftRoi] = useState<NormalizedRoi | null>(null);
  const point = (event: ReactPointerEvent<HTMLDivElement>): NormalizedPoint => {
    const bounds = event.currentTarget.getBoundingClientRect();
    return {
      x: Math.min(1, Math.max(0, (event.clientX - bounds.left) / bounds.width)),
      y: Math.min(1, Math.max(0, (event.clientY - bounds.top) / bounds.height)),
    };
  };
  const finish = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!dragStart) return;
    const roi = roiFromDrag(dragStart, point(event));
    setDragStart(null);
    setDraftRoi(null);
    if (!roi) return onMessage("ROIが小さすぎます。範囲をもう一度ドラッグしてください", "warning");
    onChange(roi);
  };
  return <div className="roi-stage">
    <img className="roi-source" src={imageUrl} alt="ROI選択用の保存撮影" />
    <div className={`roi-overlay ${disabled ? "" : "editable"}`}
      onPointerDown={(event) => {
        if (disabled) return;
        event.currentTarget.setPointerCapture(event.pointerId);
        setDragStart(point(event));
        setDraftRoi(null);
      }}
      onPointerMove={(event) => { if (dragStart) setDraftRoi(roiFromDrag(dragStart, point(event), 0)); }}
      onPointerUp={finish}
      onPointerCancel={() => { setDragStart(null); setDraftRoi(null); }}>
      {rectangles.map((rectangle) => <Rectangle key={rectangle.id} rectangle={rectangle} />)}
      {draftRoi && <Rectangle rectangle={{ ...activeRectangle, roi: draftRoi, muted: false }} draft />}
    </div>
  </div>;
}
