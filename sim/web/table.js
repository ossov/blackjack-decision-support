// Draws the simulated table in 3D (three.js) with a flat overlay for bubbles, names and buttons.
// The camera is fitted to the team's table recording (config/layout_sim.json), so the table,
// seats, shoe and discard tray sit where they do in the footage. The game runs in Python;
// this page only draws /api/state and sends button presses.
import * as THREE from "/vendor/three.module.min.js";

const W = 1920, H = 1080;
const glCanvas = document.getElementById("gl");
const overlay = document.getElementById("overlay");
const ctx = overlay.getContext("2d");
const exportCanvas = document.createElement("canvas");
exportCanvas.width = W; exportCanvas.height = H;

let L = null, S = null;
let hits = [], cardBoxes = [], bubbleLabels = [], lastCardKey = "", exporting = false;

const FONT = '"Roboto", "Helvetica Neue", Arial, sans-serif';
const SUIT = { S: "♠", H: "♥", D: "♦", C: "♣" };
const RED = { H: true, D: true };
const CHIP_VALUES = [1, 2.5, 5, 10, 20, 50, 200, 1000];
const CHIP_COLOURS = {
  1: ["#ececec", "#2f8f45"], 2.5: ["#58c4c8", "#ffffff"], 5: ["#d2a63c", "#ffffff"],
  10: ["#f4f1ea", "#e2702a"], 20: ["#8b45b3", "#ffffff"], 50: ["#c23a31", "#ffffff"],
  200: ["#2f9a52", "#ffffff"], 1000: ["#c8d43c", "#ffffff"],
};
const rad = (d) => (d * Math.PI) / 180;
const fmt = (v) => (Math.round(v * 100) / 100).toLocaleString("en-US", { maximumFractionDigits: 2 });
const money = (v) => "$" + v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

// ---------------------------------------------------------------- renderer and camera

const renderer = new THREE.WebGLRenderer({ canvas: glCanvas, antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(1);
renderer.setSize(W, H, false);
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.toneMapping = THREE.NoToneMapping;
const MAX_ANISO = renderer.capabilities.getMaxAnisotropy();

const scene = new THREE.Scene();
// Everything on the table lives in `world`, mirrored in x so that +x is the viewer's right
// (three.js cameras looking along +z have +x on the left).
const world = new THREE.Group();
world.scale.x = -1;
scene.add(world);
const camera = new THREE.PerspectiveCamera(63, W / H, 2, 5000);
const raycaster = new THREE.Raycaster();

// The page renders the whole 16:9 video frame (W x H). Layout positions are in "layout units":
// pixels of the 1920x1080 table crop measured from the recording. K and the frame origin convert them.
let K = 1, OX = 0, OY = 0;
const FX = (x) => (x - OX) * K, FY = (y) => (y - OY) * K;

function setupCamera() {
  const c = L.camera;
  [OX, OY] = L.video.origin;
  K = H / L.video.size[1];
  const f = (1080 / 2) / Math.tan(rad(c.fov) / 2) * K;      // focal length in frame pixels
  camera.fov = 2 * Math.atan((H / 2) / f) * 180 / Math.PI;
  const [px, py, pz] = c.position;
  camera.position.set(-px, py, pz);
  const a = rad(c.pitch);
  camera.lookAt(-px, py - Math.sin(a), pz + Math.cos(a));
  // put the optical centre where the footage has it
  camera.setViewOffset(W, H, W / 2 - FX(c.principal[0]), H / 2 - FY(c.principal[1]), W, H);
  camera.updateProjectionMatrix();
  camera.updateMatrixWorld();
}

// Layout position -> point on the table (height h, cm).
function toTable(lx, ly, h = 0) {
  const px = FX(lx), py = FY(ly);
  raycaster.setFromCamera(new THREE.Vector2((px / W) * 2 - 1, -((py / H) * 2 - 1)), camera);
  const plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), -h);
  const p = new THREE.Vector3();
  raycaster.ray.intersectPlane(plane, p);
  p.x = -p.x;                                // into world (mirrored) coordinates
  return p;
}

function toScreen(v) {
  const p = v.clone().project(camera);       // v is in scene coordinates
  return [(p.x + 1) / 2 * W, (1 - p.y) / 2 * H];
}

function canvasTexture(c, mirrored = false) {
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = MAX_ANISO;
  if (mirrored) {           // objects inside the mirrored `world` group need their pictures flipped back
    t.wrapS = THREE.RepeatWrapping;
    t.repeat.x = -1;
  }
  return t;
}

function roundRect(c, x, y, w, h, r) {
  c.beginPath();
  c.moveTo(x + r, y);
  c.arcTo(x + w, y, x + w, y + h, r);
  c.arcTo(x + w, y + h, x, y + h, r);
  c.arcTo(x, y + h, x, y, r);
  c.arcTo(x, y, x + w, y, r);
  c.closePath();
}

// ---------------------------------------------------------------- felt and its printing

const TEX = 4096, SPAN = 230;               // felt texture covers x and z in [-115, 115] cm
const k = TEX / SPAN;
let seatWorld = {};                          // seat -> {x, z, turn}

