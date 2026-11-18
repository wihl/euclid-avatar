"""Interactive Three.js 3D Virtual World HTML/JS generator for Proposition III.36.

Features:
1. Real-time 3D diagram highlighting of spoken points, line segments, triangles
   (`△FBD`, `△EFC`, `△EFD`, `△EBD`), and area squares/rectangles synchronized to
   acoustic word/clause timestamps.
2. Interactive 3D circumference dragging of Point `A` toward `B` on Slide 1 (~0:49)
   and interactive 3D sweeping of line `DF` across the circle on Slide 4 (~3:57),
   automatically pausing playback (and pausing immediately on grab) in lieu of the
   canned sweep animation until the user clicks Continue.
3. Compact diagram scale & elevated framing so nothing is covered by bottom
   navigation, with zero subtitles and zero background clutter.
"""

from __future__ import annotations

import json
from typing import Any


def render_world_html(spec: dict[str, Any]) -> str:
    """Return the complete HTML document for the III.36 3D virtual world."""
    spec_json = json.dumps(spec, separators=(",", ":"))
    return HTML_TEMPLATE.replace("__WORLD_SPEC_JSON__", spec_json)


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Elements III.36 · Interactive 3D Area Proof & Spherical Breakdown</title>
<style>
  :root {
    --bg-studio: #0b1418;
    --panel-bg: rgba(13, 25, 30, 0.88);
    --c-circle: #2BA05F;
    --c-tangent: #E4471A;
    --c-secant: #1B6AD1;
    --c-radius: #7A3DB5;
    --c-perp: #C98A00;
    --c-mark: #F2B300;
    --c-hl: #FFE45E;
    --text-main: #F2F6F8;
    --text-muted: #9FB3BD;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body {
    width: 100%; height: 100%; overflow: hidden;
    background: var(--bg-studio);
    font-family: "Optima", "Avenir Next", "Segoe UI", system-ui, sans-serif;
    color: var(--text-main);
    user-select: none;
  }
  #canvas-wrap { position: fixed; inset: 0; }
  canvas#gl { display: block; width: 100%; height: 100%; }

  /* Crisp 3D-projected vertex, triangle, and area tags (zero subtitles!) */
  #labels-layer {
    position: fixed; inset: 0; pointer-events: none; overflow: hidden; z-index: 5;
  }
  .geo-label {
    position: absolute;
    transform: translate(-50%, -50%);
    font-family: "Cambria", "Georgia", serif;
    font-weight: 700;
    font-size: 17px;
    line-height: 1.15;
    padding: 2.5px 7.5px;
    border-radius: 6px;
    background: rgba(11, 20, 24, 0.88);
    border: 1.5px solid rgba(255, 255, 255, 0.24);
    color: #ffffff;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.45);
    white-space: nowrap;
  }
  .geo-label.hl-active {
    border: 2px solid var(--c-hl) !important;
    background: rgba(74, 54, 4, 0.96) !important;
    color: #fff8cc !important;
    box-shadow: 0 0 18px rgba(255, 228, 94, 0.78), 0 4px 12px rgba(0,0,0,0.6) !important;
    transform: translate(-50%, -50%) scale(1.22);
    z-index: 8;
  }
  .geo-label.area-tag {
    font-family: "Avenir Next", "Calibri", sans-serif;
    font-size: 13.5px;
    padding: 4px 9px;
  }
  .geo-label.tri-tag {
    font-family: "Cambria", Georgia, serif;
    font-size: 16px;
    border: 2px solid var(--c-hl);
    background: rgba(68, 48, 4, 0.94);
    color: #fff4b8;
    box-shadow: 0 0 20px rgba(255, 228, 94, 0.65);
  }
  .geo-label.drag-hint-tag {
    font-family: "Avenir Next", sans-serif;
    font-size: 12px;
    font-weight: 800;
    border: 1.5px solid #3df5ff;
    background: rgba(6, 42, 54, 0.94);
    color: #bdfaff;
    box-shadow: 0 0 14px rgba(61, 245, 255, 0.45);
  }
  .geo-label.blue-tag { border-color: #5ea2ff; color: #dbeaff; background: rgba(14, 38, 72, 0.90); }
  .geo-label.red-tag { border-color: #ff7b54; color: #ffe1d8; background: rgba(68, 22, 12, 0.90); }
  .geo-label.gold-tag { border-color: var(--c-mark); color: #ffe799; background: rgba(50, 36, 6, 0.92); }
  .geo-label.green-tag { border-color: #4ce08a; color: #d8ffea; background: rgba(10, 48, 28, 0.90); }

  /* Compact Top-Left Slide Card */
  #slide-hud {
    position: fixed;
    top: 16px; left: 18px;
    width: 376px;
    max-width: calc(100vw - 36px);
    padding: 13px 16px;
    border-radius: 12px;
    background: var(--panel-bg);
    backdrop-filter: blur(12px);
    border: 1px solid rgba(242, 179, 0, 0.28);
    box-shadow: 0 10px 28px rgba(0, 0, 0, 0.46);
    z-index: 10;
  }
  #hud-kicker {
    font-size: 10.5px; font-weight: 800; letter-spacing: 1.5px;
    text-transform: uppercase; color: var(--c-mark);
    margin-bottom: 3px;
  }
  #hud-title {
    font-family: "Cambria", "Georgia", serif;
    font-size: 20px; font-weight: 700; line-height: 1.18;
    margin-bottom: 8px; color: #ffffff;
  }
  #hud-bullets { display: flex; flex-direction: column; gap: 5px; }
  .hud-bullet {
    display: flex; align-items: baseline; gap: 7px;
    padding: 5px 8px;
    border-radius: 7px;
    background: rgba(255, 255, 255, 0.05);
    border-left: 3px solid var(--c-mark);
    font-size: 12.5px; line-height: 1.32; color: #ebf2f5;
  }
  .hud-badge {
    font-size: 9.5px; font-weight: 800; text-transform: uppercase;
    letter-spacing: 0.6px; padding: 2px 5px; border-radius: 4px;
    color: #fff; flex-shrink: 0;
  }

  /* Top-Center Interactive Manipulation Pill (Slide 1 & Slide 4) */
  #interactive-banner {
    display: none;
    position: fixed;
    top: 16px; left: 50%; transform: translateX(-50%);
    padding: 10px 16px;
    border-radius: 12px;
    background: rgba(8, 34, 44, 0.94);
    backdrop-filter: blur(12px);
    border: 1.5px solid #3df5ff;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.55), 0 0 20px rgba(61, 245, 255, 0.22);
    z-index: 14;
    align-items: center; gap: 12px;
    max-width: min(560px, calc(100vw - 780px));
  }
  #interactive-banner.paused-highlight {
    border-color: var(--c-hl);
    box-shadow: 0 10px 32px rgba(0,0,0,0.6), 0 0 24px rgba(255, 228, 94, 0.35);
  }
  #interactive-title {
    font-size: 12.5px; font-weight: 700; color: #e6fcff; line-height: 1.25;
  }
  #interactive-slider {
    width: 135px; accent-color: #3df5ff; cursor: pointer;
  }
  #btn-continue-interactive {
    background: #2BA05F;
    border: 1px solid #57df92;
    color: #fff;
    padding: 6px 12px;
    border-radius: 8px;
    font-size: 12px; font-weight: 800;
    cursor: pointer;
    white-space: nowrap;
  }
  #btn-continue-interactive:hover { background: #34b86f; }

  /* Compact Top-Right Area, Highlight & Dependency Ledger */
  #telemetry-hud {
    position: fixed; top: 16px; right: 18px;
    width: 306px;
    padding: 12px 15px; border-radius: 12px;
    background: var(--panel-bg);
    backdrop-filter: blur(12px);
    border: 1px solid rgba(255, 255, 255, 0.15);
    z-index: 10;
    text-align: right;
  }
  #ledger-mode {
    font-size: 10px; font-weight: 800; letter-spacing: 1.4px;
    text-transform: uppercase; color: var(--c-mark);
  }
  #ledger-equation {
    font-family: "Cambria", Georgia, serif;
    font-size: 17.5px; font-weight: 700; color: #fff; margin-top: 2px;
  }
  #ledger-sub {
    font-size: 12px; color: var(--text-muted); margin-top: 2px;
  }
  #active-cue-badge {
    display: none;
    margin-top: 7px;
    padding: 3px 9px;
    border-radius: 6px;
    background: rgba(255, 228, 94, 0.18);
    border: 1px solid var(--c-hl);
    color: #fff3a8;
    font-size: 11.5px;
    font-weight: 800;
    letter-spacing: 0.4px;
  }
  #dep-pills-row {
    display: none;
    margin-top: 8px; padding-top: 7px;
    border-top: 1px solid rgba(255,255,255,0.12);
    justify-content: flex-end; flex-wrap: wrap; gap: 4px;
  }
  .dep-chip { font-size: 10px; font-weight: 700; padding: 2px 6px; border-radius: 4px; }
  .dep-safe { background: rgba(43, 160, 95, 0.28); border: 1px solid #2BA05F; color: #bdf7d4; }
  .dep-post5 { background: rgba(228, 71, 26, 0.28); border: 1px solid #E4471A; color: #ffd4c7; }

  body.capture-mode #controls-bar,
  body.capture-mode #interactive-banner { display: none !important; }

  /* Sleek Compact Bottom Navigation Bar */
  #controls-bar {
    position: fixed;
    left: 18px; right: 18px; bottom: 12px;
    height: 48px;
    padding: 0 14px;
    border-radius: 11px;
    background: rgba(12, 23, 28, 0.92);
    backdrop-filter: blur(12px);
    border: 1px solid rgba(242, 179, 0, 0.25);
    display: flex; align-items: center; gap: 11px;
    z-index: 15;
  }
  button.ctrl-btn {
    background: rgba(255, 255, 255, 0.08);
    color: #fff;
    border: 1px solid rgba(255, 255, 255, 0.18);
    padding: 6px 11px;
    border-radius: 7px;
    font-size: 12px; font-weight: 700;
    cursor: pointer;
    white-space: nowrap;
  }
  button.ctrl-btn.primary { background: var(--c-tangent); border-color: #ff6e46; }
  .slide-pill {
    padding: 4px 8px; border-radius: 6px; font-size: 11.5px; font-weight: 700;
    background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.14);
    color: var(--text-muted); cursor: pointer;
  }
  .slide-pill.active {
    background: rgba(242, 179, 0, 0.24); border-color: var(--c-mark); color: #fff;
  }
  #slide-pills { display: flex; gap: 4px; }
  .slider-group {
    display: flex; align-items: center; gap: 6px;
    font-size: 11.5px; font-weight: 700; color: #dce8ec;
  }
  input[type="range"] { accent-color: var(--c-mark); cursor: pointer; }
  #timeline-slider { flex: 1; min-width: 80px; }
  #morph-slider { width: 92px; }
  #time-readout {
    font-variant-numeric: tabular-nums; font-size: 11.5px; color: var(--text-muted);
    min-width: 74px; text-align: center;
  }
</style>
</head>
<body>
<div id="canvas-wrap"><canvas id="gl"></canvas></div>
<div id="labels-layer"></div>

<div id="slide-hud">
  <div id="hud-kicker">ELEMENTS III.36</div>
  <div id="hud-title">III.36 · A rectangle equal to a square</div>
  <div id="hud-bullets"></div>
</div>

<div id="interactive-banner">
  <div id="interactive-title">🖱️ Drag Point A along circumference toward B</div>
  <input id="interactive-slider" type="range" min="0" max="1000" value="260" />
  <button id="btn-continue-interactive" style="display:none;">▶ Continue Video</button>
</div>

<div id="telemetry-hud">
  <div id="ledger-mode">EUCLIDEAN PLANE · AREAS</div>
  <div id="ledger-equation">AD·DC = 16.00 = DB²</div>
  <div id="ledger-sub">DB = 4.00 · AD = 7.37 · DC = 2.17</div>
  <div id="active-cue-badge"></div>
  <div id="dep-pills-row">
    <span class="dep-chip dep-safe">III.18 ✓</span>
    <span class="dep-chip dep-safe">III.3 ✓</span>
    <span class="dep-chip dep-safe">I.12 ✓</span>
    <span class="dep-chip dep-post5">Post.5 → I.29 → I.46 → II.6, I.47 ✗</span>
  </div>
