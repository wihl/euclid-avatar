"""Interactive Three.js 3D Virtual World HTML/JS generator for Proposition III.18.

Supports both:
1. Interactive exploration in any modern browser (Guided Voiceover Tour, Slide Jump,
   live 2D-Plane-to-3D-Sphere Curvature Slider, I.16 Far-Foot toggle, and WASD +
   Mouse Orbit/Zoom free navigation).
2. Deterministic frame-accurate 1080p capture (`?capture=1`) via
   `window.setVirtualWorldTime(seconds)` for MP4 video and Genie seed rendering.
"""

from __future__ import annotations

import json
from typing import Any


def render_world_html(spec: dict[str, Any]) -> str:
    """Return the complete HTML document for the III.18 3D virtual world."""
    spec_json = json.dumps(spec, separators=(",", ":"))
    return HTML_TEMPLATE.replace("__WORLD_SPEC_JSON__", spec_json)


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Elements III.18 · 3D Euclidean-to-Spherical Virtual World</title>
<style>
  :root {
    --slate-bg: #0b1817;
    --panel-bg: rgba(14, 31, 28, 0.84);
    --panel-light: rgba(238, 245, 240, 0.94);
    --border-subtle: rgba(242, 179, 0, 0.32);
    --c-circle: #2BA05F;
    --c-touch: #E4471A;
    --c-radius: #1B6AD1;
    --c-supposed: #7A3DB5;
    --c-angle: #F2B300;
    --text-main: #F3F7F5;
    --text-muted: #A9BCB6;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body {
    width: 100%; height: 100%; overflow: hidden;
    background: var(--slate-bg);
    font-family: "Optima", "Avenir Next", "Segoe UI", system-ui, sans-serif;
    color: var(--text-main);
    user-select: none;
  }
  #canvas-wrap {
    position: fixed; inset: 0;
  }
  canvas#gl {
    display: block; width: 100%; height: 100%;
  }

  /* Crisp 3D-projected geometric point & callout labels */
  #labels-layer {
    position: fixed; inset: 0; pointer-events: none; overflow: hidden; z-index: 5;
  }
  .geo-label {
    position: absolute;
    transform: translate(-50%, -50%);
    font-family: "Cambria", "Georgia", serif;
    font-weight: 700;
    font-size: 20px;
    line-height: 1.15;
    padding: 3px 8px;
    border-radius: 6px;
    background: rgba(12, 24, 22, 0.82);
    border: 1.5px solid rgba(255, 255, 255, 0.25);
    color: #ffffff;
    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.48);
    white-space: nowrap;
  }
  .geo-label.callout {
    font-family: "Avenir Next", "Calibri", sans-serif;
    font-size: 15px;
    font-weight: 600;
    padding: 5px 10px;
  }
  .geo-label.supposed {
    border-color: #b47ef0;
    color: #ebd9ff;
    background: rgba(48, 20, 76, 0.88);
  }
  .geo-label.truth {
    border-color: var(--c-angle);
    color: #ffe28a;
    background: rgba(45, 33, 6, 0.90);
  }
  .geo-label.radius-tag {
    border-color: #63a4ff;
    color: #d6e8ff;
    background: rgba(14, 38, 76, 0.88);
  }

  /* Top-left Slide Card HUD */
  #slide-hud {
    position: fixed;
    top: 24px; left: 26px;
    width: 450px;
    max-width: calc(100vw - 52px);
    padding: 18px 20px;
    border-radius: 14px;
    background: var(--panel-bg);
    backdrop-filter: blur(14px);
    border: 1px solid var(--border-subtle);
    box-shadow: 0 14px 38px rgba(0, 0, 0, 0.52);
    z-index: 10;
    transition: background 0.35s ease, border-color 0.35s ease;
  }
  #hud-header-row {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 6px;
  }
  #hud-kicker {
    font-size: 11.5px; font-weight: 800; letter-spacing: 1.8px;
    text-transform: uppercase; color: var(--c-angle);
  }
  #step-dots {
    display: flex; gap: 6px; align-items: center;
  }
  .step-dot {
    width: 22px; height: 22px; border-radius: 50%;
    font-size: 11px; font-weight: 700;
    display: flex; align-items: center; justify-content: center;
    border: 1.5px solid rgba(255,255,255,0.28);
    color: var(--text-muted);
    background: rgba(255,255,255,0.05);
  }
  .step-dot.active {
    background: var(--c-touch);
    border-color: var(--c-touch);
    color: #fff;
  }
  .step-dot.done {
    background: rgba(43, 160, 95, 0.32);
    border-color: var(--c-circle);
    color: #d9f7e6;
  }
  #hud-title {
    font-family: "Cambria", "Georgia", serif;
    font-size: 24px; font-weight: 700; line-height: 1.2;
    margin-bottom: 12px; color: #ffffff;
  }
  #hud-bullets {
    display: flex; flex-direction: column; gap: 8px;
  }
  .hud-bullet {
    display: flex; align-items: baseline; gap: 9px;
    padding: 8px 10px;
    border-radius: 9px;
    background: rgba(255, 255, 255, 0.06);
    border-left: 3.5px solid var(--c-angle);
    font-size: 14px; line-height: 1.38; color: #edf4f1;
  }
  .hud-badge {
    font-size: 10.5px; font-weight: 800; text-transform: uppercase;
    letter-spacing: 0.8px; padding: 2px 6px; border-radius: 4px;
    color: #fff; flex-shrink: 0;
  }
  .kw-de { color: #ff7750; font-weight: 700; }
  .kw-fc { color: #67a8ff; font-weight: 700; }
  .kw-fg { color: #c48eff; font-weight: 700; }
  .kw-circle { color: #53d68a; font-weight: 700; }

  /* Top-right Geometry Telemetry Pill */
  #telemetry-hud {
    position: fixed; top: 24px; right: 26px;
    padding: 12px 16px; border-radius: 12px;
    background: rgba(12, 26, 24, 0.82);
    backdrop-filter: blur(12px);
    border: 1px solid rgba(255, 255, 255, 0.15);
    z-index: 10;
    text-align: right;
    min-width: 235px;
  }
  #geom-space-label {
    font-size: 11px; font-weight: 800; letter-spacing: 1.5px;
    text-transform: uppercase; color: var(--c-angle);
  }
  #geom-curvature-readout {
    font-family: "Cambria", Georgia, serif;
    font-size: 19px; font-weight: 700; color: #fff; margin-top: 2px;
  }
  #geom-invariant-readout {
    font-size: 12.5px; color: var(--text-muted); margin-top: 3px;
  }

  /* Bottom Subtitle & Voiceover Banner */
  #subtitle-banner {
    position: fixed;
    left: 50%; transform: translateX(-50%);
    bottom: 92px;
    width: min(920px, calc(100vw - 64px));
    padding: 14px 24px;
    border-radius: 14px;
    background: rgba(9, 20, 19, 0.86);
    backdrop-filter: blur(12px);
    border: 1px solid rgba(255, 255, 255, 0.16);
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
    font-size: 18.5px; line-height: 1.48;
    text-align: center; color: #f6faf8;
    z-index: 10;
  }
  body.capture-mode #subtitle-banner {
    bottom: 34px;
    font-size: 20px;
  }
  body.capture-mode #controls-bar {
    display: none !important;
  }

  /* Interactive Controls Bar */
  #controls-bar {
    position: fixed;
    left: 24px; right: 24px; bottom: 16px;
    height: 62px;
    padding: 0 18px;
    border-radius: 14px;
    background: rgba(12, 26, 24, 0.92);
    backdrop-filter: blur(14px);
    border: 1px solid rgba(242, 179, 0, 0.28);
    display: flex; align-items: center; gap: 14px;
    z-index: 15;
    box-shadow: 0 10px 32px rgba(0,0,0,0.55);
  }
  button.ctrl-btn {
    background: rgba(255, 255, 255, 0.09);
    color: #fff;
    border: 1px solid rgba(255, 255, 255, 0.2);
    padding: 8px 13px;
    border-radius: 9px;
    font-size: 13px; font-weight: 700;
    cursor: pointer;
    transition: all 0.15s ease;
    white-space: nowrap;
  }
  button.ctrl-btn:hover {
    background: rgba(242, 179, 0, 0.22);
    border-color: var(--c-angle);
  }
  button.ctrl-btn.primary {
    background: var(--c-touch);
    border-color: #ff6e46;
  }
  button.ctrl-btn.primary:hover {
    background: #f2572b;
  }
  button.ctrl-btn.active-toggle {
    background: rgba(122, 61, 181, 0.55);
    border-color: #c58fff;
  }
  #slide-pills {
    display: flex; gap: 5px;
  }
  .slide-pill {
    padding: 6px 10px;
    border-radius: 7px;
    font-size: 12px; font-weight: 700;
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.14);
    color: var(--text-muted);
    cursor: pointer;
  }
  .slide-pill.active {
    background: rgba(242, 179, 0, 0.24);
    border-color: var(--c-angle);
    color: #fff;
  }
  .slider-group {
    display: flex; align-items: center; gap: 8px;
    font-size: 12px; font-weight: 700; color: #dce8e4;
  }
  input[type="range"] {
    accent-color: var(--c-angle);
    cursor: pointer;
  }
  #timeline-slider { flex: 1; min-width: 90px; }
  #morph-slider { width: 105px; }
  #time-readout {
    font-variant-numeric: tabular-nums;
    font-size: 12px; color: var(--text-muted);
    min-width: 82px; text-align: center;
  }
  #nav-hint {
    font-size: 11px; color: var(--text-muted);
    white-space: nowrap;
  }
</style>
</head>
<body>
<div id="canvas-wrap"><canvas id="gl"></canvas></div>
<div id="labels-layer"></div>

<div id="slide-hud">
  <div id="hud-header-row">
    <div id="hud-kicker">ELEMENTS III.18</div>
    <div id="step-dots"></div>
  </div>
  <div id="hud-title">The radius meets the touching line square</div>
  <div id="hud-bullets"></div>
</div>

<div id="telemetry-hud">
  <div id="geom-space-label">3D EUCLIDEAN PLANE</div>
  <div id="geom-curvature-readout">Curvature κ = 0.00 (Flat)</div>
  <div id="geom-invariant-readout">∠FCD = 90.0° · FC = 1.00 r</div>
