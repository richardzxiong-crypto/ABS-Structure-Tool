import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as k from "/root/.claude/skills/anatomy/kit/iso-kit.mjs";
import * as G from "/root/.claude/skills/anatomy/kit/lathe.mjs";
import { tubePieces, tubeSvg } from "/root/.claude/skills/anatomy/kit/tube.mjs";
import * as A from "/root/.claude/skills/anatomy/kit/audit.mjs";
import { glCamera } from "/root/.claude/skills/anatomy/kit/gl.mjs";
import { kitScript, glScript } from "/root/.claude/skills/anatomy/scripts/inline-kit.mjs";
import { MODEL } from "./model.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const THEME = process.argv.includes("--light") ? "light" : "dark";
const DEG = Math.PI / 180;

const W = 700;
const H = 470;

// World, about 1 unit = 5 mm. The thruster's axis runs along +x at height ZA.
const PLATE = { x: -178, y: -60, w: 336, d: 120, r: 8 };
const PLATE_H = 10;
const FOOT_H = 5;
const ZA = 66;
const X0 = -96;
const XG = X0 + 76;
const R_BEAM = 29;
const PLUME = 175;
const TRAVEL = 5;

const CAR = { x: -126, y: -38, w: 128, d: 76, r: 3 };
const CAR_Z = 3;
const CAR_TOP = 8;
const ROD_Z = 5.5;
const GAUGE = [-158, 0];
const GAUGE_R = 12;
const GAUGE_TOP = 9;
const GLAND = -141;
const ROD_TIP = -130;
const SWEEP = 300;
const FULL_SCALE = 100;

const P = k.fitProjection(
  [...k.boxCorners(PLATE, -PLATE_H - FOOT_H, 0), [-110, -24, 122], [-110, 24, 122], [XG + PLUME - 20, 0, ZA + 40], [XG + PLUME - 20, 30, ZA - 30]],
  W,
  H,
  { pad: 26, azimuth: 52 },
);
const V = G.viewOf(P);
const KS = G.scaleOf(P);
const at = (point) => k.iso(point, P);
const S = (paths, style) => k.solidSvg(paths, style);
const L = (d, style) => k.lineSvg(d, style);
const D = (points, style) => k.dotsSvg(points, style);
const byDepth = (points) => [...points].sort((a, b) => k.depthOf([a[0], a[1], 0], P) - k.depthOf([b[0], b[1], 0], P));

const R = A.recorder(P);
const { nameFor } = R;
const record = R.solid;
const put = (ref, svg, { bias = 0, shapes = [], name } = {}) => R.put({ piece: "sled", at: ref, bias, svg, shapes, name: name ?? nameFor("sled.item") });

const TF = G.frameOf([X0, 0, ZA], [1, 0, 0], [0, 1, 0], [0, 0, 1]);
const along = (F, s) => G.add3(F.o, G.mul3(F.a, s));

function turned(F, profile, style = {}, { extra = "", inner = "", name, owner, smooth, bias = 0 } = {}) {
  const id = nameFor(name ?? "sled.turned");
  const paths = G.solidOf(profile, F, P, smooth ? { smooth } : {});
  const shape = record(A.solid(F, profile, { name: id, owner, ...(smooth?.radius ? { radius: smooth.radius } : {}) }));
  put(along(F, (profile[0][0] + profile[profile.length - 1][0]) / 2), S(paths, { tone: "hi", ...style, inner }) + extra, { name: id, shapes: [shape], bias });
  return shape;
}
const band = (F, s0, s1, r, style, options) => turned(F, [[s0, r], [s1, r]], style, options);

function boxAt(plan, z, h, style = {}, { extra = "", name, owner, bevel = 0.5, steps = 3, bias = 0, inner = "" } = {}) {
  const id = nameFor(name ?? "sled.box");
  put([plan.x + plan.w / 2, plan.y + plan.d / 2, z + h / 2], S(k.slabOf(plan, z, h, P, steps, bevel), { tone: "mid", ...style, inner }) + extra, { name: id, bias, shapes: [record(A.slab(plan, z, h, { name: id, owner }, steps))] });
}

