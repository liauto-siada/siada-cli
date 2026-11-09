// Responsive controls and lifecycle for generated simulations. Scene geometry
// remains in the author's module; only small user state crosses the UI bridge.
export async function mountViewer({ title, defaults, controls, setup, normalize = value => value, describe = () => "", inspectViews = {} }) {
  const sdk = window.siadaUI;
  window.uiInspection = { ready: false };
  let state = normalize({ ...defaults, ...sdk.state });
  const root = document.getElementById("app");
  const style = document.createElement("style");
  style.textContent = `
    html,body{margin:0;padding:0;background:#f6f8fb}
    .sim{font:14px/1.5 system-ui,sans-serif;color:#172033;padding:12px}
    .sim h2{font-size:18px;margin:0 0 8px}
    .sim-stage{position:relative;width:100%;height:clamp(250px,45vw,440px);background:#edf0f5;border-radius:10px;overflow:hidden}
    .sim-stage canvas{display:block;width:100%;height:100%;touch-action:none;cursor:grab}
    .sim-controls{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-top:12px}
    .sim-controls label{display:flex;flex-direction:column;gap:4px;font-size:14px}
    .sim-controls input,.sim-controls select,.sim-controls button{font:inherit;min-height:30px;width:100%;box-sizing:border-box}
    .sim-controls button,.sim-controls select{border:1px solid #ced6e3;border-radius:6px;background:#fff;padding:4px 8px}
    .sim-controls input[type=checkbox]{width:20px}
    .sim-readout{white-space:pre-wrap;padding:10px;background:white;border-radius:8px;margin-top:10px}
    .sim-error{color:#ad2434}
  `;
  document.head.append(style);
  root.className = "sim";
  const heading = document.createElement("h2");
  heading.textContent = title;
  const surface = document.createElement("div");
  surface.className = "sim-stage";
  const canvas = document.createElement("canvas");
  surface.append(canvas);
  const panel = document.createElement("div");
  panel.className = "sim-controls";
  const readout = document.createElement("div");
  readout.className = "sim-readout";
  root.append(heading, surface, panel, readout);
  const fields = [];
  let scene, active = true, disposed = false, raf, last = performance.now(), lastPaint = 0;
  const capture = () => structuredClone(normalize(state));
  const sync = () => {
    for (const { definition, input, value } of fields) {
      if (input.type === "checkbox") input.checked = !!state[definition.key];
      else if (document.activeElement !== input && definition.type !== "button") input.value = String(state[definition.key]);
      if (value) value.textContent = typeof state[definition.key] === "number" ? String(Number(state[definition.key].toFixed(2))) : String(state[definition.key]);
    }
    readout.textContent = describe(state);
  };
  const publish = () => sdk.setState(capture());
  const apply = (patch, save = true) => {
    state = normalize({ ...state, ...patch });
    sync();
    if (save) publish();
  };
  for (const definition of controls) {
    const label = document.createElement("label");
    const caption = document.createElement("span");
    caption.textContent = definition.label;
    label.append(caption);
    let input, value;
    if (definition.type === "button") {
      input = document.createElement("button");
      input.type = "button";
      input.textContent = definition.text || definition.label;
      input.onclick = () => {
        if (definition.prompt) sdk.submit(typeof definition.prompt === "function" ? definition.prompt(capture()) : definition.prompt);
        else apply(definition.action(capture()));
      };
    } else if (definition.type === "select") {
      input = document.createElement("select");
      for (const [key, text] of definition.options) {
        const option = document.createElement("option");
        option.value = String(key); option.textContent = text; input.append(option);
      }
      input.onchange = () => {
        const value = definition.numeric ? Number(input.value) : input.value;
        apply(definition.change ? definition.change(capture(), value) : { [definition.key]: value });
      };
    } else {
      input = document.createElement("input");
      input.type = definition.type === "checkbox" ? "checkbox" : "range";
      input.min = String(definition.min ?? 0); input.max = String(definition.max ?? 1); input.step = String(definition.step ?? 0.01);
      const patch = () => definition.change
        ? definition.change(capture(), Number(input.value))
        : { [definition.key]: input.type === "checkbox" ? input.checked : Number(input.value) };
      input.oninput = () => apply(patch(), false);
      input.onchange = () => apply(patch());
      if (input.type === "range") { value = document.createElement("output"); caption.append(" ", value); }
    }
    input.setAttribute("aria-label", definition.label);
    label.append(input); panel.append(label); fields.push({ definition, input, value });
  }
  sdk.registerState({ capture, restore: next => apply({ ...defaults, ...next }, false) });
  let drag, wheelTimer;
  canvas.onpointerdown = event => {
    drag = { x: event.clientX, y: event.clientY, camera: { ...state.camera } };
    canvas.setPointerCapture(event.pointerId);
  };
  canvas.onpointermove = event => {
    if (!drag || !state.camera) return;
    apply({ camera: { ...drag.camera, az: drag.camera.az - (event.clientX - drag.x) * 0.01, el: drag.camera.el + (event.clientY - drag.y) * 0.008 } }, false);
  };
  const endDrag = () => { if (drag) publish(); drag = undefined; };
  canvas.onpointerup = endDrag; canvas.onpointercancel = endDrag;
  canvas.addEventListener("wheel", event => {
    if (!state.camera) return;
    event.preventDefault();
    apply({ camera: { ...state.camera, distance: state.camera.distance * Math.exp(event.deltaY * 0.001) } }, false);
    clearTimeout(wheelTimer); wheelTimer = setTimeout(publish, 180);
  }, { passive: false });
  sync();
  try {
    scene = await setup(canvas, state);
    const resize = () => {
      const size = surface.getBoundingClientRect();
      scene.resize?.(size.width, size.height, Math.min(devicePixelRatio || 1, 1.5));
    };
    const observer = new ResizeObserver(resize);
    observer.observe(surface); resize();
    const draw = now => {
      if (disposed || !active) return;
      if (now - lastPaint >= 1000 / 30) {
        scene.render(Math.min(0.1, Math.max(0, (now - last) / 1000)), state);
        last = now; lastPaint = now; sync();
      }
      raf = requestAnimationFrame(draw);
    };
    sdk.onVisibility(visible => {
      active = visible;
      cancelAnimationFrame(raf);
      if (active) { last = performance.now(); raf = requestAnimationFrame(draw); }
    });
    addEventListener("pagehide", () => {
      disposed = true; cancelAnimationFrame(raf); clearTimeout(wheelTimer);
      observer.disconnect(); scene.dispose?.();
    }, { once: true });
    scene.render(0, state);
    window.uiInspection = {
      ready: true, getState: capture, applyState: next => apply(next, false),
      views: inspectViews,
      render: () => { scene.render(0, state); sync(); },
      metrics: () => scene.metrics?.(state) ?? {},
    };
    publish();
    raf = requestAnimationFrame(draw);
  } catch (error) {
    readout.classList.add("sim-error");
    readout.textContent = "无法启动 3D 场景：" + error.message;
    window.uiInspection = { ready: false, error: error.message };
    throw error;
  }
}