</div>

<div id="subtitle-banner">Click <b>▶ Play Guided Tour</b> to start the narrated 3D walkthrough, or drag / WASD to explore freely.</div>

<div id="controls-bar">
  <button id="btn-play" class="ctrl-btn primary">▶ Play Guided Tour</button>
  <div id="slide-pills"></div>
  <input id="timeline-slider" type="range" min="0" max="1000" value="0" title="Presentation timeline" />
  <div id="time-readout">0:00 / 0:00</div>
  <div class="slider-group" title="Continuously bend the 2D Euclidean plane into the 3D Sphere">
    <span>2D</span>
    <input id="morph-slider" type="range" min="0" max="1000" value="0" />
    <span>3D Sphere</span>
  </div>
  <button id="btn-morph" class="ctrl-btn" title="Animate 2D Plane to 3D Sphere">✨ Morph</button>
  <button id="btn-farfoot" class="ctrl-btn" title="Toggle I.16 Far-Foot Spherical Counterexample">I.16 Far Foot</button>
  <button id="btn-reattach" class="ctrl-btn" style="display:none;">🎥 Guided Cam</button>
  <span id="nav-hint">Drag: Orbit · WASD: Fly</span>
</div>

<audio id="voiceover-audio" preload="auto"></audio>

<script type="module">
import * as THREE from '/vendor/three.module.js';

const SPEC = __WORLD_SPEC_JSON__;
const params = new URLSearchParams(window.location.search);
const IS_CAPTURE = params.get('capture') === '1';
if (IS_CAPTURE) {
  document.body.classList.add('capture-mode');
}

const DEG = Math.PI / 180;
const RAD_TO_DEG = 180 / Math.PI;
const SMALL_KAPPA = 1e-6;

// ---- Math & Continuous 2D->3D Riemannian Deformation ------------------------
function smoothstep(t) {
  const c = Math.max(0, Math.min(1, t));
  return c * c * (3 - 2 * c);
}
function clamp01(v) { return Math.max(0, Math.min(1, v)); }

function quatSlerp(q0, q1, t) {
  let [w0, x0, y0, z0] = q0;
  let [w1, x1, y1, z1] = q1;
  let dot = w0*w1 + x0*x1 + y0*y1 + z0*z1;
  if (dot < 0) { dot = -dot; w1 = -w1; x1 = -x1; y1 = -y1; z1 = -z1; }
  if (dot > 0.9995) {
    const w = w0 + t*(w1 - w0), x = x0 + t*(x1 - x0), y = y0 + t*(y1 - y0), z = z0 + t*(z1 - z0);
    const n = Math.hypot(w, x, y, z);
    return [w/n, x/n, y/n, z/n];
  }
  const th0 = Math.acos(Math.min(1, dot));
  const sin0 = Math.sin(th0);
  const th = th0 * t;
  const s0 = Math.cos(th) - dot * Math.sin(th) / sin0;
  const s1 = Math.sin(th) / sin0;
  return [s0*w0 + s1*w1, s0*x0 + s1*x1, s0*y0 + s1*y1, s0*z0 + s1*z1];
}

function quatToBasis(q) {
  const [w, x, y, z] = q;
  const xx = x*x, yy = y*y, zz = z*z, xy = x*y, xz = x*z, yz = y*z;
  const wx = w*x, wy = w*y, wz = w*z;
  const e1 = new THREE.Vector3(1 - 2*(yy + zz), 2*(xy + wz), 2*(xz - wy));
  const e2 = new THREE.Vector3(2*(xy - wz), 1 - 2*(xx + zz), 2*(yz + wx));
  const nf = new THREE.Vector3(2*(xz + wy), 2*(yz - wx), 1 - 2*(xx + yy));
  return { e1, e2, nf };
}

const fPlaneVec = new THREE.Vector3(...SPEC.frames.f_world_plane);
const fSphereVec = new THREE.Vector3(...SPEC.frames.f_world_sphere);
const globeCenterVec = new THREE.Vector3(...SPEC.constants.globe_center_world);

function evaluateDeformed(tau) {
  const s = smoothstep(tau);
  const q = quatSlerp(SPEC.frames.quat_plane, SPEC.frames.quat_sphere, s);
  const { e1, e2, nf } = quatToBasis(q);
  const fPos = fPlaneVec.clone().lerp(fSphereVec, s);
  const kappa = s * SPEC.constants.max_curvature_kappa;
  const r0 = SPEC.constants.euclid_radius;
  const phi = SPEC.constants.contact_phi_deg * DEG;

  const tc = e1.clone().multiplyScalar(Math.cos(phi)).addScaledVector(e2, Math.sin(phi));
  const wDe = new THREE.Vector3().crossVectors(nf, tc);

  const sphereDeArc = SPEC.constants.sphere_along_de_deg * DEG * SPEC.constants.sphere_world_radius;
  const arcD = (1 - s) * SPEC.constants.along_d_plane * r0 + s * sphereDeArc;
  const arcE = (1 - s) * SPEC.constants.along_e_plane * r0 + s * sphereDeArc;

  function expFromF(x, y) {
    const rho = Math.hypot(x, y);
    if (rho < 1e-12) return fPos.clone();
    const dirTan = e1.clone().multiplyScalar(x / rho).addScaledVector(e2, y / rho);
    if (kappa < SMALL_KAPPA) {
      return fPos.clone()
        .addScaledVector(dirTan, rho)
        .addScaledVector(nf, -0.5 * kappa * rho * rho);
    }
    const rad = 1 / kappa;
    const psi = Math.min(Math.PI, kappa * rho);
    const center = fPos.clone().addScaledVector(nf, -rad);
    const unitDir = nf.clone().multiplyScalar(Math.cos(psi)).addScaledVector(dirTan, Math.sin(psi));
    return center.addScaledVector(unitDir, rad);
  }

  function surfaceNormalAt(x, y) {
    const rho = Math.hypot(x, y);
    if (kappa < SMALL_KAPPA || rho < 1e-12) return nf.clone();
    const dirTan = e1.clone().multiplyScalar(x / rho).addScaledVector(e2, y / rho);
    const psi = Math.min(Math.PI, kappa * rho);
    return nf.clone().multiplyScalar(Math.cos(psi)).addScaledVector(dirTan, Math.sin(psi));
  }

  let cPos, centerOpt = null, radOpt = null, ncUnit = nf.clone(), tFcAtC;
  if (kappa < SMALL_KAPPA) {
    cPos = expFromF(r0 * Math.cos(phi), r0 * Math.sin(phi));
    tFcAtC = tc.clone().negate();
  } else {
    radOpt = 1 / kappa;
    centerOpt = fPos.clone().addScaledVector(nf, -radOpt);
    const alpha = kappa * r0;
    ncUnit = nf.clone().multiplyScalar(Math.cos(alpha)).addScaledVector(tc, Math.sin(alpha));
    cPos = centerOpt.clone().addScaledVector(ncUnit, radOpt);
    tFcAtC = nf.clone().multiplyScalar(Math.sin(alpha)).addScaledVector(tc, -Math.cos(alpha));
  }

  function dePoint(arcS) {
    if (kappa < SMALL_KAPPA) {
      return cPos.clone()
        .addScaledVector(wDe, arcS)
        .addScaledVector(nf, -0.5 * kappa * arcS * arcS);
    }
    const beta = kappa * arcS;
    const nPt = ncUnit.clone().multiplyScalar(Math.cos(beta)).addScaledVector(wDe, Math.sin(beta));
    return centerOpt.clone().addScaledVector(nPt, radOpt);
  }

  return {
    tau, s, kappa, e1, e2, nf, fPos, cPos, tc, wDe, tFcAtC, ncUnit,
    arcD, arcE, centerOpt, radOpt, expFromF, surfaceNormalAt, dePoint
  };
}

// ---- Three.js Scene & Alexandrian Observatory Setup -------------------------
const canvas = document.getElementById('gl');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
renderer.setPixelRatio(IS_CAPTURE ? 1 : Math.min(window.devicePixelRatio || 1, 2));
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.12;

const scene = new THREE.Scene();
scene.background = new THREE.Color('#091318');
scene.fog = new THREE.FogExp2('#091419', 0.022);

const camera = new THREE.PerspectiveCamera(44, window.innerWidth / window.innerHeight, 0.08, 180);
camera.position.set(-3.4, 2.5, 4.3);
const camTarget = new THREE.Vector3(0, 0.2, 0);

// Lighting
const hemiLight = new THREE.HemisphereLight('#b9d6ff', '#1b2f29', 1.15);
scene.add(hemiLight);

const keyLight = new THREE.DirectionalLight('#fff0d4', 1.65);
keyLight.position.set(6.5, 11.0, 7.5);
scene.add(keyLight);

const rimLight = new THREE.DirectionalLight('#5ca4ff', 0.72);
rimLight.position.set(-7.5, 5.5, -6.5);
scene.add(rimLight);

const warmAltarLight = new THREE.PointLight('#ffca7a', 0.9, 14, 1.4);
warmAltarLight.position.set(0, 3.6, 0.5);
scene.add(warmAltarLight);

// Sky Dome + Starfield
const skyGeo = new THREE.SphereGeometry(72, 48, 32);
const skyMat = new THREE.MeshBasicMaterial({ color: '#142534', side: THREE.BackSide, fog: false });
const skyDome = new THREE.Mesh(skyGeo, skyMat);
scene.add(skyDome);

const starCount = 750;
const starPositions = new Float32Array(starCount * 3);
for (let i = 0; i < starCount; i++) {
  // Deterministic Halton-like sky distribution
  const u = ((i * 0.61803398875) % 1);
  const v = ((i * 0.38196601125) % 1);
  const th = u * Math.PI * 2;
  const el = 0.08 + v * 1.42;
  const rad = 64;
  starPositions[i*3] = rad * Math.cos(el) * Math.cos(th);
  starPositions[i*3 + 1] = rad * Math.sin(el);
  starPositions[i*3 + 2] = rad * Math.cos(el) * Math.sin(th);
}
const starGeo = new THREE.BufferGeometry();
starGeo.setAttribute('position', new THREE.BufferAttribute(starPositions, 3));
const starMat = new THREE.PointsMaterial({ color: '#dceaff', size: 0.22, transparent: true, opacity: 0.75, fog: false });
scene.add(new THREE.Points(starGeo, starMat));