</div>

<div id="controls-bar">
  <button id="btn-play" class="ctrl-btn primary">▶ Play Presentation</button>
  <div id="slide-pills"></div>
  <input id="timeline-slider" type="range" min="0" max="1000" value="0" />
  <div id="time-readout">0:00 / 0:00</div>
  <div class="slider-group" title="Bend 2D Euclidean Plane into 3D Spherical Space">
    <span>2D</span>
    <input id="morph-slider" type="range" min="0" max="1000" value="0" />
    <span>3D Sphere</span>
  </div>
  <button id="btn-morph" class="ctrl-btn">✨ 2D→3D Fracture</button>
  <button id="btn-reattach" class="ctrl-btn" style="display:none;">🎥 Guided Cam</button>
</div>

<audio id="voiceover-audio" preload="auto"></audio>

<script type="module">
import * as THREE from '/vendor/three.module.js';

const SPEC = __WORLD_SPEC_JSON__;
const params = new URLSearchParams(window.location.search);
const IS_CAPTURE = params.get('capture') === '1';
if (IS_CAPTURE) document.body.classList.add('capture-mode');

const DEG = Math.PI / 180;
const S2D = SPEC.constants.world_scale_2d; // 0.305 compact scale well above bottom nav
const P = SPEC.plane;

// Secant angle limits from D=(-4,-3): 0 rad is tangent DB, MAX_SECANT_THETA is tangent DG
const MAX_SECANT_THETA = 2 * P.theta_centre_rad; // ~73.7398 deg
// Circumference angle around E=(0,0) for Point A: B is at -90 deg, G is at atan2(G.y, G.x) ~ +163.74 deg
const CIRC_ANGLE_B = -Math.PI / 2;
const CIRC_ANGLE_G = Math.atan2(P.G[1], P.G[0]); // ~ +2.8578 rad (+163.74 deg)
const CIRC_ANGLE_CASE2_A = Math.atan2(P.case2.A[1], P.case2.A[0]);

function smoothstep(t) {
  const c = Math.max(0, Math.min(1, t));
  return c * c * (3 - 2 * c);
}
function clamp01(v) { return Math.max(0, Math.min(1, v)); }
function lerp(a, b, t) { return a + (b - a) * t; }

function euclidToWorld(x, y, liftY = 0.015) {
  return new THREE.Vector3(x * S2D, liftY, -y * S2D);
}
function worldToEuclid(wx, wz) {
  return [wx / S2D, -wz / S2D];
}

function cutLineJS(thetaRad) {
  const clampedTh = Math.max(0.0004, Math.min(MAX_SECANT_THETA - 0.0004, thetaRad));
  const ux = Math.cos(clampedTh), uy = Math.sin(clampedTh);
  const dx = P.E[0] - P.D[0], dy = P.E[1] - P.D[1];
  const fd = dx * ux + dy * uy;
  const fx = P.D[0] + fd * ux, fy = P.D[1] + fd * uy;
  const efSq = Math.max(0, (dx*dx + dy*dy) - fd*fd);
  const ef = Math.sqrt(efSq);
  const hc = Math.sqrt(max0(P.r * P.r - efSq));
  const dc = fd - hc, da = fd + hc;
  return {
    theta: clampedTh,
    C: [P.D[0] + dc * ux, P.D[1] + dc * uy],
    A: [P.D[0] + da * ux, P.D[1] + da * uy],
    F: [fx, fy],
    DC: dc, DA: da, FC: hc, FD: fd, EF: ef
  };
}
function max0(x) { return x > 0 ? x : 0; }

function cutLineFromCircAngleA(phiAroundE) {
  // phiAroundE in [CIRC_ANGLE_B, CIRC_ANGLE_G]
  const clampedPhi = Math.max(CIRC_ANGLE_B + 0.002, Math.min(CIRC_ANGLE_G - 0.02, phiAroundE));
  const ax = P.r * Math.cos(clampedPhi);
  const ay = P.r * Math.sin(clampedPhi);
  const theta = Math.atan2(ay - P.D[1], ax - P.D[0]);
  return cutLineJS(theta);
}

// ---- Three.js Studio Setup --------------------------------------------------
const canvas = document.getElementById('gl');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
renderer.setPixelRatio(IS_CAPTURE ? 1 : Math.min(window.devicePixelRatio || 1, 2));
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.08;

const scene = new THREE.Scene();
scene.background = new THREE.Color(SPEC.colors.studio_bg);

const camera = new THREE.PerspectiveCamera(38, window.innerWidth / window.innerHeight, 0.1, 100);
const camTarget = new THREE.Vector3(0.3, 0, 0.7);

scene.add(new THREE.HemisphereLight('#d6e8f5', '#132026', 1.25));
const keyLight = new THREE.DirectionalLight('#fff6e8', 1.45);
keyLight.position.set(5, 10, 6);
scene.add(keyLight);
const rimLight = new THREE.DirectionalLight('#64a8ff', 0.55);
rimLight.position.set(-6, 5, -5);
scene.add(rimLight);

// Studio Coordinate Platform
const platformGroup = new THREE.Group();
scene.add(platformGroup);
const stageSlabMat = new THREE.MeshStandardMaterial({
  color: '#111e24', roughness: 0.72, metalness: 0.08, transparent: true, opacity: 0.96
});
const stageSlab = new THREE.Mesh(new THREE.BoxGeometry(6.8, 0.05, 4.6), stageSlabMat);
stageSlab.position.set(0.54, -0.035, 0.40);
platformGroup.add(stageSlab);

const stageRim = new THREE.LineSegments(
  new THREE.EdgesGeometry(new THREE.BoxGeometry(6.8, 0.05, 4.6)),
  new THREE.LineBasicMaterial({ color: '#2b444f', transparent: true, opacity: 0.65 })
);
stageRim.position.copy(stageSlab.position);
platformGroup.add(stageRim);

const subtleGrid = new THREE.GridHelper(6.5, 20, '#223842', '#182930');
subtleGrid.position.set(0.54, -0.005, 0.40);
subtleGrid.material.transparent = true;
subtleGrid.material.opacity = 0.42;
platformGroup.add(subtleGrid);

// ---- Euclidean 2D-in-3D Group -----------------------------------------------
const euclidGroup = new THREE.Group();
scene.add(euclidGroup);

function makeTube(parent, colorHex, radius = 0.019, emissiveInt = 0.22) {
  const mat = new THREE.MeshStandardMaterial({
    color: colorHex, emissive: colorHex, emissiveIntensity: emissiveInt,
    roughness: 0.34, metalness: 0.1, transparent: true, opacity: 1.0
  });
  const m = new THREE.Mesh(new THREE.BufferGeometry(), mat);
  m.userData.rad = radius;
  parent.add(m);
  return m;
}
function setTubePts(mesh, pts, closed = false, radOverride = null) {
  if (!pts || pts.length < 2) { mesh.visible = false; return; }
  mesh.visible = true;
  const curve = new THREE.CatmullRomCurve3(pts, closed, 'centripetal', 0.05);
  const rad = radOverride || mesh.userData.rad || 0.019;
  const g = new THREE.TubeGeometry(curve, Math.max(12, pts.length * 2), rad, 12, closed);
  mesh.geometry.dispose();
  mesh.geometry = g;
}

function createAreaSlab(colorHex, withUnitGrid = false) {
  const grp = new THREE.Group();
  const mat = new THREE.MeshStandardMaterial({
    color: colorHex, emissive: colorHex, emissiveIntensity: 0.16,
    roughness: 0.42, metalness: 0.08, transparent: true, opacity: 0.72
  });
  const box = new THREE.Mesh(new THREE.BoxGeometry(1, 0.042, 1), mat);
  const edgeMat = new THREE.LineBasicMaterial({ color: '#ffffff', transparent: true, opacity: 0.65 });
  const edges = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(1, 0.042, 1)), edgeMat);
  const gridLines = new THREE.LineSegments(
    new THREE.BufferGeometry(),
    new THREE.LineBasicMaterial({ color: '#ffffff', transparent: true, opacity: 0.28 })
  );
  gridLines.visible = withUnitGrid;
  grp.add(box, edges, gridLines);
  grp.userData = { box, mat, edges, edgeMat, gridLines, withUnitGrid, lastW: -1, lastH: -1, baseColor: colorHex };
  euclidGroup.add(grp);
  return grp;
}

function updateAreaSlab(grp, x0E, y0E, wE, hE, liftY = 0.024, alpha = 0.72, highlighted = false) {
  if (wE <= 0.001 || hE <= 0.001 || alpha <= 0.01) {
    grp.visible = false;
    return;
  }
  grp.visible = true;
  const wW = wE * S2D, hW = hE * S2D, thick = 0.042;
  grp.position.set((x0E + 0.5 * wE) * S2D, liftY, -(y0E - 0.5 * hE) * S2D);
  const ud = grp.userData;
  ud.box.scale.set(wW, 1, hW);
  ud.mat.opacity = highlighted ? Math.min(0.95, alpha + 0.18) : alpha;
  ud.mat.emissiveIntensity = highlighted ? 0.62 : 0.16;
  ud.edgeMat.color.set(highlighted ? '#FFE45E' : '#ffffff');
  ud.edgeMat.opacity = highlighted ? 1.0 : Math.min(0.85, alpha + 0.15);

  if (Math.abs(ud.lastW - wE) > 0.008 || Math.abs(ud.lastH - hE) > 0.008) {
    ud.lastW = wE; ud.lastH = hE;
    ud.edges.geometry.dispose();
    ud.edges.geometry = new THREE.EdgesGeometry(new THREE.BoxGeometry(wW, thick, hW));
    if (ud.withUnitGrid) {
      const pts = [];
      const topY = thick * 0.5 + 0.003;
      for (let gx = 1; gx < wE - 0.05; gx++) {
        const lx = -0.5 * wW + gx * S2D;
        pts.push(new THREE.Vector3(lx, topY, -0.5 * hW), new THREE.Vector3(lx, topY, 0.5 * hW));
      }
      for (let gy = 1; gy < hE - 0.05; gy++) {
        const lz = -0.5 * hW + gy * S2D;
        pts.push(new THREE.Vector3(-0.5 * wW, topY, lz), new THREE.Vector3(0.5 * wW, topY, lz));
      }
      ud.gridLines.geometry.dispose();
      ud.gridLines.geometry = new THREE.BufferGeometry().setFromPoints(pts);
    }
  }
}

// Circle (E, r=3)
const circleDiscGeo = new THREE.CircleGeometry(P.r * S2D, 96);
circleDiscGeo.rotateX(-Math.PI / 2);
const circleDisc = new THREE.Mesh(
  circleDiscGeo,
  new THREE.MeshBasicMaterial({ color: SPEC.colors.circle, transparent: true, opacity: 0.18 })
);
circleDisc.position.copy(euclidToWorld(0, 0, 0.004));
euclidGroup.add(circleDisc);

const circleRingPts = [];
for (let i = 0; i < 96; i++) {
  const a = (i / 96) * Math.PI * 2;
  circleRingPts.push(euclidToWorld(P.r * Math.cos(a), P.r * Math.sin(a), 0.016));
}
const circleTube = makeTube(euclidGroup, SPEC.colors.circle, 0.020);
setTubePts(circleTube, circleRingPts, true);

const dbTube = makeTube(euclidGroup, SPEC.colors.tangent, 0.023);
const dgTube = makeTube(euclidGroup, SPEC.colors.tangent, 0.021);
const secantFullTube = makeTube(euclidGroup, SPEC.colors.secant, 0.018);
const secantDcHeavy = makeTube(euclidGroup, SPEC.colors.secant, 0.026);
const ebRadiusTube = makeTube(euclidGroup, SPEC.colors.radius, 0.019);
const ecRadiusTube = makeTube(euclidGroup, SPEC.colors.radius, 0.019);
const egRadiusTube = makeTube(euclidGroup, SPEC.colors.radius, 0.018);
const efPerpTube = makeTube(euclidGroup, SPEC.colors.perp, 0.019);
const edLineDashed = new THREE.Line(
  new THREE.BufferGeometry(),
  new THREE.LineDashedMaterial({ color: SPEC.colors.ed_line, dashSize: 0.07, gapSize: 0.05 })
);
euclidGroup.add(edLineDashed);

