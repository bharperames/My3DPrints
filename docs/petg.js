/* PETG as it actually looks, for every page that draws the jig.

   Printed PETG is a glossy plastic with a soft clearcoat sheen; metallic
   ("silk") PETG carries fine flakes that read as a dull metal. The
   colors are real filament colors, not UI tokens. Each part gets a
   slightly different shade of its filament, so two parts in the same
   color still read as two parts where they meet. The viewer picks a
   scheme or sets each group; the choice is remembered per browser. */
import * as THREE from 'three';

/* Lighter than the filament's swatch on a reel, on purpose: the scene's
   ground is a dark slate, and true black PETG vanished into it. Black is
   drawn as the charcoal black PETG reads as under a lamp. */
export const FILAMENTS = {
  black:    { name: 'Black',    color: '#727a85', rough: 0.30, metal: 0.00, coat: 0.55 },
  grey:     { name: 'Grey',     color: '#aab0b7', rough: 0.34, metal: 0.00, coat: 0.45 },
  blue:     { name: 'Blue',     color: '#3a7bcc', rough: 0.30, metal: 0.00, coat: 0.55 },
  green:    { name: 'Green',    color: '#3cae6e', rough: 0.30, metal: 0.00, coat: 0.55 },
  metallic: { name: 'Metallic', color: '#c8ced5', rough: 0.40, metal: 0.65, coat: 0.25 },
};

/* The groups a viewer colors by: what is printed together, roughly. */
export const GROUPS = {
  base:     { name: 'Base',       parts: ['stator', 'puck_a', 'puck_b', 'puck_c', 'corner_foot_a', 'corner_foot_b', 'corner_foot_c'] },
  ring:     { name: 'Ring',       parts: ['rotor'] },
  arc:      { name: 'Arc',        parts: ['arc'] },
  carriage: { name: 'Carriage',   parts: ['saddle', 'shoe', 'receiver'] },
  drive:    { name: 'Drive',      parts: ['driver', 'drive_block', 'drive_cap'] },
  small:    { name: 'Sleeves & mount', parts: ['sleeve_a', 'sleeve_b', 'sleeve_c',
              'mount_screw', 'mount_wing_nut', 'mount_hex_nut'] },
  ctrl:     { name: 'Controller', parts: ['ctrl_box', 'ctrl_tray', 'ctrl_lid'] },
  plate:    { name: 'Rod field plate', parts: ['rod_plate', 'rod_field_jig'] },
};

/* Schemes chosen for contrast: neighbors never share a filament, and the
   default puts nothing dark against the dark ground. (The spec wanted
   what sits under the specimen matte black for feature matching; that
   is a choice for the print, and Stealth shows it.) */
export const SCHEMES = {
  contrast: { name: 'Contrast', base: 'grey', ring: 'blue', arc: 'green', carriage: 'grey',
              drive: 'metallic', small: 'metallic', ctrl: 'grey', plate: 'green' },
  stealth:  { name: 'Stealth', base: 'black', ring: 'grey', arc: 'black', carriage: 'grey',
              drive: 'metallic', small: 'metallic', ctrl: 'black', plate: 'black' },
  ocean:    { name: 'Ocean', base: 'grey', ring: 'blue', arc: 'metallic', carriage: 'blue',
              drive: 'black', small: 'metallic', ctrl: 'grey', plate: 'grey' },
  forest:   { name: 'Forest', base: 'black', ring: 'green', arc: 'grey', carriage: 'green',
              drive: 'metallic', small: 'grey', ctrl: 'black', plate: 'metallic' },
  metallic: { name: 'Metallic', base: 'black', ring: 'metallic', arc: 'grey', carriage: 'metallic',
              drive: 'blue', small: 'grey', ctrl: 'black', plate: 'blue' },
};