function feltTexture() {
  const c = document.createElement("canvas");
  c.width = c.height = TEX;
  const g = c.getContext("2d");
  // world cm -> texture pixels; +z (towards the dealer) is up in the texture
  g.setTransform(k, 0, 0, k, TEX / 2, TEX / 2);
  const grad = g.createRadialGradient(0, 0, 10, 0, 0, 115);
  grad.addColorStop(0, "#7a3c80");
  grad.addColorStop(0.7, "#6c3272");
  grad.addColorStop(1, "#5c2a62");
  g.fillStyle = grad;
  g.fillRect(-115, -115, 230, 230);
  // subtle cloth grain
  g.globalAlpha = 0.05;
  for (let i = 0; i < 9000; i++) {
    g.fillStyle = Math.random() < 0.5 ? "#000" : "#fff";
    g.fillRect(Math.random() * 230 - 115, Math.random() * 230 - 115, 0.25, 0.25);
  }
  g.globalAlpha = 1;
  const ink = "rgba(238,228,244,0.86)";
  const z = (v) => -v;                       // texture y = -world z

  // Printed arcs: circles centred behind the dealer edge.
  const cz = 42;
  const arcText = (str, r, size, weight, spacing = 1) => {
    g.save();
    g.font = `${weight} ${size}px ${FONT}`;
    g.fillStyle = ink; g.textAlign = "center"; g.textBaseline = "middle";
    const widths = [...str].map((ch) => g.measureText(ch).width * spacing);
    const total = widths.reduce((a, b) => a + b, 0);
    let a = -total / 2 / r;
    for (let i = 0; i < str.length; i++) {
      const phi = a + widths[i] / 2 / r;    // angle from straight towards the players
      g.save();
      g.translate(r * Math.sin(phi), z(cz - r * Math.cos(phi)));
      g.rotate(-phi);
      g.fillText(str[i], 0, 0);
      g.restore();
      a += widths[i] / r;
    }
    g.restore();
  };
  // outlined band with rounded ends (canvas angle pi/2 points towards the players)
  g.save();
  g.strokeStyle = ink; g.lineWidth = 0.45;
  const r1 = 95.5, r2 = 116, half = rad(34), rm = (r1 + r2) / 2, rc = (r2 - r1) / 2, cy = z(cz);
  g.beginPath();
  g.arc(0, cy, r1, Math.PI / 2 + half, Math.PI / 2 - half, true);
  g.arc(rm * Math.sin(half), cy + rm * Math.cos(half), rc, 1.5 * Math.PI - half, 2.5 * Math.PI - half, false);
  g.arc(0, cy, r2, Math.PI / 2 - half, Math.PI / 2 + half, false);
  g.arc(-rm * Math.sin(half), cy + rm * Math.cos(half), rc, Math.PI / 2 + half, 1.5 * Math.PI + half, false);
  g.closePath();
  g.stroke();
  g.restore();
  arcText("BLACKJACK PAYS 3 TO 2", 101, 5.4, "bold", 1.04);
  arcText("Dealer must draw to 16 and stand on all 17's", 106, 3.6, "normal", 1.02);
  arcText("INSURANCE PAYS 2 TO 1", 112, 5.0, "bold", 1.04);
  // a plain table name where a casino would print its logo
  g.save();
  g.font = `bold 6px ${FONT}`; g.fillStyle = "rgba(238,228,244,0.6)"; g.textAlign = "center";
  g.fillText("SIMULATED TABLE", 0, z(-49.5));
  g.restore();

  // Seat boxes: traced from the footage (their corners are back-projected onto the felt),
  // each with a bet circle and side-bet segments (printed only).
  for (const [n, s] of Object.entries(seatWorld)) {
    const pts = s.corners.map((p) => [p.x, z(p.z)]);
    g.save();
    g.strokeStyle = "rgba(238,228,244,0.6)"; g.lineWidth = 0.4;
    g.beginPath();
    for (let i = 0; i < 4; i++) {
      const a = pts[i], b = pts[(i + 1) % 4], m = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
      if (i === 0) g.moveTo(...m);
      const nb = pts[(i + 1) % 4], nn = pts[(i + 2) % 4];
      g.arcTo(nb[0], nb[1], (nb[0] + nn[0]) / 2, (nb[1] + nn[1]) / 2, 2.2);
    }
    g.closePath(); g.stroke();
    // bet circle, oriented with the box
    const rr = s.ring;
    g.translate(s.x, z(s.z));
    g.rotate(-s.turn);
    g.lineWidth = 0.3;
    g.beginPath(); g.arc(0, 0, rr, 0, Math.PI * 2); g.stroke();
    g.beginPath(); g.arc(0, 0, rr * 0.55, 0, Math.PI * 2); g.stroke();
    for (const a of [rad(25), rad(155), rad(-60), rad(-120)]) {
      g.beginPath(); g.moveTo(Math.cos(a) * rr * 0.55, Math.sin(a) * rr * 0.55);
      g.lineTo(Math.cos(a) * rr, Math.sin(a) * rr); g.stroke();
    }
    g.fillStyle = "rgba(238,228,244,0.2)";
    g.beginPath(); g.arc(0, 0, rr, rad(25), rad(155)); g.arc(0, 0, rr * 0.55, rad(155), rad(25), true); g.fill();
    const label = (str, a, size) => {
      g.save(); g.rotate(a); g.translate(0, -(rr * 0.78));
      g.font = `bold ${size}px ${FONT}`; g.fillStyle = "rgba(238,228,244,0.65)";
      g.textAlign = "center"; g.textBaseline = "middle"; g.fillText(str, 0, 0); g.restore();
    };
    label("21+3", rad(28), rr * 0.2);
    label("TOP-3", rad(95), rr * 0.18);
    label("PLAYER PAIR", rad(-62), rr * 0.15);
    g.save(); g.translate(0, rr * 0.78); g.font = `bold ${rr * 0.17}px ${FONT}`; g.fillStyle = "rgba(238,228,244,0.7)";
    g.textAlign = "center"; g.textBaseline = "middle"; g.fillText("BET BEHIND", 0, 0); g.restore();
    g.restore();
  }
  return canvasTexture(c);
}

function buildTable() {
  const R = L.world.felt_radius, RZ = L.world.felt_depth || R, ez = L.world.dealer_edge_z;
  const phi0 = Math.acos(ez / RZ);
  // felt outline: the arc towards the players, closed by the dealer's straight edge
  const shape = new THREE.Shape();
  const N = 160;
  for (let i = 0; i <= N; i++) {
    const phi = phi0 + (i / N) * (2 * Math.PI - 2 * phi0);
    const x = R * Math.sin(phi), z = RZ * Math.cos(phi);
    if (i === 0) shape.moveTo(x, -z); else shape.lineTo(x, -z);
  }
  shape.closePath();
  const geo = new THREE.ShapeGeometry(shape, 64);
  geo.rotateX(-Math.PI / 2);
  const pos = geo.attributes.position, uv = geo.attributes.uv;
  for (let i = 0; i < pos.count; i++) {
    uv.setXY(i, (pos.getX(i) + SPAN / 2) / SPAN, (pos.getZ(i) + SPAN / 2) / SPAN);
  }
  const felt = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ map: feltTexture(), roughness: 0.96, metalness: 0 }));
  felt.receiveShadow = true;
  world.add(felt);

  // padded armrest along the curved edge
  const rim = L.world.rim.radius;
  const pts = [];
  for (let i = 0; i <= N; i++) {
    const phi = phi0 - 0.02 + (i / N) * (2 * Math.PI - 2 * phi0 + 0.04);
    pts.push(new THREE.Vector3((R + rim) * Math.sin(phi), rim * 0.55, (RZ + rim) * Math.cos(phi)));
  }
  const curve = new THREE.CatmullRomCurve3(pts);
  const leather = new THREE.MeshStandardMaterial({ color: 0x0c0c10, roughness: 0.42, metalness: 0.05 });
  const tube = new THREE.Mesh(new THREE.TubeGeometry(curve, 300, rim, 24, false), leather);
  tube.scale.y = 0.85;
  tube.castShadow = tube.receiveShadow = true;
  world.add(tube);

  // body of the table under the felt
  const body = new THREE.Shape();
  for (let i = 0; i <= N; i++) {
    const phi = phi0 + (i / N) * (2 * Math.PI - 2 * phi0);
    const x = (R + rim * 1.15) * Math.sin(phi), z = (RZ + rim * 1.15) * Math.cos(phi);
    if (i === 0) body.moveTo(x, -z); else body.lineTo(x, -z);
  }
  body.closePath();
  const bgeo = new THREE.ExtrudeGeometry(body, { depth: 22, bevelEnabled: false, curveSegments: 64 });
  bgeo.rotateX(-Math.PI / 2);
  const bmesh = new THREE.Mesh(bgeo, new THREE.MeshStandardMaterial({ color: 0x101016, roughness: 0.7 }));
  bmesh.position.y = -22.2;
  world.add(bmesh);
  // the dealer's side of the table, behind the felt
  const ledge = new THREE.Mesh(new THREE.BoxGeometry(2 * R + 20, 2.5, 26),
    new THREE.MeshStandardMaterial({ color: 0x15151c, roughness: 0.6 }));
  ledge.position.set(0, 0.8, ez + 13);
  ledge.receiveShadow = true;
  world.add(ledge);
}