// Classical Alexandrian Rotunda Architecture
const archGroup = new THREE.Group();
scene.add(archGroup);

const slateFloorMat = new THREE.MeshStandardMaterial({
  color: '#102420', roughness: 0.36, metalness: 0.18
});
const outerRingMat = new THREE.MeshStandardMaterial({
  color: '#1c2b2d', roughness: 0.58, metalness: 0.08
});
const marbleMat = new THREE.MeshStandardMaterial({
  color: '#d8d2c5', roughness: 0.48, metalness: 0.05
});
const goldTrimMat = new THREE.MeshStandardMaterial({
  color: '#d49b27', roughness: 0.32, metalness: 0.68
});

const sanctuaryDisc = new THREE.Mesh(new THREE.CylinderGeometry(8.8, 9.1, 0.18, 72), slateFloorMat);
sanctuaryDisc.position.y = -0.11;
archGroup.add(sanctuaryDisc);

const stylobateRing = new THREE.Mesh(new THREE.RingGeometry(8.75, 11.4, 72), outerRingMat);
stylobateRing.rotation.x = -Math.PI / 2;
stylobateRing.position.y = -0.015;
archGroup.add(stylobateRing);

const innerBrassTrim = new THREE.Mesh(new THREE.RingGeometry(3.15, 3.21, 72), goldTrimMat);
innerBrassTrim.rotation.x = -Math.PI / 2;
innerBrassTrim.position.y = -0.01;
archGroup.add(innerBrassTrim);

// 12 Peristyle Columns around radius 9.8
const numCols = 12;
const colRad = 9.8;
const colShaftGeo = new THREE.CylinderGeometry(0.24, 0.29, 4.4, 20);
const colBaseGeo = new THREE.CylinderGeometry(0.38, 0.42, 0.22, 20);
const colCapGeo = new THREE.BoxGeometry(0.72, 0.20, 0.72);
for (let i = 0; i < numCols; i++) {
  const a = (i / numCols) * Math.PI * 2 + Math.PI / 12;
  const cx = colRad * Math.cos(a), cz = colRad * Math.sin(a);
  const cGrp = new THREE.Group();
  cGrp.position.set(cx, 0, cz);
  cGrp.lookAt(0, 0, 0);
  const base = new THREE.Mesh(colBaseGeo, marbleMat);
  base.position.y = 0.10;
  const shaft = new THREE.Mesh(colShaftGeo, marbleMat);
  shaft.position.y = 2.40;
  const cap = new THREE.Mesh(colCapGeo, marbleMat);
  cap.position.y = 4.68;
  cGrp.add(base, shaft, cap);
  archGroup.add(cGrp);
}
const architrave = new THREE.Mesh(new THREE.TorusGeometry(colRad, 0.22, 12, 72), marbleMat);
architrave.rotation.x = Math.PI / 2;
architrave.position.y = 4.88;
archGroup.add(architrave);

// ---- 6 Architectural Slide Monoliths along the North Gallery Arc ------------
const monoliths = [];
function drawSlideTexture(slide) {
  const cnv = document.createElement('canvas');
  cnv.width = 1024; cnv.height = 720;
  const ctx = cnv.getContext('2d');

  // Slate-card background
  const grad = ctx.createLinearGradient(0, 0, 0, 720);
  if (slide.theme === 'dark') {
    grad.addColorStop(0, '#14302A');
    grad.addColorStop(1, '#0c1e1a');
  } else {
    grad.addColorStop(0, '#182b29');
    grad.addColorStop(1, '#101d1c');
  }
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, 1024, 720);

  // Subtle border
  ctx.strokeStyle = 'rgba(242, 179, 0, 0.55)';
  ctx.lineWidth = 6;
  ctx.strokeRect(14, 14, 996, 692);

  // Kicker
  ctx.fillStyle = '#F2B300';
  ctx.font = 'bold 24px "Avenir Next", sans-serif';
  ctx.fillText(slide.kicker, 52, 74);

  // Slide number badge
  ctx.fillStyle = 'rgba(255,255,255,0.12)';
  ctx.fillRect(860, 42, 112, 44);
  ctx.fillStyle = '#EEF5F0';
  ctx.font = 'bold 22px "Avenir Next", sans-serif';
  ctx.fillText(`SLIDE ${slide.slide_number}/6`, 872, 72);

  // Title
  ctx.fillStyle = '#FFFFFF';
  ctx.font = 'bold 44px "Cambria", Georgia, serif';
  ctx.fillText(slide.title, 52, 138);

  // Bullets
  let y = 200;
  for (const b of slide.bullets) {
    ctx.fillStyle = 'rgba(255, 255, 255, 0.07)';
    ctx.fillRect(52, y, 920, 104);
    ctx.fillStyle = b.badge_color;
    ctx.fillRect(52, y, 10, 104);

    ctx.fillStyle = b.badge_color;
    ctx.font = 'bold 21px "Avenir Next", sans-serif';
    ctx.fillText(b.badge.toUpperCase(), 80, y + 36);

    ctx.fillStyle = '#F1F7F4';
    ctx.font = '27px "Avenir Next", Calibri, sans-serif';
    ctx.fillText(b.text, 80, y + 78, 872);
    y += 120;
  }

  const tex = new THREE.CanvasTexture(cnv);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

const arcRadius = 5.85;
for (let i = 0; i < SPEC.slides.length; i++) {
  const slide = SPEC.slides[i];
  // Spread from left-back (-148 deg) to right-back (-32 deg) in XZ
  const frac = i / (SPEC.slides.length - 1);
  const ang = (-152 + frac * 124) * DEG;
  const mx = arcRadius * Math.cos(ang);
  const mz = arcRadius * Math.sin(ang);

  const g = new THREE.Group();
  g.position.set(mx, 0, mz);
  g.lookAt(0, 1.35, 0);

  const ped = new THREE.Mesh(new THREE.BoxGeometry(2.15, 0.36, 0.36), marbleMat);
  ped.position.y = 0.18;

  const frameMat = new THREE.MeshStandardMaterial({
    color: '#2c3d3a', emissive: '#000000', roughness: 0.35, metalness: 0.55
  });
  const frame = new THREE.Mesh(new THREE.BoxGeometry(2.26, 1.64, 0.10), frameMat);
  frame.position.y = 1.38;

  const screenMat = new THREE.MeshBasicMaterial({ map: drawSlideTexture(slide) });
  const screen = new THREE.Mesh(new THREE.PlaneGeometry(2.12, 1.49), screenMat);
  screen.position.set(0, 1.38, 0.056);

  g.add(ped, frame, screen);
  archGroup.add(g);
  monoliths.push({ group: g, frameMat, slideNumber: slide.slide_number });
}

// ---- Dynamic Deforming 2D-Plane -> 3D-Sphere Geometry Objects ---------------
const stageGroup = new THREE.Group();
scene.add(stageGroup);

// 1. Parametric Coordinate Sheet -> Globe Surface (44 x 44 grid)
const GRID_N = 44;
const sheetGeo = new THREE.PlaneGeometry(1, 1, GRID_N, GRID_N);
const sheetMat = new THREE.MeshStandardMaterial({
  color: '#17332d',
  roughness: 0.52,
  metalness: 0.10,
  side: THREE.DoubleSide,
  transparent: true,
  opacity: 0.94,
  polygonOffset: true,
  polygonOffsetFactor: 2,
  polygonOffsetUnits: 2
});
const sheetMesh = new THREE.Mesh(sheetGeo, sheetMat);
stageGroup.add(sheetMesh);

// Euclidean Grid Lines (fade out as tau -> 1)
const euclidGridGroup = new THREE.Group();
stageGroup.add(euclidGridGroup);
const euclidGridLines = [];
const gridLineMat = new THREE.LineBasicMaterial({ color: '#396b60', transparent: true, opacity: 0.45 });
for (let k = -2; k <= 2; k += 0.5) {
  const gH = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3()]);
  const gV = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3()]);
  const lH = new THREE.Line(gH, gridLineMat);
  const lV = new THREE.Line(gV, gridLineMat);
  euclidGridGroup.add(lH, lV);
  euclidGridLines.push({ coord: k, horiz: lH, vert: lV });
}

// Spherical Graticule Lines (fade in as tau -> 1, matching iii18-figures.R every 30 deg)
const graticuleGroup = new THREE.Group();
stageGroup.add(graticuleGroup);
const graticuleMajorMat = new THREE.LineBasicMaterial({ color: '#698cb8', transparent: true, opacity: 0 });
const graticuleMinorMat = new THREE.LineBasicMaterial({ color: '#9ab0cc', transparent: true, opacity: 0 });

function makeUnitVecRWorld(latDeg, lonDeg) {
  const lat = latDeg * DEG, lon = lonDeg * DEG;
  const xr = Math.cos(lat) * Math.cos(lon);
  const yr = Math.cos(lat) * Math.sin(lon);
  const zr = Math.sin(lat);
  return new THREE.Vector3(yr, zr, xr);
}
const graticuleUnitCurves = [];
for (const k of [-60, -30, 0, 30, 60]) {
  const major = (k === 0);
  const latPts = [];
  for (let lon = -180; lon <= 180; lon += 4) latPts.push(makeUnitVecRWorld(k, lon));
  const latLine = new THREE.Line(new THREE.BufferGeometry().setFromPoints(latPts), major ? graticuleMajorMat : graticuleMinorMat);
  graticuleGroup.add(latLine);
  graticuleUnitCurves.push({ line: latLine, unitPts: latPts });
}
for (let lon = -150; lon <= 180; lon += 30) {
  const major = (lon === 0 || lon === 180);
  const lonPts = [];
  for (let lat = -90; lat <= 90; lat += 3) lonPts.push(makeUnitVecRWorld(lat, lon));
  const lonLine = new THREE.Line(new THREE.BufferGeometry().setFromPoints(lonPts), major ? graticuleMajorMat : graticuleMinorMat);
  graticuleGroup.add(lonLine);
  graticuleUnitCurves.push({ line: lonLine, unitPts: lonPts });
}