// Shaded Right Triangle FBD (Case 1)
const triFbdGeo = new THREE.BufferGeometry();
triFbdGeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(9), 3));
const triFbdMesh = new THREE.Mesh(
  triFbdGeo,
  new THREE.MeshBasicMaterial({ color: SPEC.colors.mark, transparent: true, opacity: 0.20, side: THREE.DoubleSide })
);
euclidGroup.add(triFbdMesh);

// Dynamic Spoken Highlight Overlay Meshes (Segments + Active Triangle!)
const hlGroup = new THREE.Group();
scene.add(hlGroup);
const hlSegTubes = [0, 1, 2].map(() => makeTube(hlGroup, '#FFE45E', 0.036, 0.92));
const hlTriGeo = new THREE.BufferGeometry();
hlTriGeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(9), 3));
const hlTriMesh = new THREE.Mesh(
  hlTriGeo,
  new THREE.MeshBasicMaterial({ color: '#FFE45E', transparent: true, opacity: 0.44, side: THREE.DoubleSide, depthWrite: false })
);
hlGroup.add(hlTriMesh);

// Interactive Glowing Drag Handle Ring (placed on A in Slide 1 and F in Slide 4)
const dragRingGeo = new THREE.RingGeometry(0.068, 0.105, 32);
dragRingGeo.rotateX(-Math.PI / 2);
const dragRingMat = new THREE.MeshBasicMaterial({ color: '#3df5ff', side: THREE.DoubleSide, transparent: true, opacity: 0.92 });
const dragRingMesh = new THREE.Mesh(dragRingGeo, dragRingMat);
euclidGroup.add(dragRingMesh);

function makeRightMark() {
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(12), 3));
  g.setIndex([0, 1, 2, 0, 2, 3]);
  const m = new THREE.MeshBasicMaterial({ color: SPEC.colors.mark, transparent: true, opacity: 0.85, side: THREE.DoubleSide });
  const mesh = new THREE.Mesh(g, m);
  euclidGroup.add(mesh);
  return mesh;
}
function setRightMark2D(mesh, vXY, pXY, qXY, sizeE = 0.36) {
  const ux = pXY[0] - vXY[0], uy = pXY[1] - vXY[1];
  const un = Math.hypot(ux, uy) || 1;
  const wx = qXY[0] - vXY[0], wy = qXY[1] - vXY[1];
  const wn = Math.hypot(wx, wy) || 1;
  const u = [sizeE * ux / un, sizeE * uy / un];
  const w = [sizeE * wx / wn, sizeE * wy / wn];
  const pts = [
    euclidToWorld(vXY[0], vXY[1], 0.022),
    euclidToWorld(vXY[0] + u[0], vXY[1] + u[1], 0.022),
    euclidToWorld(vXY[0] + u[0] + w[0], vXY[1] + u[1] + w[1], 0.022),
    euclidToWorld(vXY[0] + w[0], vXY[1] + w[1], 0.022),
  ];
  const arr = mesh.geometry.attributes.position.array;
  pts.forEach((pt, i) => { arr[i*3] = pt.x; arr[i*3+1] = pt.y; arr[i*3+2] = pt.z; });
  mesh.geometry.attributes.position.needsUpdate = true;
}
const rightMarkB = makeRightMark();
const rightMarkF = makeRightMark();
const rightMarkG = makeRightMark();

const fanStaticObjs = P.fan.map(() => ({
  sec: makeTube(euclidGroup, SPEC.colors.secant, 0.009),
  perp: new THREE.Line(
    new THREE.BufferGeometry(),
    new THREE.LineDashedMaterial({ color: SPEC.colors.perp, dashSize: 0.045, gapSize: 0.04, transparent: true, opacity: 0.68 })
  ),
}));
for (const fo of fanStaticObjs) euclidGroup.add(fo.perp);

const euclidDots = {};
for (const k of ['A', 'B', 'C', 'D', 'E', 'F', 'G']) {
  const d = new THREE.Mesh(
    new THREE.SphereGeometry(0.039, 18, 18),
    new THREE.MeshStandardMaterial({ color: '#f5f8fa', emissive: '#000000', roughness: 0.28 })
  );
  euclidGroup.add(d);
  euclidDots[k] = d;
}

const slabSquareDb = createAreaSlab(SPEC.colors.tangent, true);
const slabRectSide = createAreaSlab(SPEC.colors.secant, true);
const slabGnomonStem = createAreaSlab(SPEC.colors.secant, true);
const slabGnomonWing = createAreaSlab(SPEC.colors.secant, true);
const slabFcSquare = createAreaSlab(SPEC.colors.radius, true);
const slabFbSquareRhs = createAreaSlab(SPEC.colors.radius, true);
const slabDbSquareRhs = createAreaSlab(SPEC.colors.tangent, true);
const slabFeSquareLhs = createAreaSlab(SPEC.colors.mark, false);
const slabFeSquareRhs = createAreaSlab(SPEC.colors.mark, false);
const slabFdSquareRhs = createAreaSlab('#466275', false);

// ---- Slide 5: 2D -> 3D Spherical Breakdown Group ----------------------------
const sphereGroup = new THREE.Group();
scene.add(sphereGroup);
const globeCenter = new THREE.Vector3(...SPEC.constants.globe_center_world);
const globeRad = SPEC.constants.sphere_world_radius;

const SGRID = 42;
const morphGeo = new THREE.PlaneGeometry(1, 1, SGRID, SGRID);
const morphMat = new THREE.MeshStandardMaterial({
  color: '#132227', roughness: 0.55, metalness: 0.08, side: THREE.DoubleSide
});
const morphMesh = new THREE.Mesh(morphGeo, morphMat);
sphereGroup.add(morphMesh);

const graticules = [];
const gratMat = new THREE.LineBasicMaterial({ color: '#8aa4c2', transparent: true, opacity: 0 });
for (const lat of [-60, -30, 0, 30, 60]) {
  const pts = [];
  for (let lon = -180; lon <= 180; lon += 4) {
    const la = lat * DEG, lo = lon * DEG;
    pts.push(new THREE.Vector3(Math.cos(la)*Math.sin(lo), Math.sin(la), Math.cos(la)*Math.cos(lo)));
  }
  const ln = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), gratMat);
  sphereGroup.add(ln);
  graticules.push({ line: ln, unitPts: pts });
}
for (let lon = -150; lon <= 180; lon += 30) {
  const pts = [];
  for (let lat = -90; lat <= 90; lat += 4) {
    const la = lat * DEG, lo = lon * DEG;
    pts.push(new THREE.Vector3(Math.cos(la)*Math.sin(lo), Math.sin(la), Math.cos(la)*Math.cos(lo)));
  }
  const ln = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), gratMat);
  sphereGroup.add(ln);
  graticules.push({ line: ln, unitPts: pts });
}

const sphCircleTube = makeTube(sphereGroup, SPEC.colors.circle, 0.019);
const sphSecantTube = makeTube(sphereGroup, SPEC.colors.secant, 0.021);
const sphTangentTube = makeTube(sphereGroup, SPEC.colors.tangent, 0.023);
const sphRadiusEbTube = makeTube(sphereGroup, SPEC.colors.radius, 0.019);
const sphRightMarkB = makeRightMark();
sphereGroup.add(sphRightMarkB);

const sphSqSide2 = makeTube(sphereGroup, SPEC.colors.tangent, 0.017);
const sphSqSide3 = makeTube(sphereGroup, SPEC.colors.tangent, 0.017);
const sphSqSide4 = makeTube(sphereGroup, SPEC.colors.tangent, 0.017);
const sphFractureGapLine = new THREE.Line(
  new THREE.BufferGeometry(),
  new THREE.LineDashedMaterial({ color: '#ffdf4d', dashSize: 0.06, gapSize: 0.045 })
);
sphereGroup.add(sphFractureGapLine);

const sphDots = {};
for (const k of ['E', 'D', 'B', 'C', 'A', 'P3', 'P4']) {
  const col = (k === 'P3' || k === 'P4') ? '#ffdf4d' : '#ffffff';
  const d = new THREE.Mesh(
    new THREE.SphereGeometry(0.039, 16, 16),
    new THREE.MeshStandardMaterial({ color: col, emissive: '#000000' })
  );
  sphereGroup.add(d);
  sphDots[k] = d;
}

const barGroup = new THREE.Group();
barGroup.position.set(2.12, 0.24, 0.0);
sphereGroup.add(barGroup);
barGroup.add(new THREE.Mesh(
  new THREE.BoxGeometry(1.22, 0.05, 0.56),
  new THREE.MeshStandardMaterial({ color: '#1b2d36', roughness: 0.6 })
));
const barProdMesh = new THREE.Mesh(
  new THREE.BoxGeometry(0.34, 1.0, 0.34),
  new THREE.MeshStandardMaterial({ color: SPEC.colors.secant, roughness: 0.35 })
);
const barSqMesh = new THREE.Mesh(
  new THREE.BoxGeometry(0.34, 1.0, 0.34),
  new THREE.MeshStandardMaterial({ color: SPEC.colors.tangent, roughness: 0.35 })
);
barGroup.add(barProdMesh, barSqMesh);

// ---- Projected Labels -------------------------------------------------------
const labelsLayer = document.getElementById('labels-layer');
const labelSpecs = {
  A: { text: 'A', cls: 'geo-label' },
  B: { text: 'B', cls: 'geo-label' },
  C: { text: 'C', cls: 'geo-label' },
  D: { text: 'D', cls: 'geo-label' },
  E: { text: 'E', cls: 'geo-label' },
  F: { text: 'F', cls: 'geo-label' },
  G: { text: 'G', cls: 'geo-label' },
  tagSqDb: { text: 'DB² = 16.00', cls: 'geo-label area-tag red-tag' },
  tagRect: { text: 'AD·DC = 16.00', cls: 'geo-label area-tag blue-tag' },
  tagWorkLhs: { text: 'II.6: AD·DC (16) + FC² (9) = 25', cls: 'geo-label area-tag blue-tag' },
  tagWorkRhs: { text: 'I.47: FB² (9) + DB² (16) = 25', cls: 'geo-label area-tag red-tag' },
  tagFracture: { text: '4th corner splits open! (No squares on sphere)', cls: 'geo-label area-tag gold-tag' },
  tagBarProd: { text: 'AD×DC = 1.22', cls: 'geo-label area-tag blue-tag' },
  tagBarSq: { text: 'DB² = 1.36', cls: 'geo-label area-tag red-tag' },
  tagSphereHold: { text: 'III.18 holds: ∠EBD = 90.0°', cls: 'geo-label area-tag green-tag' },
  tagActiveTri: { text: '△FBD', cls: 'geo-label tri-tag' },
  tagDragHandle: { text: '⇄ Drag A', cls: 'geo-label drag-hint-tag' },
};
const labelItems = {};
for (const [k, def] of Object.entries(labelSpecs)) {
  const el = document.createElement('div');
  el.className = def.cls;
  el.textContent = def.text;
  el.style.display = 'none';
  labelsLayer.appendChild(el);
  labelItems[k] = { el, baseCls: def.cls, pos: new THREE.Vector3(), visible: false };
}
function setLabel(key, vis, worldPos, customText = null, isHighlighted = false) {
  const it = labelItems[key];
  if (!it) return;
  it.visible = vis;
  if (worldPos) it.pos.copy(worldPos);
  if (customText !== null) it.el.textContent = customText;
  it.el.className = isHighlighted ? `${it.baseCls} hl-active` : it.baseCls;
}
function clearAllLabels() {
  for (const it of Object.values(labelItems)) {
    it.visible = false;
    it.el.className = it.baseCls;
  }
}
function projectLabels() {
  const w = window.innerWidth, h = window.innerHeight;
  const v = new THREE.Vector3();
  for (const it of Object.values(labelItems)) {
    if (!it.visible) { it.el.style.display = 'none'; continue; }
    v.copy(it.pos).project(camera);
    if (v.z < -1 || v.z > 1) { it.el.style.display = 'none'; continue; }
    it.el.style.display = 'block';
    it.el.style.left = `${((v.x * 0.5 + 0.5) * w).toFixed(1)}px`;
    it.el.style.top = `${((-v.y * 0.5 + 0.5) * h).toFixed(1)}px`;
  }
}