function buildRoom() {
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(3000, 3000),
    new THREE.MeshBasicMaterial({ color: 0x3c3d46 }));
  floor.rotation.x = -Math.PI / 2; floor.position.y = -90;
  floor.receiveShadow = true;
  world.add(floor);
  // back wall with plain light panels (no branding)
  const c = document.createElement("canvas"); c.width = 2048; c.height = 512;
  const g = c.getContext("2d");
  const bg = g.createLinearGradient(0, 0, 0, 512); bg.addColorStop(0, "#04081f"); bg.addColorStop(1, "#0b1030");
  g.fillStyle = bg; g.fillRect(0, 0, 2048, 512);
  const panel = (x, w, col) => { const p = g.createLinearGradient(x, 0, x + w, 512); p.addColorStop(0, col); p.addColorStop(1, "#0d1438"); g.fillStyle = p; g.fillRect(x, 40, w, 400); };
  panel(1180, 300, "#1d3f7a"); panel(1530, 90, "#2f2a6e"); panel(520, 120, "#1a3266");
  g.fillStyle = "rgba(90,170,255,0.9)"; g.fillRect(0, 470, 2048, 6);
  const wall = new THREE.Mesh(new THREE.PlaneGeometry(1400, 350), new THREE.MeshBasicMaterial({ map: canvasTexture(c) }));
  wall.position.set(0, 60, 420);
  wall.rotation.y = Math.PI;
  world.add(wall);
  // light panels in the studio (plain shapes, no branding)
  for (const [x, w, h, col] of [[200, 120, 200, 0x15305e], [-190, 40, 170, 0x1d1b4a], [440, 26, 220, 0x12405a]]) {
    const panel = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ color: col }));
    panel.position.set(x, 40 + h / 2 - 60, 380); panel.rotation.y = Math.PI; world.add(panel);
  }
  // lights
  world.add(new THREE.HemisphereLight(0xd8d4ff, 0x505058, 1.05));
  const key = new THREE.SpotLight(0xffffff, 52000, 0, rad(45), 0.8, 2);
  key.position.set(0, 260, -40);
  key.target.position.set(0, 0, -45);
  key.castShadow = true;
  key.shadow.mapSize.set(2048, 2048);
  key.shadow.bias = -0.0004;
  key.shadow.radius = 4;
  world.add(key, key.target);
  const fill = new THREE.DirectionalLight(0xffffff, 0.35);
  fill.position.set(0, 200, -300);
  world.add(fill);
}

// ---------------------------------------------------------------- acrylic: discard tray and shoe

const acrylic = new THREE.MeshPhysicalMaterial({
  color: 0xdfe8ff, transparent: true, opacity: 0.16, roughness: 0.05, metalness: 0,
  clearcoat: 1, side: THREE.DoubleSide, depthWrite: false,
});
const edgeMat = new THREE.LineBasicMaterial({ color: 0xeaf0ff, transparent: true, opacity: 0.75 });
const cardSideMat = new THREE.MeshStandardMaterial({ color: 0xf2efe9, roughness: 0.8 });
let backTex = null;

function acrylicBox(w, h, d, openTop = true) {
  const g = new THREE.Group();
  const geo = new THREE.BoxGeometry(w, h, d);
  const mesh = new THREE.Mesh(geo, acrylic);
  mesh.renderOrder = 2;
  g.add(mesh);
  g.add(new THREE.LineSegments(new THREE.EdgesGeometry(geo), edgeMat));
  return g;
}

let trayStack = null, tray = null;
function buildTray() {
  const t = L.world.discard_tray;
  const [w, h, d] = t.size;
  tray = new THREE.Group();
  tray.position.set(t.centre[0], 0, t.centre[1]);
  tray.rotation.y = rad(t.turn);
  const box = acrylicBox(w, h, d);
  box.position.y = h / 2 + 0.2;
  tray.add(box);
  const base = new THREE.Mesh(new THREE.BoxGeometry(w + 1, 0.6, d + 1), new THREE.MeshStandardMaterial({ color: 0xcfd6e6, transparent: true, opacity: 0.5 }));
  base.position.y = 0.3;
  tray.add(base);
  trayStack = new THREE.Mesh(new THREE.BoxGeometry(L.world.card[0], 1, L.world.card[1] * 0.75),
    [cardSideMat, cardSideMat, new THREE.MeshStandardMaterial({ map: backTex, roughness: 0.6 }), cardSideMat, cardSideMat, cardSideMat]);
  trayStack.castShadow = true;
  tray.add(trayStack);
  world.add(tray);
}

let shoeStack = null, shoeCut = null, shoeFront = null, shoeLen = 0;
function buildShoe() {
  const s = L.world.shoe;
  const [mx, mz] = s.mouth, [bx, bz] = s.back;
  shoeLen = Math.hypot(bx - mx, bz - mz);
  const [sw, sh] = s.size;
  const shoe = new THREE.Group();
  shoe.position.set(mx, 0, mz);
  shoe.rotation.y = -Math.atan2(bz - mz, bx - mx);
  const inner = new THREE.Group();          // local x runs from the mouth to the back
  inner.rotation.z = rad(s.tilt);
  inner.position.y = sh / 2;
  shoe.add(inner);
  const body = acrylicBox(shoeLen, sh, sw);
  body.position.x = shoeLen / 2;
  inner.add(body);
  // cards stand on edge inside, pushed towards the mouth
  shoeStack = new THREE.Mesh(new THREE.BoxGeometry(1, sh * 0.82, sw * 0.86), cardSideMat);
  shoeStack.castShadow = true;
  inner.add(shoeStack);
  shoeFront = new THREE.Mesh(new THREE.PlaneGeometry(sw * 0.86, sh * 0.82), new THREE.MeshStandardMaterial({ map: backTex, roughness: 0.6 }));
  shoeFront.rotation.y = -Math.PI / 2;
  inner.add(shoeFront);
  // the cut card is a card: same size as the cards in the shoe and just as thin
  shoeCut = new THREE.Mesh(new THREE.BoxGeometry(0.05, sh * 0.82, sw * 0.86),
    new THREE.MeshStandardMaterial({ color: 0xffd400, roughness: 0.5, polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1 }));
  inner.add(shoeCut);
  world.add(shoe);
}