// 2. Shaded Disc / Spherical Cap Mesh (polar rings x sectors)
const CAP_RINGS = 10, CAP_SEGS = 72;
const capPositions = new Float32Array((CAP_RINGS + 1) * (CAP_SEGS + 1) * 3);
const capIndices = [];
for (let r = 0; r < CAP_RINGS; r++) {
  for (let j = 0; j < CAP_SEGS; j++) {
    const a = r * (CAP_SEGS + 1) + j;
    const b = a + CAP_SEGS + 1;
    capIndices.push(a, b, a + 1, b, b + 1, a + 1);
  }
}
const capGeo = new THREE.BufferGeometry();
capGeo.setAttribute('position', new THREE.BufferAttribute(capPositions, 3));
capGeo.setIndex(capIndices);
const capMat = new THREE.MeshBasicMaterial({
  color: SPEC.colors.circle, transparent: true, opacity: 0.25, side: THREE.DoubleSide, depthWrite: false
});
const capMesh = new THREE.Mesh(capGeo, capMat);
stageGroup.add(capMesh);

// Helper for crisp 3D Tube Curves
function makeTubeMesh(colorHex, radius = 0.022) {
  const mat = new THREE.MeshStandardMaterial({
    color: colorHex, emissive: colorHex, emissiveIntensity: 0.28, roughness: 0.32, metalness: 0.15,
    transparent: true, opacity: 1.0
  });
  const mesh = new THREE.Mesh(new THREE.BufferGeometry(), mat);
  mesh.userData.tubeRadius = radius;
  stageGroup.add(mesh);
  return mesh;
}
function updateTube(mesh, pts, closed = false, radiusOverride = null) {
  if (!pts || pts.length < 2) {
    mesh.visible = false;
    return;
  }
  mesh.visible = true;
  const curve = new THREE.CatmullRomCurve3(pts, closed, 'centripetal', 0.1);
  const rad = radiusOverride || mesh.userData.tubeRadius || 0.022;
  const segs = Math.max(12, pts.length * 2);
  const nextGeo = new THREE.TubeGeometry(curve, segs, rad, 10, closed);
  mesh.geometry.dispose();
  mesh.geometry = nextGeo;
}

// Primary Geometric Tubes
const circleTube = makeTubeMesh(SPEC.colors.circle, 0.024);
const deTube = makeTubeMesh(SPEC.colors.touch, 0.026);
const deGreatCircleGhost = new THREE.Line(
  new THREE.BufferGeometry(),
  new THREE.LineDashedMaterial({ color: SPEC.colors.touch, dashSize: 0.09, gapSize: 0.07, transparent: true, opacity: 0.45 })
);
stageGroup.add(deGreatCircleGhost);

const fcTube = makeTubeMesh(SPEC.colors.radius, 0.026);
const fbTube = makeTubeMesh(SPEC.colors.radius, 0.026);
const fgTube = makeTubeMesh(SPEC.colors.supposed, 0.024);
const bgHeavyTube = makeTubeMesh(SPEC.colors.supposed, 0.036);
const antipodeFcGhost = new THREE.Line(
  new THREE.BufferGeometry(),
  new THREE.LineDashedMaterial({ color: SPEC.colors.radius, dashSize: 0.08, gapSize: 0.06, transparent: true, opacity: 0.55 })
);
stageGroup.add(antipodeFcGhost);

// Slide 1 extra tangents & radii (indices 1 & 2 of claim_contacts)
const extraClaimObjs = [0, 1].map(() => ({
  tan: makeTubeMesh(SPEC.colors.touch, 0.022),
  rad: makeTubeMesh(SPEC.colors.radius, 0.022),
  sq: makeQuadMesh(SPEC.colors.angle, 0.86),
  dot: new THREE.Mesh(new THREE.SphereGeometry(0.042, 16, 16), new THREE.MeshStandardMaterial({ color: '#ffffff' }))
}));
for (const o of extraClaimObjs) {
  stageGroup.add(o.dot);
}

// Right-angle square at C + Wedge meshes + Triangle FGC patch
function makeQuadMesh(colorHex, opacity = 0.82) {
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(12), 3));
  g.setIndex([0, 1, 2, 0, 2, 3]);
  const m = new THREE.MeshBasicMaterial({ color: colorHex, transparent: true, opacity, side: THREE.DoubleSide, depthWrite: false });
  const mesh = new THREE.Mesh(g, m);
  stageGroup.add(mesh);
  return mesh;
}
function setQuadCorners(mesh, p0, p1, p2, p3) {
  const arr = mesh.geometry.attributes.position.array;
  const pts = [p0, p1, p2, p3];
  for (let i = 0; i < 4; i++) {
    arr[i*3] = pts[i].x; arr[i*3+1] = pts[i].y; arr[i*3+2] = pts[i].z;
  }
  mesh.geometry.attributes.position.needsUpdate = true;
  mesh.geometry.computeBoundingSphere();
}
const rightSquareC = makeQuadMesh(SPEC.colors.angle, 0.86);

// Supposed Triangle FGC translucent patch
const triFgcGeo = new THREE.BufferGeometry();
triFgcGeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(9), 3));
const triFgcMesh = new THREE.Mesh(
  triFgcGeo,
  new THREE.MeshBasicMaterial({ color: SPEC.colors.supposed, transparent: true, opacity: 0.24, side: THREE.DoubleSide, depthWrite: false })
);
stageGroup.add(triFgcMesh);

// Gold Angle Wedges at G (50 deg) and C (90 deg)
function makeWedgeMesh() {
  const segs = 28;
  const pos = new Float32Array((segs + 2) * 3);
  const idx = [];
  for (let i = 1; i <= segs; i++) idx.push(0, i, i + 1);
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  g.setIndex(idx);
  const m = new THREE.MeshBasicMaterial({ color: SPEC.colors.angle, transparent: true, opacity: 0.72, side: THREE.DoubleSide, depthWrite: false });
  const mesh = new THREE.Mesh(g, m);
  stageGroup.add(mesh);
  return mesh;
}
function updatePlanarWedge(mesh, vPt, pPt, qPt, rad, state) {
  const a1 = Math.atan2(pPt[1] - vPt[1], pPt[0] - vPt[0]);
  let sweep = ((Math.atan2(qPt[1] - vPt[1], qPt[0] - vPt[0]) - a1 + Math.PI) % (2 * Math.PI)) - Math.PI;
  if (sweep < -Math.PI) sweep += 2 * Math.PI;
  const segs = 28;
  const arr = mesh.geometry.attributes.position.array;
  const lift = state.nf.clone().multiplyScalar(0.018);
  const v3 = state.expFromF(vPt[0], vPt[1]).add(lift);
  arr[0] = v3.x; arr[1] = v3.y; arr[2] = v3.z;
  for (let i = 0; i <= segs; i++) {
    const a = a1 + sweep * (i / segs);
    const pt = state.expFromF(vPt[0] + rad * Math.cos(a), vPt[1] + rad * Math.sin(a)).add(lift);
    arr[(i + 1)*3] = pt.x; arr[(i + 1)*3 + 1] = pt.y; arr[(i + 1)*3 + 2] = pt.z;
  }
  mesh.geometry.attributes.position.needsUpdate = true;
}
const wedgeG = makeWedgeMesh();
const wedgeC = makeWedgeMesh();

// Tick marks on FC and FB + Raised 3D Bracket over FG
const tickFc = makeTubeMesh('#ffffff', 0.015);
const tickFb = makeTubeMesh('#ffffff', 0.015);
const fgBracketTube = makeTubeMesh(SPEC.colors.supposed, 0.014);

// Step 4 Fan (4 lines from F to DE crossing at B_i)
const fanObjs = SPEC.plane.fan.map(() => ({
  inSeg: makeTubeMesh(SPEC.colors.radius, 0.014),
  outSeg: makeTubeMesh(SPEC.colors.supposed, 0.014),
  bDot: new THREE.Mesh(new THREE.SphereGeometry(0.036, 14, 14), new THREE.MeshStandardMaterial({ color: SPEC.colors.radius, emissive: SPEC.colors.radius, emissiveIntensity: 0.35 })),
  gDot: new THREE.Mesh(new THREE.SphereGeometry(0.036, 14, 14), new THREE.MeshStandardMaterial({ color: SPEC.colors.supposed, emissive: SPEC.colors.supposed, emissiveIntensity: 0.35 })),
}));
for (const fo of fanObjs) stageGroup.add(fo.bDot, fo.gDot);

// Named Vertex Spheres (A, B, C, D, E, F, G)
const vertexDots = {};
for (const name of ['A', 'B', 'C', 'D', 'E', 'F', 'G']) {
  const col = (name === 'C' || name === 'F') ? '#ffffff' : '#e6eef2';
  const m = new THREE.Mesh(
    new THREE.SphereGeometry(0.048, 18, 18),
    new THREE.MeshStandardMaterial({ color: col, roughness: 0.25, metalness: 0.2 })
  );
  stageGroup.add(m);
  vertexDots[name] = m;
}

// Slide 6B: I.16 Far-Foot Spherical Counterexample Group
const farFootGroup = new THREE.Group();
stageGroup.add(farFootGroup);
const ffCircleLine = makeTubeMesh(SPEC.colors.touch, 0.019);
const ffFcTube = makeTubeMesh(SPEC.colors.radius, 0.022);
const ffFgFarTube = makeTubeMesh(SPEC.colors.supposed, 0.022);
const ffFgNearLine = new THREE.Line(
  new THREE.BufferGeometry(),
  new THREE.LineDashedMaterial({ color: '#45e3ff', dashSize: 0.07, gapSize: 0.05 })
);
const ffRightSqG = makeQuadMesh(SPEC.colors.angle, 0.88);
const ffObtuseWedgeC = makeWedgeMesh();
const ffDots = ['F', 'C', 'G', 'Near'].map(() => {
  const d = new THREE.Mesh(new THREE.SphereGeometry(0.05, 16, 16), new THREE.MeshStandardMaterial({ color: '#ffe58f' }));
  farFootGroup.add(d);
  return d;
});
// Move ff tubes into farFootGroup
farFootGroup.add(ffCircleLine, ffFcTube, ffFgFarTube, ffFgNearLine, ffRightSqG, ffObtuseWedgeC);