function flangeAt(centre, axis, r, thick, { name, owner, tone = "hi" } = {}) {
  const F = G.frameAlong(centre, axis);
  const id = nameFor(name);
  put(centre, S(G.disc(-thick / 2, thick / 2, r, F, P), { tone }), { name: id, shapes: [record(A.disc(F, -thick / 2, thick / 2, r, { name: id, owner }))] });
}

function pipe(name, control, r, { flangeR = 1.7, tone = "hi" } = {}) {
  const line = G.fillet(control, Math.max(r * 2.8, 3), 12, { P, tube: r });
  const total = G.pathLength(line);
  const thick = Math.max(0.9, r * 0.7);
  const id = nameFor(name);
  const gaps = [[0, thick], [total - thick, total]];
  R.route(id, line, r, { owner: id, gaps, rims: [r * flangeR, r * flangeR], piece: "sled" });
  tubePieces(line, r, P, { maxLength: 12, spacing: 0.7, gaps }).forEach((part, index) =>
    R.put({ piece: "sled", at: part.mid, svg: tubeSvg(part, { tone }), name: `${id}:${index}`, route: id, chunk: index, shapes: [A.tube(part.points, part.radii)] }),
  );
  [[0, -1], [total, 1]].forEach(([s, sign]) => {
    const tangent = G.tangentAlong(line, s);
    flangeAt(G.add3(G.pointAlong(line, s), G.mul3(tangent, (-sign * thick) / 2)), tangent, r * flangeR, thick, { name: `${id}.flange`, owner: id, tone });
  });
}

// ---------- static base: plate, rails, gauge ----------
const back = [];
back.push(`<path class="iso-halo" d="${k.haloOf(PLATE, -PLATE_H - FOOT_H, PLATE_H, P)}"/>`);
for (const [x, y] of byDepth(k.corners(PLATE, 22))) {
  back.push(S(k.cylinder(x, y, 7, -PLATE_H - FOOT_H, 1.6, P, 28), { tone: "lo" }));
  back.push(S(k.cylinder(x, y, 5.4, -PLATE_H - FOOT_H + 1.6, FOOT_H - 1.6, P, 28), { tone: "mid" }));
}
back.push(S(k.slabOf(PLATE, -PLATE_H, PLATE_H, P, 8, 1.6), { tone: "mid" }));
record(A.slab(PLATE, -PLATE_H, PLATE_H, { name: "stand.plate" }));
back.push(L(k.planOutline(k.insetPlan(PLATE, 5), 0, P), { tone: "lo" }));
const SCREWS = k.corners(PLATE, 11);
back.push(L(SCREWS.map(([x, y]) => k.ring(x, y, 2.2, 0, P, 16)).join(""), { tone: "lo" }));
back.push(D(SCREWS.map(([x, y]) => at([x, y, 0])), { size: 0.5 }));

// ruler strip under the beam, along the near edge
const STRIP = { x: XG, y: PLATE.y + PLATE.d - 16, w: 150, d: 7, r: 1 };
back.push(S(k.slabOf(STRIP, 0, 0.6, P, 3), { tone: "lo", crease: "none" }));
const TICKS = k.topTicks(STRIP.x + 5, STRIP.x + STRIP.w - 5, 5, 4, STRIP.y + 0.6, 0.6, [2, 3.6], P);
back.push(L(TICKS.minor, { tone: "lo" }), L(TICKS.major, { tone: "mid" }));
back.push(D([at([STRIP.x + 2, STRIP.y + 4.6, 0.6]), at([STRIP.x + STRIP.w - 2, STRIP.y + 4.6, 0.6])], { size: 0.45 }));

// label plate
const LABEL = { x: -160, y: 40, w: 36, d: 13, r: 1.5 };
back.push(S(k.slabOf(LABEL, 0, 0.8, P, 4), { tone: "lo", crease: "none" }));
back.push(L(k.planOutline(k.insetPlan(LABEL, 1.6), 0.8, P, 3), { tone: "faint" }));
[[24, 4], [16, 6.5], [20, 9]].forEach(([len, y]) => back.push(L(k.lineOnTop([LABEL.x + 5, LABEL.y + y], [LABEL.x + 5 + len, LABEL.y + y], 0.8, P), { tone: "lo", free: true })));
back.push(D([at([LABEL.x + 2.4, LABEL.y + 2.4, 0.8]), at([LABEL.x + LABEL.w - 2.4, LABEL.y + LABEL.d - 2.4, 0.8])], { size: 0.4 }));