// ---- Spoken Highlight Cue Lookup --------------------------------------------
const allCues = (SPEC.timeline && SPEC.timeline.highlight_cues) ? SPEC.timeline.highlight_cues : [];

function getActiveHighlightState(tSec, suppressForInteractive) {
  const empty = { label: '', points: new Set(), segments: new Set(), triangles: new Set(), slabs: new Set() };
  if (suppressForInteractive) return empty;
  const labels = [];
  for (const c of allCues) {
    if (tSec >= c.start_s && tSec <= c.end_s) {
      labels.push(c.label);
      c.points.forEach(p => empty.points.add(p));
      c.segments.forEach(s => empty.segments.add(s));
      c.triangles.forEach(tr => empty.triangles.add(tr));
      c.slabs.forEach(sl => empty.slabs.add(sl));
    }
  }
  empty.label = labels[labels.length - 1] || '';
  return empty;
}

// ---- Interactive State (Slide 1 Point A Drag & Slide 4 Line DF Drag) --------
let userCircAngleA = null;        // Custom circumference angle for A on Slide 1
let userSweepThetaDF = null;      // Custom secant angle for DF on Slide 4
let interactiveAutoPausedSegs = new Set(); // Track auto-paused checkpoint IDs
let pausedForInteraction = false;
let activeDragMode = null;        // 'point_a' | 'line_df' | null

// Record world positions of draggable handles for pointer hit-testing
let currentDraggableWorldPos = null;
let currentInteractiveKind = null; // 'drag_point_a' | 'sweep_line_df' | null

// ---- Apply 3D Spoken Highlights on Euclidean Stage --------------------------
function renderEuclideanHighlights(hl, ptMap2D, pulseScale) {
  hlSegTubes.forEach(t => { t.visible = false; });
  hlTriMesh.visible = false;

  const segEndpoints = {
    DB: ['D', 'B'],
    DG: ['D', 'G'],
    AD: ['A', 'D'],
    DC: ['D', 'C'],
    AC: ['A', 'C'],
    FB: ['F', 'B'],
    FC: ['F', 'C'],
    FD: ['F', 'D'],
    EF: ['E', 'F'],
    EC: ['E', 'C'],
    ED: ['E', 'D'],
    EB: ['E', 'B'],
  };

  let tubeIdx = 0;
  for (const segName of hl.segments) {
    if (tubeIdx >= hlSegTubes.length) break;
    const pair = segEndpoints[segName];
    if (!pair) continue;
    const p1 = ptMap2D[pair[0]], p2 = ptMap2D[pair[1]];
    if (!p1 || !p2) continue;
    setTubePts(
      hlSegTubes[tubeIdx],
      [euclidToWorld(p1[0], p1[1], 0.032), euclidToWorld(p2[0], p2[1], 0.032)],
      false,
      0.032 * pulseScale
    );
    tubeIdx++;
  }

  for (const triName of hl.triangles) {
    const a = ptMap2D[triName[0]], b = ptMap2D[triName[1]], c = ptMap2D[triName[2]];
    if (a && b && c) {
      hlTriMesh.visible = true;
      const arr = hlTriGeo.attributes.position.array;
      [euclidToWorld(a[0], a[1], 0.014), euclidToWorld(b[0], b[1], 0.014), euclidToWorld(c[0], c[1], 0.014)]
        .forEach((v, i) => { arr[i*3] = v.x; arr[i*3+1] = v.y; arr[i*3+2] = v.z; });
      hlTriGeo.attributes.position.needsUpdate = true;
      const cx = (a[0] + b[0] + c[0]) / 3, cy = (a[1] + b[1] + c[1]) / 3;
      setLabel('tagActiveTri', true, euclidToWorld(cx, cy, 0.18), `△${triName}`);
    }
  }
}