let cutOut = null;
function buildCutCardOut() {
  const [cw, ch] = L.world.card;
  cutOut = new THREE.Mesh(new THREE.BoxGeometry(cw, 0.05, ch), new THREE.MeshStandardMaterial({ color: 0xffd400, roughness: 0.5 }));
  cutOut.position.set(L.world.shoe.mouth[0] - 6, 0.1, L.world.shoe.mouth[1] - 14);
  cutOut.rotation.y = rad(12);
  cutOut.castShadow = true;
  cutOut.visible = false;
  world.add(cutOut);
}

function updateShoeAndTray() {
  const total = S.shoe.total, remaining = S.shoe.remaining;
  const stackCm = L.world.shoe.stack_cm;
  const len = Math.max(0.2, (remaining / total) * stackCm);
  const mouthGap = 2.5;
  shoeStack.scale.x = len;
  shoeStack.position.set(mouthGap + len / 2, -L.world.shoe.size[1] * 0.06, 0);
  shoeFront.position.set(mouthGap - 0.01, -L.world.shoe.size[1] * 0.06, 0);
  shoeCut.visible = !S.shoe.cut_card_out;
  shoeCut.position.set(mouthGap + ((S.shoe.cut_index - S.shoe.dealt) / total) * stackCm, -L.world.shoe.size[1] * 0.06, 0);
  cutOut.visible = S.shoe.cut_card_out;
  const h = Math.max(0.05, (S.discard.count / total) * 13);
  trayStack.visible = S.discard.count > 0;
  trayStack.scale.y = h;
  trayStack.position.y = 0.6 + h / 2;
}

// ---------------------------------------------------------------- cards and chips

const faceCache = new Map();
function cardCanvas(c) {
  const cw = 344, chh = 480;
  const cv = document.createElement("canvas"); cv.width = cw; cv.height = chh;
  const g = cv.getContext("2d");
  roundRect(g, 2, 2, cw - 4, chh - 4, 26);
  if (!c) {
    g.fillStyle = "#f4ecee"; g.fill();
    roundRect(g, 16, 16, cw - 32, chh - 32, 18); g.fillStyle = "#d98f99"; g.fill();
    g.strokeStyle = "rgba(255,255,255,0.35)"; g.lineWidth = 3;
    for (let x = -chh; x < cw; x += 22) { g.beginPath(); g.moveTo(x, 16); g.lineTo(x + chh, chh); g.stroke(); }
    return cv;
  }
  g.fillStyle = "#f8f8f6"; g.fill();
  const col = RED[c.suit] ? "#d21f2f" : "#121212";
  for (const flip of [false, true]) {
    g.save();
    if (flip) { g.translate(cw, chh); g.rotate(Math.PI); }
    g.fillStyle = col;
    g.font = `bold ${c.rank === "10" ? 140 : 160}px ${FONT}`;
    g.textAlign = "left"; g.textBaseline = "top";
    g.fillText(c.rank, 20, 14);
    g.font = `130px ${FONT}`; g.textAlign = "right";
    g.fillText(SUIT[c.suit], cw - 18, 24);
    g.restore();
  }
  g.fillStyle = "#a9a9b0";
  g.fillRect(cw * 0.32, chh / 2 - 12, cw * 0.36, 8);
  g.fillRect(cw * 0.32, chh / 2 + 4, cw * 0.36, 8);
  return cv;
}
function faceTexture(c) {
  const key = c ? c.rank + c.suit : "back";
  if (!faceCache.has(key)) faceCache.set(key, canvasTexture(cardCanvas(c), true));
  return faceCache.get(key);
}

function makeCard(c, faceUp) {
  const [cw, ch] = L.world.card;
  const g = new THREE.Group();
  const geo = new THREE.PlaneGeometry(cw, ch);
  geo.rotateX(-Math.PI / 2);
  geo.rotateY(Math.PI);                       // texture top points away from the camera (+z)
  const top = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ map: faceTexture(faceUp ? c : null), roughness: 0.55, alphaTest: 0.5 }));
  top.castShadow = true; top.receiveShadow = true;
  g.add(top);
  g.userData = { card: c, faceUp };
  return g;
}

const chipCache = new Map();
function chipMaterials(value, label) {
  const key = value + "|" + label;
  if (chipCache.has(key)) return chipCache.get(key);
  let best = 1;
  for (const v of CHIP_VALUES) if (value >= v) best = v;
  const [face, edge] = CHIP_COLOURS[best];
  const cv = document.createElement("canvas"); cv.width = cv.height = 256;
  const g = cv.getContext("2d");
  g.fillStyle = face; g.beginPath(); g.arc(128, 128, 128, 0, Math.PI * 2); g.fill();
  g.strokeStyle = edge; g.lineWidth = 34; g.setLineDash([46, 34]);
  g.beginPath(); g.arc(128, 128, 104, 0, Math.PI * 2); g.stroke(); g.setLineDash([]);
  g.fillStyle = "#ffffff"; g.beginPath(); g.arc(128, 128, 78, 0, Math.PI * 2); g.fill();
  g.fillStyle = "#222"; g.textAlign = "center"; g.textBaseline = "middle";
  g.font = `bold ${label.length > 3 ? 54 : 74}px ${FONT}`; g.fillText(label, 128, 132);
  const side = document.createElement("canvas"); side.width = 256; side.height = 16;
  const s = side.getContext("2d");
  s.fillStyle = face; s.fillRect(0, 0, 256, 16);
  s.fillStyle = edge; for (let x = 0; x < 256; x += 32) s.fillRect(x, 0, 14, 16);
  const mats = [new THREE.MeshStandardMaterial({ map: canvasTexture(side), roughness: 0.5 }),
                new THREE.MeshStandardMaterial({ map: canvasTexture(cv, true), roughness: 0.45 }),
                new THREE.MeshStandardMaterial({ color: face, roughness: 0.5 })];
  chipCache.set(key, mats);
  return mats;
}
const chipGeo = new THREE.CylinderGeometry(1.9, 1.9, 0.42, 48);
function makeChip(value, label) {
  const m = new THREE.Mesh(chipGeo, chipMaterials(value, label ?? fmt(value)));
  m.castShadow = true; m.receiveShadow = true;
  const g = new THREE.Group();          // turn the chip so its number reads upright from the camera
  m.rotation.y = -Math.PI / 2;
  g.add(m);
  return g;
}