// rails and end stops
const RAILS = [-32, 27];
const RAIL_X = [-140, 18];
for (const y of RAILS) {
  const rail = { x: RAIL_X[0], y, w: RAIL_X[1] - RAIL_X[0], d: 5, r: 1 };
  back.push(S(k.slabOf(rail, 0, CAR_Z, P, 3, 0.4), { tone: "mid" }));
  record(A.slab(rail, 0, CAR_Z, { name: "stand.rail" }, 3));
  for (const x of [RAIL_X[0] - 5, RAIL_X[1]]) {
    const stop = { x, y: y - 2.5, w: 5, d: 10, r: 1.2 };
    back.push(S(k.slabOf(stop, 0, 6.5, P, 3, 0.5), { tone: "mid" }));
    back.push(D([at([x + 2.5, y + 2.5, 6.5])], { size: 0.45 }));
    record(A.slab(stop, 0, 6.5, { name: "stand.stop" }, 3));
  }
}
back.push(D(RAILS.flatMap((y) => [-20, 6].map((x) => at([x, y + 2.5, CAR_Z]))), { size: 0.4 }));

// dial gauge lying on the plate, its plunger pointing at the sled
function gauge() {
  const [x, y] = GAUGE;
  const out = [];
  out.push(S(k.cylinder(x, y, GAUGE_R, 0, GAUGE_TOP, P, 56, 0.8), { tone: "hi", crease: "lo" }));
  out.push(L(k.knurl(x, y, GAUGE_R, GAUGE_TOP - 3, GAUGE_TOP, 64, P, 0.3), { tone: "lo" }));
  out.push(L(k.sideArc(x, y, GAUGE_R, GAUGE_TOP - 3, P, 36), { tone: "faint" }));
  out.push(L(k.ring(x, y, GAUGE_R - 1.8, GAUGE_TOP, P, 56), { tone: "lo" }));
  const ticks = k.radialTicks(x, y, GAUGE_R - 2.4, 50, 5, GAUGE_TOP, [1, 2.2], P, (-SWEEP / 2) * DEG, SWEEP * DEG);
  out.push(L(ticks.minor, { tone: "lo" }), L(ticks.major, { tone: "mid" }));
  out.push(L(k.ring(x, y, 1.3, GAUGE_TOP, P, 14), { tone: "mid" }));
  return out.join("");
}
back.push(gauge());
record(A.cylinder(GAUGE[0], GAUGE[1], GAUGE_R, 0, GAUGE_TOP, { name: "stand.gauge" }));
const RODF = G.frameOf([0, 0, ROD_Z], [1, 0, 0], [0, 1, 0], [0, 0, 1]);
back.push(S(G.disc(GAUGE[0] + GAUGE_R - 0.2, GLAND, 2.2, RODF, P), { tone: "mid" }) + L(G.circleOf(RODF, GLAND, 1.6, P, 16), { tone: "faint" }));
record(A.disc(RODF, GAUGE[0] + GAUGE_R - 0.2, GLAND, 2.2, { name: "stand.sleeve" }));
const ROD = G.rodOut(RODF, GLAND, ROD_TIP, 1.2, P, { stroke: TRAVEL });
back.push(`<g data-part="rod"><clipPath id="ie-rod"><path data-hold d="${ROD.clip}"/></clipPath><g clip-path="url(#ie-rod)">${S(ROD.paths, { tone: "hi", lit: true })}</g></g>`);
record(A.disc(RODF, GLAND, ROD_TIP, 1.2, { name: "stand.rod" }));

