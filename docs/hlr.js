/* Hidden-line rendering, drawn the way a draughtsman would: a line wherever
   a surface turns away from the eye (a silhouette) or turns sharply (a
   crease), and nothing behind a surface.

   Creases alone -- EdgesGeometry -- cannot draw a smooth part: a screw's
   shank, a wing head, a round boss has no crease to draw, so it vanished
   from the drawing and left only its end circles. So this draws from the
   rendered picture instead. Pass one renders every surface's normal and
   depth off-screen; pass two inks each pixel whose depth jumps (an
   outline) or whose normal turns (a crease, a thread's crest) against its
   neighbours. What is hidden is hidden because it never reached the depth
   buffer. Annotations -- paths, rays -- go over the top unchanged. */
import * as THREE from 'three';

const NORMAL_VS = `
varying vec3 vN;
void main() {
  vN = normalize(normalMatrix * normal);
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}`;
const NORMAL_FS = `
varying vec3 vN;
void main() {
  vec3 n = normalize(vN);
  if (!gl_FrontFacing) n = -n;
  gl_FragColor = vec4(n * 0.5 + 0.5, 1.0);
}`;
const INK_FS = `
uniform sampler2D tNormal;
uniform sampler2D tDepth;
uniform vec2 res;
uniform float near, far, depthK, normalK;
uniform bool ortho;
uniform vec3 ink, paper;
float lin(float d) {
  if (ortho) return near + d * (far - near);
  float z = d * 2.0 - 1.0;
  return 2.0 * near * far / (far + near - z * (far - near));
}
void main() {
  vec2 uv = gl_FragCoord.xy / res, px = 1.0 / res;
  float d0 = texture2D(tDepth, uv).r;
  vec3 n0 = texture2D(tNormal, uv).rgb * 2.0 - 1.0;
  float z0 = lin(d0);
  float e = 0.0;
  vec2 off[4];
  off[0] = vec2(px.x, 0.0); off[1] = vec2(-px.x, 0.0);
  off[2] = vec2(0.0, px.y); off[3] = vec2(0.0, -px.y);
  for (int i = 0; i < 4; i++) {
    float d = texture2D(tDepth, uv + off[i]).r;
    bool bg0 = d0 >= 0.99999, bg = d >= 0.99999;
    if (bg0 && bg) continue;
    if (bg0 != bg) { e = 1.0; break; }                    // the outline against the ground
    float z = lin(d);
    // keep the line on the nearer surface, so it is one pixel, not two
    if (z0 > z && abs(z - z0) / min(z, z0) > depthK) { e = 1.0; break; }
    vec3 n = texture2D(tNormal, uv + off[i]).rgb * 2.0 - 1.0;
    if (!bg0 && 1.0 - dot(n0, n) > normalK) e = max(e, 1.0);
  }
  gl_FragColor = vec4(mix(paper, ink, e), 1.0);
  #include <colorspace_fragment>
}`;

export class HiddenLine {
  constructor(renderer, { ink = '#dfe7ee', paper = '#22272e', depthK = 0.012,
                          creaseDeg = 30 } = {}) {
    this.r = renderer;
    this.rt = new THREE.WebGLRenderTarget(1, 1, {
      type: THREE.HalfFloatType,
      depthTexture: new THREE.DepthTexture(1, 1, THREE.FloatType),
    });
    this.normalMat = new THREE.ShaderMaterial({
      vertexShader: NORMAL_VS, fragmentShader: NORMAL_FS, side: THREE.DoubleSide });
    this.inkMat = new THREE.ShaderMaterial({
      uniforms: {
        tNormal: { value: this.rt.texture }, tDepth: { value: this.rt.depthTexture },
        res: { value: new THREE.Vector2(1, 1) }, near: { value: 1 }, far: { value: 1000 },
        ortho: { value: false },
        depthK: { value: depthK }, normalK: { value: 1 - Math.cos(creaseDeg * Math.PI / 180) },
        ink: { value: new THREE.Color(ink) }, paper: { value: new THREE.Color(paper) },
      },
      vertexShader: 'void main() { gl_Position = vec4(position.xy, 0.0, 1.0); }',
      fragmentShader: INK_FS, depthTest: false, depthWrite: false,
    });
    this.quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), this.inkMat);
    this.quad.frustumCulled = false;
    this.quadScene = new THREE.Scene();
    this.quadScene.add(this.quad);
    this.quadCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  }
  setColors(ink, paper) {
    this.inkMat.uniforms.ink.value.set(ink);
    this.inkMat.uniforms.paper.value.set(paper);
  }
  /* Draw `scene` from `camera` into the renderer's current viewport and
     scissor. `overlays` are drawn over the drawing as they are. */
  render(scene, camera, overlays = []) {
    const r = this.r, pr = r.getPixelRatio();
    const W = r.domElement.width, H = r.domElement.height;
    if (this.rt.width !== W || this.rt.height !== H) this.rt.setSize(W, H);
    const vp = r.getViewport(new THREE.Vector4()).multiplyScalar(pr);
    this.rt.viewport.copy(vp); this.rt.scissor.copy(vp); this.rt.scissorTest = true;
    // pass one: surfaces only -- no lines, no annotations
    const hidden = [];
    const keepOut = new Set(overlays);
    scene.traverse(o => {
      if (!o.visible) return;
      let inOverlay = false;
      for (let p = o; p; p = p.parent) if (keepOut.has(p)) { inOverlay = true; break; }
      // lines, annotations and anything marked see-through stay out of the drawing
      if (o.isLine || o.isPoints || o.isSprite || inOverlay || o.userData.noHLR) { o.visible = false; hidden.push(o); }
    });
    const bg = scene.background, cc = r.getClearColor(new THREE.Color()), ca = r.getClearAlpha();
    scene.background = null;
    scene.overrideMaterial = this.normalMat;
    r.setRenderTarget(this.rt);
    r.setClearColor(0x808080, 1);
    r.clear();
    r.render(scene, camera);
    scene.overrideMaterial = null;
    scene.background = bg;
    r.setClearColor(cc, ca);
    for (const o of hidden) o.visible = true;
    r.setRenderTarget(null);
    // pass two: ink where depth jumps or the surface turns
    const u = this.inkMat.uniforms;
    u.res.value.set(W, H);
    u.near.value = camera.near; u.far.value = camera.far;
    u.ortho.value = !!camera.isOrthographicCamera;
    r.render(this.quadScene, this.quadCam);
    // annotations on top
    if (overlays.length) {
      const ac = r.autoClear;
      r.autoClear = false;
      r.clearDepth();
      const off = [];
      scene.traverse(o => {
        if (!o.visible || o === scene) return;
        let inOverlay = false;
        for (let p = o; p; p = p.parent) if (keepOut.has(p)) { inOverlay = true; break; }
        if (!inOverlay && (o.isMesh || o.isLine || o.isPoints || o.isSprite)) { o.visible = false; off.push(o); }
      });
      // without its background, which would paint over the drawing
      const bg2 = scene.background;
      scene.background = null;
      r.render(scene, camera);
      scene.background = bg2;
      for (const o of off) o.visible = true;
      r.autoClear = ac;
    }
  }
}