// Seat overlays that lie on the felt: active highlight and empty-seat icon.
const seatPlates = {};
function plateTexture() {   // the empty-seat icon
  const cv = document.createElement("canvas"); cv.width = cv.height = 400;
  const g = cv.getContext("2d");
  g.strokeStyle = "rgba(255,255,255,0.92)"; g.lineWidth = 14; g.shadowColor = "#fff"; g.shadowBlur = 16;
  g.beginPath(); g.arc(200, 200, 170, 0, Math.PI * 2); g.stroke();
  g.beginPath(); g.arc(200, 150, 52, 0, Math.PI * 2); g.stroke();
  g.beginPath(); g.arc(200, 305, 110, Math.PI * 1.17, Math.PI * 1.83); g.stroke();
  return canvasTexture(cv);
}
function buildSeatPlates() {
  const icon = plateTexture();
  for (const [n, s] of Object.entries(seatWorld)) {
    const shape = new THREE.Shape();
    s.corners.forEach((p, i) => (i ? shape.lineTo(p.x, -p.z) : shape.moveTo(p.x, -p.z)));
    shape.closePath();
    const geo = new THREE.ShapeGeometry(shape);
    geo.rotateX(-Math.PI / 2);
    const fill = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.16, depthWrite: false }));
    fill.position.y = 0.05;
    const loop = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(s.corners.map((p) => new THREE.Vector3(p.x, 0.08, p.z))),
      new THREE.LineBasicMaterial({ color: 0xffffff }));
    const active = new THREE.Group(); active.add(fill, loop); active.visible = false; world.add(active);
    const size = s.ring * 1.9;
    const igeo = new THREE.PlaneGeometry(size, size); igeo.rotateX(-Math.PI / 2); igeo.rotateY(Math.PI);
    const empty = new THREE.Mesh(igeo, new THREE.MeshBasicMaterial({ map: icon, transparent: true, depthWrite: false }));
    empty.position.set(s.x, 0.06, s.z); empty.rotation.y = -s.turn; empty.visible = false; world.add(empty);
    seatPlates[n] = { active, empty };
  }
}

// ---------------------------------------------------------------- per-frame table contents

const dynamic = new THREE.Group();
world.add(dynamic);
let dynamicKey = "";

function rebuildDynamic() {
  // cards and chips only change when the state does
  const key = JSON.stringify([S.seats.map((s) => [s.occupied, s.bet, s.hands.map((h) => h.cards.length + (h.doubled ? "d" : ""))]),
    S.dealer.cards.length, S.dealer.hole_hidden, S.round]);
  if (key === dynamicKey) return;
  dynamicKey = key;
  dynamic.clear();
  const [cw, ch] = L.world.card;
  const [stepX, stepZ] = L.world.card_step;
  for (const s of S.seats) {
    const sw = seatWorld[s.seat];
    if (!s.occupied) continue;
    if (s.bet > 0) {
      // chips scale with the seat's betting circle so they never overlap each other
      const chipScale = Math.min(1, (sw.ring * 0.31) / 1.9);
      // one main chip per hand: after a split each hand carries its own bet
      const nh = Math.max(1, s.hands.length);
      const ct0 = Math.cos(sw.turn), st0 = Math.sin(sw.turn);
      let main;
      for (let hi = 0; hi < nh; hi++) {
        const amount = s.hands[hi] ? s.hands[hi].bet * (s.hands[hi].doubled ? 2 : 1) : s.bet;
        main = makeChip(amount, fmt(amount));
        main.scale.set(chipScale, 1, chipScale);
        const lx = ((nh - 1) / 2 - hi) * sw.ring * 0.72;
        main.position.set(sw.x + lx * ct0, 0.3, sw.z + lx * st0);
        if (hi < nh - 1) dynamic.add(main);
      }
      dynamic.add(main);
      if (!s.is_player && nh === 1) {     // decorative side bets for the other players (they do not work)
        const side = [];
        const rr = sw.ring * 0.76;   // side bets sit in the circle's segments: pair left, top-3 right, 21+3 top
        if (s.seat % 2 === 1) side.push([2.5, -rr, 0], [2.5, rr, 0]);
        if (s.seat % 3 === 0) side.push([5, 0, rr]);
        for (const [v, lx, lz] of side) {
          const m = makeChip(v);
          m.scale.set(chipScale, 1, chipScale);
          const ct = Math.cos(sw.turn), st = Math.sin(sw.turn);
          m.position.set(sw.x + lx * ct - lz * st, 0.3, sw.z + lx * st + lz * ct);
          dynamic.add(m);
        }
      }
    }
    const n = s.hands.length;
    s.hands.forEach((hand, hi) => {
      // split hands: the first hand (played first) sits on the right, as on the live table
      const off = ((n - 1) / 2 - hi) * L.world.split_gap;
      const ax = sw.cx + off * Math.cos(sw.cardTurn), az = sw.cz - off * Math.sin(sw.cardTurn);
      // Keep the last card clear of the seat box: if the usual step would reach the box's far
      // edge, the cards close up (the dealer tucks them tighter), down to a third of the step.
      const dir = { x: -Math.sin(sw.cardTurn), z: -Math.cos(sw.cardTurn) };        // towards the player
      const edge = { x: (sw.corners[0].x + sw.corners[1].x) / 2, z: (sw.corners[0].z + sw.corners[1].z) / 2 };
      const room = (edge.x - ax) * dir.x + (edge.z - az) * dir.z - L.world.card[1] / 2 - 1.0;
      const last = hand.cards.length - 1;
      const k = last > 0 ? Math.max(1 / 3, Math.min(1, room / (Math.abs(stepZ) * last))) : 1;
      hand.cards.forEach((c, i) => {
        const m = makeCard(c, true);
        const lx = stepX * i * k, lz = stepZ * i * k;
        const ct = Math.cos(sw.cardTurn), st = Math.sin(sw.cardTurn);
        m.position.set(ax + lx * ct + lz * st, 0.12 + i * 0.08, az - lx * st + lz * ct);
        m.rotation.y = sw.cardTurn + rad(((s.seat * 7 + i * 13) % 7) - 3);
        if (hand.doubled && i === 2) m.rotation.y += Math.PI / 2;   // a double card lies sideways
        dynamic.add(m);
      });
    });
  }
  const d0 = L._dealer;
  S.dealer.cards.forEach((c, i) => {
    const hidden = i === 1 && S.dealer.hole_hidden;
    const m = makeCard(c, !hidden);
    m.position.set(d0.x + i * L.world.dealer_spacing, 0.12, d0.z);
    dynamic.add(m);
  });
}

// ---------------------------------------------------------------- flat overlay (the casino UI layer)

function text(str, x, y, size, colour, weight = "bold", align = "center") {
  ctx.font = `${weight} ${size}px ${FONT}`;
  ctx.fillStyle = colour; ctx.textAlign = align; ctx.textBaseline = "middle";
  ctx.fillText(str, x, y);
}

// Total bubbles, measured from the live table: about 41 units across, light grey with a thin
// dark border; green for the hand being played; dark red with a white total when the hand is bust.
function labelBubble(text, kind, x, y, w, h, seat, hand) {
  bubbleLabels.push({ text, kind, seat, hand,
    box: [FX(x - w / 2), FY(y - h / 2), w * K, h * K].map((v) => Math.round(v)) });
}