const needleAt = (share) => {
  const angle = (-SWEEP / 2 + SWEEP * share) * DEG;
  const [x, y] = GAUGE;
  return k.lineOnTop([x - Math.sin(angle) * 2.4, y + Math.cos(angle) * 2.4], [x + Math.sin(angle) * (GAUGE_R - 3.2), y - Math.cos(angle) * (GAUGE_R - 3.2)], GAUGE_TOP + 0.2, P);
};
back.push(`<path data-part="needle" class="iso-line" data-tone="lit" data-free="start" d="${needleAt(0)}" style="stroke-width:1.1"/>`);

// ---------- the sled: everything that the thrust pushes ----------
boxAt(CAR, CAR_Z, CAR_TOP - CAR_Z, { tone: "mid" }, {
  name: "sled.deck",
  bevel: 0.6,
  steps: 5,
  extra:
    L(k.planOutline(k.insetPlan(CAR, 3.5), CAR_TOP, P, 4), { tone: "faint" }) +
    D(k.corners(CAR, 6.5).map(([x, y]) => at([x, y, CAR_TOP])), { size: 0.45 }) +
    D([-70, -50, -30, -10].map((x) => at([x, CAR.y + CAR.d - 1.8, CAR_TOP])), { size: 0.38, tone: "lo" }),
});
band(RODF, ROD_TIP, CAR.x, 2.4, { tone: "mid" }, { name: "sled.striker" });

const FOOT = { x: -112, y: -25, w: 26, d: 49.5, r: 2 };
boxAt(FOOT, CAR_TOP, 3, { tone: "mid" }, { name: "sled.foot", extra: D(k.corners(FOOT, 4).filter(([x]) => x > -100).map(([x, y]) => at([x, y, CAR_TOP + 3])), { size: 0.45 }) });
const BRACKET = { x: -110, y: -24, w: 6, d: 48, r: 1.4 };
const BR_Z = [CAR_TOP + 3, 118];
boxAt(BRACKET, BR_Z[0], BR_Z[1] - BR_Z[0], { tone: "mid" }, {
  name: "sled.bracket",
  bevel: 0.6,
  inner: L(k.sideSeam(BRACKET, 24, P, 3) + k.sideSeam(BRACKET, 98, P, 3), { tone: "faint" }),
  extra: D([[-107, -19], [-107, 19]].map(([x, y]) => at([x, y, BR_Z[1]])), { size: 0.4 }),
});
for (const y of [-21, 19]) {
  const GF = G.frameOf([-104, 0, CAR_TOP + 3], [0, 1, 0], [1, 0, 0], [0, 0, 1]);
  const tri = [[0, 0], [15, 0], [0, 34]];
  const id = nameFor("sled.gusset");
  put([-99, y + 1, CAR_TOP + 14], S(G.prismOf(GF, tri, y, y + 2, P), { tone: "mid" }), { name: id, shapes: [record(A.prism(GF, tri, y, y + 2, { name: id }))] });
}
for (const y of RAILS)
  for (const x of [CAR.x + 5, CAR.x + CAR.w - 21]) {
    const block = { x, y: y - 2, w: 16, d: 8, r: 1.2 };
    boxAt(block, CAR_TOP, 2.6, { tone: "mid" }, { name: "sled.bearing", bevel: 0.4, extra: D([at([x + 3, y + 2.5, CAR_TOP + 2.6]), at([x + 13, y + 2.5, CAR_TOP + 2.6])], { size: 0.42 }) });
  }
const MANIFOLD = { x: -104, y: -12, w: 7, d: 26, r: 1 };
const MAN_Z = [102, 114];
boxAt(MANIFOLD, MAN_Z[0], MAN_Z[1] - MAN_Z[0], { tone: "hi" }, {
  name: "sled.manifold",
  extra: L(k.planOutline(k.insetPlan(MANIFOLD, 1.2), MAN_Z[1], P, 2), { tone: "faint" }),
});
{
  const [x, y] = [-100.5, -7];
  const id = nameFor("sled.supply");
  put([x, y, MAN_Z[1] + 2.5], S(k.cylinder(x, y, 1.9, MAN_Z[1], 3.4, P, 18), { tone: "hi" }) + S(k.cylinder(x, y, 2.6, MAN_Z[1] + 3.4, 1.6, P, 20), { tone: "mid" }) + L(k.knurl(x, y, 2.6, MAN_Z[1] + 3.4, MAN_Z[1] + 5, 14, P), { tone: "lo" }) + D([at([x, y, MAN_Z[1] + 5])], { size: 0.45 }), {
    name: id,
    shapes: [record(A.cylinder(x, y, 1.9, MAN_Z[1], 3.4, { name: id })), record(A.cylinder(x, y, 2.6, MAN_Z[1] + 3.4, 1.6, { name: `${id}.cap` }))],
  });
}
const POST = { x: X0 + 42, y: -7, w: 3, d: 14, r: 0.8 };
boxAt(POST, CAR_TOP, ZA - 33.5 - CAR_TOP, { tone: "mid" }, { name: "sled.saddle", bevel: 0.3 });