/* Bought hardware, by what it is made of. */
export const HARDWARE = {
  steel:  { color: '#b9bec4', rough: 0.28, metal: 0.92 },
  dark:   { color: '#2a2d31', rough: 0.45, metal: 0.30 },   // black-oxide heads, Hall epoxy
  brass:  { color: '#c9a45a', rough: 0.35, metal: 0.85 },
  magnet: { color: '#c7ccd2', rough: 0.22, metal: 0.95 },   // nickel plating
  pcb:    { color: '#1f6b4a', rough: 0.55, metal: 0.10 },
  cable:  { color: '#30343a', rough: 0.60, metal: 0.00 },
  phone:  { color: '#5a626b', rough: 0.35, metal: 0.40 },
  anodized: { color: '#3b3e43', rough: 0.55, metal: 0.55 },   // the clamp's bead-blasted aluminum
  rubber:   { color: '#141516', rough: 0.85, metal: 0.00 },   // its jaw pads
  // the controller: boards, their parts, the wires and what joins them
  pcb_black: { color: '#1b1d20', rough: 0.55, metal: 0.10 },   // the XIAO
  pcb_green: { color: '#1f6b3a', rough: 0.55, metal: 0.10 },   // Pololu's
  gold:      { color: '#d4a94e', rough: 0.25, metal: 0.95 },   // pads, ENIG
  shield:    { color: '#cfd3d8', rough: 0.30, metal: 0.90 },
  plastic:   { color: '#26282c', rough: 0.50, metal: 0.00 },   // IC bodies, plugs
  ceramic:   { color: '#b59a74', rough: 0.60, metal: 0.00 },   // SMD caps
  solder:    { color: '#d9dde2', rough: 0.18, metal: 1.00 },
  shrink:    { color: '#18191b', rough: 0.70, metal: 0.00 },
  r_body_blue: { color: '#7fa3c0', rough: 0.55, metal: 0.00 }, // 2 W metal oxide
  r_body_tan:  { color: '#d6bf91', rough: 0.55, metal: 0.00 }, // carbon film
  cap_sleeve:  { color: '#1d1f24', rough: 0.45, metal: 0.10 },
  cap_stripe:  { color: '#a9b0b8', rough: 0.45, metal: 0.10 },
  wire_red:    { color: '#d42a2a', rough: 0.50, metal: 0.00 },
  wire_black:  { color: '#1e1f22', rough: 0.50, metal: 0.00 },
  wire_yellow: { color: '#f2c414', rough: 0.50, metal: 0.00 },
  wire_white:  { color: '#efefea', rough: 0.50, metal: 0.00 },
  wire_blue:   { color: '#2563d4', rough: 0.50, metal: 0.00 },
  wire_green:  { color: '#1f9a48', rough: 0.50, metal: 0.00 },
  band_yellow: { color: '#f2c414', rough: 0.50, metal: 0.00 },
  band_violet: { color: '#7d3fc2', rough: 0.50, metal: 0.00 },
  band_gold:   { color: '#c9a45a', rough: 0.30, metal: 0.80 },
  band_brown:  { color: '#6b3e1f', rough: 0.50, metal: 0.00 },
  band_black:  { color: '#151515', rough: 0.50, metal: 0.00 },
  band_orange: { color: '#e8761a', rough: 0.50, metal: 0.00 },
};

const KEY = 'jig.petg.v2';      // v1 remembered the old, too-dark black
export function loadChoice() {
  // a saved choice keeps what it set; a group added since takes its
  // scheme's colour rather than none
  try {
    const v = JSON.parse(localStorage.getItem(KEY) || 'null');
    if (v && v.groups) {
      const base = SCHEMES[v.scheme] || SCHEMES.contrast;
      return { scheme: v.scheme, groups: { ...base, ...v.groups } };
    }
  } catch (e) {}
  return { scheme: 'contrast', groups: { ...SCHEMES.contrast } };
}
export function saveChoice(c) { try { localStorage.setItem(KEY, JSON.stringify(c)); } catch (e) {} }

export function groupOfPart(name) {
  for (const [g, d] of Object.entries(GROUPS)) if (d.parts.includes(name)) return g;
  return 'small';
}

/* A small, stable per-part shade shift, so parts of one color still read
   apart: a few percent of lightness, keyed on the part's name. */
function shade(name) {
  let h = 2166136261;
  for (const ch of name) { h ^= ch.charCodeAt(0); h = Math.imul(h, 16777619); }
  return ((h >>> 0) % 1000) / 1000 * 0.12 - 0.06;
}

export function petgMaterial(filamentKey, partName = '') {
  const f = FILAMENTS[filamentKey] || FILAMENTS.grey;
  const c = new THREE.Color(f.color);
  const hsl = {}; c.getHSL(hsl);
  c.setHSL(hsl.h, hsl.s, Math.min(1, Math.max(0, hsl.l * (1 + shade(partName)) + shade(partName) * 0.04)));
  return new THREE.MeshPhysicalMaterial({
    color: c, roughness: f.rough, metalness: f.metal,
    clearcoat: f.coat, clearcoatRoughness: 0.35,
  });
}
/* Metal shows what it reflects: with nothing round it, steel renders
   near black. The pages hand over a small studio -- a grey room, two soft
   light panels -- for the bought parts to reflect; the printed PETG keeps
   the page's own lighting, so a chosen filament reads as itself. */