function bubble(str, x, y, active, bust = false, seat = null, hand = 0) {
  if (!str) return;
  const h = 41;
  ctx.save();
  ctx.font = `bold 22px ${FONT}`;
  const w = Math.max(h, ctx.measureText(str).width + 18);
  ctx.shadowColor = "rgba(0,0,0,0.45)"; ctx.shadowBlur = 6;
  roundRect(ctx, x - w / 2, y - h / 2, w, h, h / 2);
  labelBubble(str, bust ? "bust" : active ? "active" : "normal", x, y, w, h, seat, hand);
  ctx.fillStyle = bust ? "#73001c" : active ? "#41ee22" : "#cecece"; ctx.fill();
  ctx.shadowColor = "transparent";
  ctx.strokeStyle = bust ? "#4a0012" : active ? "#2a9a16" : "#7c7c7c"; ctx.lineWidth = 1.5; ctx.stroke();
  ctx.restore();
  text(str, x, y + 1, 22, bust ? "#ffffff" : "#000000");
}

function dealerBubble(str) {
  if (!str) return;
  const [x, y] = L.dealer.bubble;
  const h = 46;
  ctx.save();
  ctx.font = `bold 23px ${FONT}`;
  const w = Math.max(h, ctx.measureText(str).width + 22);
  roundRect(ctx, x - w / 2, y - h / 2, w, h, h / 2);
  labelBubble(str, "dealer", x, y, w, h, 0, 0);
  ctx.fillStyle = "#020102"; ctx.fill();
  ctx.strokeStyle = "#9f929f"; ctx.lineWidth = 2.5; ctx.stroke();
  ctx.restore();
  text(str, x, y + 1, 23, "#ffffff");
}

function uiChip(value, x, y, r) {
  let best = 1;
  for (const v of CHIP_VALUES) if (value >= v) best = v;
  const [face, edge] = CHIP_COLOURS[best];
  ctx.save();
  ctx.shadowColor = "rgba(0,0,0,0.5)"; ctx.shadowBlur = 8;
  ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fillStyle = face; ctx.fill();
  ctx.shadowColor = "transparent";
  ctx.strokeStyle = edge; ctx.lineWidth = r * 0.28; ctx.setLineDash([r * 0.45, r * 0.35]);
  ctx.beginPath(); ctx.arc(x, y, r * 0.82, 0, Math.PI * 2); ctx.stroke(); ctx.setLineDash([]);
  ctx.beginPath(); ctx.arc(x, y, r * 0.6, 0, Math.PI * 2); ctx.fillStyle = "#fff"; ctx.fill();
  ctx.restore();
  const s = value >= 1000 ? "1,000" : fmt(value);
  text(s, x, y + 1, s.length > 3 ? r * 0.42 : r * 0.62, "#222");
}

function pill(label, x, y, w, h, fill, action, params = {}) {
  ctx.save();
  ctx.shadowColor = "rgba(0,0,0,0.5)"; ctx.shadowBlur = 8;
  roundRect(ctx, x - w / 2, y - h / 2, w, h, Math.min(h / 2, 14));
  ctx.fillStyle = fill; ctx.fill();
  ctx.restore();
  text(label, x, y + 1, Math.min(24, h * 0.45), "#ffffff");
  hits.push({ x: x - w / 2, y: y - h / 2, w, h, action, params });
}

function timerRing(secs, total) {
  const [x, y] = L.timer;
  ctx.save();
  ctx.beginPath(); ctx.arc(x, y, 36, 0, Math.PI * 2); ctx.fillStyle = "rgba(40,90,40,0.75)"; ctx.fill();
  ctx.strokeStyle = "#3be228"; ctx.lineWidth = 7; ctx.shadowColor = "#3be228"; ctx.shadowBlur = 12;
  ctx.beginPath(); ctx.arc(x, y, 36, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * Math.max(0, secs / total)); ctx.stroke();
  ctx.restore();
  text(String(Math.ceil(secs)), x, y + 2, 34, "#ffffff");
}

function drawOverlay() {
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, W, H);
  ctx.setTransform(K, 0, 0, K, -OX * K, -OY * K);     // draw in layout units
  hits = [];
  bubbleLabels = [];
  // names and bubbles
  for (const s of S.seats) {
    const geo = L.seats[String(s.seat)];
    if (s.occupied) {
      ctx.save(); ctx.shadowColor = "rgba(0,0,0,0.85)"; ctx.shadowBlur = 5;
      const nm = s.is_player ? "You" : (s.name.length > 11 ? s.name.slice(0, 10) + "…" : s.name);
      text(nm, geo.name[0], geo.name[1], 21, "#ffffff", "500");
      ctx.restore();
    }
    const n = s.hands.length;
    s.hands.forEach((h, hi) => {
      const off = ((n - 1) / 2 - hi) * L.split_offset;
      // the hand being played gets a green bubble that sits a little higher
      if (h.cards.length) bubble(h.bubble, geo.bubble[0] + off, geo.bubble[1] - (h.active ? L.active_bubble_lift || 0 : 0), h.active, h.bust, s.seat, hi);
    });
  }
  dealerBubble(S.dealer.bubble);
  // stage message, timer and buttons
  const [tx, ty] = L.stage_text, y = L.button_row_y;
  const me = S.seats[S.player_seat - 1];
  let msg = S.message;
  if (S.phase === "player_turn" && S.legal_moves.length) msg = "MAKE YOUR DECISION";
  if (S.phase === "round_over") msg = "";
  if (msg) {
    ctx.save(); ctx.font = `500 26px ${FONT}`;
    const w = ctx.measureText(msg).width + 60;
    const grad = ctx.createLinearGradient(tx - w / 2, 0, tx + w / 2, 0);
    grad.addColorStop(0, "rgba(0,0,0,0)"); grad.addColorStop(0.2, "rgba(0,0,0,0.55)");
    grad.addColorStop(0.8, "rgba(0,0,0,0.55)"); grad.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = grad; ctx.fillRect(tx - w / 2, ty - 22, w, 44);
    ctx.restore();
    text(msg, tx, ty + 1, 26, "#ffffff", "500");
  }
  const total = S.wait === "betting" ? 15 : S.wait === "insurance" ? 8 : 10;
  if (S.timer !== null && S.timer !== undefined) timerRing(S.timer, total);
  if (!S.script) {
    if (S.wait === "betting" && S.timer !== null) {
      ctx.save(); ctx.fillStyle = "rgba(225,225,235,0.32)";
      roundRect(ctx, 628, y - 62, 742, 124, 14); ctx.fill(); ctx.restore();
      pill("↺", 544, y, 96, 96, "rgba(40,40,48,0.85)", "undo");
      text("UNDO", 544, y + 90, 19, "#e8e8e8", "500");
      CHIP_VALUES.slice(0, 7).forEach((v, i) => {
        const cx = 752 + i * 84;
        uiChip(v, cx, y, 33);
        hits.push({ x: cx - 33, y: y - 33, w: 66, h: 66, action: "bet", params: { amount: v } });
      });
      pill("×2", 1454, y, 96, 96, "rgba(40,40,48,0.85)", "double_bet");
      text("DOUBLE", 1454, y + 90, 19, "#e8e8e8", "500");
      if (me.bet >= S.min_bet) pill("DEAL", 998, y + 100, 130, 44, "#2e9e4f", "deal");
    }
    if (S.insurance_offered) {
      pill("YES", 900, y, 130, 56, "#2e9e4f", "insurance", { take: true });
      pill("NO", 1096, y, 130, 56, "#b8372e", "insurance", { take: false });
    }
    if (S.legal_moves.length) {
      const order = ["double", "hit", "stand", "split"];
      const labels = { hit: "HIT", stand: "STAND", double: "DOUBLE", split: "SPLIT" };
      const colours = { hit: "#2e9e4f", stand: "#b8372e", double: "#c9962f", split: "#3f6fd1" };
      const moves = order.filter((m) => S.legal_moves.includes(m));
      const start = 998 - ((moves.length - 1) * 160) / 2;
      moves.forEach((m, i) => pill(labels[m], start + i * 160, y, 146, 60, colours[m], m));
    }
  }
  // balance and bet, bottom left
  const g = ctx.createLinearGradient(0, 960, 0, 1080);
  g.addColorStop(0, "rgba(0,0,0,0)"); g.addColorStop(1, "rgba(0,0,0,0.75)");
  ctx.fillStyle = g; ctx.fillRect(0, 960, 1920, 120);
  text("Balance", L.hud.balance[0], L.hud.balance[1] - 14, 24, "#ffffff", "500");
  text(money(S.balance), L.hud.balance[0], L.hud.balance[1] + 18, 26, "#f2c14e", "500");
  text("Bet", L.hud.bet[0], L.hud.bet[1] - 14, 24, "#ffffff", "500");
  const bet = me.hands.reduce((a, h) => a + h.bet * (h.doubled ? 2 : 1), 0) || me.bet;
  text("$ " + fmt(bet), L.hud.bet[0], L.hud.bet[1] + 18, 26, "#f2c14e", "500");
  if (S.paused) {
    ctx.fillStyle = "rgba(0,0,0,0.6)"; roundRect(ctx, 40, 40, 190, 52, 8); ctx.fill();
    text("❚❚  PAUSED", 135, 67, 22, "#ffffff");
  }
}