// the thruster, rear to front
band(TF, -8, 0, 10, { tone: "mid" }, { name: "thruster.mount" });
band(TF, 0, 8, 16, { tone: "hi" }, { name: "thruster.plenum" });
band(TF, 8, 11, 18.5, { tone: "mid" }, { name: "thruster.magnet" });
const cone = (s0, r0, s1, r1, name) =>
  turned(TF, [[s0, r0], [s1, r1]], { tone: "hi" }, { name, extra: k.fadedSvg(G.ribsOf(TF, s0, s1, r0, Math.round(r0 * 1.5), P, { r1, fade: [0.1, 0.55] }), { tone: "faint" }) });
cone(11, 16.5, 26, 23.5, "thruster.cone");
band(TF, 26, 29, 26, { tone: "mid" }, { name: "thruster.magnet" });
cone(29, 24.5, 42, 31, "thruster.cone");
band(TF, 42, 45, 33.5, { tone: "mid" }, { name: "thruster.magnet" });
turned(TF, [[45, 31], [62, 31]], { tone: "hi" }, { name: "thruster.shell", extra: k.fadedSvg(G.ribsOf(TF, 45, 62, 31, 46, P, { fade: [0.1, 0.55] }), { tone: "faint" }) });
band(TF, 62, 65, 33.5, { tone: "mid" }, { name: "thruster.magnet" });
band(TF, 65, 70, 37, { tone: "hi" }, { name: "thruster.mask", extra: D(G.dotsOf(TF, 70, 33.6, 18, P, { all: true }), { size: 0.45, tone: "mid" }) + L(G.circleOf(TF, 70, 30.6, P, 64), { tone: "faint" }) });

// the grids: a dished, drilled molybdenum dome
const RG = (30 * 30 + 6 * 6) / (2 * 6);
const GC = 76 - RG;
const domeR = (s) => Math.sqrt(Math.max(0, RG * RG - (s - GC) ** 2));
const domeSlope = (s) => -(s - GC) / Math.max(domeR(s), 0.6);
const DOME = [...Array.from({ length: 22 }, (_, i) => { const s = 70 + 6 * (1 - (1 - i / 22) ** 2); return [s, domeR(s), i ? 1 : 0]; }), [76, 0]];
const HOLES = [at(G.pointOf(TF, 76, 0, 0))];
for (let i = 1; i <= 7; i++) {
  const r = i * 3.9;
  HOLES.push(...G.dotsOf(TF, GC + Math.sqrt(RG * RG - r * r), r, i * 6, P, { all: true, phase: i * 0.26 }));
}
turned(TF, DOME, { tone: "hi", lit: true }, { name: "thruster.grid", smooth: { slope: domeSlope, radius: domeR }, extra: `<g data-part="holes">${D(HOLES, { size: 0.42, tone: "hi" })}</g>` });

// main propellant port and line
const BOSS = G.frameAlong(G.pointOf(TF, 53, 31, 90 * DEG), [0, 0, 1]);
turned(BOSS, [[-0.1, 2.2], [2.5, 2.2]], { tone: "hi" }, { name: "thruster.port" });
pipe("line.main", [[-97, 0, 108], [X0 + 53, 0, 108], [X0 + 53, 0, ZA + 33.5]], 1.1);