function buildSphereArcPts(uStart, uEnd, center, rad, steps = 36) {
  const dot = Math.max(-1, Math.min(1, uStart.dot(uEnd)));
  const om = Math.acos(dot);
  const pts = [];
  if (om < 1e-6) {
    return [center.clone().addScaledVector(uStart, rad), center.clone().addScaledVector(uEnd, rad)];
  }
  const sinOm = Math.sin(om);
  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    const u = uStart.clone().multiplyScalar(Math.sin((1 - t)*om)/sinOm)
      .addScaledVector(uEnd, Math.sin(t*om)/sinOm);
    pts.push(center.clone().addScaledVector(u, rad));
  }
  return pts;
}

function populateFarFootGeometry() {
  const ff = SPEC.frames.far_foot;
  const rad = SPEC.constants.sphere_world_radius * 1.006;
  const ctr = globeCenterVec;
  const uG = new THREE.Vector3(...ff.G_unit);
  const uF = new THREE.Vector3(...ff.F_unit);
  const uC = new THREE.Vector3(...ff.C_unit);
  const uNear = new THREE.Vector3(...ff.near_unit);

  updateTube(ffFcTube, buildSphereArcPts(uF, uC, ctr, rad, 28), false, 0.022);
  updateTube(ffFgFarTube, buildSphereArcPts(uF, uG, ctr, rad, 48), false, 0.025);
  // Route meridian through uNear -> uC -> uG to avoid antipodal sin(pi)=0 singularity
  const merPart1 = buildSphereArcPts(uNear, uC, ctr, rad, 28);
  const merPart2 = buildSphereArcPts(uC, uG, ctr, rad, 40).slice(1);
  updateTube(ffCircleLine, merPart1.concat(merPart2), false, 0.019);

  const nearPts = buildSphereArcPts(uF, uNear, ctr, rad, 24);
  ffFgNearLine.geometry.dispose();
  ffFgNearLine.geometry = new THREE.BufferGeometry().setFromPoints(nearPts);
  ffFgNearLine.computeLineDistances();

  // Right angle square at G between GF and GC
  const tGF = uF.clone().addScaledVector(uG, -uF.dot(uG)).normalize();
  const tGC = uC.clone().addScaledVector(uG, -uC.dot(uG)).normalize();
  const sqS = 0.12;
  const gPos = ctr.clone().addScaledVector(uG, rad + 0.01);
  setQuadCorners(
    ffRightSqG,
    gPos,
    gPos.clone().addScaledVector(tGF, sqS),
    gPos.clone().addScaledVector(tGF, sqS).addScaledVector(tGC, sqS),
    gPos.clone().addScaledVector(tGC, sqS)
  );

  // Obtuse 131.2 deg wedge at C between CF and CG
  const tCF = uF.clone().addScaledVector(uC, -uF.dot(uC)).normalize();
  const tCG = uG.clone().addScaledVector(uC, -uG.dot(uC)).normalize();
  const ang = Math.acos(Math.max(-1, Math.min(1, tCF.dot(tCG))));
  const ortho = tCG.clone().addScaledVector(tCF, -tCG.dot(tCF)).normalize();
  const cPos = ctr.clone().addScaledVector(uC, rad + 0.012);
  const arr = ffObtuseWedgeC.geometry.attributes.position.array;
  arr[0] = cPos.x; arr[1] = cPos.y; arr[2] = cPos.z;
  for (let i = 0; i <= 28; i++) {
    const a = ang * (i / 28);
    const dir = tCF.clone().multiplyScalar(Math.cos(a)).addScaledVector(ortho, Math.sin(a));
    const p = cPos.clone().addScaledVector(dir, 0.22);
    arr[(i + 1)*3] = p.x; arr[(i + 1)*3 + 1] = p.y; arr[(i + 1)*3 + 2] = p.z;
  }
  ffObtuseWedgeC.geometry.attributes.position.needsUpdate = true;

  const units = [uF, uC, uG, uNear];
  units.forEach((u, idx) => ffDots[idx].position.copy(ctr).addScaledVector(u, rad));
}
populateFarFootGeometry();

// ---- HTML Projected 3D Labels -----------------------------------------------
const labelsLayer = document.getElementById('labels-layer');
const labelDefs = {
  A: { text: 'A', cls: 'geo-label' },
  B: { text: 'B', cls: 'geo-label' },
  C: { text: 'C', cls: 'geo-label' },
  D: { text: 'D', cls: 'geo-label' },
  E: { text: 'E', cls: 'geo-label' },
  F: { text: 'F', cls: 'geo-label' },
  G: { text: 'G', cls: 'geo-label' },
  supposedG: { text: 'supposed right (90°?)', cls: 'geo-label callout supposed' },
  supposedC: { text: 'so, acute (<90°?)', cls: 'geo-label callout supposed' },
  trueG: { text: 'truly 50°', cls: 'geo-label callout truth' },
  trueC: { text: 'truly 90°', cls: 'geo-label callout truth' },
  wholeFG: { text: 'FG, the whole (1.31 r)', cls: 'geo-label callout supposed' },
  sphereFC: { text: 'FC = 40°', cls: 'geo-label callout radius-tag' },
  sphereAngleC: { text: '∠FCD = 90.0°', cls: 'geo-label callout truth' },
  ffPoleG: { text: 'Far foot G · ∠G = 90.0° (FG = 151.1°)', cls: 'geo-label callout supposed' },
  ffObtuseC: { text: '∠FCG = 131.2° (obtuse — I.17 fails!)', cls: 'geo-label callout truth' },
};
const labelEls = {};
for (const [k, def] of Object.entries(labelDefs)) {
  const el = document.createElement('div');
  el.className = def.cls;
  el.textContent = def.text;
  el.style.opacity = '0';
  labelsLayer.appendChild(el);
  labelEls[k] = { el, worldPos: new THREE.Vector3(), visible: false };
}

function setLabel(key, visible, worldVec) {
  const item = labelEls[key];
  if (!item) return;
  item.visible = visible;
  if (worldVec) item.worldPos.copy(worldVec);
}

function projectLabels() {
  const w = window.innerWidth, h = window.innerHeight;
  const tmp = new THREE.Vector3();
  for (const item of Object.values(labelEls)) {
    if (!item.visible) {
      item.el.style.display = 'none';
      continue;
    }
    tmp.copy(item.worldPos).project(camera);
    if (tmp.z > 1 || tmp.z < -1) {
      item.el.style.display = 'none';
      continue;
    }
    item.el.style.display = 'block';
    const sx = (tmp.x * 0.5 + 0.5) * w;
    const sy = (-tmp.y * 0.5 + 0.5) * h;
    item.el.style.left = `${sx.toFixed(1)}px`;
    item.el.style.top = `${sy.toFixed(1)}px`;
    item.el.style.opacity = '1';
  }
}

// ---- Update All 3D Geometry for Current (tau, visualMode, segProgress) ------
const cPlaneColor = new THREE.Color('#16312b');
const cSphereColor = new THREE.Color('#dbe8f6');