// ---- Update Euclidean Scene (Slides 1 - 4) ----------------------------------
function updateEuclideanScene(visualMode, segFrac, hl, nowSec) {
  euclidGroup.visible = true;
  sphereGroup.visible = false;
  platformGroup.visible = true;
  stageSlabMat.opacity = 0.96;
  dragRingMesh.visible = false;
  currentDraggableWorldPos = null;
  currentInteractiveKind = null;

  dgTube.visible = false;
  egRadiusTube.visible = false;
  ebRadiusTube.visible = false;
  ecRadiusTube.visible = false;
  efPerpTube.visible = false;
  edLineDashed.visible = false;
  triFbdMesh.visible = false;
  rightMarkB.visible = false;
  rightMarkF.visible = false;
  rightMarkG.visible = false;
  fanStaticObjs.forEach(fo => { fo.sec.visible = false; fo.perp.visible = false; });

  [
    slabSquareDb, slabRectSide, slabGnomonStem, slabGnomonWing,
    slabFcSquare, slabFbSquareRhs, slabDbSquareRhs,
    slabFeSquareLhs, slabFeSquareRhs, slabFdSquareRhs
  ].forEach(s => { s.visible = false; });
  for (const d of Object.values(euclidDots)) {
    d.visible = false;
    d.scale.setScalar(1.0);
    d.material.color.set('#f5f8fa');
    d.material.emissive.set('#000000');
  }

  const pulse = 1.0 + 0.10 * Math.sin(nowSec * 7.5);
  const ptMap2D = { D: P.D, B: P.B, E: P.E, G: P.G };

  const setVertex = (name, xy, labelOffset = [0, 0.38]) => {
    ptMap2D[name] = xy;
    const dot = euclidDots[name];
    dot.visible = true;
    dot.position.copy(euclidToWorld(xy[0], xy[1], 0.025));
    const isHl = hl.points.has(name);
    if (isHl) {
      dot.scale.setScalar(1.55);
      dot.material.color.set('#FFE45E');
      dot.material.emissive.set('#997300');
    }
    setLabel(name, true, euclidToWorld(xy[0] + labelOffset[0], xy[1] + labelOffset[1], 0.13), null, isHl);
  };

  setTubePts(dbTube, [euclidToWorld(P.D[0], P.D[1], 0.020), euclidToWorld(P.B[0], P.B[1], 0.020)]);
  setVertex('D', P.D, [-0.46, 0.16]);
  setVertex('B', P.B, [0.40, -0.24]);

  const ledgerMode = document.getElementById('ledger-mode');
  const ledgerEq = document.getElementById('ledger-equation');
  const ledgerSub = document.getElementById('ledger-sub');
  document.getElementById('dep-pills-row').style.display = 'none';

  // ---- SLIDE 1: THE CLAIM & INTERACTIVE POINT A CIRCUMFERENCE DRAG ----------
  if (visualMode.startsWith('claim')) {
    setVertex('E', P.E, [0.0, 0.44]);
    let activeCut = P.case2;
    let rectX = P.r + 1.4, rectY = P.r, rectLift = 0.024;
    currentInteractiveKind = 'drag_point_a';

    if (userCircAngleA !== null && !IS_CAPTURE) {
      // User is manipulating (or has manipulated) Point A in lieu of canned animation!
      activeCut = cutLineFromCircAngleA(userCircAngleA);
      // When dragged very close to B (within 4 deg), smoothly show proximity to 4x4 square
      if (Math.abs(userCircAngleA - CIRC_ANGLE_B) < 0.06) {
        activeCut = { C: [...P.B], A: [...P.B], F: [...P.B], DC: 4.0, DA: 4.0, FC: 0, FD: 4.0, EF: 3.0 };
      }
    } else if (visualMode === 'claim_morph_overlay') {
      const sweepT = smoothstep(clamp01(segFrac / 0.58));
      const slideT = smoothstep(clamp01((segFrac - 0.58) / 0.42));
      const th = lerp(P.theta_case2_rad, 0.0005, sweepT);
      activeCut = cutLineJS(th);
      rectX = lerp(P.r + 1.4, P.D[0], slideT);
      rectY = lerp(P.r, P.D[1], slideT);
      rectLift = lerp(0.024, 0.072, Math.sin(slideT * Math.PI)) + 0.028 * slideT;
    }

    setTubePts(secantFullTube, [euclidToWorld(P.D[0], P.D[1], 0.018), euclidToWorld(activeCut.A[0], activeCut.A[1], 0.018)]);
    setTubePts(secantDcHeavy, [euclidToWorld(P.D[0], P.D[1], 0.022), euclidToWorld(activeCut.C[0], activeCut.C[1], 0.022)]);
    setVertex('C', activeCut.C, [-0.15, 0.44]);
    setVertex('A', activeCut.A, [0.42, 0.26]);

    if (!IS_CAPTURE) {
      const aWorld = euclidToWorld(activeCut.A[0], activeCut.A[1], 0.028);
      dragRingMesh.visible = true;
      dragRingMesh.position.copy(aWorld);
      dragRingMesh.scale.setScalar(pulse);
      currentDraggableWorldPos = aWorld;
      setLabel('tagDragHandle', true, euclidToWorld(activeCut.A[0] + 0.55, activeCut.A[1] - 0.35, 0.14), '⇄ Drag A');
    }

    const showSlabs = visualMode !== 'claim_setup' || segFrac > 0.32 || userCircAngleA !== null;
    const slabAlpha = (visualMode === 'claim_setup' && userCircAngleA === null)
      ? smoothstep((segFrac - 0.32) / 0.5) * 0.72 : 0.74;
    if (showSlabs) {
      updateAreaSlab(slabSquareDb, P.D[0], P.D[1], P.DB, P.DB, 0.022, slabAlpha, hl.slabs.has('sqDB'));
      updateAreaSlab(slabRectSide, rectX, rectY, activeCut.DC, activeCut.DA, rectLift, slabAlpha, hl.slabs.has('rectADDC'));
      setLabel('tagSqDb', true, euclidToWorld(P.D[0] + 2.0, P.D[1] - 2.0, 0.12), 'Square DB² = 16.00', hl.slabs.has('sqDB'));
      setLabel(
        'tagRect', true,
        euclidToWorld(rectX + 0.5 * activeCut.DC, rectY - 0.5 * activeCut.DA, rectLift + 0.12),
        `AD·DC = ${activeCut.DA.toFixed(2)} × ${activeCut.DC.toFixed(2)} = 16.00`,
        hl.slabs.has('rectADDC')
      );
    }

    renderEuclideanHighlights(hl, ptMap2D, pulse);
    ledgerMode.textContent = 'SLIDE 1 · AREA EQUIVALENCE';
    ledgerEq.textContent = 'AD·DC = 16.00 = DB²';
    ledgerSub.textContent = `AD = ${activeCut.DA.toFixed(2)} · DC = ${activeCut.DC.toFixed(2)} · DB = 4.00`;
    return;
  }

  // ---- SLIDE 2: CASE 1 (THROUGH CENTRE F) -----------------------------------
  if (visualMode.startsWith('case1')) {
    const c1 = P.case1;
    setTubePts(secantFullTube, [euclidToWorld(P.D[0], P.D[1], 0.018), euclidToWorld(c1.A[0], c1.A[1], 0.018)]);
    setTubePts(secantDcHeavy, [euclidToWorld(P.D[0], P.D[1], 0.022), euclidToWorld(c1.C[0], c1.C[1], 0.022)]);
    setTubePts(ebRadiusTube, [euclidToWorld(0, 0, 0.020), euclidToWorld(P.B[0], P.B[1], 0.020)]);
    setTubePts(ecRadiusTube, [euclidToWorld(0, 0, 0.020), euclidToWorld(c1.C[0], c1.C[1], 0.020)]);
    rightMarkB.visible = true;
    setRightMark2D(rightMarkB, P.B, [0, 0], P.D);

    triFbdMesh.visible = true;
    const tArr = triFbdGeo.attributes.position.array;
    [euclidToWorld(0, 0, 0.008), euclidToWorld(P.B[0], P.B[1], 0.008), euclidToWorld(P.D[0], P.D[1], 0.008)]
      .forEach((pt, i) => { tArr[i*3] = pt.x; tArr[i*3+1] = pt.y; tArr[i*3+2] = pt.z; });
    triFbdGeo.attributes.position.needsUpdate = true;

    setVertex('F', [0, 0], [-0.25, 0.45]);
    setVertex('C', c1.C, [-0.05, -0.45]);
    setVertex('A', c1.A, [0.40, 0.28]);

    const wx = 3.8, wy = 2.6;
    const hlGnomon = hl.slabs.has('gnomon') || hl.slabs.has('rectADDC');
    if (visualMode === 'case1_gnomon') {
      const foldT = smoothstep(clamp01((segFrac - 0.15) / 0.65));
      updateAreaSlab(slabGnomonStem, wx, wy, 2.0, 5.0, 0.024, 0.78, hlGnomon);
      const wingX = lerp(wx, wx + 2.0, foldT);
      const wingY = lerp(wy - 5.0, wy, foldT);
      const wingW = lerp(2.0, 3.0, foldT);
      const wingH = lerp(3.0, 2.0, foldT);
      updateAreaSlab(slabGnomonWing, wingX, wingY, wingW, wingH, 0.028, 0.78, hlGnomon);
      updateAreaSlab(slabFcSquare, wx + 2.0, wy - 2.0, 3.0, 3.0, 0.024, smoothstep(segFrac * 1.6) * 0.78, hl.slabs.has('sqFC'));
      setLabel('tagWorkLhs', true, euclidToWorld(wx + 2.5, wy + 0.65, 0.12), 'II.6: AD·DC (16) + FC² (9) = FD² (25)', hl.slabs.has('sqFD'));
    } else if (visualMode === 'case1_cancel') {
      const cancelT = smoothstep(clamp01((segFrac - 0.38) / 0.52));
      const liftCancel = 0.024 + cancelT * 1.05;
      const alphaCancel = 0.78 * (1 - cancelT);

      updateAreaSlab(slabGnomonStem, 3.6, 3.0, 2.0, 5.0, 0.024, 0.78, hlGnomon);
      updateAreaSlab(slabGnomonWing, 5.6, 3.0, 3.0, 2.0, 0.024, 0.78, hlGnomon);
      updateAreaSlab(slabFcSquare, 5.6, 1.0, 3.0, 3.0, liftCancel, alphaCancel, hl.slabs.has('sqFC'));

      updateAreaSlab(slabDbSquareRhs, 3.6, -2.5, 4.0, 4.0, 0.024, 0.78, hl.slabs.has('sqDB'));
      updateAreaSlab(slabFbSquareRhs, 7.6, -2.5, 3.0, 3.0, liftCancel, alphaCancel, hl.slabs.has('sqFB'));

      setLabel('tagWorkLhs', true, euclidToWorld(6.1, 3.55, 0.12),
        cancelT > 0.7 ? 'Remaining Blue Area: AD·DC = 16' : 'FD² (25) = AD·DC (16) + FC² (9)');
      setLabel('tagWorkRhs', true, euclidToWorld(6.5, -1.95, 0.12),
        cancelT > 0.7 ? 'Remaining Square: DB² = 16' : 'FD² (25) = DB² (16) + FB² (9)');
    }

    renderEuclideanHighlights(hl, ptMap2D, pulse);
    ledgerMode.textContent = 'CASE 1 · II.6 + I.47';
    ledgerEq.textContent = '16 + 3² = 5² = 4² + 3²';
    ledgerSub.textContent = 'Subtract FC² = FB² = 9 → AD·DC = DB²';
    return;
  }

  // ---- SLIDE 3: CASE 2 (GENERAL LINE + ADDING FE^2) -------------------------
  if (visualMode.startsWith('case2')) {
    const c2 = P.case2;
    setTubePts(secantFullTube, [euclidToWorld(P.D[0], P.D[1], 0.018), euclidToWorld(c2.A[0], c2.A[1], 0.018)]);
    setTubePts(secantDcHeavy, [euclidToWorld(P.D[0], P.D[1], 0.022), euclidToWorld(c2.C[0], c2.C[1], 0.022)]);
    setTubePts(efPerpTube, [euclidToWorld(0, 0, 0.020), euclidToWorld(c2.F[0], c2.F[1], 0.020)]);
    setTubePts(ebRadiusTube, [euclidToWorld(0, 0, 0.020), euclidToWorld(P.B[0], P.B[1], 0.020)]);
    setTubePts(ecRadiusTube, [euclidToWorld(0, 0, 0.020), euclidToWorld(c2.C[0], c2.C[1], 0.020)]);

    edLineDashed.visible = true;
    edLineDashed.geometry.dispose();
    edLineDashed.geometry = new THREE.BufferGeometry().setFromPoints([
      euclidToWorld(0, 0, 0.023), euclidToWorld(P.D[0], P.D[1], 0.023)
    ]);
    edLineDashed.computeLineDistances();

    rightMarkB.visible = true; setRightMark2D(rightMarkB, P.B, [0, 0], P.D);
    rightMarkF.visible = true; setRightMark2D(rightMarkF, c2.F, [0, 0], c2.A, 0.32);

    setVertex('E', [0, 0], [-0.25, 0.44]);
    setVertex('F', c2.F, [0.24, -0.45]);
    setVertex('C', c2.C, [-0.25, -0.44]);
    setVertex('A', c2.A, [0.40, 0.25]);

    if (visualMode === 'case2_drop_perp') {
      updateAreaSlab(slabRectSide, 3.8, 2.8, c2.DC, c2.DA, 0.024, 0.76, hl.slabs.has('rectADDC'));
      updateAreaSlab(slabFcSquare, 6.3, 2.8, c2.FC, c2.FC, 0.024, 0.72, hl.slabs.has('sqFC'));
      updateAreaSlab(slabFdSquareRhs, 6.3, -0.6, c2.FD, c2.FD, 0.024, 0.68, hl.slabs.has('sqFD'));
      setLabel('tagWorkLhs', true, euclidToWorld(6.4, 3.35, 0.12), 'II.6: AD·DC (16.00) + FC² (6.75)');
      setLabel('tagWorkRhs', true, euclidToWorld(8.6, -0.1, 0.12), '= FD² (22.75)');
    } else if (visualMode === 'case2_add_fe2') {
      const dropT = smoothstep(clamp01(segFrac * 1.5));
      const dropLift = lerp(0.85, 0.024, dropT);
      updateAreaSlab(slabRectSide, 3.8, 2.8, c2.DC, c2.DA, 0.024, 0.76, hl.slabs.has('rectADDC'));
      updateAreaSlab(slabFcSquare, 6.3, 2.8, c2.FC, c2.FC, 0.024, 0.72, hl.slabs.has('sqFC'));
      updateAreaSlab(slabFeSquareLhs, 9.1, 2.8, c2.EF, c2.EF, dropLift, 0.85, hl.slabs.has('sqFE'));

      updateAreaSlab(slabFdSquareRhs, 6.3, -0.6, c2.FD, c2.FD, 0.024, 0.68, hl.slabs.has('sqFD'));
      updateAreaSlab(slabFeSquareRhs, 11.2, -0.6, c2.EF, c2.EF, dropLift, 0.85, hl.slabs.has('sqFE'));

      setLabel('tagWorkLhs', true, euclidToWorld(7.2, 3.35, 0.12), 'FC² (6.75) + FE² (2.25) = EC² (9.00)');
      setLabel('tagWorkRhs', true, euclidToWorld(8.8, -0.05, 0.12), 'FD² (22.75) + FE² (2.25) = ED² (25.00)');
    } else if (visualMode === 'case2_cancel') {
      const cancelT = smoothstep(clamp01((segFrac - 0.35) / 0.55));
      const liftR = 0.024 + cancelT * 1.0;
      const alphaR = 0.78 * (1 - cancelT);
      updateAreaSlab(slabRectSide, 3.8, 2.8, c2.DC, c2.DA, 0.024, 0.78, hl.slabs.has('rectADDC'));
      updateAreaSlab(slabFcSquare, 6.4, 2.8, 3.0, 3.0, liftR, alphaR, hl.slabs.has('sqFC'));

      updateAreaSlab(slabDbSquareRhs, 3.8, -2.6, 4.0, 4.0, 0.024, 0.78, hl.slabs.has('sqDB'));
      updateAreaSlab(slabFbSquareRhs, 8.1, -2.6, 3.0, 3.0, liftR, alphaR, hl.slabs.has('sqFB'));

      setLabel('tagWorkLhs', true, euclidToWorld(6.4, 3.35, 0.12),
        cancelT > 0.7 ? 'AD·DC = 16.00' : 'AD·DC (16) + EC² (9) = ED² (25)');
      setLabel('tagWorkRhs', true, euclidToWorld(6.8, -2.05, 0.12),
        cancelT > 0.7 ? 'DB² = 16.00' : 'DB² (16) + EB² (9) = ED² (25)');
    }

    renderEuclideanHighlights(hl, ptMap2D, pulse);
    ledgerMode.textContent = 'CASE 2 · ADD FE² BRIDGE';
    ledgerEq.textContent = 'AD·DC + EC² = ED² = DB² + EB²';
    ledgerSub.textContent = 'FC² + FE² = 6.75 + 2.25 = 9.00 (r²)';
    return;
  }

  // ---- SLIDE 4: INTERACTIVE SWEEP OF LINE DF ACROSS CIRCLE ------------------
  currentInteractiveKind = 'sweep_line_df';
  setTubePts(dgTube, [euclidToWorld(P.D[0], P.D[1], 0.020), euclidToWorld(P.G[0], P.G[1], 0.020)]);
  setTubePts(ebRadiusTube, [euclidToWorld(0, 0, 0.018), euclidToWorld(P.B[0], P.B[1], 0.018)]);
  setTubePts(egRadiusTube, [euclidToWorld(0, 0, 0.018), euclidToWorld(P.G[0], P.G[1], 0.018)]);
  rightMarkB.visible = true; setRightMark2D(rightMarkB, P.B, [0, 0], P.D);
  rightMarkG.visible = true; setRightMark2D(rightMarkG, P.G, [0, 0], P.D);

  edLineDashed.visible = true;
  edLineDashed.geometry.dispose();
  edLineDashed.geometry = new THREE.BufferGeometry().setFromPoints([
    euclidToWorld(0, 0, 0.023), euclidToWorld(P.D[0], P.D[1], 0.023)
  ]);
  edLineDashed.computeLineDistances();

  P.fan.forEach((fItem, idx) => {
    const fo = fanStaticObjs[idx];
    setTubePts(fo.sec, [euclidToWorld(P.D[0], P.D[1], 0.012), euclidToWorld(fItem.A[0], fItem.A[1], 0.012)], false, 0.009);
    if (fItem.EF > 1e-4) {
      fo.perp.visible = true;
      fo.perp.geometry.dispose();
      fo.perp.geometry = new THREE.BufferGeometry().setFromPoints([
        euclidToWorld(0, 0, 0.014), euclidToWorld(fItem.F[0], fItem.F[1], 0.014)
      ]);
      fo.perp.computeLineDistances();
    }
  });

  let sweepTheta;
  if (userSweepThetaDF !== null && !IS_CAPTURE) {
    sweepTheta = userSweepThetaDF;
  } else {
    const osc = 0.5 - 0.5 * Math.cos(segFrac * Math.PI * 2);
    sweepTheta = lerp(6 * DEG, 67 * DEG, visualMode === 'fan_sweep' ? osc : 0.28);
  }
  const liveCut = cutLineJS(sweepTheta);
  setTubePts(secantFullTube, [euclidToWorld(P.D[0], P.D[1], 0.022), euclidToWorld(liveCut.A[0], liveCut.A[1], 0.022)]);
  setTubePts(secantDcHeavy, [euclidToWorld(P.D[0], P.D[1], 0.026), euclidToWorld(liveCut.C[0], liveCut.C[1], 0.026)]);
  ptMap2D.C = liveCut.C;
  ptMap2D.A = liveCut.A;
  ptMap2D.F = liveCut.F;

  if (liveCut.EF > 0.04) {
    setTubePts(efPerpTube, [euclidToWorld(0, 0, 0.022), euclidToWorld(liveCut.F[0], liveCut.F[1], 0.022)]);
    setVertex('F', liveCut.F, [0.24, -0.38]);
  } else {
    setVertex('F', liveCut.F, [-0.32, -0.38]);
  }
  setVertex('E', [0, 0], [0.28, 0.36]);
  setVertex('G', P.G, [-0.25, 0.44]);

  if (!IS_CAPTURE) {
    const fWorld = euclidToWorld(liveCut.F[0], liveCut.F[1], 0.028);
    dragRingMesh.visible = true;
    dragRingMesh.position.copy(fWorld);
    dragRingMesh.scale.setScalar(pulse);
    currentDraggableWorldPos = fWorld;
    setLabel('tagDragHandle', true, euclidToWorld(liveCut.F[0] + 0.58, liveCut.F[1] + 0.32, 0.14), '↕ Drag DF');
  }

  updateAreaSlab(slabSquareDb, P.D[0], P.D[1], P.DB, P.DB, 0.022, 0.72, hl.slabs.has('sqDB'));
  updateAreaSlab(slabRectSide, 4.3, 3.0, liveCut.DC, liveCut.DA, 0.024, 0.78, hl.slabs.has('rectADDC'));
  setLabel('tagSqDb', true, euclidToWorld(P.D[0] + 2.0, P.D[1] - 2.0, 0.12), 'DB² = 16.00', hl.slabs.has('sqDB'));
  setLabel(
    'tagRect', true,
    euclidToWorld(4.3 + 0.5 * liveCut.DC, 3.0 - 0.5 * liveCut.DA, 0.12),
    `${liveCut.DA.toFixed(2)} × ${liveCut.DC.toFixed(2)} = 16.00`,
    hl.slabs.has('rectADDC')
  );

  renderEuclideanHighlights(hl, ptMap2D, pulse);
  ledgerMode.textContent = 'POWER OF POINT D · INVARIANT';
  ledgerEq.textContent = 'AD·DC = ED² − r² = 16.00';
  ledgerSub.textContent = `EF = ${liveCut.EF.toFixed(2)} · AD·DC = ${(liveCut.DA * liveCut.DC).toFixed(2)}`;
}

