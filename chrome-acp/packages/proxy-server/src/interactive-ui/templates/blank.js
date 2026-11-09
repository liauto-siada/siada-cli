// A small editable starting point. The model may replace this with any UI.
import { mountViewer } from "./viewer.js";
await mountViewer({
  title: "交互页面",
  defaults: { amount: 10 },
  controls: [{ type: "range", key: "amount", label: "数值", min: 0, max: 100, step: 1 }],
  describe: state => `当前数值：${state.amount}`,
  setup(canvas) {
    const context = canvas.getContext("2d");
    let width = 400, height = 280;
    return {
      resize(w, h) { width = w; height = h; canvas.width = w; canvas.height = h; },
      render(dt, state) {
        context.clearRect(0, 0, width, height);
        context.fillStyle = "#427fe6";
        context.fillRect(20, height / 2, (width - 40) * state.amount / 100, 40);
      },
    };
  },
});