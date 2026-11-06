// The geometry and kinematics come from the installed MIT teardown skill.
import { createV8Stage } from "./v8-shared/stage.js";
import { CYL, E, STROKE, bankXY, piston, pressure, psi, strokeOf } from "./v8-shared/kin.js";
import { warmComposer } from "./kit/warm.js";
import { mountViewer } from "./viewer.js";

const clamp = (value, min, max, fallback) => Number.isFinite(value) ? Math.min(max, Math.max(min, value)) : fallback;
const cameras = {
  hero: { az: 0.8, el: 0.45, distance: 1.85 },
  front: { az: 0, el: 0.2, distance: 1.8 },
  side: { az: 1.57, el: 0.2, distance: 1.8 },
  cylinder: { az: 0.3, el: 0.3, distance: 1.05 },
};
const defaults = {
  angle: 12, rpm: 700, speed: 0.05, paused: false, cylinder: 1,
  view: "hero", cut: "glass", isolated: false, explode: 0, camera: cameras.hero,
};
const phases = { POWER: "做功", EXHAUST: "排气", INTAKE: "进气", COMPRESSION: "压缩" };
function normalize(value) {
  const view = Object.hasOwn(cameras, value.view) ? value.view : "hero";
  const camera = value.camera || cameras[view];
  return {
    angle: clamp(value.angle, 0, 720, 12), rpm: clamp(value.rpm, 300, 8000, 700),
    speed: clamp(value.speed, 0.01, 1, 0.05), paused: !!value.paused,
    cylinder: Math.round(clamp(value.cylinder, 1, 8, 1)),
    view, cut: ["glass", "section", "solid"].includes(value.cut) ? value.cut : "glass",
    isolated: !!value.isolated, explode: clamp(value.explode, 0, 1, 0),
    camera: { az: clamp(camera.az, -20, 20, cameras[view].az), el: clamp(camera.el, -0.2, 1.4, cameras[view].el), distance: clamp(camera.distance, 0.45, 4, cameras[view].distance) },
  };
}
await mountViewer({
  title: "V8 发动机 · 交互拆解",
  defaults, normalize,
  controls: [
    { type: "button", label: "播放 / 暂停", action: state => ({ paused: !state.paused }) },
    { type: "select", key: "view", label: "视角", options: [["hero", "整体"], ["front", "正面"], ["side", "侧面"], ["cylinder", "气缸内部"]], change: (state, value) => ({ view: value, camera: { ...cameras[value] } }) },
    { type: "select", key: "cut", label: "剖切", options: [["glass", "透明"], ["section", "剖面"], ["solid", "实体"]] },
    { type: "select", key: "cylinder", label: "气缸", numeric: true, options: CYL.map(cylinder => [cylinder.c, String(cylinder.c)]) },
    { type: "checkbox", key: "isolated", label: "隔离当前气缸" },
    { type: "range", key: "explode", label: "拆解程度", min: 0, max: 1, step: 0.05, change: (state, value) => ({ explode: value, paused: value > 0 || state.paused }) },
    { type: "range", key: "rpm", label: "转速 RPM", min: 300, max: 8000, step: 100 },
    { type: "range", key: "angle", label: "曲轴角度", min: 0, max: 720, step: 1, change: (state, value) => ({ angle: value, paused: true }) },
    { type: "button", label: "请助手解释当前气缸", prompt: "请结合当前视角和曲轴角度，解释我选中的气缸正在做什么。" },
  ],
  describe: state => `第 ${state.cylinder} 缸 · ${phases[strokeOf(psi(state.cylinder, state.angle))]} · 压力 ${pressure(psi(state.cylinder, state.angle)).toFixed(1)} bar\n缸径 ${E.bore} mm · 行程 ${STROKE} mm · 连杆 ${E.rod} mm`,
  inspectViews: {
    assembled: { paused: true, angle: 12, cut: "solid", explode: 0, isolated: false },
    section: { paused: true, angle: 160, cut: "section", explode: 0, isolated: true },
    exploded: { paused: true, angle: 12, cut: "glass", explode: 0.65, isolated: false },
  },
  async setup(canvas, initialState) {
    const stage = createV8Stage({ canvas });
    stage.setQuality({ samples: 0, ao: false, shadow: 1024 });
    await warmComposer(stage.renderer, stage.composer, stage.scene, stage.camera);
    return {
      resize: stage.resize,
      render(dt, state) {
        if (!state.paused && !state.explode) state.angle = (state.angle + state.rpm / 60 * 360 * dt * state.speed) % 720;
        const cylinder = CYL[state.cylinder - 1];
        const focus = state.view === "cylinder";
        const [x, y] = bankXY(cylinder.bank, 0, 170);
        const target = focus ? [x * 0.001, y * 0.001, cylinder.z * 0.001] : [0, 0.12, 0];
        // Keep the lifted head and rocker layers inside the frame when opening.
        target[1] += state.explode * 0.28;
        stage.setCut(state.cut, cylinder.z * 0.001);
        stage.eng.setRefract(false);
        stage.frame(state.angle, { tx: target[0], ty: target[1], tz: target[2], az: state.camera.az, el: state.camera.el, d: state.camera.distance * (1 + state.explode * 0.6), sx: 0, sy: 0 }, { solo: state.isolated ? state.cylinder - 1 : -1, charge: 1, arrows: 1, explode: state.explode });
      },
      metrics: state => ({ pistonMm: piston(state.cylinder - 1, state.angle).s, pressureBar: pressure(psi(state.cylinder, state.angle)), strokeMm: STROKE, crankY: stage.eng.crank.position.y, rootY: stage.eng.root.position.y }),
      dispose() {
        stage.scene.traverse(object => {
          object.geometry?.dispose();
          for (const material of Array.isArray(object.material) ? object.material : [object.material]) material?.dispose();
        });
        stage.composer.dispose(); stage.renderer.dispose();
      },
    };
  },
});