// ---- Update Slide 5: 2D -> 3D Spherical Breakdown Scene ---------------------
const colStage = new THREE.Color('#132227');
const colGlobe = new THREE.Color('#dce8f5');

function geoStepUnit(pU, tU, ang) {
  const ca = Math.cos(ang), sa = Math.sin(ang);
  const np = pU.clone().multiplyScalar(ca).addScaledVector(tU, sa).normalize();
  const nt = tU.clone().multiplyScalar(ca).addScaledVector(pU, -sa).normalize();
  return [np, nt];
}

function updateSphericalScene(tau, visualMode, hl, nowSec) {
  const s = smoothstep(tau);
  euclidGroup.visible = false;
  sphereGroup.visible = true;
  platformGroup.visible = s < 0.12;
  stageSlabMat.opacity = Math.max(0, 0.95 * (1 - s * 8.5));
  hlSegTubes.forEach(t => { t.visible = false; });
  hlTriMesh.visible = false;
  currentDraggableWorldPos = null;
  currentInteractiveKind = null;

  document.getElementById('dep-pills-row').style.display = 'flex';

  const kappa = Math.max(1e-4, s / globeRad);
  const curRad = 1 / kappa;
  const topAnchor = new THREE.Vector3(0.16, 0, 0).lerp(
    globeCenter.clone().add(new THREE.Vector3(0, 0, globeRad)), s
  );
  const nFront = new THREE.Vector3(0, 1, 0).lerp(new THREE.Vector3(0, 0, 1), s).normalize();
  const eRight = new THREE.Vector3(1, 0, 0);
  const eUp = new THREE.Vector3().crossVectors(nFront, eRight).normalize();
  const curCenter = topAnchor.clone().addScaledVector(nFront, -curRad);

  const halfExt = (1 - s) * 2.2 + s * (Math.PI * globeRad);
  const posAttr = morphGeo.attributes.position;
  for (let iy = 0; iy <= SGRID; iy++) {
    const vy = (0.5 - iy / SGRID) * 2 * halfExt;
    for (let ix = 0; ix <= SGRID; ix++) {
      const vx = (ix / SGRID - 0.5) * 2 * halfExt;
      const rho = Math.hypot(vx, vy);
      const idx = iy * (SGRID + 1) + ix;
      if (rho < 1e-7) {
        posAttr.setXYZ(idx, topAnchor.x, topAnchor.y, topAnchor.z);
      } else {
        const psi = Math.min(Math.PI, kappa * rho);
        const dirT = eRight.clone().multiplyScalar(vx / rho).addScaledVector(eUp, vy / rho);
        const u = nFront.clone().multiplyScalar(Math.cos(psi)).addScaledVector(dirT, Math.sin(psi));
        const p = curCenter.clone().addScaledVector(u, curRad - 0.008);
        posAttr.setXYZ(idx, p.x, p.y, p.z);
      }
    }
  }
  posAttr.needsUpdate = true;
  morphGeo.computeVertexNormals();
  morphMat.color.copy(colStage).lerp(colGlobe, s);

  gratMat.opacity = clamp01((s - 0.35) / 0.65) * 0.52;
  graticules.forEach(g => {
    g.line.visible = gratMat.opacity > 0.01;
    if (g.line.visible) {
      g.line.geometry.setFromPoints(g.unitPts.map(u => curCenter.clone().addScaledVector(u, curRad + 0.002)));
    }
  });

  const alphaR = Math.max(0.02, s * 30 * DEG + (1 - s) * (3.0 * S2D / curRad));
  const ratioDR = lerp(5 / 3, 7 / 3, s);
  const alphaD = ratioDR * alphaR;
  const alphaDC = alphaD - alphaR;
  const alphaDA = alphaD + alphaR;
  const alphaDB = Math.acos(Math.max(-1, Math.min(1, Math.cos(alphaD) / Math.cos(alphaR))));

  const mapU = (ux, uy, uz) => {
    const yaw = 26 * DEG * s;
    const x1 = ux * Math.cos(yaw) + uz * Math.sin(yaw);
    const z1 = -ux * Math.sin(yaw) + uz * Math.cos(yaw);
    const pitchLift = 34 * DEG * s;
    const y2 = uy * Math.cos(pitchLift) + z1 * Math.sin(pitchLift);
    const z2 = -uy * Math.sin(pitchLift) + z1 * Math.cos(pitchLift);
    return eRight.clone().multiplyScalar(x1)
      .addScaledVector(eUp, y2)
      .addScaledVector(nFront, z2)
      .normalize();
  };

  const uE = mapU(0, 0, 1);
  const uD = mapU(-Math.sin(alphaD), 0, Math.cos(alphaD));
  const uC = mapU(-Math.sin(alphaR), 0, Math.cos(alphaR));
  const uA = mapU(Math.sin(alphaR), 0, Math.cos(alphaR));
  const bz = Math.cos(alphaR);
  const bx = (Math.cos(alphaD) * bz - Math.cos(alphaDB)) / mathSinSafe(alphaD);
  const by = -Math.sqrt(Math.max(0, 1 - bx*bx - bz*bz));
  const uB = mapU(bx, by, bz);

  const surfR = curRad + 0.013;
  const onSurf = (u, extra = 0) => curCenter.clone().addScaledVector(u, surfR + extra);

  const circPts = [];
  const t1 = uE.clone().cross(new THREE.Vector3(0, 1, 0)).lengthSq() > 0.01
    ? uE.clone().cross(new THREE.Vector3(0, 1, 0)).normalize()
    : uE.clone().cross(new THREE.Vector3(1, 0, 0)).normalize();
  const t2 = new THREE.Vector3().crossVectors(uE, t1).normalize();
  for (let i = 0; i < 84; i++) {
    const a = (i / 84) * Math.PI * 2;
    const ringDir = t1.clone().multiplyScalar(Math.cos(a)).addScaledVector(t2, Math.sin(a));
    const u = uE.clone().multiplyScalar(Math.cos(alphaR)).addScaledVector(ringDir, Math.sin(alphaR));
    circPts.push(onSurf(u));
  }
  setTubePts(sphCircleTube, circPts, true, 0.018);

  const buildArcCur = (ua, ub, steps = 32, extra = 0) => {
    const om = Math.acos(Math.max(-1, Math.min(1, ua.dot(ub))));
    if (om < 1e-5) return [onSurf(ua, extra), onSurf(ub, extra)];
    const so = Math.sin(om);
    const pts = [];
    for (let i = 0; i <= steps; i++) {
      const f = i / steps;
      const u = ua.clone().multiplyScalar(Math.sin((1 - f)*om)/so).addScaledVector(ub, Math.sin(f*om)/so);
      pts.push(onSurf(u, extra));
    }
    return pts;
  };
  setTubePts(sphSecantTube, buildArcCur(uD, uA, 40), false, 0.020);
  setTubePts(sphTangentTube, buildArcCur(uD, uB, 32), false, 0.022);
  setTubePts(sphRadiusEbTube, buildArcCur(uE, uB, 24), false, 0.018);

  // Highlight spoken geodesic arcs on the 3D sphere too!
  const sphArcMap = {
    EB: [uE, uB], DB: [uD, uB], ED: [uE, uD], AD: [uD, uA], DC: [uD, uC]
  };
  let hIdx = 0;
  const pulse = 1.0 + 0.10 * Math.sin(nowSec * 7.5);
  for (const sName of hl.segments) {
    if (hIdx >= hlSegTubes.length) break;
    const pair = sphArcMap[sName];
    if (pair) {
      setTubePts(hlSegTubes[hIdx], buildArcCur(pair[0], pair[1], 28, 0.008), false, 0.032 * pulse);
      hIdx++;
    }
  }

  sphRightMarkB.visible = true;
  const tBE = uE.clone().addScaledVector(uB, -uE.dot(uB)).normalize();
  const tBD = uD.clone().addScaledVector(uB, -uD.dot(uB)).normalize();
  const bSurf = onSurf(uB, 0.008);
  const sqSz = 0.115;
  const rArr = sphRightMarkB.geometry.attributes.position.array;
  [
    bSurf,
    bSurf.clone().addScaledVector(tBE, sqSz),
    bSurf.clone().addScaledVector(tBE, sqSz).addScaledVector(tBD, sqSz),
    bSurf.clone().addScaledVector(tBD, sqSz)
  ].forEach((pt, i) => { rArr[i*3] = pt.x; rArr[i*3+1] = pt.y; rArr[i*3+2] = pt.z; });
  sphRightMarkB.geometry.attributes.position.needsUpdate = true;

  const outB = tBE.clone().negate();
  const [uP2, tEnd2] = geoStepUnit(uB, outB, alphaDB);
  let turnP2 = new THREE.Vector3().crossVectors(uP2, tEnd2).normalize();
  if (turnP2.dot(uD) < turnP2.clone().negate().dot(uD)) turnP2.negate();
  const [uP3] = geoStepUnit(uP2, turnP2, alphaDB);

  const tDB_at_D = uB.clone().addScaledVector(uD, -uB.dot(uD)).normalize();
  let outD = new THREE.Vector3().crossVectors(tDB_at_D, uD).normalize();
  if (outD.dot(outB) < 0) outD.negate();
  const [uP4] = geoStepUnit(uD, outD, alphaDB);

  setTubePts(sphSqSide2, buildArcCur(uB, uP2, 28), false, 0.016);
  setTubePts(sphSqSide3, buildArcCur(uP2, uP3, 28), false, 0.016);
  setTubePts(sphSqSide4, buildArcCur(uD, uP4, 28), false, 0.016);

  sphFractureGapLine.visible = s > 0.15;
  if (sphFractureGapLine.visible) {
    sphFractureGapLine.geometry.dispose();
    sphFractureGapLine.geometry = new THREE.BufferGeometry().setFromPoints([onSurf(uP3), onSurf(uP4)]);
    sphFractureGapLine.computeLineDistances();
  }

  const mapDots = { E: uE, D: uD, B: uB, C: uC, A: uA, P3: uP3, P4: uP4 };
  for (const [k, u] of Object.entries(mapDots)) {
    const d = sphDots[k];
    d.visible = (k !== 'P3' && k !== 'P4') || s > 0.15;
    d.position.copy(onSurf(u));
    const isHl = hl.points.has(k);
    d.scale.setScalar(isHl ? 1.55 : 1.0);
    d.material.color.set(isHl ? '#FFE45E' : ((k === 'P3' || k === 'P4') ? '#ffdf4d' : '#ffffff'));
  }
  ['D', 'B', 'C', 'A', 'E'].forEach(k => {
    setLabel(k, true, onSurf(mapDots[k], 0.13), null, hl.points.has(k));
  });

  if (s > 0.75) {
    setLabel('tagSphereHold', true, onSurf(uB, 0.18).add(new THREE.Vector3(0.30, 0.10, 0)));
  }
  if (s > 0.45 && (visualMode === 'sphere_broken_square' || visualMode === 'sphere_product_mismatch')) {
    const midGap = onSurf(uP3).lerp(onSurf(uP4), 0.5).add(new THREE.Vector3(0, -0.15, 0.15));
    setLabel('tagFracture', true, midGap);
  }

  const rEff = lerp(3.0 / alphaR, 1.0, s);
  const prodVal = (rEff * alphaDA) * (rEff * alphaDC);
  const sqVal = (rEff * alphaDB) ** 2;
  const maxRef = Math.max(prodVal, sqVal, 0.1);
  const hProd = 1.25 * (prodVal / maxRef);
  const hSq = 1.25 * (sqVal / maxRef);

  barGroup.visible = s > 0.35;
  if (barGroup.visible) {
    barProdMesh.scale.y = hProd;
    barProdMesh.position.set(-0.25, 0.025 + 0.5 * hProd, 0);
    barSqMesh.scale.y = hSq;
    barSqMesh.position.set(0.25, 0.025 + 0.5 * hSq, 0);

    const wProdTop = barGroup.position.clone().add(new THREE.Vector3(-0.28, 0.16 + hProd, 0));
    const wSqTop = barGroup.position.clone().add(new THREE.Vector3(0.28, 0.16 + hSq, 0));
    setLabel('tagBarProd', true, wProdTop, `AD×DC = ${prodVal.toFixed(2)}`, hl.segments.has('AD') || hl.segments.has('DC'));
    setLabel('tagBarSq', true, wSqTop, `DB² = ${sqVal.toFixed(2)}`, hl.segments.has('DB'));
  }

  const ledgerMode = document.getElementById('ledger-mode');
  const ledgerEq = document.getElementById('ledger-equation');
  const ledgerSub = document.getElementById('ledger-sub');
  if (s < 0.95) {
    ledgerMode.textContent = `CURVATURE MORPH · ${(s * 100).toFixed(0)}%`;
    ledgerEq.textContent = `AD×DC (${prodVal.toFixed(2)}) ≠ DB² (${sqVal.toFixed(2)})`;
    ledgerSub.textContent = 'Squares split open as Postulate 5 fails';
  } else {
    ledgerMode.textContent = '3D SPHERE (R = 30°, ED = 70°)';
    ledgerEq.textContent = 'AD×DC = 1.22 ≠ DB² = 1.36';
    ledgerSub.textContent = 'tan(AD/2)·tan(DC/2) = tan²(DB/2) = 0.434';
  }
}
function mathSinSafe(a) { return Math.abs(Math.sin(a)) < 1e-6 ? 1e-6 : Math.sin(a); }