// ---------------------------------------------------------------- card boxes for the dataset

function collectCardBoxes() {
  cardBoxes = [];
  const [cw, ch] = L.world.card;
  dynamic.children.forEach((obj) => {
    if (!obj.userData.card || !obj.userData.faceUp) return;
    obj.updateMatrixWorld();
    const xs = [], ys = [];
    for (const [x, z] of [[-cw / 2, -ch / 2], [cw / 2, -ch / 2], [cw / 2, ch / 2], [-cw / 2, ch / 2]]) {
      const [sx, sy] = toScreen(new THREE.Vector3(x, 0, z).applyMatrix4(obj.matrixWorld));
      xs.push(sx); ys.push(sy);
    }
    const c = obj.userData.card;
    const label = c.rank === "A" ? "A" : ["10", "J", "Q", "K"].includes(c.rank) ? "10" : c.rank;
    cardBoxes.push({ label, box: [Math.min(...xs), Math.min(...ys), Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)].map(Math.round) });
  });
}

function maybeExport() {
  if (!S.dataset || exporting) return;
  // save a frame whenever a card or a bubble changes (a stand changes only the bubble)
  const key = cardBoxes.map((b) => b.label + b.box.join(",")).join("|") + "#" +
    bubbleLabels.map((b) => `${b.seat}.${b.hand}:${b.text}:${b.kind}`).join("|");
  if (!key || key === lastCardKey) return;
  lastCardKey = key;
  exporting = true;
  const g = exportCanvas.getContext("2d");
  g.drawImage(glCanvas, 0, 0);
  g.drawImage(overlay, 0, 0);
  fetch("/api/dataset", { method: "POST", body: JSON.stringify({ image: exportCanvas.toDataURL("image/jpeg", 0.9), labels: cardBoxes, bubbles: bubbleLabels, truth: S.truth || null, round: S.round, width: W, height: H }) })
    .finally(() => { exporting = false; });
}

// ---------------------------------------------------------------- setup, input and loop

function setup() {
  setupCamera();
  for (const [n, s] of Object.entries(L.seats)) {
    const traced = s.box.map((p) => toTable(...p));
    const cx = traced.reduce((a, p) => a + p.x, 0) / 4, cz = traced.reduce((a, p) => a + p.z, 0) / 4;
    // shrink each box about its centre so neighbouring boxes have the gap the real table has
    const k = L.world.box_shrink || 1;
    const corners = traced.map((p) => ({ x: cx + (p.x - cx) * k, z: cz + (p.z - cz) * k }));
    // the box's front edge (nearest the player) sets its angle; the corners run TL, TR, BR, BL
    const front = { x: corners[2].x - corners[3].x, z: corners[2].z - corners[3].z };
    const turn = Math.atan2(front.z, front.x);
    const width = Math.hypot(front.x, front.z);
    // depth: from the middle of the back edge to the middle of the front edge
    const depth = Math.hypot((corners[0].x + corners[1].x - corners[2].x - corners[3].x) / 2,
                             (corners[0].z + corners[1].z - corners[2].z - corners[3].z) / 2);
    // the betting circle must fit inside the box, with a small margin to every edge
    const ring = Math.min(width, depth) * 0.42;
    const card = toTable(...s.card);
    // cards lean towards a point behind the dealer; further back means a gentler lean on the outer seats
    const cardTurn = Math.atan2(-card.x, (L.world.card_aim_z || 30) - card.z);
    seatWorld[n] = { x: cx, z: cz, turn, corners, ring, cx: card.x, cz: card.z, cardTurn };
  }
  const d = toTable(...L.dealer.first_card);
  L._dealer = { x: d.x, z: d.z };
  backTex = faceTexture(null);
  buildRoom();
  buildTable();
  buildTray();
  buildShoe();
  buildCutCardOut();
  buildSeatPlates();
}

function frame() {
  if (S) {
    rebuildDynamic();
    updateShoeAndTray();
    for (const s of S.seats) {
      const p = seatPlates[s.seat];
      p.empty.visible = !s.occupied;
      p.active.visible = !!(S.active && S.active[0] === s.seat);
    }
    renderer.render(scene, camera);
    drawOverlay();
    collectCardBoxes();
    maybeExport();
  }
  requestAnimationFrame(frame);
}

async function send(action, params = {}) {
  const r = await fetch("/api/action", { method: "POST", body: JSON.stringify({ action, ...params }) });
  const body = await r.json();
  document.getElementById("error").textContent = body.error || "";
  if (!body.error) S = body;
}
async function togglePause() { S = await (await fetch("/api/pause", { method: "POST", body: "{}" })).json(); }
// Restart needs a second click within 3 seconds, so a stray click cannot end the game.
let restartArmed = null;
async function restart() {
  const btn = document.getElementById("restart");
  if (!restartArmed) {
    btn.textContent = "Click again to restart";
    restartArmed = setTimeout(() => { restartArmed = null; btn.textContent = "Restart"; }, 3000);
    return;
  }
  clearTimeout(restartArmed);
  restartArmed = null;
  btn.textContent = "Restart";
  S = await (await fetch("/api/restart", { method: "POST", body: "{}" })).json();
}