function updateSceneGeometry(tau, visualMode, segFrac, forceFarFoot) {
  const st = evaluateDeformed(tau);
  const s = st.s;
  const r0 = SPEC.constants.euclid_radius;
  const phi = SPEC.constants.contact_phi_deg * DEG;
  const liftEps = st.nf.clone().multiplyScalar(0.012);

  // 1. Deforming Sheet -> Full Sphere
  // Extent grows from 2.35 (flat table) to pi / kappa (closing at the antipode!)
  const maxHalfExtent = st.kappa > 0.02
    ? (1 - s) * 2.35 + s * (Math.PI / Math.max(st.kappa, 0.25))
    : 2.35;
  const posAttr = sheetGeo.attributes.position;
  for (let iy = 0; iy <= GRID_N; iy++) {
    const vy = (0.5 - iy / GRID_N) * 2 * maxHalfExtent;
    for (let ix = 0; ix <= GRID_N; ix++) {
      const vx = (ix / GRID_N - 0.5) * 2 * maxHalfExtent;
      const p = st.expFromF(vx, vy).addScaledVector(st.surfaceNormalAt(vx, vy), -0.012);
      const idx = iy * (GRID_N + 1) + ix;
      posAttr.setXYZ(idx, p.x, p.y, p.z);
    }
  }
  posAttr.needsUpdate = true;
  sheetGeo.computeVertexNormals();
  sheetMat.color.copy(cPlaneColor).lerp(cSphereColor, s);

  // Euclidean grid lines fade out with s
  gridLineMat.opacity = Math.max(0, 0.44 * (1 - s * 1.35));
  euclidGridGroup.visible = gridLineMat.opacity > 0.01;
  if (euclidGridGroup.visible) {
    for (const gl of euclidGridLines) {
      const hPts = [], vPts = [];
      for (let t = -2.2; t <= 2.2; t += 0.2) {
        hPts.push(st.expFromF(t, gl.coord));
        vPts.push(st.expFromF(gl.coord, t));
      }
      gl.horiz.geometry.setFromPoints(hPts);
      gl.vert.geometry.setFromPoints(vPts);
    }
  }

  // Spherical latitude/longitude graticules fade in with s
  const gratAlpha = clamp01((s - 0.25) / 0.75);
  graticuleGroup.visible = gratAlpha > 0.01 && st.centerOpt !== null;
  if (graticuleGroup.visible) {
    graticuleMajorMat.opacity = 0.72 * gratAlpha;
    graticuleMinorMat.opacity = 0.42 * gratAlpha;
    const radG = st.radOpt + 0.003;
    for (const gc of graticuleUnitCurves) {
      const pts = gc.unitPts.map(u => st.centerOpt.clone().addScaledVector(u, radG));
      gc.line.geometry.setFromPoints(pts);
    }
  }

  // Show/dim main III.18 vs Far-Foot counterexample
  const showFarFoot = forceFarFoot || visualMode === 'sphere_far_foot';
  farFootGroup.visible = showFarFoot && s > 0.85;
  const mainAlpha = farFootGroup.visible ? 0.22 : 1.0;

  // 2. Shaded Green Disc / Spherical Cap
  const capArr = capGeo.attributes.position.array;
  for (let ir = 0; ir <= CAP_RINGS; ir++) {
    const rr = r0 * (ir / CAP_RINGS);
    for (let ij = 0; ij <= CAP_SEGS; ij++) {
      const th = (ij / CAP_SEGS) * Math.PI * 2;
      const p = st.expFromF(rr * Math.cos(th), rr * Math.sin(th)).addScaledVector(st.nf, 0.004);
      const k = (ir * (CAP_SEGS + 1) + ij) * 3;
      capArr[k] = p.x; capArr[k + 1] = p.y; capArr[k + 2] = p.z;
    }
  }
  capGeo.attributes.position.needsUpdate = true;
  capMat.opacity = (visualMode.startsWith('step2') || visualMode.startsWith('step3') ? 0.15 : 0.28) * mainAlpha;

  // 3. Circle ABC Tube
  const circPts = [];
  for (let i = 0; i < 96; i++) {
    const a = (i / 96) * Math.PI * 2;
    circPts.push(st.expFromF(r0 * Math.cos(a), r0 * Math.sin(a)).add(liftEps));
  }
  updateTube(circleTube, circPts, true);
  circleTube.material.opacity = mainAlpha;

  // 4. Touching Line / Great Circle DE
  const dePts = [];
  const deCount = 56;
  const drawFracDe = visualMode === 'step1_construct' ? clamp01(segFrac * 1.8) : 1.0;
  for (let i = 0; i <= deCount; i++) {
    const u = (i / deCount) * drawFracDe;
    const arcS = -st.arcE + u * (st.arcD + st.arcE);
    dePts.push(st.dePoint(arcS).add(liftEps));
  }
  updateTube(deTube, dePts, false);
  deTube.material.opacity = mainAlpha;

  // Full great circle ghost on sphere
  deGreatCircleGhost.visible = s > 0.65 && !farFootGroup.visible;
  if (deGreatCircleGhost.visible && st.radOpt) {
    const fullPts = [];
    const fullCirc = 2 * Math.PI * st.radOpt;
    for (let i = 0; i <= 120; i++) {
      fullPts.push(st.dePoint((i / 120) * fullCirc));
    }
    deGreatCircleGhost.geometry.dispose();
    deGreatCircleGhost.geometry = new THREE.BufferGeometry().setFromPoints(fullPts);
    deGreatCircleGhost.computeLineDistances();
  }

  // 5. Radius FC
  const fcPts = [];
  const fcDraw = visualMode === 'step1_construct' ? clamp01((segFrac - 0.35) * 2.0) : 1.0;
  if (fcDraw > 0.02) {
    for (let i = 0; i <= 24; i++) {
      const rr = r0 * fcDraw * (i / 24);
      fcPts.push(st.expFromF(rr * Math.cos(phi), rr * Math.sin(phi)).add(liftEps));
    }
    updateTube(fcTube, fcPts, false);
    fcTube.material.opacity = mainAlpha;
  } else {
    fcTube.visible = false;
  }

  // Antipodal continuation on sphere (showing second 90 deg intersection at -C)
  antipodeFcGhost.visible = visualMode === 'sphere_picture_holds' && s > 0.9 && st.radOpt !== null;
  if (antipodeFcGhost.visible) {
    const antiPts = [];
    for (let i = 0; i <= 64; i++) {
      const rr = -r0 * ((Math.PI / SPEC.constants.sphere_circle_radius_deg / DEG - 1) * (i / 64));
      antiPts.push(st.expFromF(rr * Math.cos(phi), rr * Math.sin(phi)));
    }
    antipodeFcGhost.geometry.dispose();
    antipodeFcGhost.geometry = new THREE.BufferGeometry().setFromPoints(antiPts);
    antipodeFcGhost.computeLineDistances();
  }

  // 6. Slide 1 Extra Claim Tangents & Radii
  const showAllThree = visualMode === 'claim_all_three' || visualMode === 'claim_focus_c';
  const extraAlpha = visualMode === 'claim_focus_c' ? Math.max(0.18, 1 - segFrac * 0.85) : 1.0;
  for (let idx = 0; idx < 2; idx++) {
    const obj = extraClaimObjs[idx];
    const cc = SPEC.plane.claim_contacts[idx + 1];
    obj.tan.visible = showAllThree;
    obj.rad.visible = showAllThree;
    obj.sq.visible = showAllThree;
    obj.dot.visible = showAllThree;
    if (showAllThree) {
      const p3 = st.expFromF(cc.P[0], cc.P[1]).add(liftEps);
      const tStart = st.expFromF(cc.line_start[0], cc.line_start[1]).add(liftEps);
      const tEnd = st.expFromF(cc.line_end[0], cc.line_end[1]).add(liftEps);
      updateTube(obj.tan, [tStart, p3, tEnd], false, 0.020);
      updateTube(obj.rad, [st.fPos.clone().add(liftEps), p3], false, 0.020);
      obj.tan.material.opacity = extraAlpha;
      obj.rad.material.opacity = extraAlpha;
      obj.sq.material.opacity = 0.86 * extraAlpha;
      const uIn = st.fPos.clone().add(liftEps).sub(p3).normalize().multiplyScalar(0.14);
      const uTan = tEnd.clone().sub(p3).normalize().multiplyScalar(0.14);
      const sqBase = p3.clone().addScaledVector(st.nf, 0.008);
      setQuadCorners(
        obj.sq,
        sqBase,
        sqBase.clone().add(uIn),
        sqBase.clone().add(uIn).add(uTan),
        sqBase.clone().add(uTan)
      );
      obj.dot.position.copy(p3);
    }
  }

  // 7. Right-Angle Square at C (shown on Claim, Step 3 QED, Step 4, and Sphere)
  const showRightAtC = (
    visualMode.startsWith('claim') ||
    visualMode === 'step3_qed' ||
    visualMode === 'step4_fan_complete' ||
    visualMode.startsWith('sphere')
  ) && !farFootGroup.visible;
  rightSquareC.visible = showRightAtC;
  if (showRightAtC) {
    const sqSize = 0.145;
    const u1 = st.tFcAtC.clone().normalize().multiplyScalar(sqSize);
    const u2 = st.wDe.clone().normalize().multiplyScalar(sqSize);
    const cBase = st.cPos.clone().addScaledVector(st.ncUnit, 0.016);
    setQuadCorners(
      rightSquareC,
      cBase,
      cBase.clone().add(u1),
      cBase.clone().add(u1).add(u2),
      cBase.clone().add(u2)
    );
  }

  // 8. Step 2 & Step 3: Supposed Perpendicular FG, Triangle FGC, Wedges, Radii Ticks
  const g2 = SPEC.plane.G;
  const b2 = SPEC.plane.B;
  const c2 = SPEC.plane.C;
  const g3 = st.expFromF(g2[0], g2[1]).add(liftEps);
  const b3 = st.expFromF(b2[0], b2[1]).add(liftEps);
  const f3 = st.fPos.clone().add(liftEps);
  const c3 = st.cPos.clone().add(liftEps);

  const inStep2 = visualMode.startsWith('step2');
  const inStep3 = visualMode.startsWith('step3');
  const inStep4Early = visualMode === 'step4_focus_b' || visualMode === 'step4_single_crossing';

  fgTube.visible = inStep2 || inStep4Early;
  if (fgTube.visible) {
    const endPt = visualMode === 'step2_fg' ? f3.clone().lerp(g3, clamp01(segFrac * 1.7)) : g3;
    updateTube(fgTube, [f3, endPt], false, 0.024);
  }

  triFgcMesh.visible = visualMode === 'step2_supposed_labels' || visualMode === 'step2_true_wedges';
  if (triFgcMesh.visible) {
    const arr = triFgcGeo.attributes.position.array;
    const liftTri = st.nf.clone().multiplyScalar(0.008);
    const pts = [st.fPos.clone().add(liftTri), g3.clone().add(liftTri), st.cPos.clone().add(liftTri)];
    pts.forEach((p, i) => { arr[i*3] = p.x; arr[i*3+1] = p.y; arr[i*3+2] = p.z; });
    triFgcGeo.attributes.position.needsUpdate = true;
  }

  wedgeG.visible = visualMode === 'step2_true_wedges';
  wedgeC.visible = visualMode === 'step2_true_wedges';
  if (wedgeG.visible) {
    updatePlanarWedge(wedgeG, g2, [0, 0], c2, 0.30, st);
    updatePlanarWedge(wedgeC, c2, [0, 0], g2, 0.22, st);
  }

  // Step 3: FB + heavy BG + ticks + FG whole bracket
  fbTube.visible = inStep3 || inStep4Early;
  bgHeavyTube.visible = visualMode === 'step3_part_whole' || visualMode === 'step3_qed' || inStep4Early;
  if (fbTube.visible) updateTube(fbTube, [f3, b3], false, 0.027);
  if (bgHeavyTube.visible) updateTube(bgHeavyTube, [b3, g3], false, 0.036);

  tickFc.visible = inStep3;
  tickFb.visible = inStep3;
  if (inStep3) {
    // Tick across FC midpoint and FB midpoint
    const midFc = st.expFromF(0.5 * c2[0], 0.5 * c2[1]).add(liftEps);
    const perpFc = st.wDe.clone().multiplyScalar(0.075);
    updateTube(tickFc, [midFc.clone().sub(perpFc), midFc.clone().add(perpFc)], false, 0.013);

    const midFb = st.expFromF(0.5 * b2[0], 0.5 * b2[1]).add(liftEps);
    const perpFb = st.e2.clone().multiplyScalar(0.075);
    updateTube(tickFb, [midFb.clone().sub(perpFb), midFb.clone().add(perpFb)], false, 0.013);
  }

  fgBracketTube.visible = visualMode === 'step3_part_whole';
  if (fgBracketTube.visible) {
    const up = st.nf.clone().multiplyScalar(0.24);
    const leg = st.nf.clone().multiplyScalar(0.04);
    updateTube(fgBracketTube, [
      f3.clone().add(leg),
      f3.clone().add(up),
      f3.clone().lerp(g3, 0.5).add(up),
      g3.clone().add(up),
      g3.clone().add(leg)
    ], false, 0.012);
  }

  // 9. Step 4 Fan
  const showFan = visualMode === 'step4_fan_complete';
  fanObjs.forEach((fo, idx) => {
    fo.inSeg.visible = showFan;
    fo.outSeg.visible = showFan;
    fo.bDot.visible = showFan;
    fo.gDot.visible = showFan;
    if (showFan) {
      const fItem = SPEC.plane.fan[idx];
      const fb3 = st.expFromF(fItem.B[0], fItem.B[1]).add(liftEps);
      const fg3 = st.expFromF(fItem.G[0], fItem.G[1]).add(liftEps);
      updateTube(fo.inSeg, [f3, fb3], false, 0.013);
      updateTube(fo.outSeg, [fb3, fg3], false, 0.013);
      fo.bDot.position.copy(fb3);
      fo.gDot.position.copy(fg3);
    }
  });

  // 10. Named Vertices & Labels
  const a2 = SPEC.plane.A;
  const a3 = st.expFromF(a2[0], a2[1]).add(liftEps);
  const d3 = st.dePoint(st.arcD).add(liftEps);
  const e3 = st.dePoint(-st.arcE).add(liftEps);

  const posMap = { A: a3, B: b3, C: c3, D: d3, E: e3, F: f3, G: g3 };
  const isClaim = visualMode.startsWith('claim');
  const isSphere = visualMode.startsWith('sphere') || s > 0.5;

  const visMap = {
    F: !farFootGroup.visible,
    C: !farFootGroup.visible,
    D: !isClaim && !farFootGroup.visible,
    E: !isClaim && !farFootGroup.visible,
    A: visualMode.startsWith('step1') && !isSphere,
    B: (visualMode.startsWith('step1') || inStep3 || visualMode.startsWith('step4')) && !isSphere,
    G: (inStep2 || inStep3 || visualMode.startsWith('step4')) && !isSphere,
  };
  const labelLift = st.nf.clone().multiplyScalar(0.13);
  for (const [name, dotMesh] of Object.entries(vertexDots)) {
    dotMesh.visible = !!visMap[name];
    dotMesh.position.copy(posMap[name]);
    setLabel(name, !!visMap[name], posMap[name].clone().add(labelLift));
  }

  setLabel('supposedG', visualMode === 'step2_supposed_labels' || visualMode === 'step2_true_wedges',
    g3.clone().addScaledVector(st.e1, 0.25).addScaledVector(st.e2, -0.22).add(labelLift));
  setLabel('supposedC', visualMode === 'step2_supposed_labels' || visualMode === 'step2_true_wedges',
    c3.clone().addScaledVector(st.e1, 0.32).addScaledVector(st.e2, -0.18).add(labelLift));
  setLabel('trueG', visualMode === 'step2_true_wedges',
    g3.clone().addScaledVector(st.nf, 0.30).addScaledVector(st.e1, -0.12));
  setLabel('trueC', visualMode === 'step2_true_wedges',
    c3.clone().addScaledVector(st.nf, 0.30).addScaledVector(st.e1, -0.15));
  setLabel('wholeFG', visualMode === 'step3_part_whole',
    f3.clone().lerp(g3, 0.5).addScaledVector(st.nf, 0.36));

  const showSphereTags = s > 0.85 && !farFootGroup.visible;
  setLabel('sphereFC', showSphereTags, f3.clone().lerp(c3, 0.5).addScaledVector(st.e1, -0.26).add(labelLift));
  setLabel('sphereAngleC', showSphereTags, c3.clone().addScaledVector(st.wDe, 0.28).add(labelLift));

  const radS = SPEC.constants.sphere_world_radius;
  setLabel('ffPoleG', farFootGroup.visible,
    globeCenterVec.clone().add(new THREE.Vector3(...SPEC.frames.far_foot.G_unit).multiplyScalar(radS + 0.18)).add(new THREE.Vector3(0, 0.18, 0)));
  setLabel('ffObtuseC', farFootGroup.visible,
    globeCenterVec.clone().add(new THREE.Vector3(...SPEC.frames.far_foot.C_unit).multiplyScalar(radS + 0.18)).add(new THREE.Vector3(0.28, 0.34, 0.15)));

  // Update Telemetry Readout
  const spaceEl = document.getElementById('geom-space-label');
  const curvEl = document.getElementById('geom-curvature-readout');
  const invEl = document.getElementById('geom-invariant-readout');
  if (s < 0.02) {
    spaceEl.textContent = '2D EUCLIDEAN PLANE (IN 3D)';
    curvEl.textContent = 'Curvature κ = 0.000 (Flat)';
    invEl.textContent = '∠FCD = 90.0° · FC = 1.00 r';
  } else if (s < 0.98) {
    spaceEl.textContent = 'CONTINUOUS RIEMANNIAN MORPH';
    curvEl.textContent = `Curvature ${(s * 100).toFixed(0)}% · R = ${(1 / st.kappa).toFixed(2)}`;
    invEl.textContent = 'Geodesic ∠FCD = 90.0° preserved';
  } else if (farFootGroup.visible) {
    spaceEl.textContent = '3D SPHERICAL COUNTEREXAMPLE';
    curvEl.textContent = 'Far Foot G: ∠G = 90.0°';
    invEl.textContent = 'FC = 40° · ∠FCG = 131.2° (I.17 fails)';
  } else {
    spaceEl.textContent = '3D SPHERICAL GEOMETRY';
    curvEl.textContent = 'Sphere Radius · FC = 40°';
    invEl.textContent = 'Great Circle DE · ∠FCD = 90.0°';
  }
}

