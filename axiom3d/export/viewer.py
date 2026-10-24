"""A self-contained HTML viewer: play an axiom3d animation, or turn a static model, in any browser."""

from __future__ import annotations

import base64
import html
import tempfile
from pathlib import Path
from string import Template

import numpy as np

from axiom3d.conventions import zup_to_yup
from axiom3d.export.gltf import export_glb, export_mesh_glb

THREE_MODULE = "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js"
THREE_ADDONS = "https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/"

_STANDALONE_HEAD = (
    '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
)

_PAGE = Template(r"""<title>$title</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;700&family=JetBrains+Mono:wght@400;600&display=swap">
<style>
/* Layout: one-screen instrument — header strip, stage that fills the rest, transport bar pinned under it. */
:root {
  --bg: #eef1f4; --panel: #ffffff; --fg: #1b232b; --muted: #5d6a76; --line: #d3dae1; --accent: #2f3d4a;
  --left: #4285f4; --right: #f48c28; --stage: #e4e9ee;
  --display: "Archivo", "Helvetica Neue", Arial, sans-serif;
  --mono: "JetBrains Mono", ui-monospace, "SFMono-Regular", Menlo, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #11161b; --panel: #182028; --fg: #e3e9ef; --muted: #93a1ae; --line: #2a3540; --accent: #c9d4de;
  --stage: #0c1115; color-scheme: dark } }
:root[data-theme="dark"] {
  --bg: #11161b; --panel: #182028; --fg: #e3e9ef; --muted: #93a1ae; --line: #2a3540; --accent: #c9d4de;
  --stage: #0c1115; color-scheme: dark }
html, body { height: 100%; }
[hidden] { display: none !important; }
body { margin: 0; background: var(--bg); color: var(--fg); font-family: var(--display); display: flex; flex-direction: column;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px));
  padding-block: 12px; gap: 12px; box-sizing: border-box; }
header { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 6px 16px; }
h1 { font-size: 1.15rem; font-weight: 700; margin: 0; letter-spacing: 0.01em; text-wrap: balance; }
.meta { font-family: var(--mono); font-size: 0.75rem; color: var(--muted); display: flex; gap: 12px; flex-wrap: wrap; }
.stage { position: relative; flex: 1; min-height: 260px; border: 1px solid var(--line); border-radius: 6px;
  background: var(--stage); overflow: hidden; }
canvas { display: block; width: 100%; height: 100%; touch-action: none; }
.legend { position: absolute; left: 10px; top: 10px; right: 10px; display: flex; flex-wrap: wrap; gap: 8px;
  font-family: var(--mono); font-size: 0.72rem; pointer-events: none; }
.chip { display: inline-flex; align-items: center; gap: 6px; padding: 3px 8px; border-radius: 999px;
  background: var(--panel); border: 1px solid var(--line); color: var(--fg); }
.dot { width: 9px; height: 9px; border-radius: 50%; }
.notice { position: absolute; inset: 0; display: grid; place-items: center; padding: 24px; text-align: center;
  color: var(--muted); font-size: 0.9rem; }
.transport { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 14px; background: var(--panel);
  border: 1px solid var(--line); border-radius: 6px; padding: 10px 12px; }
button { font: 600 0.85rem var(--display); color: var(--panel); background: var(--accent); border: 0;
  border-radius: 4px; padding: 8px 14px; min-width: 76px; cursor: pointer; }
button:focus-visible, input:focus-visible { outline: 2px solid var(--left); outline-offset: 2px; }
input[type=range] { flex: 1 1 180px; min-width: 0; accent-color: var(--accent); }
.readout { font-family: var(--mono); font-size: 0.8rem; font-variant-numeric: tabular-nums; color: var(--fg); white-space: nowrap; }
.readout span { color: var(--muted); }
</style>

<header>
  <h1>$title</h1>
  <div class="meta">$meta</div>
</header>
<div class="stage" id="stage">
  <canvas id="view" aria-label="$aria; drag to orbit, pinch or scroll to zoom"></canvas>
  <div class="legend">$legend</div>
  <div class="notice" id="notice">Loading the 3D view…</div>
</div>
<div class="transport"$transport_attr>
  <button id="play" type="button">Pause</button>
  <input id="scrub" type="range" min="0" max="$end" step="1" value="0" aria-label="Frame">
  <div class="readout"><span>frame</span> <b id="frame" data-frame="0">0</b> <span>/ $end ·</span> <b id="secs">0.00</b><span> s</span></div>
</div>

<script type="application/octet-stream" id="glb">$glb</script>
<script type="importmap">{"imports": {"three": "$three_module", "three/addons/": "$three_addons"}}</script>
<script>
  setTimeout(function () {
    if (!window.__axiomViewerReady) {
      document.getElementById("notice").textContent = "The 3D library didn't load. Check your connection and reload the page.";
    }
  }, 8000);
</script>
<script type="module">
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const FPS = $fps, END = $end;
const FRAME_CENTER = [$cx, $cy, $cz], FRAME_RADIUS = $radius;
const stage = document.getElementById("stage"), canvas = document.getElementById("view");
const playBtn = document.getElementById("play"), scrub = document.getElementById("scrub");
const frameEl = document.getElementById("frame"), secsEl = document.getElementById("secs");
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(40, 1, 0.05, 100);
const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
scene.add(new THREE.HemisphereLight(0xffffff, 0x8a96a3, 1.6));
const sun = new THREE.DirectionalLight(0xffffff, 1.6);
sun.position.set(2.5, 4, 3);
scene.add(sun);
const grid = new THREE.GridHelper($grid_size, $grid_div);
scene.add(grid);

function paintTheme() {
  scene.background = new THREE.Color(css("--stage"));
  grid.material.color = new THREE.Color(css("--line"));
}
paintTheme();
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", paintTheme);
new MutationObserver(paintTheme).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

// Fit the whole motion (all frames), from the front-left and above, for any screen shape.
const target = new THREE.Vector3(...FRAME_CENTER);
let userMoved = false;
controls.addEventListener("start", () => { userMoved = true; controls.autoRotate = false; });
function frameMotion() {
  const v = THREE.MathUtils.degToRad(camera.fov);
  const h = 2 * Math.atan(Math.tan(v / 2) * camera.aspect);
  const dist = 1.05 * FRAME_RADIUS / Math.sin(Math.min(v, h) / 2);
  controls.target.copy(target);
  camera.position.copy(target).addScaledVector(new THREE.Vector3(0.75, 0.38, 0.95).normalize(), dist);
}
function resize() {
  const w = stage.clientWidth, h = stage.clientHeight;
  renderer.setSize(w, h, false);
  camera.aspect = w / Math.max(h, 1);
  camera.updateProjectionMatrix();
  if (!userMoved) frameMotion();
}
new ResizeObserver(resize).observe(stage);

const raw = atob(document.getElementById("glb").textContent.replace(/\s+/g, ""));
const bytes = new Uint8Array(raw.length);
for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);

let mixer = null, action = null;
let playing = !matchMedia("(prefers-reduced-motion: reduce)").matches;
playBtn.textContent = playing ? "Pause" : "Play";

function show(frame) {
  frameEl.textContent = String(frame);
  frameEl.dataset.frame = String(frame);
  secsEl.textContent = (frame / FPS).toFixed(2);
  scrub.value = String(frame);
}

new GLTFLoader().parse(bytes.buffer, "", (gltf) => {
  scene.add(gltf.scene);
  grid.position.set(target.x, 0, target.z);
  if (gltf.animations.length) {
    mixer = new THREE.AnimationMixer(gltf.scene);
    action = mixer.clipAction(gltf.animations[0]);
    action.play();
  } else if (playing) {
    controls.autoRotate = true;  // a static model turns slowly until touched
    controls.autoRotateSpeed = 1.2;
  }
  document.getElementById("notice").hidden = true;
  window.__axiomViewerReady = true;
  resize();
}, (err) => {
  document.getElementById("notice").textContent = "This animation file couldn't be read: " + err.message;
});

playBtn.addEventListener("click", () => {
  playing = !playing;
  playBtn.textContent = playing ? "Pause" : "Play";
});
scrub.addEventListener("input", () => {
  playing = false;
  playBtn.textContent = "Play";
  if (mixer) mixer.setTime(Number(scrub.value) / FPS);
  show(Number(scrub.value));
});

const clock = new THREE.Clock();
renderer.setAnimationLoop(() => {
  const dt = clock.getDelta();
  if (mixer && playing) {
    mixer.update(dt);
    const t = action.time % ((END + 1) / FPS);
    show(Math.min(END, Math.round(t * FPS)));
  }
  controls.update();
  renderer.render(scene, camera);
});
</script>
""")