// neutraliser cathode on its stem, and its line
const N_DEG = 40;
const N_DIR = [0, Math.cos(N_DEG * DEG), Math.sin(N_DEG * DEG)];
const N_R = 43.2;
const NF = G.frameOf([X0, N_R * N_DIR[1], ZA + N_R * N_DIR[2]], [1, 0, 0], [0, 1, 0], [0, 0, 1]);
const STEM = G.frameAlong(G.pointOf(TF, 67.5, 37, N_DEG * DEG), N_DIR);
turned(STEM, [[-0.05, 1.2], [N_R - 3.2 - 37, 1.2]], { tone: "mid" }, { name: "neutraliser.stem" });
band(NF, 56, 73, 3.2, { tone: "hi" }, { name: "neutraliser.body", inner: L(G.arcOf(NF, 60, 3.2, P) + G.arcOf(NF, 69, 3.2, P), { tone: "faint" }) });
band(NF, 73, 77, 2.3, { tone: "hi" }, { name: "neutraliser.keeper", extra: L(G.circleOf(NF, 77, 1.1, P, 14), { tone: "lo" }) + D([at(G.pointOf(NF, 77, 0, 0))], { size: 0.5, tone: "hi" }) });
const N_TIP = G.pointOf(NF, 78, 0, 0);
pipe("line.neutraliser", [[-97, 8, 108], [-72, 8, 108], [-51, NF.o[1], NF.o[2]], [X0 + 56, NF.o[1], NF.o[2]]], 0.8);

A.settle(R, P);
R.items.sort((a, b) => a.key - b.key);
A.auditOrExit(R, P);

// SVG stand-in for the beam, shown only when WebGL is missing
const fallback = [];
for (const [dy, dz] of [[0, 0], [0, 16], [0, -16], [15, 8], [-15, 8], [15, -8], [-15, -8]]) {
  const from = [XG - 2, dy, ZA + dz];
  const to = [XG + PLUME * 0.8, dy * 1.35, ZA + dz * 1.35];
  fallback.push(k.fadeLineSvg([at(from), at(to)], { fade: [3, 60], tone: "lit" }));
}

// the beam probe downstream
const front = [];
{
  const [x, y] = [118, -38];
  front.push(S(k.cylinder(x, y, 4.2, 0, 3, P, 24, 0.4), { tone: "mid" }));
  front.push(S(k.cylinder(x, y, 1.8, 3, ZA - 3.5 - 3, P, 18), { tone: "mid", crease: "none" }));
  front.push(L([24, 44].map((z) => k.sideArc(x, y, 1.8, z, P, 12)).join(""), { tone: "faint" }));
  const block = { x: x - 3.5, y: y - 3.5, w: 7, d: 7, r: 1.5 };
  front.push(S(k.slabOf(block, ZA - 3.5, 7, P, 3, 0.4), { tone: "mid" }));
  front.push(D([at([x, y, ZA + 3.5])], { size: 0.45 }));
  const ARM = G.frameAlong([x, y + 3.5, ZA], [0, 1, 0]);
  front.push(S(G.disc(0, 12.6, 1.1, ARM, P), { tone: "mid" }));
  const CUP = G.frameAlong([x, y + 20.5, ZA], [1, 0, 0]);
  front.push(S(G.disc(-2.6, 2.6, 4.5, CUP, P), { tone: "hi" }) + L(G.circleOf(CUP, 2.6, 3.1, P, 24), { tone: "faint" }) + D([at(G.pointOf(CUP, 2.6, 0, 0))], { size: 0.45 }));
  record(A.cylinder(x, y, 4.2, 0, 3, { name: "stand.probe" }));
}