// ---- Slide HUD & Monolith Highlighting --------------------------------------
let activeSlideNum = -1;
function formatKeyedHtml(str) {
  return str
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\b(DE)\b/g, '<span class="kw-de">$1</span>')
    .replace(/\b(FC|FB)\b/g, '<span class="kw-fc">$1</span>')
    .replace(/\b(FG|BG)\b/g, '<span class="kw-fg">$1</span>')
    .replace(/the circle ABC/g, '<span class="kw-circle">the circle ABC</span>');
}

function setActiveSlideUI(slideNumber) {
  if (slideNumber === activeSlideNum) return;
  activeSlideNum = slideNumber;
  const slide = SPEC.slides.find(s => s.slide_number === slideNumber) || SPEC.slides[0];

  document.getElementById('hud-kicker').textContent = slide.kicker;
  document.getElementById('hud-title').textContent = slide.title;

  const dotsWrap = document.getElementById('step-dots');
  dotsWrap.innerHTML = '';
  if (slide.step_tracker > 0) {
    for (let i = 1; i <= 4; i++) {
      const d = document.createElement('div');
      d.className = 'step-dot' + (i === slide.step_tracker ? ' active' : (i < slide.step_tracker ? ' done' : ''));
      d.textContent = String(i);
      dotsWrap.appendChild(d);
    }
  }

  const bWrap = document.getElementById('hud-bullets');
  bWrap.innerHTML = '';
  for (const b of slide.bullets) {
    const row = document.createElement('div');
    row.className = 'hud-bullet';
    row.style.borderLeftColor = b.badge_color;
    row.innerHTML = `<span class="hud-badge" style="background:${b.badge_color}">${b.badge}</span><span>${formatKeyedHtml(b.text)}</span>`;
    bWrap.appendChild(row);
  }

  document.querySelectorAll('.slide-pill').forEach(el => {
    el.classList.toggle('active', Number(el.dataset.slide) === slideNumber);
  });

  for (const m of monoliths) {
    const isAct = m.slideNumber === slideNumber;
    m.frameMat.emissive.set(isAct ? '#593e05' : '#000000');
  }
}

// ---- Timeline Evaluation & Camera Choreography ------------------------------
const timelineSegs = SPEC.timeline ? SPEC.timeline.segments : [];
const totalDurationS = SPEC.timeline ? SPEC.timeline.total_duration_s : 120.0;

function evaluateTimelineState(tSec) {
  if (!timelineSegs.length) {
    return {
      slideNumber: 1, spoken: '', tau: 0, visualMode: 'claim_all_three', segFrac: 1,
      camPos: new THREE.Vector3(0.2, 2.4, 3.3), lookAt: new THREE.Vector3(0, 0.1, 0)
    };
  }
  const t = Math.max(0, Math.min(totalDurationS, tSec));
  let seg = timelineSegs[0];
  let nextSeg = null;
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
  const tau = seg.tau_start + (seg.tau_end - seg.tau_start) * eased;

  const cStart = new THREE.Vector3(...seg.cam_start);
  const cEnd = new THREE.Vector3(...seg.cam_end);
  const lStart = new THREE.Vector3(...seg.look_start);
  const lEnd = new THREE.Vector3(...seg.look_end);

  const camPos = cStart.lerp(cEnd, eased);
  const lookAt = lStart.lerp(lEnd, eased);

  // Smooth bridge into next segment during inter-segment / inter-slide pause
  if (nextSeg && t > seg.end_s) {
    const pauseSpan = Math.max(0.05, seg.hold_end_s - seg.end_s);
    const bridgeT = smoothstep((t - seg.end_s) / pauseSpan);
    camPos.lerp(new THREE.Vector3(...nextSeg.cam_start), bridgeT);
    lookAt.lerp(new THREE.Vector3(...nextSeg.look_start), bridgeT);
  }

  return {
    slideNumber: seg.slide_number,
    spoken: seg.spoken,
    tau,
    visualMode: seg.visual_mode,
    segFrac: rawFrac,
    camPos,
    lookAt
  };
}

// ---- Interactive Controls (Audio, Sliders, Free-Roam Orbit + WASD) ----------
const audioEl = document.getElementById('voiceover-audio');
if (SPEC.timeline && SPEC.timeline.master_wav_url && !IS_CAPTURE) {
  audioEl.src = SPEC.timeline.master_wav_url;
}

let isPlaying = false;
let manualTimeS = 0.0;
let manualTauOverride = null;
let morphAnimActive = false;
let morphAnimStartMs = 0;
let morphFromTau = 0;
let morphToTau = 1;
let forceFarFoot = false;
let userDetachedCam = false;

// Orbit & WASD state
let camSpherical = new THREE.Spherical(3.8, 1.05, 0.12);
const keysDown = new Set();
let isDragging = false, lastMouseX = 0, lastMouseY = 0;

function syncOrbitFromCurrentCam() {
  const offset = camera.position.clone().sub(camTarget);
  camSpherical.setFromVector3(offset);
}