// ---- Slide HUD & Timeline Choreography --------------------------------------
let activeSlide = -1;
function updateSlideCard(slideNumber) {
  if (slideNumber === activeSlide) return;
  activeSlide = slideNumber;
  const sl = SPEC.slides.find(x => x.slide_number === slideNumber) || SPEC.slides[0];
  document.getElementById('hud-kicker').textContent = sl.kicker;
  document.getElementById('hud-title').textContent = sl.title;

  const wrap = document.getElementById('hud-bullets');
  wrap.innerHTML = '';
  for (const b of sl.bullets) {
    const d = document.createElement('div');
    d.className = 'hud-bullet';
    d.style.borderLeftColor = b.badge_color;
    d.innerHTML = `<span class="hud-badge" style="background:${b.badge_color}">${b.badge}</span><span>${b.text}</span>`;
    wrap.appendChild(d);
  }
  document.querySelectorAll('.slide-pill').forEach(p => {
    p.classList.toggle('active', Number(p.dataset.slide) === slideNumber);
  });
}

const timelineSegs = SPEC.timeline ? SPEC.timeline.segments : [];
const totalDurationS = SPEC.timeline ? SPEC.timeline.total_duration_s : 180.0;

function evaluateTimeline(tSec) {
  if (!timelineSegs.length) {
    return {
      segId: '', slideNumber: 1, tau: 0, visualMode: 'claim_grid_compare', interactiveMode: null,
      segFrac: 1, camPos: new THREE.Vector3(0.40, 4.15, 5.20), lookAt: new THREE.Vector3(0.36, 0, 0.88)
    };
  }
  const t = Math.max(0, Math.min(totalDurationS, tSec));
  let seg = timelineSegs[0], nextSeg = null;
  for (let i = 0; i < timelineSegs.length; i++) {
    if (t <= timelineSegs[i].hold_end_s || i === timelineSegs.length - 1) {
      seg = timelineSegs[i];
      nextSeg = timelineSegs[i + 1] || null;
      break;
    }
  }
  const dur = Math.max(0.05, seg.end_s - seg.start_s);
  const rawFrac = clamp01((t - seg.start_s) / dur);
  const eased = smoothstep(rawFrac);
  const tau = lerp(seg.tau_start, seg.tau_end, eased);

  const camPos = new THREE.Vector3(...seg.cam_start).lerp(new THREE.Vector3(...seg.cam_end), eased);
  const lookAt = new THREE.Vector3(...seg.look_start).lerp(new THREE.Vector3(...seg.look_end), eased);

  if (nextSeg && t > seg.end_s) {
    const pSpan = Math.max(0.05, seg.hold_end_s - seg.end_s);
    const bt = smoothstep((t - seg.end_s) / pSpan);
    camPos.lerp(new THREE.Vector3(...nextSeg.cam_start), bt);
    lookAt.lerp(new THREE.Vector3(...nextSeg.look_start), bt);
  }
  return {
    segId: seg.id,
    slideNumber: seg.slide_number,
    tau,
    visualMode: seg.visual_mode,
    interactiveMode: seg.interactive_mode || null,
    segFrac: rawFrac,
    camPos,
    lookAt
  };
}

// ---- Audio, Interactive Checkpoints & Raycast Dragging ----------------------
const audioEl = document.getElementById('voiceover-audio');
if (SPEC.timeline && SPEC.timeline.master_wav_url && !IS_CAPTURE) {
  audioEl.src = SPEC.timeline.master_wav_url;
}

let isPlaying = false;
let manualTimeS = 0.0;
let manualTauOverride = null;
let morphAnimActive = false;
let morphStartMs = 0, morphFrom = 0, morphTo = 1;
let userDetachedCam = false;
const camSpherical = new THREE.Spherical(5.2, 0.98, 0.08);
let isOrbitDragging = false, lastX = 0, lastY = 0;

const btnPlay = document.getElementById('btn-play');
const btnMorph = document.getElementById('btn-morph');
const btnReattach = document.getElementById('btn-reattach');
const timelineSlider = document.getElementById('timeline-slider');
const morphSlider = document.getElementById('morph-slider');
const timeReadout = document.getElementById('time-readout');

const interactiveBanner = document.getElementById('interactive-banner');
const interactiveTitle = document.getElementById('interactive-title');
const interactiveSlider = document.getElementById('interactive-slider');
const btnContinueInteractive = document.getElementById('btn-continue-interactive');
const activeCueBadge = document.getElementById('active-cue-badge');