const KNOB = { at: [-98, 48], r: 4.6, top: 5.2, sweep: 270 };
{
  const [x, y] = KNOB.at;
  front.push(S(k.cylinder(x, y, 8.6, 0, 0.7, P, 40), { tone: "lo", crease: "none" }));
  const ticks = k.radialTicks(x, y, 8.4, 30, 5, 0.7, [1.1, 2], P, (-KNOB.sweep / 2) * DEG, KNOB.sweep * DEG);
  front.push(L(ticks.minor, { tone: "lo" }), L(ticks.major, { tone: "mid" }));
  front.push(S(k.cylinder(x, y, KNOB.r, 0.7, KNOB.top - 0.7, P, 32, 0.5), { tone: "hi" }));
  front.push(L(k.knurl(x, y, KNOB.r, 0.7, KNOB.top, 30, P), { tone: "lo" }));
}
const pointerAt = (share) => {
  const angle = (-KNOB.sweep / 2 + KNOB.sweep * share) * DEG;
  const [x, y] = KNOB.at;
  return k.lineOnTop([x, y], [x + Math.sin(angle) * KNOB.r, y - Math.cos(angle) * KNOB.r], KNOB.top, P);
};
front.push(`<path data-part="pointer" class="iso-line" data-tone="hi" data-free="start" d="${pointerAt(0)}"/>`);

const LABEL_TEXT =
  "A gridded ion thruster on a thrust stand. The thruster is a cone and drum ringed by magnets, closed at the front by a dished grid drilled with holes; a small neutraliser cathode sits beside the grid and two thin xenon lines feed it from a manifold. A throttle knob sits on the base. The thruster is bolted to a sled on two rails. When the beam is on, a pale blue plume leaves the grid, the sled is pushed back against the plunger of a dial gauge, and the needle reads the thrust.";

const sled = `<g data-part="sled">${R.items.map((item) => item.svg).join("")}<g class="ie-fallback">${fallback.join("")}</g></g>`;
const svg = k.figureSvg({ width: W, height: H, label: LABEL_TEXT, body: [back.join(""), sled, front.join("")], className: "ie-back" });

const DATA = {
  W,
  H,
  P,
  camera: glCamera(P),
  model: MODEL,
  travel: TRAVEL,
  fullScale: FULL_SCALE,
  sweep: SWEEP,
  gauge: { at: GAUGE, r: GAUGE_R, top: GAUGE_TOP },
  knob: KNOB,
  xg: XG,
  za: ZA,
  r0: R_BEAM,
  plume: PLUME,
  neutraliser: N_TIP,
};

const CSS = readFileSync(join(HERE, "ion.css"), "utf8");
const LIVE = readFileSync(join(HERE, "live.js"), "utf8").replace("__DATA__", JSON.stringify(DATA)).replace("__MODEL__", readFileSync(join(HERE, "model.mjs"), "utf8").replace(/^export /gm, ""));

const full = MODEL.at(1);
const body = k.plateHtml({
  fig: "Fig 1",
  title: "Ion thruster on a thrust stand",
  hint: "Hover to throttle the beam",
  readout: "beam off · 0 mN",
  keys: [
    { mark: "lit", label: "Grids, gauge plunger and needle: where the push is made and where it is read" },
    { mark: "blue", label: "Xenon ions leaving at up to 40 km/s" },
    { mark: "raised", label: "Sled on rails, free to slide" },
  ],
  caption: `A gridded ion thruster with the proportions and throttle range of NASA's NSTAR engine, which flew on Deep Space 1 and Dawn. Xenon is ionised inside the drum, and ${full.volts} V between the two grids throws the ions out at ${full.speed.toFixed(0)} km/s; the small cathode beside the grid adds electrons so the craft stays neutral. At full power the push is ${full.thrust.toFixed(0)} mN, about the weight of two sheets of paper. The sled's travel is drawn large so the needle can show it.`,
  body: `<div class="iso-stage ie-stage" tabindex="0" role="slider" aria-label="Ion thruster: arrow keys throttle the beam, Home switches it off, End is full power" aria-valuemin="0" aria-valuemax="${Math.round(full.thrust)}" aria-valuenow="0">${svg}<canvas class="ie-layer ie-gl" aria-hidden="true"></canvas></div>`,
});

const file = THEME === "light" ? "ion-thruster-light.html" : "ion-thruster.html";
writeFileSync(join(HERE, file), k.pageHtml({ title: "Ion thruster on a thrust stand", theme: THEME, body: `<style>${CSS}</style>${body}`, script: kitScript() + glScript() + LIVE, width: 760 }));
console.log("wrote", file, "·", R.items.length, "sled items");
