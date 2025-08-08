import React, { useEffect } from "react";
import { animate, useMotionValue } from "framer-motion";
import "./loading.css"

// 极坐标转笛卡尔
function polarToCartesian(cx: number, cy: number, r: number, angle: number) {
  const a = ((angle - 90) * Math.PI) / 180.0;
  return {
    x: cx + r * Math.cos(a),
    y: cy + r * Math.sin(a),
  };
}

// 生成圆弧 path
function describeArc(cx: number, cy: number, r: number, startAngle: number, endAngle: number) {
  const start = polarToCartesian(cx, cy, r, startAngle);
  const end = polarToCartesian(cx, cy, r, endAngle);
  const largeArcFlag = endAngle - startAngle <= 180 ? "0" : "1";
  return [
    "M", start.x, start.y,
    "A", r, r, 0, largeArcFlag, 1, end.x, end.y
  ].join(" ");
}

export function LoadingIcon({ size = 44, color = "#FFFFFFE6" }) {
  const STROKE = size * 6 / 44; // 保持线宽比例
  const R = size / 2 - STROKE / 2;
  const CENTER = size / 2;

  // 起点角度（顶部=0°，左侧=-90°）
  const startAngle = useMotionValue(0);
  // 终点角度（右侧=90°）
  const endAngle = useMotionValue(90);
  // 整体旋转角度
  const rotateValue = useMotionValue(0);

  // 计算 path
  const [arcPath, setArcPath] = React.useState(
    describeArc(CENTER, CENTER, R, 0, 90)
  );

  // 监听角度变化，更新 path（叠加整体旋转）
  useEffect(() => {
    const update = () => {
      const rotate = rotateValue.get();
      setArcPath(
        describeArc(
          CENTER,
          CENTER,
          R,
          startAngle.get() + rotate,
          endAngle.get() + rotate
        )
      );
    };
    const unsub1 = startAngle.on("change", update);
    const unsub2 = endAngle.on("change", update);
    const unsub3 = rotateValue.on("change", update);
    update();
    return () => {
      unsub1();
      unsub2();
      unsub3();
    };
  }, [startAngle, endAngle, rotateValue, size]);

  // 动画循环（头尾动画）
  useEffect(() => {
    let stop = false;
    function loop() {
      if (stop) return;
      // 计算目标角度
      const nextStart = startAngle.get() + 270;
      const nextEnd = endAngle.get() + 270;
      // 起点动画
      const startAnim = animate(startAngle, nextStart, { duration: 1.5, ease: [0.37, 0, 0.63, 1] });
      // 终点动画
      const endAnim = animate(endAngle, nextEnd, { duration: 1.5, ease: [0.25, 0.1, 0.25, 1] });
      Promise.all([startAnim, endAnim]).then(() => {
        if (!stop) loop();
      });
    }
    loop();
    return () => {
      stop = true;
    };
  }, [startAngle, endAngle]);

  // 匀速整体旋转动画
  useEffect(() => {
    let stop = false;
    function loop() {
      if (stop) return;
      animate(rotateValue, rotateValue.get() + 450, {
        duration: 1.5,
        ease: "linear",
        onComplete: () => {
          if (!stop) loop();
        }
      });
    }
    loop();
    return () => { stop = true; };
  }, [rotateValue]);

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
    >
      {/* 底部完整圆环 */}
      <circle
        cx={CENTER}
        cy={CENTER}
        r={R}
        stroke={color}
        strokeWidth={STROKE}
        opacity={0.2}
        fill="none"
      />
      {/* 动画圆环 */}
      <g>
        <path
          d={arcPath}
          stroke={color}
          strokeWidth={STROKE}
          opacity={0.5}
          fill="none"
          strokeLinecap="round"
        />
      </g>
    </svg>
  );
}

export function Loading() {
  return (
    <div className="w-full h-full flex items-center justify-center">
      <LoadingIcon color="var(--loading-icon-color)" />
    </div>
  )
}