const btnPlay = document.getElementById('btn-play');
const btnMorph = document.getElementById('btn-morph');
const btnFarFoot = document.getElementById('btn-farfoot');
const btnReattach = document.getElementById('btn-reattach');
const timelineSlider = document.getElementById('timeline-slider');
const morphSlider = document.getElementById('morph-slider');
const timeReadout = document.getElementById('time-readout');
const subtitleBanner = document.getElementById('subtitle-banner');

function fmtTime(sec) {
  const s = Math.max(0, Math.floor(sec));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

// Populate Slide Pills
const pillsWrap = document.getElementById('slide-pills');
for (const sl of SPEC.slides) {
  const b = document.createElement('button');
  b.className = 'slide-pill';
  b.dataset.slide = sl.slide_number;
  b.textContent = sl.slide_number === 6 ? '6 · Sphere' : `${sl.slide_number}`;
  b.title = sl.title;
  b.addEventListener('click', () => {
    const firstSeg = timelineSegs.find(x => x.slide_number === sl.slide_number);
    if (firstSeg) {
      manualTauOverride = null;
      morphAnimActive = false;
      manualTimeS = firstSeg.start_s;
      if (audioEl.src) audioEl.currentTime = manualTimeS;
    }
  });
  pillsWrap.appendChild(b);
}

btnPlay.addEventListener('click', async () => {
  if (!isPlaying) {
    manualTauOverride = null;
    if (manualTimeS >= totalDurationS - 0.5) {
      manualTimeS = 0;
      if (audioEl.src) audioEl.currentTime = 0;
    }
    if (audioEl.src) {
      audioEl.currentTime = manualTimeS;
      try { await audioEl.play(); } catch (_) {}
    }
    isPlaying = true;
    btnPlay.textContent = '⏸ Pause';
  } else {
    isPlaying = false;
    if (audioEl.src) audioEl.pause();
    btnPlay.textContent = '▶ Resume Tour';
  }
});

audioEl.addEventListener('ended', () => {
  isPlaying = false;
  btnPlay.textContent = '↺ Replay Tour';
});

timelineSlider.addEventListener('input', () => {
  manualTauOverride = null;
  morphAnimActive = false;
  manualTimeS = (Number(timelineSlider.value) / 1000) * totalDurationS;
  if (audioEl.src) audioEl.currentTime = manualTimeS;
});

morphSlider.addEventListener('input', () => {
  morphAnimActive = false;
  manualTauOverride = Number(morphSlider.value) / 1000;
});

btnMorph.addEventListener('click', () => {
  const curVal = Number(morphSlider.value) / 1000;
  morphFromTau = curVal;
  morphToTau = curVal > 0.5 ? 0.0 : 1.0;
  morphAnimStartMs = performance.now();
  morphAnimActive = true;
});

btnFarFoot.addEventListener('click', () => {
  forceFarFoot = !forceFarFoot;
  btnFarFoot.classList.toggle('active-toggle', forceFarFoot);
  if (forceFarFoot && (manualTauOverride === null ? evaluateTimelineState(manualTimeS).tau : manualTauOverride) < 0.9) {
    manualTauOverride = 1.0;
    morphSlider.value = '1000';
  }
});

btnReattach.addEventListener('click', () => {
  userDetachedCam = false;
  btnReattach.style.display = 'none';
});

// Pointer Orbit + Wheel Zoom + WASD Free Flight
canvas.addEventListener('pointerdown', (e) => {
  if (IS_CAPTURE) return;
  isDragging = true;
  lastMouseX = e.clientX; lastMouseY = e.clientY;
  if (!userDetachedCam) {
    syncOrbitFromCurrentCam();
    userDetachedCam = true;
    btnReattach.style.display = 'inline-block';
  }
});
window.addEventListener('pointermove', (e) => {
  if (!isDragging) return;
  const dx = e.clientX - lastMouseX, dy = e.clientY - lastMouseY;
  lastMouseX = e.clientX; lastMouseY = e.clientY;
  camSpherical.theta -= dx * 0.0055;
  camSpherical.phi = Math.max(0.14, Math.min(Math.PI * 0.49, camSpherical.phi - dy * 0.0055));
});
window.addEventListener('pointerup', () => { isDragging = false; });
canvas.addEventListener('wheel', (e) => {
  if (IS_CAPTURE) return;
  e.preventDefault();
  if (!userDetachedCam) {
    syncOrbitFromCurrentCam();
    userDetachedCam = true;
    btnReattach.style.display = 'inline-block';
  }
  camSpherical.radius = Math.max(1.25, Math.min(14.0, camSpherical.radius + e.deltaY * 0.0035));
}, { passive: false });

window.addEventListener('keydown', (e) => {
  if (IS_CAPTURE) return;
  const k = e.key.toLowerCase();
  if (['w','a','s','d','q','e','arrowup','arrowdown','arrowleft','arrowright'].includes(k)) {
    keysDown.add(k);
    if (!userDetachedCam) {
      syncOrbitFromCurrentCam();
      userDetachedCam = true;
      btnReattach.style.display = 'inline-block';
    }
  }
});
window.addEventListener('keyup', (e) => keysDown.delete(e.key.toLowerCase()));

function applyFreeCameraStep(dt) {
  const speed = 2.8 * dt;
  const forward = new THREE.Vector3();
  camera.getWorldDirection(forward);
  forward.y = 0;
  if (forward.lengthSq() > 1e-6) forward.normalize();
  const right = new THREE.Vector3().crossVectors(forward, new THREE.Vector3(0, 1, 0)).normalize();

  if (keysDown.has('w') || keysDown.has('arrowup')) camTarget.addScaledVector(forward, speed);
  if (keysDown.has('s') || keysDown.has('arrowdown')) camTarget.addScaledVector(forward, -speed);
  if (keysDown.has('d') || keysDown.has('arrowright')) camTarget.addScaledVector(right, speed);
  if (keysDown.has('a') || keysDown.has('arrowleft')) camTarget.addScaledVector(right, -speed);
  if (keysDown.has('e')) camTarget.y = Math.min(4.5, camTarget.y + speed * 0.7);
  if (keysDown.has('q')) camTarget.y = Math.max(0.0, camTarget.y - speed * 0.7);

  const offset = new THREE.Vector3().setFromSpherical(camSpherical);
  camera.position.copy(camTarget).add(offset);
  camera.lookAt(camTarget);
}

// ---- Deterministic Render State Function ------------------------------------
function renderAtTime(tSec, dt = 0.016) {
  const st = evaluateTimelineState(tSec);
  setActiveSlideUI(st.slideNumber);

  if (st.spoken) {
    subtitleBanner.textContent = st.spoken;
  }

  let effectiveTau = st.tau;
  if (morphAnimActive) {
    const u = clamp01((performance.now() - morphAnimStartMs) / 3600);
    effectiveTau = morphFromTau + (morphToTau - morphFromTau) * smoothstep(u);
    manualTauOverride = effectiveTau;
    if (u >= 1) morphAnimActive = false;
  } else if (manualTauOverride !== null) {
    effectiveTau = manualTauOverride;
  }

  let effectiveMode = st.visualMode;
  if (manualTauOverride !== null && manualTauOverride > 0.65 && !effectiveMode.startsWith('sphere')) {
    effectiveMode = 'sphere_picture_holds';
  }

  if (!IS_CAPTURE) {
    timelineSlider.value = String(Math.round((tSec / Math.max(0.1, totalDurationS)) * 1000));
    morphSlider.value = String(Math.round(effectiveTau * 1000));
    timeReadout.textContent = `${fmtTime(tSec)} / ${fmtTime(totalDurationS)}`;
  }

  updateSceneGeometry(effectiveTau, effectiveMode, st.segFrac, forceFarFoot);

  if (!userDetachedCam || IS_CAPTURE) {
    if (manualTauOverride !== null && !IS_CAPTURE && manualTauOverride > 0.4 && st.tau < 0.2) {
      // Adjust camera smoothly up when user manually morphs to sphere on earlier slides
      const sphereLook = new THREE.Vector3(0, 1.55, 0);
      const sphereCam = new THREE.Vector3(0.45, 2.15, 4.65);
      camTarget.copy(st.lookAt).lerp(sphereLook, smoothstep(manualTauOverride));
      camera.position.copy(st.camPos).lerp(sphereCam, smoothstep(manualTauOverride));
    } else {
      camTarget.copy(st.lookAt);
      camera.position.copy(st.camPos);
    }
    camera.lookAt(camTarget);
  } else {
    applyFreeCameraStep(dt);
  }

  renderer.render(scene, camera);
  projectLabels();
}

// Expose deterministic capture hook for headless Chrome video & seed exporter
window.setVirtualWorldTime = (tSec, opts = {}) => {
  manualTimeS = tSec;
  manualTauOverride = (opts.tau !== undefined) ? opts.tau : null;
  forceFarFoot = !!opts.farFoot;
  if (opts.hideHud !== undefined) {
    const disp = opts.hideHud ? 'none' : '';
    document.getElementById('slide-hud').style.display = disp;
    document.getElementById('telemetry-hud').style.display = disp;
    document.getElementById('subtitle-banner').style.display = disp;
    document.getElementById('labels-layer').style.display = disp;
  }
  renderAtTime(tSec, 0);
  if (opts.camPos && opts.lookAt) {
    camera.position.set(...opts.camPos);
    camTarget.set(...opts.lookAt);
    camera.lookAt(camTarget);
    renderer.render(scene, camera);
  }
  return true;
};

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderAtTime(manualTimeS, 0);
});

// Load optional AI skybox texture before declaring __worldReady
async function initWorld() {
  if (SPEC.timeline && SPEC.timeline.skybox_url) {
    await new Promise((resolve) => {
      const loader = new THREE.TextureLoader();
      loader.load(
        SPEC.timeline.skybox_url,
        (tex) => {
          tex.colorSpace = THREE.SRGBColorSpace;
          tex.mapping = THREE.EquirectangularReflectionMapping;
          skyMat.map = tex;
          skyMat.color.set('#ffffff');
          skyMat.needsUpdate = true;
          scene.environment = tex;
          resolve();
        },
        undefined,
        () => resolve()
      );
    });
  }
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
      renderAtTime(manualTimeS, dt);
      requestAnimationFrame(animate);
    }
    requestAnimationFrame(animate);
  }
}
initWorld();
</script>
</body>
</html>
"""
