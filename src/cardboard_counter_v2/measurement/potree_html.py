"""Potree専用ビューと3D成果物の表示切替ページを生成する。"""

from __future__ import annotations

import html
import json
from pathlib import Path


POTREE_ROOT_URL = "/vendor/potree"


def write_debug_point_cloud_viewer(
    path: Path,
    *,
    context_metadata_relative_url: str | None,
    context_point_count: int,
    stages: list[dict[str, object]],
) -> None:
    """段階ごとの実写色点群と、背景付き赤強調を同じPotree画面で切り替える。"""
    context_url = json.dumps(context_metadata_relative_url, ensure_ascii=False)
    stages_json = json.dumps(stages, ensure_ascii=False, separators=(",", ":"))
    path.write_text(
        '<!doctype html><html lang="ja"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>段階別ポイントクラウド</title>'
        f'<link rel="stylesheet" href="{POTREE_ROOT_URL}/build/potree/potree.css">'
        f'<link rel="stylesheet" href="{POTREE_ROOT_URL}/libs/jquery-ui/jquery-ui.min.css">'
        f'<link rel="stylesheet" href="{POTREE_ROOT_URL}/libs/openlayers3/ol.css">'
        f'<link rel="stylesheet" href="{POTREE_ROOT_URL}/libs/spectrum/spectrum.css">'
        f'<link rel="stylesheet" href="{POTREE_ROOT_URL}/libs/jstree/themes/mixed/style.css">'
        '<style>html,body{width:100%;height:100%;margin:0;overflow:hidden}'
        '.point-note{position:absolute;z-index:10;top:8px;right:12px;padding:7px 10px;'
        'border-radius:7px;background:#111d;color:#fff;font:13px sans-serif}'
        '.empty{position:absolute;z-index:11;inset:0;display:none;place-items:center;pointer-events:none;'
        'color:white;font:700 16px sans-serif}.empty span{padding:14px 18px;background:#111d;'
        'border-radius:8px}</style></head><body>'
        f'<script src="{POTREE_ROOT_URL}/libs/jquery/jquery-3.1.1.min.js"></script>'
        f'<script src="{POTREE_ROOT_URL}/libs/spectrum/spectrum.js"></script>'
        f'<script src="{POTREE_ROOT_URL}/libs/jquery-ui/jquery-ui.min.js"></script>'
        f'<script src="{POTREE_ROOT_URL}/libs/other/BinaryHeap.js"></script>'
        f'<script src="{POTREE_ROOT_URL}/libs/tween/tween.min.js"></script>'
        f'<script src="{POTREE_ROOT_URL}/libs/d3/d3.js"></script>'
        f'<script src="{POTREE_ROOT_URL}/libs/proj4/proj4.js"></script>'
        f'<script src="{POTREE_ROOT_URL}/libs/openlayers3/ol.js"></script>'
        f'<script src="{POTREE_ROOT_URL}/libs/i18next/i18next.js"></script>'
        f'<script src="{POTREE_ROOT_URL}/libs/jstree/jstree.js"></script>'
        f'<script src="{POTREE_ROOT_URL}/build/potree/potree.js"></script>'
        f'<script src="{POTREE_ROOT_URL}/libs/plasio/js/laslaz.js"></script>'
        '<div class="potree_container" style="position:absolute;width:100%;height:100%;left:0;top:0">'
        f'<div id="potree_render_area" style="background-image:url(\'{POTREE_ROOT_URL}/build/potree/resources/images/background.jpg\')"></div>'
        '<div id="potree_sidebar_container"></div></div><div class="point-note" id="note">読込中</div>'
        '<div class="empty" id="empty"><span>この段階に表示できる点はありません。</span></div>'
        '<script type="module">'
        f'import * as THREE from "{POTREE_ROOT_URL}/libs/three.js/build/three.module.js";'
        'window.THREE=THREE;const stageDefs='
        f'{stages_json};const contextPointCount={int(context_point_count)};'
        'const viewer=window.viewer=new Potree.Viewer(document.getElementById("potree_render_area"));'
        'viewer.setEDLEnabled(true);viewer.setFOV(60);viewer.setPointBudget(1000000);'
        'viewer.setDescription("段階別点群。実写色のみ、または周辺背景＋処理対象の赤強調を切替できます。");'
        'viewer.loadGUI(()=>viewer.setLanguage("jp"));const note=document.getElementById("note");'
        'const empty=document.getElementById("empty");let contextCloud=null;const stageClouds=[],solidClouds=[];'
        'let activeStage=0,colorMode="actual",shapeMode="solid";const cloudCache=new Map();'
        'function loadCloud(url,name){if(!url)return Promise.resolve(null);if(cloudCache.has(url))return cloudCache.get(url);'
        'const promise=new Promise(resolve=>{Potree.loadPointCloud(url,name,event=>{const cloud=event.pointcloud;'
        'viewer.scene.addPointCloud(cloud);cloud.visible=false;cloud.material.activeAttributeName="rgba";'
        'cloud.material.size=1;cloud.material.minSize=2;'
        'cloud.material.pointSizeType=Potree.PointSizeType.ADAPTIVE;resolve(cloud);});});'
        'cloudCache.set(url,promise);return promise}'
        f'const contextPromise=loadCloud({context_url},"背景");'
        'const stagePromises=stageDefs.map((stage,index)=>stage.uses_context?Promise.resolve(null):'
        'loadCloud(stage.metadata,`段階${index+1}`));'
        'const solidPromises=stageDefs.map((stage,index)=>loadCloud(stage.solid_metadata,`立体段階${index+1}`));'
        'Promise.all([contextPromise,Promise.all(stagePromises),Promise.all(solidPromises)]).then(values=>{'
        'contextCloud=values[0];stageClouds.push(...values[1]);solidClouds.push(...values[2]);applyView(true);});'
        'function rgb(cloud,solid=false){if(!cloud)return;cloud.material.activeAttributeName="rgba";'
        'cloud.material.size=solid?3:1;cloud.material.pointSizeType=solid?'
        'Potree.PointSizeType.FIXED:Potree.PointSizeType.ADAPTIVE;}'
        'function red(cloud,solid=false){if(!cloud)return;cloud.material.activeAttributeName="color";'
        'cloud.material.color=new THREE.Color(0.92,0.05,0.05);cloud.material.size=solid?3.5:2.4;'
        'cloud.material.pointSizeType=solid?Potree.PointSizeType.FIXED:Potree.PointSizeType.ADAPTIVE;}'
        'function applyView(fit=false){new Set([...stageClouds,...solidClouds]).forEach(cloud=>{if(cloud)cloud.visible=false});'
        'if(contextCloud)contextCloud.visible=false;const stage=stageDefs[activeStage];'
        'const surfaceCloud=stage.uses_context?contextCloud:stageClouds[activeStage];'
        'const solidCloud=solidClouds[activeStage];const useSolid=shapeMode==="solid"&&solidCloud;'
        'const cloud=useSolid?solidCloud:surfaceCloud;'
        'empty.style.display=cloud?"none":"grid";if(colorMode==="highlight"){if(contextCloud){rgb(contextCloud,false);'
        'contextCloud.visible=true}if(cloud){red(cloud,useSolid);cloud.visible=true}}else if(cloud){rgb(cloud,useSolid);cloud.visible=true}'
        'const shapeLabel=useSolid?`立体充填（縦${stage.solid_vertical_step_mm}mm間隔）`:"表面点群";'
        'const pointCount=useSolid?stage.solid_point_count:stage.point_count;'
        'note.textContent=`${stage.title} / ${shapeLabel} / ${colorMode==="highlight"?"背景＋処理対象を赤強調":"実写色"} / ${pointCount.toLocaleString()}点`;'
        'if(fit){viewer.fitToScreen();setTimeout(()=>viewer.fitToScreen(),500)}}'
        'window.addEventListener("message",event=>{const data=event.data||{};if(data.type==="debug-stage")'
        '{activeStage=Math.max(0,Math.min(stageDefs.length-1,Number(data.stage)||0));applyView(false)}'
        'if(data.type==="debug-color"){colorMode=data.mode==="highlight"?"highlight":"actual";applyView(false)}});'
        'window.addEventListener("message",event=>{const data=event.data||{};if(data.type==="debug-shape")'
        '{shapeMode=data.mode==="solid"?"solid":"surface";applyView(false)}});'
        '</script></body></html>',
        encoding="utf-8",
    )