function fmtTime(sec) {
  const s = Math.max(0, Math.floor(sec));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

function pauseForUserManipulation(kind) {
  if (isPlaying) {
    isPlaying = false;
    if (audioEl.src) audioEl.pause();
  }
  pausedForInteraction = true;
  btnPlay.textContent = '▶ Continue Video';
  btnContinueInteractive.style.display = 'inline-block';
  interactiveBanner.classList.add('paused-highlight');
  if (kind === 'drag_point_a' && userCircAngleA === null) {
    userCircAngleA = CIRC_ANGLE_CASE2_A;
  } else if (kind === 'sweep_line_df' && userSweepThetaDF === null) {
    userSweepThetaDF = P.theta_case2_rad;
  }
}

async function resumePresentationPlayback() {
  pausedForInteraction = false;
  btnContinueInteractive.style.display = 'none';
  interactiveBanner.classList.remove('paused-highlight');
  manualTauOverride = null;
  if (manualTimeS >= totalDurationS - 0.5) {
    manualTimeS = 0;
    interactiveAutoPausedSegs.clear();
    userCircAngleA = null;
    userSweepThetaDF = null;
    if (audioEl.src) audioEl.currentTime = 0;
  }
  if (audioEl.src) {
    audioEl.currentTime = manualTimeS;
    try { await audioEl.play(); } catch (_) {}
  }
  isPlaying = true;
  btnPlay.textContent = '⏸ Pause';
}

const pillsWrap = document.getElementById('slide-pills');
for (const sl of SPEC.slides) {
  const b = document.createElement('button');
  b.className = 'slide-pill';
  b.dataset.slide = sl.slide_number;
  b.textContent = sl.slide_number === 5 ? '5 · 3D Breakdown' : `${sl.slide_number}`;
  b.title = sl.title;
  b.addEventListener('click', () => {
    const first = timelineSegs.find(x => x.slide_number === sl.slide_number);
    if (first) {
      manualTauOverride = null;
      morphAnimActive = false;
      userCircAngleA = null;
      userSweepThetaDF = null;
      pausedForInteraction = false;
      btnContinueInteractive.style.display = 'none';
      manualTimeS = first.start_s;
      if (audioEl.src) audioEl.currentTime = manualTimeS;
    }
  });
  pillsWrap.appendChild(b);
}

btnPlay.addEventListener('click', async () => {
  if (!isPlaying) {
    await resumePresentationPlayback();
  } else {
    isPlaying = false;
    if (audioEl.src) audioEl.pause();
    btnPlay.textContent = '▶ Resume';
  }
});
btnContinueInteractive.addEventListener('click', async () => {
  await resumePresentationPlayback();
});
audioEl.addEventListener('ended', () => { isPlaying = false; btnPlay.textContent = '↺ Replay'; });

timelineSlider.addEventListener('input', () => {
  manualTauOverride = null; morphAnimActive = false;
  userCircAngleA = null; userSweepThetaDF = null;
  pausedForInteraction = false;
  interactiveAutoPausedSegs.clear();
  manualTimeS = (Number(timelineSlider.value) / 1000) * totalDurationS;
  if (audioEl.src) audioEl.currentTime = manualTimeS;
});

// Synced Interactive Banner Slider (Slide 1: A -> B, Slide 4: Sweep DF)
interactiveSlider.addEventListener('input', () => {
  const frac = Number(interactiveSlider.value) / 1000;
  if (currentInteractiveKind === 'drag_point_a') {
    pauseForUserManipulation('drag_point_a');
    // frac=0 -> G (upper circumference), frac=1 -> B (-90 deg tangent!)
    userCircAngleA = lerp(CIRC_ANGLE_G - 0.08, CIRC_ANGLE_B, frac);
  } else if (currentInteractiveKind === 'sweep_line_df') {
    pauseForUserManipulation('sweep_line_df');
    userSweepThetaDF = lerp(3.5 * DEG, (MAX_SECANT_THETA / DEG - 3.5) * DEG, frac);
  }
});

morphSlider.addEventListener('input', () => {
  morphAnimActive = false;
  manualTauOverride = Number(morphSlider.value) / 1000;
});
btnMorph.addEventListener('click', () => {
  const cur = Number(morphSlider.value) / 1000;
  morphFrom = cur; morphTo = cur > 0.5 ? 0.0 : 1.0;
  morphStartMs = performance.now();
  morphAnimActive = true;
});
btnReattach.addEventListener('click', () => {
  userDetachedCam = false;
  btnReattach.style.display = 'none';
});

// 3D Raycasting onto Horizontal Plane y = 0 for Direct Dragging of A (Slide 1) & DF (Slide 4)
const raycaster = new THREE.Raycaster();
const groundPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
const hitVec3 = new THREE.Vector3();

function raycastMouseToEuclid(clientX, clientY) {
  const rect = canvas.getBoundingClientRect();
  const ndc = new THREE.Vector2(
    ((clientX - rect.left) / rect.width) * 2 - 1,
    -((clientY - rect.top) / rect.height) * 2 + 1
  );
  raycaster.setFromCamera(ndc, camera);
  if (raycaster.ray.intersectPlane(groundPlane, hitVec3)) {
    return worldToEuclid(hitVec3.x, hitVec3.z);
  }
  return null;
}

function isNearInteractiveTarget(clientX, clientY) {
  if (!currentInteractiveKind || !currentDraggableWorldPos) return false;
  const ptE = raycastMouseToEuclid(clientX, clientY);
  if (!ptE) return false;
  if (currentInteractiveKind === 'drag_point_a') {
    // Hit if near Point A OR near the right/upper circumference arc of the circle!
    const distFromE = Math.hypot(ptE[0], ptE[1]);
    const aWorld = currentDraggableWorldPos;
    const aE = worldToEuclid(aWorld.x, aWorld.z);
    if (Math.hypot(ptE[0] - aE[0], ptE[1] - aE[1]) < 0.85) return true;
    return Math.abs(distFromE - P.r) < 0.45 && ptE[0] > -2.5;
  }
  if (currentInteractiveKind === 'sweep_line_df') {
    const fE = worldToEuclid(currentDraggableWorldPos.x, currentDraggableWorldPos.z);
    if (Math.hypot(ptE[0] - fE[0], ptE[1] - fE[1]) < 0.95) return true;
    // Also allow grabbing anywhere along chord inside the circle
    return Math.hypot(ptE[0], ptE[1]) < P.r * 0.95;
  }
  return false;
}

function applyRaycastDrag(clientX, clientY) {
  const ptE = raycastMouseToEuclid(clientX, clientY);
  if (!ptE) return;
  if (activeDragMode === 'drag_point_a') {
    let ang = Math.atan2(ptE[1] - P.E[1], ptE[0] - P.E[0]);
    // Unwrap negative angles below -90 deg (third quadrant) to clamp cleanly at B (-90 deg)
    if (ang < -Math.PI / 2) {
      ang = (ptE[1] > 0) ? CIRC_ANGLE_G - 0.05 : CIRC_ANGLE_B;
    }
    userCircAngleA = Math.max(CIRC_ANGLE_B, Math.min(CIRC_ANGLE_G - 0.05, ang));
    const sliderFrac = (CIRC_ANGLE_G - 0.08 - userCircAngleA) / (CIRC_ANGLE_G - 0.08 - CIRC_ANGLE_B);
    interactiveSlider.value = String(Math.round(clamp01(sliderFrac) * 1000));
  } else if (activeDragMode === 'sweep_line_df') {
    const th = Math.atan2(ptE[1] - P.D[1], ptE[0] - P.D[0]);
    userSweepThetaDF = Math.max(2.5 * DEG, Math.min(MAX_SECANT_THETA - 2.5 * DEG, th));
    const sliderFrac = (userSweepThetaDF - 3.5 * DEG) / (MAX_SECANT_THETA - 7.0 * DEG);
    interactiveSlider.value = String(Math.round(clamp01(sliderFrac) * 1000));
  }
}

canvas.addEventListener('pointerdown', (e) => {
  if (IS_CAPTURE) return;
  if (isNearInteractiveTarget(e.clientX, e.clientY)) {
    activeDragMode = currentInteractiveKind;
    pauseForUserManipulation(activeDragMode);
    applyRaycastDrag(e.clientX, e.clientY);
    canvas.style.cursor = 'grabbing';
    return;
  }
  isOrbitDragging = true; lastX = e.clientX; lastY = e.clientY;
  if (!userDetachedCam) {
    camSpherical.setFromVector3(camera.position.clone().sub(camTarget));
    userDetachedCam = true;
    btnReattach.style.display = 'inline-block';
  }
});

window.addEventListener('pointermove', (e) => {
  if (IS_CAPTURE) return;
  if (activeDragMode) {
    applyRaycastDrag(e.clientX, e.clientY);
    return;
  }
  if (isOrbitDragging) {
    camSpherical.theta -= (e.clientX - lastX) * 0.0055;
    camSpherical.phi = Math.max(0.15, Math.min(Math.PI * 0.48, camSpherical.phi - (e.clientY - lastY) * 0.0055));
    lastX = e.clientX; lastY = e.clientY;
    return;
  }
  canvas.style.cursor = isNearInteractiveTarget(e.clientX, e.clientY) ? 'grab' : 'default';
});

window.addEventListener('pointerup', () => {
  activeDragMode = null;
  isOrbitDragging = false;
  canvas.style.cursor = 'default';
});

canvas.addEventListener('wheel', (e) => {
  if (IS_CAPTURE) return;
  e.preventDefault();
  if (!userDetachedCam) {
    camSpherical.setFromVector3(camera.position.clone().sub(camTarget));
    userDetachedCam = true;
    btnReattach.style.display = 'inline-block';
  }
  camSpherical.radius = Math.max(2.0, Math.min(12.0, camSpherical.radius + e.deltaY * 0.0035));
}, { passive: false });

// ---- Deterministic & Interactive Render Loop --------------------------------
function renderAtTime(tSec, nowSec = 0) {
  clearAllLabels();
  const st = evaluateTimeline(tSec);
  updateSlideCard(st.slideNumber);

  // Clear slide-specific manual overrides when moving to another slide
  if (st.slideNumber !== 1 && userCircAngleA !== null && !pausedForInteraction) userCircAngleA = null;
  if (st.slideNumber !== 4 && userSweepThetaDF !== null && !pausedForInteraction) userSweepThetaDF = null;

  // Auto-pause at Interactive Checkpoints (~0:49 Slide 1 & ~3:57 Slide 4) during live playback!
  if (!IS_CAPTURE && isPlaying && st.interactiveMode && !interactiveAutoPausedSegs.has(st.segId)) {
    interactiveAutoPausedSegs.add(st.segId);
    pauseForUserManipulation(st.interactiveMode);
  }

  // Show/update Top-Center Interactive Manipulation Pill on Slide 1 and Slide 4
  if (!IS_CAPTURE && (st.slideNumber === 1 || st.slideNumber === 4) && (manualTauOverride === null || manualTauOverride < 0.05)) {
    interactiveBanner.style.display = 'flex';
    if (st.slideNumber === 1) {
      interactiveTitle.textContent = pausedForInteraction
        ? '⏸ Paused: Drag Point A toward B (blue area stays 16)'
        : '🖱️ Interactive: Drag Point A along circle toward B';
      if (userCircAngleA === null) {
        const curA = st.visualMode === 'claim_morph_overlay'
          ? cutLineJS(lerp(P.theta_case2_rad, 0.0005, smoothstep(clamp01(st.segFrac / 0.58)))).A
          : P.case2.A;
        const curAng = Math.atan2(curA[1], curA[0]);
        const frac = (CIRC_ANGLE_G - 0.08 - curAng) / (CIRC_ANGLE_G - 0.08 - CIRC_ANGLE_B);
        interactiveSlider.value = String(Math.round(clamp01(frac) * 1000));
      }
    } else {
      interactiveTitle.textContent = pausedForInteraction
        ? '⏸ Paused: Sweep line DF across chords (AD·DC stays 16)'
        : '🖱️ Interactive: Drag point F / sweep line DF';
      if (userSweepThetaDF === null) {
        const osc = 0.5 - 0.5 * Math.cos(st.segFrac * Math.PI * 2);
        const curTh = lerp(6 * DEG, 67 * DEG, st.visualMode === 'fan_sweep' ? osc : 0.28);
        const frac = (curTh - 3.5 * DEG) / (MAX_SECANT_THETA - 7.0 * DEG);
        interactiveSlider.value = String(Math.round(clamp01(frac) * 1000));
      }
    }
  } else if (!IS_CAPTURE) {
    interactiveBanner.style.display = 'none';
  }

  let effTau = st.tau;
  if (morphAnimActive) {
    const u = clamp01((performance.now() - morphStartMs) / 3600);
    effTau = lerp(morphFrom, morphTo, smoothstep(u));
    manualTauOverride = effTau;
    if (u >= 1) morphAnimActive = false;
  } else if (manualTauOverride !== null) {
    effTau = manualTauOverride;
  }

  const hl = getActiveHighlightState(tSec, pausedForInteraction);
  if (hl.label) {
    activeCueBadge.style.display = 'inline-block';
    activeCueBadge.textContent = `🔦 ${hl.label}`;
  } else {
    activeCueBadge.style.display = 'none';
  }

  if (!IS_CAPTURE) {
    timelineSlider.value = String(Math.round((tSec / Math.max(0.1, totalDurationS)) * 1000));
    morphSlider.value = String(Math.round(effTau * 1000));
    timeReadout.textContent = `${fmtTime(tSec)} / ${fmtTime(totalDurationS)}`;
  }

  if (effTau > 0.015 || st.visualMode.startsWith('sphere')) {
    updateSphericalScene(effTau, st.visualMode.startsWith('sphere') ? st.visualMode : 'sphere_product_mismatch', hl, nowSec);
  } else {
    updateEuclideanScene(st.visualMode, st.segFrac, hl, nowSec);
  }

  if (!userDetachedCam || IS_CAPTURE) {
    if (manualTauOverride !== null && manualTauOverride > 0.05 && !st.visualMode.startsWith('sphere')) {
      const sCam = new THREE.Vector3(0.45, 2.05, 4.95);
      const sLook = new THREE.Vector3(0.20, 1.36, 0.0);
      camera.position.copy(st.camPos).lerp(sCam, smoothstep(manualTauOverride));
      camTarget.copy(st.lookAt).lerp(sLook, smoothstep(manualTauOverride));
    } else {
      camera.position.copy(st.camPos);
      camTarget.copy(st.lookAt);
    }
    camera.lookAt(camTarget);
  } else {
    camera.position.copy(camTarget).add(new THREE.Vector3().setFromSpherical(camSpherical));
    camera.lookAt(camTarget);
  }

  renderer.render(scene, camera);
  projectLabels();
}

window.setVirtualWorldTime = (tSec, opts = {}) => {
  manualTimeS = tSec;
  manualTauOverride = (opts.tau !== undefined) ? opts.tau : null;
  renderAtTime(tSec, tSec);
  return true;
};

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderAtTime(manualTimeS, performance.now() / 1000);
});

renderAtTime(0, 0);
window.__worldReady = true;

if (!IS_CAPTURE) {
  let prevMs = performance.now();
  function animate(nowMs) {
    const dt = Math.min(0.05, (nowMs - prevMs) / 1000);
    prevMs = nowMs;
    if (isPlaying) {
      if (audioEl.src && !audioEl.paused) {
        manualTimeS = audioEl.currentTime;
      } else {
        manualTimeS = Math.min(totalDurationS, manualTimeS + dt);
        if (manualTimeS >= totalDurationS) isPlaying = false;
      }
    }
    renderAtTime(manualTimeS, nowMs / 1000);
    requestAnimationFrame(animate);
  }
  requestAnimationFrame(animate);
}
</script>
</body>
</html>
"""
