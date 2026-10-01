import { useEffect, useRef, useState } from "react";
import { Circle, Group, Image as KonvaImage, Label, Layer, Stage, Tag, Text } from "react-konva";
import type { CameraStreamStatus, FactoryMapSummary } from "../types";
import { useCachedImage } from "../useCachedImage";
import {
  effectivePalletState,
  markerLabel,
  stateColors,
  tooltipText,
} from "./presentation";
import type { PalletMarker } from "./presentation";
import type { MapPosition } from "./useFactoryMapEditor";

const MARKER_RADIUS_PX = 12;
const MARKER_FONT_SIZE_PX = 9;

type Props = {
  map: FactoryMapSummary;
  markers: PalletMarker[];
  streams: CameraStreamStatus[];
  monitorRunning: boolean;
  positions: Record<string, MapPosition>;
  editMode: boolean;
  selectedMarker: number | null;
  onSelectMarker: (palletSlotId: number) => void;
  onSetPosition: (palletSlotId: number, position: MapPosition) => void;
  onOpenCamera: (cameraId: string) => void;
};

export default function FactoryMapCanvas(props: Props) {
  const [containerWidth, setContainerWidth] = useState(1);
  const [hoveredPallet, setHoveredPallet] = useState<number | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapImage = useCachedImage(props.map.image_url);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const update = () => setContainerWidth(Math.max(container.clientWidth, 1));
    update();
    const observer = new ResizeObserver(update);
    observer.observe(container);
    return () => observer.disconnect();
  }, [props.map.factory_map_id]);

  const scale = containerWidth / props.map.image_width;
  const mapMarkers = props.markers.filter(({ pallet }) => (
    props.positions[pallet.pallet_slot_id]
  ));
  const constrain = (position: MapPosition): MapPosition => ({
    x: Math.min(
      Math.max(position.x, MARKER_RADIUS_PX),
      props.map.image_width - MARKER_RADIUS_PX,
    ),
    y: Math.min(
      Math.max(position.y, MARKER_RADIUS_PX),
      props.map.image_height - MARKER_RADIUS_PX,
    ),
  });
  const dropPallet = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    if (!props.editMode || !containerRef.current) return;
    const palletSlotId = Number(event.dataTransfer.getData("text/pallet-slot-id"));
    if (!props.markers.some(({ pallet }) => pallet.pallet_slot_id === palletSlotId)) return;
    const bounds = containerRef.current.getBoundingClientRect();
    props.onSetPosition(palletSlotId, constrain({
      x: (event.clientX - bounds.left) / scale,
      y: (event.clientY - bounds.top) / scale,
    }));
  };

  return <div className={props.editMode ? "factory-map-canvas editing" : "factory-map-canvas"}
    ref={containerRef}
    onDragOver={(event) => { if (props.editMode) event.preventDefault(); }}
    onDrop={dropPallet}>
    {mapImage.image && <Stage width={containerWidth}
      height={props.map.image_height * scale} scaleX={scale} scaleY={scale}>
      <Layer listening={false}>
        <KonvaImage image={mapImage.image} width={props.map.image_width}
          height={props.map.image_height} />
      </Layer>
      <Layer>
        {mapMarkers.map(({ camera, pallet }) => {
          const position = props.positions[pallet.pallet_slot_id];
          const effective = effectivePalletState(
            camera, pallet, props.streams, props.monitorRunning,
          );
          const selected = props.selectedMarker === pallet.pallet_slot_id;
          return <Group key={pallet.pallet_slot_id} x={position.x} y={position.y}
            scaleX={1 / scale} scaleY={1 / scale}
            draggable={props.editMode}
            onDragEnd={(event) => props.onSetPosition(
              pallet.pallet_slot_id,
              constrain({ x: event.target.x(), y: event.target.y() }),
            )}
            onClick={() => props.editMode
              ? props.onSelectMarker(pallet.pallet_slot_id)
              : props.onOpenCamera(camera.camera_id)}
            onTap={() => props.editMode
              ? props.onSelectMarker(pallet.pallet_slot_id)
              : props.onOpenCamera(camera.camera_id)}
            onMouseEnter={() => setHoveredPallet(pallet.pallet_slot_id)}
            onMouseLeave={() => setHoveredPallet(null)}>
            <Circle radius={MARKER_RADIUS_PX} fill="#ffffff"
              stroke={stateColors[effective.state]}
              strokeWidth={selected ? 5 : 3} shadowColor="#111820"
              shadowBlur={3} shadowOpacity={0.3} />
            <Text text={markerLabel(camera, pallet)} width={MARKER_RADIUS_PX * 2}
              offsetX={MARKER_RADIUS_PX} offsetY={4}
              align="center" fontSize={MARKER_FONT_SIZE_PX}
              fontStyle="bold" fill="#111820"
              listening={false} />
          </Group>;
        })}
        {hoveredPallet !== null && (() => {
          const marker = props.markers.find(
            ({ pallet }) => pallet.pallet_slot_id === hoveredPallet,
          );
          const position = props.positions[hoveredPallet];
          if (!marker || !position) return null;
          const effective = effectivePalletState(
            marker.camera, marker.pallet, props.streams, props.monitorRunning,
          );
          return <Label x={position.x + 20 / scale} y={position.y - 18 / scale}
            scaleX={1 / scale} scaleY={1 / scale} listening={false}>
            <Tag fill="#111820" cornerRadius={6} shadowColor="#000"
              shadowBlur={5} opacity={0.94} />
            <Text text={tooltipText(marker.camera, marker.pallet, effective.message)} fill="white"
              fontSize={13} lineHeight={1.35} padding={9} />
          </Label>;
        })()}
      </Layer>
    </Stage>}
    {mapImage.status === "loading" && <div className="map-loading" aria-live="polite"
      aria-busy="true"><span>工場マップを読み込み中です</span></div>}
    {mapImage.status === "error" && <div className="map-image-error" role="alert">
      <strong>工場マップ画像を表示できませんでした</strong>
      <p>{mapImage.error?.message}。通信状態を確認して再読み込みしてください。</p>
      <button type="button" onClick={mapImage.retry}>画像を再読み込み</button>
    </div>}
  </div>;
}