def write_empty_point_cloud_viewer(path: Path) -> None:
    """箱セルがない測定でも成果物全体を失敗させず、理由を表示する。"""
    path.write_text(
        '<!doctype html><html lang="ja"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>高さ充填ポイントクラウド</title><style>'
        'html,body{height:100%;margin:0;background:#111820;color:white;font-family:sans-serif}'
        'body{display:grid;place-items:center}.message{padding:24px;border:1px solid #52606d;'
        'border-radius:10px;background:#19252f}</style></head><body>'
        '<div class="message">充填表示の対象になる箱セルはありません。</div>'
        '</body></html>',
        encoding="utf-8",
    )


def write_potree_viewer(
    path: Path,
    *,
    metadata_relative_url: str,
    point_count: int,
    title: str = "RGBポイントクラウド",
    description: str = "パレット座標 RGBポイントクラウド（Z軸が平面からの高さ）",
    height_range_mm: tuple[float, float] | None = None,
    color_by_elevation: bool = True,
    adaptive_point_size: bool = True,
    point_size: float = 1.0,
) -> None:
    """フルPotree GUIを使う点群ビューを書き出す。"""
    metadata_url = json.dumps(metadata_relative_url, ensure_ascii=False)
    safe_title = html.escape(title)
    description_json = json.dumps(description, ensure_ascii=False)
    point_size_type = "ADAPTIVE" if adaptive_point_size else "FIXED"
    material_attribute = 'cloud.material.activeAttributeName="rgba";'
    if height_range_mm is not None and color_by_elevation:
        minimum_height, maximum_height = height_range_mm
        material_attribute = (
            'cloud.material.activeAttributeName="elevation";'
            f'cloud.material.elevationRange=[{minimum_height / 1000.0:g},'
            f'{maximum_height / 1000.0:g}];'
            'cloud.material.gradient=['
            '[0,new THREE.Color(0.867,0.867,0.867)],'
            '[0.35,new THREE.Color(0.965,0.698,0.490)],'
            '[0.70,new THREE.Color(0.910,0.361,0.247)],'
            '[1,new THREE.Color(0.722,0,0.122)]];'
        )
    legend = ""
    if height_range_mm is not None:
        minimum_height, maximum_height = height_range_mm
        legend = (
            '<div class="height-legend"><span>'
            f'{maximum_height:.0f} mm</span><i></i><span>{minimum_height:.0f} mm</span></div>'
        )
    path.write_text(
        '<!doctype html><html lang="ja"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{safe_title} - Potree</title>'
        f'<link rel="stylesheet" href="{POTREE_ROOT_URL}/build/potree/potree.css">'
        f'<link rel="stylesheet" href="{POTREE_ROOT_URL}/libs/jquery-ui/jquery-ui.min.css">'
        f'<link rel="stylesheet" href="{POTREE_ROOT_URL}/libs/openlayers3/ol.css">'
        f'<link rel="stylesheet" href="{POTREE_ROOT_URL}/libs/spectrum/spectrum.css">'
        f'<link rel="stylesheet" href="{POTREE_ROOT_URL}/libs/jstree/themes/mixed/style.css">'
        '<style>html,body{width:100%;height:100%;margin:0;overflow:hidden}'
        '.point-note{position:absolute;z-index:10;top:8px;right:12px;padding:7px 10px;'
        'border-radius:7px;background:#111c;color:#fff;font:13px sans-serif}'
        '.height-legend{position:absolute;z-index:10;right:14px;top:52px;display:grid;'
        'grid-template-rows:auto 180px auto;justify-items:center;gap:4px;padding:9px;'
        'border-radius:7px;background:#111c;color:#fff;font:12px sans-serif}'
        '.height-legend i{display:block;width:18px;height:180px;background:linear-gradient('
        'to top,#ddd 0%,#f6b27d 35%,#e85c3f 70%,#b8001f 100%)}</style></head><body>'
        f'<script src="{POTREE_ROOT_URL}/libs/jquery/jquery-3.1.1.min.js"></script>'
        f'<script src="{POTREE_ROOT_URL}/libs/spectrum/spectrum.js"></script>'
        f'<script src="{POTREE_ROOT_URL}/libs/jquery-ui/jquery-ui.min.js"></script>'
        f'<script src="{POTREE_ROOT_URL}/libs/other/BinaryHeap.js"></script>'
        f'<script src="{POTREE_ROOT_URL}/libs/tween/tween.min.js"></script>'
        f'<script src="{POTREE_ROOT_URL}/libs/d3/d3.js"></script>'
        f'<script src="{POTREE_ROOT_URL}/libs/proj4/proj4.js"></script>'
        f'<script src="{POTREE_ROOT_URL}/libs/openlayers3/ol.js"></script>'
        f'<script src="{POTREE_ROOT_URL}/libs/i18next/i18next.js"></script>'
        f'<script src="{POTREE_ROOT_URL}/libs/jstree/jstree.js"></script>'
        f'<script src="{POTREE_ROOT_URL}/build/potree/potree.js"></script>'
        f'<script src="{POTREE_ROOT_URL}/libs/plasio/js/laslaz.js"></script>'
        '<div class="potree_container" style="position:absolute;width:100%;height:100%;left:0;top:0">'
        f'<div id="potree_render_area" style="background-image:url(\'{POTREE_ROOT_URL}/build/potree/resources/images/background.jpg\')"></div>'
        '<div id="potree_sidebar_container"></div></div>'
        f'<div class="point-note">{safe_title} {point_count:,}点 / 座標単位 m</div>{legend}'
        '<script type="module">'
        f'import * as THREE from "{POTREE_ROOT_URL}/libs/three.js/build/three.module.js";'
        'window.THREE=THREE;'
        'const viewer=window.viewer=new Potree.Viewer(document.getElementById("potree_render_area"));'
        'viewer.setEDLEnabled(true);viewer.setFOV(60);viewer.setPointBudget(1000000);'
        f'viewer.setDescription({description_json});'
        'viewer.loadGUI(()=>{viewer.setLanguage("jp");});'
        f'Potree.loadPointCloud({metadata_url},"pallet",event=>{{'
        'const cloud=event.pointcloud;viewer.scene.addPointCloud(cloud);'
        f'{material_attribute}cloud.material.size={float(point_size):g};'
        f'cloud.material.minSize=2;cloud.material.pointSizeType=Potree.PointSizeType.{point_size_type};'
        # 大きな変換済み点群では初回ノード読込み後にも合わせ直し、空画面を避ける。
        'viewer.fitToScreen();setTimeout(()=>viewer.fitToScreen(),500);});'
        '</script></body></html>',
        encoding="utf-8",
    )


