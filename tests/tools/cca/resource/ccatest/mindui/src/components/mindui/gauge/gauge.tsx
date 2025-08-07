import React, { useState, useLayoutEffect, useRef, useMemo } from "react";
import {
  ResponsiveContainer,
  PieChart as RechartsPieChart,
  Pie,
  Cell,
} from "recharts";
import { cn } from "@/lib/utils";
import "./gauge.css";

export interface GaugeProps {
  value: number;
  max?: number;
  label?: React.ReactNode;
  unit?: string;
  thicknessRatio?: number;
  color?: 'blue' | 'green' | 'yellow' | 'red' | 'gray';
  trackColor?: string;
  unitColor?: string;
  className?: string;
  startAngle?: number;
  endAngle?: number;
  showLabels?: boolean;
  curvedText?: string;
  isAnimationActive?: boolean;
}

const Gauge: React.FC<GaugeProps> = ({
  value,
  max = 100,
  label,
  unit,
  thicknessRatio = 0.2, // 默认 20%
  color = "blue", // 主色
  trackColor = "var(--gauge-color-track)", // 轨道颜色
  unitColor = "#818A95",
  className = "",
  startAngle = 225,
  endAngle = startAngle - 360,
  showLabels = true,
  curvedText,
  isAnimationActive = false,
}) => {
  const ref = useRef<HTMLDivElement>(null);
  const [containerDims, setContainerDims] = useState({ width: 0, height: 0 });

  useLayoutEffect(() => {
    if (!ref.current) return;
    const resizeObserver = new ResizeObserver((entries) => {
      if (entries[0]) {
        const { width, height } = entries[0].contentRect;
        setContainerDims({ width, height });
      }
    });
    resizeObserver.observe(ref.current);
    return () => resizeObserver.disconnect();
  }, []);

  const containerSize = Math.min(containerDims.width, containerDims.height);
  const data = useMemo(
    () => [
      { name: "value", value: value, color: `var(--gauge-color-${color})` },
      {
        name: "track",
        value: max > value ? max - value : 0,
        color: trackColor,
      },
    ],
    [value, max, color, trackColor],
  );

  const thickness = containerSize * thicknessRatio;
  const outerRadius = containerSize / 2;
  const innerRadius = outerRadius - thickness;

  const labelFontSize = containerSize * 0.3;
  const unitFontSize = Math.round(Math.max(containerSize * 0.059, 18));

  const pathId = "gauge-curved-text-path";

  // Calculate a concentric path for the text outside the gauge
  const textPathRadius = outerRadius + unitFontSize * 1.5; // Padding based on font size
  const cx = containerDims.width / 2;
  const cy = containerDims.height / 2;
  const x1 = cx - textPathRadius;
  const y1 = cy;
  const x2 = cx + textPathRadius;
  const y2 = cy;

  // Path for a 180-degree bottom arc, concentric with the gauge
  const textPathD =
    containerSize > 0
      ? `M ${x1},${y1} A ${textPathRadius},${textPathRadius} 0 0 0 ${x2},${y2}`
      : "";

  return (
    <div
      ref={ref}
      className={cn(
        "pointer-events-none relative flex h-full w-full items-center justify-center",
        className,
      )}
      tabIndex={-1}
    >
      <ResponsiveContainer width="100%" height="100%">
        <RechartsPieChart>
          <Pie
            data={data}
            dataKey="value"
            cx="50%"
            cy="50%"
            innerRadius={innerRadius}
            outerRadius={outerRadius}
            startAngle={startAngle}
            endAngle={endAngle}
            paddingAngle={0}
            isAnimationActive={isAnimationActive}
          >
            {data.map((entry) => (
              <Cell
                key={`cell-${entry.name}`}
                fill={entry.color}
                stroke={entry.color}
              />
            ))}
          </Pie>
        </RechartsPieChart>
      </ResponsiveContainer>
      {showLabels && (
        <div className="absolute inset-0">
          <div
            className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 leading-none font-bold text-gray-900"
            style={{
              fontSize: labelFontSize,
            }}
          >
            {label !== undefined ? label : Math.round(value)}
          </div>
          {unit && (
            <div
              className="absolute left-1/2 text-gray-400"
              style={{
                fontSize: unitFontSize,
                top: `calc(50% + ${containerSize * 0.155}px)`,
                transform: "translateX(-50%)",
              }}
            >
              {unit}
            </div>
          )}
        </div>
      )}
      {curvedText && containerSize > 0 && (
        <svg
          width={containerDims.width}
          height={containerDims.height}
          className="absolute top-0 left-0 overflow-visible"
        >
          <defs>
            <path id={pathId} d={textPathD} />
          </defs>
          <text fill={unitColor}>
            <textPath
              href={`#${pathId}`}
              startOffset="50%"
              textAnchor="middle"
              fontSize={unitFontSize * 1.2}
            >
              {curvedText}
            </textPath>
          </text>
        </svg>
      )}
    </div>
  );
};

// 示例组件 - 速度仪表盘
const SpeedGaugeExample: React.FC = () => {
  return (
    <div className="h-[600px] w-[500px]">
      <Gauge
        value={33}
        max={120}
        unit="km/h"
        color="yellow"
        trackColor="#C7B599"
        startAngle={225}
        curvedText="shis a fhas h"
      />
    </div>
  );
};

// 示例组件 - 档位仪表盘
const GearGaugeExample: React.FC = () => {
  return (
    <div className="h-64 w-64">
      <Gauge
        value={25}
        max={100}
        label="D"
        unit="auto"
        color="blue"
        startAngle={225}
      />
    </div>
  );
};

export default Gauge;
export { Gauge, SpeedGaugeExample, GearGaugeExample };
