/* PETG as it actually looks, for every page that draws the jig.

   Printed PETG is a glossy plastic with a soft clearcoat sheen; metallic
   ("silk") PETG carries fine flakes that read as a dull metal. The
   colors are real filament colors, not UI tokens. Each part gets a
   slightly different shade of its filament, so two parts in the same
   color still read as two parts where they meet. The viewer picks a
   scheme or sets each group; the choice is remembered per browser. */
import * as THREE from 'three';

export const FILAMENTS = {
  black:    { name: 'Black',    color: '#1c1e21', rough: 0.30, metal: 0.00, coat: 0.55 },
  grey:     { name: 'Grey',     color: '#878d93', rough: 0.34, metal: 0.00, coat: 0.45 },
  blue:     { name: 'Blue',     color: '#1f5ea6', rough: 0.30, metal: 0.00, coat: 0.55 },
  green:    { name: 'Green',    color: '#2e8a58', rough: 0.30, metal: 0.00, coat: 0.55 },
  metallic: { name: 'Metallic', color: '#a9b0b8', rough: 0.40, metal: 0.70, coat: 0.25 },
};

/* The groups a viewer colors by: what is printed together, roughly. */
export const GROUPS = {
  base:     { name: 'Base',       parts: ['stator', 'sole_plate'] },
  ring:     { name: 'Ring',       parts: ['rotor'] },
  arc:      { name: 'Arc',        parts: ['arc'] },
  carriage: { name: 'Carriage',   parts: ['saddle', 'shoe', 'receiver'] },
  drive:    { name: 'Drive',      parts: ['driver', 'drive_block', 'drive_cap'] },
  small:    { name: 'Sleeves & mount', parts: ['sleeve_a', 'sleeve_b', 'sleeve_c',
              'mount_screw', 'mount_wing_nut', 'mount_hex_nut'] },
  ctrl:     { name: 'Controller', parts: ['ctrl_box', 'ctrl_lid'] },
};

/* Schemes chosen for contrast: neighbors never share a filament. The
   base is matte-dark in most, because the spec wants what sits under the
   specimen to drop out of feature matching. */
export const SCHEMES = {
  contrast: { name: 'Contrast', base: 'black', ring: 'blue', arc: 'green', carriage: 'grey',
              drive: 'metallic', small: 'grey', ctrl: 'black' },
  stealth:  { name: 'Stealth', base: 'black', ring: 'grey', arc: 'black', carriage: 'grey',
              drive: 'metallic', small: 'metallic', ctrl: 'black' },
  ocean:    { name: 'Ocean', base: 'grey', ring: 'blue', arc: 'metallic', carriage: 'blue',
              drive: 'black', small: 'metallic', ctrl: 'grey' },
  forest:   { name: 'Forest', base: 'black', ring: 'green', arc: 'grey', carriage: 'green',
              drive: 'metallic', small: 'grey', ctrl: 'black' },
  metallic: { name: 'Metallic', base: 'black', ring: 'metallic', arc: 'grey', carriage: 'metallic',
              drive: 'blue', small: 'grey', ctrl: 'black' },
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
};

const KEY = 'jig.petg.v1';
export function loadChoice() {
  try { const v = JSON.parse(localStorage.getItem(KEY) || 'null'); if (v && v.groups) return v; } catch (e) {}
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
export function hardwareMaterial(kind) {
  const h = HARDWARE[kind] || HARDWARE.steel;
  return new THREE.MeshStandardMaterial({ color: new THREE.Color(h.color), roughness: h.rough, metalness: h.metal });
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