def write_artifact_index(
    path: Path,
    *,
    summary: dict[str, object],
    volume_relative_url: str,
    point_cloud_relative_url: str,
    height_filled_relative_url: str,
) -> None:
    """既存の成果物URLを保ったまま、Plotly体積とPotreeを切り替える。"""
    summary_text = html.escape(json.dumps(summary, ensure_ascii=False))
    volume_url = json.dumps(volume_relative_url)
    point_url = json.dumps(point_cloud_relative_url)
    path.write_text(
        '<!doctype html><html lang="ja"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>パレット3D診断</title><style>'
        'html,body{height:100%;margin:0;font-family:sans-serif;background:#edf1f4}'
        '.summary{padding:10px 16px;background:#111820;color:white;white-space:nowrap;overflow:auto}'
        '.views{display:flex;gap:8px;padding:9px 16px}.views button{padding:9px 14px;'
        'border:1px solid #8e9aa5;border-radius:8px;background:white;font-weight:700;cursor:pointer}'
        '.views button.active{background:#007d83;color:white;border-color:#007d83}'
        'iframe{display:block;width:100%;height:calc(100% - 92px);border:0;background:white}'
        '</style></head><body>'
        f'<div class="summary">{summary_text}</div>'
        '<div class="views"><button data-view="volume">10mmセルの柱状体積</button>'
        '<button data-view="points">周辺＋体積推定領域ポイントクラウド（Potree）</button>'
        '<button data-view="filled">高さ充填ポイントクラウド（Potree）</button></div>'
        '<iframe id="viewer" title="3D診断"></iframe><script>'
        f'const urls={{volume:{volume_url},points:{point_url},filled:{json.dumps(height_filled_relative_url)}}};'
        'const frame=document.getElementById("viewer");const buttons=[...document.querySelectorAll("button")];'
        'function show(view){buttons.forEach(button=>button.classList.toggle("active",button.dataset.view===view));'
        'frame.src=urls[view];}buttons.forEach(button=>button.onclick=()=>show(button.dataset.view));show("volume");'
        '</script></body></html>',
        encoding="utf-8",
    )