def _motion_bounds(states) -> tuple[list[float], float]:
    """Centre and radius of every point over every frame, in the viewer's Y-up frame."""
    pts = np.array([zup_to_yup(p) for s in states for p in s.points.values()])
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    return [float(v) for v in (lo + hi) / 2], float(np.linalg.norm(hi - lo) / 2)


def _page(glb: bytes, centre, radius: float, standalone: bool, **fields) -> str:
    encoded = base64.b64encode(glb).decode("ascii")
    wrapped = "\n".join(encoded[i:i + 120] for i in range(0, len(encoded), 120))
    page = _PAGE.substitute(
        glb=wrapped, three_module=THREE_MODULE, three_addons=THREE_ADDONS,
        cx=f"{centre[0]:.3f}", cy=f"{centre[1]:.3f}", cz=f"{centre[2]:.3f}", radius=f"{radius:.3f}", **fields,
    )
    return _STANDALONE_HEAD + page + "</html>\n" if standalone else page


def _spans(items) -> str:
    return "".join(f"<span>{html.escape(str(i))}</span>" for i in items)


def viewer_html(skel, clip, states, title: str, task: str, standalone: bool = True) -> str:
    centre, radius = _motion_bounds(states)
    with tempfile.TemporaryDirectory() as tmp:
        glb = export_glb(skel, clip, states, Path(tmp) / "clip.glb").read_bytes()
    end = clip.timeline.end
    legend = ('<span class="chip"><span class="dot" style="background:var(--left)"></span>LEFT</span>'
              '<span class="chip"><span class="dot" style="background:var(--right)"></span>RIGHT</span>')
    return _page(glb, centre, radius, standalone, title=html.escape(title), fps=clip.timeline.fps, end=end,
                 meta=_spans([f"task {task}", f"{clip.timeline.fps} fps", f"frames 0–{end}", "grid 0.5 m", "Y-up view"]),
                 aria="3D view of the animation", legend=legend, transport_attr="", grid_size=6, grid_div=12)


def mesh_viewer_html(mesh, colors, title: str, task: str, facts=(), standalone: bool = True) -> str:
    """A static model (no transport bar) that turns slowly; `facts` show as chips over the view."""
    pts = np.array([zup_to_yup(p) for p in mesh.vertices.astype(float)])
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    with tempfile.TemporaryDirectory() as tmp:
        glb = export_mesh_glb(mesh, colors, Path(tmp) / "model.glb").read_bytes()
    legend = "".join(f'<span class="chip">{html.escape(str(f))}</span>' for f in facts)
    return _page(glb, (lo + hi) / 2, float(np.linalg.norm(hi - lo) / 2), standalone, title=html.escape(title),
                 fps=24, end=0, meta=_spans([f"task {task}", "static model", "grid 0.1 m", "Y-up view"]),
                 aria="3D view of the model", legend=legend, transport_attr=" hidden", grid_size=1, grid_div=10)


def export_html(skel, clip, states, path: Path, title: str, task: str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(viewer_html(skel, clip, states, title, task), encoding="utf-8")
    return path