overlay.addEventListener("click", (e) => {
  const rect = overlay.getBoundingClientRect();
  const x = ((e.clientX - rect.left) / rect.width) * W / K + OX, y = ((e.clientY - rect.top) / rect.height) * H / K + OY;
  for (const h of hits) if (x >= h.x && x <= h.x + h.w && y >= h.y && y <= h.y + h.h) { send(h.action, h.params); return; }
});
document.addEventListener("keydown", (e) => {
  const key = e.key.toLowerCase();
  const map = { h: ["hit"], s: ["stand"], d: ["double"], p: ["split"], y: ["insurance", { take: true }],
                n: ["insurance", { take: false }], enter: ["deal"], backspace: ["undo"] };
  if (key === " ") { e.preventDefault(); togglePause(); }
  else if (key === "t") document.getElementById("stats").classList.toggle("hidden");
  else if (map[key]) send(...map[key]);
  else if (/^[1-8]$/.test(key)) send("bet", { amount: CHIP_VALUES[Number(key) - 1] });
});
document.getElementById("pause").addEventListener("click", togglePause);
document.getElementById("restart").addEventListener("click", restart);

// ?demo=N shows a still table with every seat holding N cards, for checking the layout.
function demoState(n) {
  const sets = [
    [["2", "S"], ["3", "H"], ["5", "D"], ["9", "C"], ["A", "D"]],
    [["A", "H"], ["2", "C"], ["3", "D"], ["4", "S"], ["5", "H"]],
    [["4", "C"], ["4", "D"], ["2", "H"], ["7", "S"], ["3", "C"]],
    [["3", "S"], ["2", "D"], ["6", "C"], ["8", "H"], ["2", "S"]],
    [["5", "H"], ["2", "S"], ["A", "C"], ["10", "D"], ["2", "D"]],
    [["2", "H"], ["2", "D"], ["3", "C"], ["K", "S"], ["A", "S"]],
    [["6", "D"], ["A", "S"], ["2", "C"], ["3", "H"], ["4", "D"]],
  ];
  const val = (r) => (r === "A" ? 1 : ["10", "J", "Q", "K"].includes(r) ? 10 : Number(r));
  const seats = sets.map((cards, i) => {
    const hand = cards.slice(0, n).map(([rank, suit]) => ({ rank, suit }));
    const hard = hand.reduce((a, c) => a + val(c.rank), 0);
    const soft = hand.some((c) => c.rank === "A") && hard + 10 <= 21;
    const bubble = hard > 21 ? String(hard) : soft && hard + 10 !== 21 ? `${hard}/${hard + 10}` : String(soft ? hard + 10 : hard);
    const seat = i + 1;
    return { seat, name: seat === 4 ? "You" : `Player${1000000 + seat * 137}`, occupied: true, is_player: seat === 4,
      bet: [25, 10, 50, 10, 20, 30, 100][i], chips: [], insurance: 0,
      hands: [{ cards: hand, bubble, bust: hard > 21, bet: 10, doubled: false, result: null, active: seat === 4 }] };
  });
  if (params.has("split")) {   // seat 4 has split a pair of 8s and is playing the second hand
    const mk = (cards, active) => ({ cards: cards.map(([rank, suit]) => ({ rank, suit })), bubble: "", bust: false, bet: 10,
      doubled: false, result: null, active });
    const h1 = mk([["8", "S"], ["3", "D"], ["9", "C"]], false), h2 = mk([["8", "H"], ["2", "C"]], true);
    h1.bubble = "20"; h2.bubble = "10";
    seats[3].hands = [h1, h2];
  }
  return { phase: "player_turn", message: "", round: 1, timer: null, wait: null, balance: 1000, player_seat: 4,
    legal_moves: [], insurance_offered: false, active: [4, params.has("split") ? 1 : 0], seats,
    dealer: { cards: [{ rank: "9", suit: "S" }, { rank: "2", suit: "H" }], hole_hidden: true, bubble: "9" },
    shoe: { total: 416, dealt: 30, remaining: 386, cut_index: 208, cut_card_out: false }, discard: { count: 60 },
    min_bet: 10, max_bet: 5000, paused: false, script: true, seed: 0, dataset: params.has("save") };
}

const SUIT_NAME = { S: "\u2660", H: "\u2665", D: "\u2666", C: "\u2663" };
function showTruth(s) {
  const tr = s.truth;
  if (!tr) return;
  const sign = (v) => (v > 0 ? "+" : "") + v;
  const set = (id, v) => { document.getElementById(id).textContent = v; };
  set("st-run", sign(tr.running_count));
  set("st-true", sign(tr.true_count.toFixed(2)));
  set("st-decks", tr.decks_left.toFixed(1));
  set("st-seen", tr.cards_seen);
  const c = tr.last_card;
  set("st-last", c ? `${c.rank}${SUIT_NAME[c.suit]} \u2192 ${c.to === "dealer" ? "Dealer" : "Seat " + c.seat}` : "\u2013");
  set("st-round", `${tr.shoe} \u00B7 ${s.round}`);
  set("st-cut", `${s.shoe.cut_card_out ? "out" : "at " + s.shoe.cut_index} (dealt ${s.shoe.dealt})`);
}

async function poll() {
  try {
    S = params.get("demo") ? demoState(Number(params.get("demo")) || 4) : await (await fetch("/api/state")).json();
    document.getElementById("pause").textContent = S.paused ? "Resume" : "Pause";
    showTruth(S);
    document.getElementById("info").textContent =
      `Round ${S.round} · ${S.phase.replace("_", " ")} · seed ${S.seed} · ` +
      `shoe ${S.shoe.dealt}/${S.shoe.total} (cut at ${S.shoe.cut_index}) · discard ${S.discard.count}` +
      (S.script ? " · test script" : "") + (S.dataset ? " · saving card pictures" : "");
  } catch (_) { /* server restarting */ }
  setTimeout(poll, 100);
}

// Fit the frame into the stage the way the real page does: fill the height, crop the sides.
const stage = document.getElementById("stage");
const params = new URLSearchParams(location.search);
function fit() {
  if (!L) return;                       // layout not loaded yet
  const inset = (params.get("inset") || L.page.inset_css_px.join(",")).split(",").map(Number);
  Object.assign(stage.style, { left: inset[0] + "px", right: inset[1] + "px", top: inset[2] + "px", bottom: inset[3] + "px" });
  const sw = stage.clientWidth, sh = stage.clientHeight;
  const scale = Math.max(sw / W, sh / H);
  for (const c of [glCanvas, overlay]) {
    Object.assign(c.style, { width: W * scale + "px", height: H * scale + "px",
      left: (sw - W * scale) / 2 + "px", top: (sh - H * scale) / 2 + "px" });
  }
}
window.addEventListener("resize", fit);

L = await (await fetch("/layout.json")).json();
fit();
setup();
poll();
frame();