let HW_ENV = null;
export function studioEnvironment(renderer) {
  const pm = new THREE.PMREMGenerator(renderer);
  const room = new THREE.Scene();
  room.add(new THREE.Mesh(new THREE.BoxGeometry(10, 10, 10),
    new THREE.MeshBasicMaterial({ color: 0x5a6068, side: THREE.BackSide })));
  for (const [pos, size, k] of [[[0, 0, 4.9], [8, 8], 3.0], [[4.9, 0, 1], [5, 6], 1.6], [[-4.9, 2, 0], [4, 4], 0.8]]) {
    const p = new THREE.Mesh(new THREE.PlaneGeometry(...size),
      new THREE.MeshBasicMaterial({ color: new THREE.Color(k, k, k), side: THREE.DoubleSide }));
    p.position.set(...pos); p.lookAt(0, 0, 0);
    room.add(p);
  }
  HW_ENV = pm.fromScene(room, 0.03).texture;
  pm.dispose();
  return HW_ENV;
}
export function hardwareMaterial(kind) {
  const h = HARDWARE[kind] || HARDWARE.steel;
  return new THREE.MeshStandardMaterial({ color: new THREE.Color(h.color), roughness: h.rough,
    metalness: h.metal, envMap: HW_ENV, envMapIntensity: HW_ENV ? 1.0 : 0 });
}
/* Edges that show on dark filament as well as light. */
export function edgeColor(material) {
  const c = material.color.clone(), hsl = {}; c.getHSL(hsl);
  return hsl.l < 0.25 ? c.clone().offsetHSL(0, 0, 0.22) : c.clone().multiplyScalar(0.4);
}

/* The picker: schemes, then one swatch row per group. `apply()` is
   called with the new choice whenever it changes. */
export function buildPicker(el, choice, apply) {
  const sw = k => `background:${FILAMENTS[k].color}${FILAMENTS[k].metal > 0.3 ? `;background-image:linear-gradient(135deg,#fff6 0,#fff0 45%,#0003 100%)` : ''}`;
  const render = () => {
    el.innerHTML =
      `<div class="pk-row"><span class="pk-lbl">scheme</span><span class="pk-seg">` +
      Object.entries(SCHEMES).map(([k, s]) =>
        `<button data-scheme="${k}" class="${choice.scheme === k ? 'on' : ''}">${s.name}</button>`).join('') +
      `</span></div>` +
      Object.entries(GROUPS).map(([g, d]) =>
        `<div class="pk-row"><span class="pk-lbl">${d.name}</span><span class="pk-sw">` +
        Object.entries(FILAMENTS).map(([k, f]) =>
          `<button data-group="${g}" data-fil="${k}" title="${f.name} PETG" aria-label="${d.name}: ${f.name}" ` +
          `class="${choice.groups[g] === k ? 'on' : ''}" style="${sw(k)}"></button>`).join('') +
        `</span></div>`).join('');
    el.querySelectorAll('[data-scheme]').forEach(b => b.onclick = () => {
      choice.scheme = b.dataset.scheme; choice.groups = { ...SCHEMES[choice.scheme] };
      saveChoice(choice); render(); apply(choice); });
    el.querySelectorAll('[data-group]').forEach(b => b.onclick = () => {
      choice.groups[b.dataset.group] = b.dataset.fil; choice.scheme = 'custom';
      saveChoice(choice); render(); apply(choice); });
  };
  render();
}

export const PICKER_CSS = `
  .pk-row { display:flex; align-items:center; gap:8px; margin:5px 0; flex-wrap:wrap; }
  .pk-lbl { font-size:12px; color:var(--ink-soft); width:104px; flex:0 0 104px; }
  .pk-seg { display:inline-flex; flex-wrap:wrap; border:1px solid var(--edge); border-radius:6px; overflow:hidden; }
  .pk-seg button { border:0; border-radius:0; padding:4px 9px; font-size:12px; }
  .pk-seg button + button { border-left:1px solid var(--edge); }
  .pk-seg button.on { background:var(--accent); color:var(--accent-ink); }
  .pk-sw { display:inline-flex; gap:5px; }
  /* a light rim, so black filament reads against the dark panel */
  .pk-sw button { width:22px; height:22px; padding:0; border-radius:50%; border:2px solid #7d8b92; }
  .pk-sw button.on { border-color:var(--ink); box-shadow:0 0 0 2px var(--accent); }
  .pk-sw button:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
`;
