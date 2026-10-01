"""新方式の診断データをPlotly HTMLへ変換する表示専用モジュール。"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from cardboard_counter_v2.measurement.core.height_grid import HeightGridDebugPoints
from cardboard_counter_v2.measurement.core.pallet_geometry import PalletProjectionGeometry
from cardboard_counter_v2.measurement.volume_mesh import VolumeMesh

# Webコンテナが配信する共有ファイル。各診断HTMLへPlotly本体を埋め込まない。
PLOTLY_SCRIPT_URL = "/vendor/plotly/plotly.min.js"


def _surface_values(
    height_grid: np.ndarray, mask: np.ndarray
) -> list[list[float | None]]:
    return [
        [
            round(float(height_grid[row, column]), 2)
            if mask[row, column]
            else None
            for column in range(height_grid.shape[1])
        ]
        for row in range(height_grid.shape[0])
    ]


def _points(values: np.ndarray) -> dict[str, list[float]]:
    if values.size == 0:
        return {"x": [], "y": [], "z": []}
    return {
        "x": np.round(values[:, 0], 2).tolist(),
        "y": np.round(values[:, 1], 2).tolist(),
        "z": np.round(values[:, 2], 2).tolist(),
    }


def _volume_values(mesh: VolumeMesh) -> dict[str, list[float] | list[int]]:
    return {
        "x": np.round(mesh.x, 2).tolist(),
        "y": np.round(mesh.y, 2).tolist(),
        "z": np.round(mesh.z, 2).tolist(),
        "i": mesh.i.tolist(),
        "j": mesh.j.tolist(),
        "k": mesh.k.tolist(),
    }


def write_height_plot(
    path: Path,
    *,
    height_grid: np.ndarray,
    original_height_grid: np.ndarray,
    box_region: np.ndarray,
    protrusion_mask: np.ndarray,
    geometry: PalletProjectionGeometry,
    volume_mesh: VolumeMesh,
    summary: dict[str, object],
) -> None:
    grid_mm = geometry.cell_size_mm
    u = geometry.minimum_u + (np.arange(height_grid.shape[1]) + 0.5) * grid_mm
    v = geometry.minimum_v + (np.arange(height_grid.shape[0]) + 0.5) * grid_mm
    rows, columns = np.nonzero(protrusion_mask)
    polygon_uv = geometry.polygon_uv
    payload = {
        "u": np.round(u, 2).tolist(),
        "v": np.round(v, 2).tolist(),
        "volume": _volume_values(volume_mesh),
        "outline_u": np.round(
            np.append(polygon_uv[:, 0], polygon_uv[0, 0]), 2
        ).tolist(),
        "outline_v": np.round(
            np.append(polygon_uv[:, 1], polygon_uv[0, 1]), 2
        ).tolist(),
        "excluded_u": np.round(u[columns], 2).tolist(),
        "excluded_v": np.round(v[rows], 2).tolist(),
        "excluded_h": np.round(original_height_grid[rows, columns], 2).tolist(),
    }
    path.write_text(
        '<!doctype html><html lang="ja"><head><meta charset="utf-8">'
        '<title>パレット平面測定</title>'
        f'<script src="{PLOTLY_SCRIPT_URL}"></script>'
        '<style>body{margin:0;font-family:sans-serif}.summary{padding:10px 16px;background:#111820;color:white}'
        '#plot{width:100vw;height:78vh}</style></head><body>'
        f'<div class="summary">{json.dumps(summary, ensure_ascii=False)}</div>'
        '<div id="plot"></div>'
        f'<script>const p={json.dumps(payload, ensure_ascii=False, separators=(",", ":"))};'
        "const heightColors=[[0,'#dddddd'],[.35,'#f6b27d'],[.7,'#e85c3f'],[1,'#b8001f']];"
        "const volume={type:'mesh3d',x:p.volume.x,y:p.volume.y,z:p.volume.z,"
        "i:p.volume.i,j:p.volume.j,k:p.volume.k,intensity:p.volume.z,intensitymode:'vertex',"
        "colorscale:heightColors,colorbar:{title:'高さ mm'},flatshading:true,"
        "lighting:{ambient:.7,diffuse:.8,specular:.15,roughness:.8},name:'10mmセル柱状体積'};"
        "const outline={type:'scatter3d',mode:'lines',x:p.outline_u,y:p.outline_v,"
        "z:p.outline_u.map(()=>0),line:{color:'#00bcd4',width:8},name:'パレット外周'};"
        "const excluded={type:'scatter3d',mode:'markers',x:p.excluded_u,y:p.excluded_v,z:p.excluded_h,"
        "marker:{color:'#ff9800',size:3},name:'局所突起として除外',visible:'legendonly'};"
        "Plotly.newPlot('plot',[volume,outline,excluded],{title:'pallet_plane_2roi 最終柱状体積',"
        "scene:{xaxis:{title:'パレットU mm'},yaxis:{title:'パレットV mm'},"
        "zaxis:{title:'平面からの高さ mm'},aspectmode:'data',camera:{eye:{x:1.45,y:1.45,z:1.05}}},"
        "uirevision:'pallet-volume',margin:{l:0,r:0,b:0,t:40}},{responsive:true,scrollZoom:true});"
        "</script></body></html>",
        encoding="utf-8",
    )


def write_debug_stages_plot(
    path: Path,
    *,
    debug_points: HeightGridDebugPoints,
    height_grid: np.ndarray,
    original_height_grid: np.ndarray,
    box_region: np.ndarray,
    protrusion_mask: np.ndarray,
    geometry: PalletProjectionGeometry,
    volume_mesh: VolumeMesh,
    summary: dict[str, object],
    point_cloud_relative_url: str,
) -> None:
    """1回の解析で得た中間値を、再計算せず6段階で表示する。"""
    grid_mm = geometry.cell_size_mm
    u = geometry.minimum_u + (np.arange(height_grid.shape[1]) + 0.5) * grid_mm
    v = geometry.minimum_v + (np.arange(height_grid.shape[0]) + 0.5) * grid_mm
    rows, columns = np.nonzero(protrusion_mask)
    payload = {
        "raw": _points(debug_points.raw_xyz),
        "candidate": _points(debug_points.candidate_xyz),
        "projected": _points(debug_points.projected_uvh),
        "u": np.round(u, 2).tolist(),
        "v": np.round(v, 2).tolist(),
        "grid": _surface_values(original_height_grid, box_region),
        "corrected": _surface_values(height_grid, box_region),
        "volume": _volume_values(volume_mesh),
        "outline_u": np.round(
            np.append(geometry.polygon_uv[:, 0], geometry.polygon_uv[0, 0]), 2
        ).tolist(),
        "outline_v": np.round(
            np.append(geometry.polygon_uv[:, 1], geometry.polygon_uv[0, 1]), 2
        ).tolist(),
        "excluded_u": np.round(u[columns], 2).tolist(),
        "excluded_v": np.round(v[rows], 2).tolist(),
        "excluded_h": np.round(original_height_grid[rows, columns], 2).tolist(),
        "summary": summary,
    }
    path.write_text(
        '<!doctype html><html lang="ja"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>新方式 段階別3D診断</title>'
        f'<script src="{PLOTLY_SCRIPT_URL}"></script>'
        '<style>body{margin:0;font-family:sans-serif;background:#f4f6f8;color:#17202a}'
        '.head{padding:14px 18px;background:#111820;color:white}.toolbar{display:flex;gap:10px;'
        'align-items:center;padding:10px 12px 0;flex-wrap:wrap}.display-modes,.point-options,'
        '.color-options,.shape-options{display:flex;gap:7px}'
        '.toolbar button,.steps button{white-space:nowrap;padding:9px 12px;border:1px solid #8e9aa5;'
        'border-radius:8px;background:white;font-weight:700;cursor:pointer}.toolbar button.active,'
        '.steps button.active{background:#007d83;color:white;border-color:#007d83}.point-options{display:none}'
        '.toolbar button:disabled{cursor:not-allowed;opacity:.45}'
        '.steps{display:flex;gap:8px;'
        'padding:12px;overflow:auto}.steps button{white-space:nowrap;padding:9px 12px;border:1px solid #8e9aa5;'
        'border-radius:8px;background:white;font-weight:700}'
        '#plot,#point-view{width:100vw;height:75vh}#point-view{display:none;border:0;background:#111820}'
        '</style></head><body>'
        f'<div class="head">新方式 段階別3D診断 / {json.dumps(summary, ensure_ascii=False)}</div>'
        '<div class="toolbar"><div class="display-modes">'
        '<button data-display="map" class="active">高さカラーマップ</button>'
        '<button data-display="points">ポイントクラウド</button></div>'
        '<div class="point-options"><div class="color-options">'
        '<button data-color="actual" class="active">実写色</button>'
        '<button data-color="highlight">背景＋処理対象を赤強調</button></div>'
        '<div class="shape-options"><button data-shape="surface">表面点群</button>'
        '<button data-shape="solid" class="active">立体充填</button></div></div></div>'
        '<div class="steps"></div><div id="plot"></div><iframe id="point-view" title="段階別ポイントクラウド"></iframe>'
        f'<script>const p={json.dumps(payload, ensure_ascii=False, separators=(",", ":"))};'
        f'const pointUrl={json.dumps(point_cloud_relative_url)};'
        "const names=['1 生点群','2 現在フレーム候補','3 側面除外・平面投影・外周制限','4 10mm高さグリッド','5 局所突起除外','6 最終体積'];"
        "const steps=document.querySelector('.steps');let activeStage=0,displayMode='map',colorMode='actual',shapeMode='solid';"
        "names.forEach((n,i)=>{const b=document.createElement('button');b.textContent=n;b.onclick=()=>setStage(i);steps.appendChild(b)});"
        "const scatter=(q,name,color)=>({type:'scatter3d',mode:'markers',x:q.x,y:q.y,z:q.z,"
        "marker:{size:2,color:q.z,colorscale:color,opacity:.75},name});"
        "const heightColors=[[0,'#dddddd'],[.35,'#f6b27d'],[.7,'#e85c3f'],[1,'#b8001f']];"
        "const outline={type:'scatter3d',mode:'lines',x:p.outline_u,y:p.outline_v,"
        "z:p.outline_u.map(()=>0),line:{color:'#00bcd4',width:8},name:'パレット外周'};"
        "const surface=(z,name)=>({type:'surface',x:p.u,y:p.v,z,colorscale:heightColors,"
        "colorbar:{title:'高さ mm'},connectgaps:false,name});"
        "const volume=name=>({type:'mesh3d',x:p.volume.x,y:p.volume.y,z:p.volume.z,"
        "i:p.volume.i,j:p.volume.j,k:p.volume.k,intensity:p.volume.z,intensitymode:'vertex',"
        "colorscale:heightColors,colorbar:{title:'高さ mm'},flatshading:true,"
        "lighting:{ambient:.7,diffuse:.8,specular:.15,roughness:.8},name});"
        "function render(i){let traces,title,axes={xaxis:{title:'X mm'},yaxis:{title:'Y mm'},"
        "zaxis:{title:'カメラ奥行きZ mm（小さいほど高い）',autorange:'reversed'}};"
        "if(i===0){traces=[scatter(p.raw,'生点群','Turbo')];title=names[i]}"
        "else if(i===1){traces=[scatter(p.candidate,'有効Depth点群','Turbo')];title=names[i]}"
        "else if(i===2){traces=[scatter(p.projected,'採用点','Turbo'),outline];title=names[i];axes={xaxis:{title:'U mm'},yaxis:{title:'V mm'},zaxis:{title:'平面からの高さ mm'}}}"
        "else if(i===3){traces=[surface(p.grid,'75%分位高さ'),outline];title=names[i];axes={xaxis:{title:'U mm'},yaxis:{title:'V mm'},zaxis:{title:'高さ mm'}}}"
        "else if(i===4){traces=[surface(p.corrected,'補正後高さ'),outline];traces.push({type:'scatter3d',mode:'markers',"
        "x:p.excluded_u,y:p.excluded_v,z:p.excluded_h,marker:{size:4,color:'#7b2cbf'},name:'除外点'});title=names[i];"
        "axes={xaxis:{title:'U mm'},yaxis:{title:'V mm'},zaxis:{title:'高さ mm'}}}"
        "else {traces=[volume('10mmセル柱状体積'),outline];title=names[i];"
        "axes={xaxis:{title:'U mm'},yaxis:{title:'V mm'},zaxis:{title:'高さ mm'}}}"
        "[...steps.children].forEach((b,j)=>b.classList.toggle('active',j===i));"
        "Plotly.react('plot',traces,{title,scene:{...axes,aspectmode:'data',camera:{eye:{x:1.45,y:1.45,z:1.05}}},"
        "margin:{l:0,r:0,b:0,t:45}},{responsive:true,scrollZoom:true});}"
        "const plot=document.getElementById('plot'),pointView=document.getElementById('point-view');"
        "const pointOptions=document.querySelector('.point-options');"
        "function effectiveShape(){return activeStage>=3?shapeMode:'surface'}"
        "function updateShapeControls(){const enabled=activeStage>=3;document.querySelectorAll('[data-shape]').forEach(b=>{"
        "b.disabled=b.dataset.shape==='solid'&&!enabled;b.classList.toggle('active',b.dataset.shape===effectiveShape())})}"
        "function sendPointState(){if(pointView.contentWindow){pointView.contentWindow.postMessage({type:'debug-stage',stage:activeStage},location.origin);"
        "pointView.contentWindow.postMessage({type:'debug-color',mode:colorMode},location.origin);"
        "pointView.contentWindow.postMessage({type:'debug-shape',mode:effectiveShape()},location.origin)}}"
        "function setStage(i){activeStage=i;[...steps.children].forEach((b,j)=>b.classList.toggle('active',j===i));"
        "updateShapeControls();if(displayMode==='map')render(i);else sendPointState()}"
        "function setDisplay(mode){displayMode=mode;document.querySelectorAll('[data-display]').forEach(b=>b.classList.toggle('active',b.dataset.display===mode));"
        "const points=mode==='points';plot.style.display=points?'none':'block';pointView.style.display=points?'block':'none';"
        "pointOptions.style.display=points?'flex':'none';if(points){if(!pointView.getAttribute('src')){pointView.src=pointUrl}else sendPointState()}else render(activeStage)}"
        "document.querySelectorAll('[data-display]').forEach(b=>b.onclick=()=>setDisplay(b.dataset.display));"
        "document.querySelectorAll('[data-color]').forEach(b=>b.onclick=()=>{colorMode=b.dataset.color;"
        "document.querySelectorAll('[data-color]').forEach(x=>x.classList.toggle('active',x===b));sendPointState()});"
        "document.querySelectorAll('[data-shape]').forEach(b=>b.onclick=()=>{if(b.disabled)return;shapeMode=b.dataset.shape;"
        "updateShapeControls();sendPointState()});"
        "pointView.onload=sendPointState;setStage(0);</script></body></html>",
        encoding="utf-8",
    )
