import { cn } from "@/lib/utils";
import React, { useState, useLayoutEffect, useRef, useMemo } from "react";
import {
  PolarAngleAxis,
  RadialBar,
  RadialBarChart as RechartsRadialBarChart, // Renamed to avoid conflict
  ResponsiveContainer,
} from "recharts";
import "./radial-bar-chart.css";

interface RadialBarChartProps {
  value: number;
  max?: number;
  unit?: string;
  className?: string;
  barColor?: 'blue' | 'green' | 'yellow' | 'red' | 'gray';
  backgroundColor?: string;
}

const RadialBarChart: React.FC<RadialBarChartProps> = ({
  value,
  max = 200,
  unit,
  className,
  barColor = "green",
  backgroundColor = "var(--radial-bar-chart-color-bg)",
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerSize, setContainerSize] = useState(0);

  useLayoutEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const resizeObserver = new ResizeObserver((entries) => {
      if (entries[0]) {
        const { width, height } = entries[0].contentRect;
        setContainerSize(Math.min(width, height));
      }
    });

    resizeObserver.observe(container);
    return () => resizeObserver.disconnect();
  }, []);

  const data = useMemo(() => [{ name: "value", value }], [value]);

  const valueFontSize = containerSize * 0.2;
  const unitFontSize = containerSize * 0.06;

  return (
    <div ref={containerRef} className={cn("relative h-full w-full", className)}>
      <ResponsiveContainer width="100%" height="100%">
        <RechartsRadialBarChart
          innerRadius="75%"
          outerRadius="100%"
          data={data}
          startAngle={225}
          endAngle={-45}
        >
          <PolarAngleAxis type="number" domain={[0, max]} tick={false} />
          <RadialBar
            background={{ fill: backgroundColor }}
            dataKey="value"
            cornerRadius="100px"
            fill={`var(--radial-bar-chart-color-${barColor})`}
          />
        </RechartsRadialBarChart>
      </ResponsiveContainer>
      <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center pt-4">
        <span
          className="font-semibold text-gray-900"
          style={{ fontSize: valueFontSize }}
        >
          {value}
        </span>
        {unit && (
          <span className="text-gray-400" style={{ fontSize: unitFontSize }}>
            {unit}
          </span>
        )}
      </div>
    </div>
  );
};

const RadialBarChartExample = () => {
  return (
    <div className="flex h-[600px] w-[500px] flex-col items-center">
      <RadialBarChart value={120} unit="kwh" max={200} />
      {/* <div className="flex items-center space-x-3 text-gray-500">
           <span>功能1</span>
           <span>·</span>
           <span>功能2</span>
           <span>·</span>
           <span>功能3</span>
        </div> */}
    </div>
  );
};

export default RadialBarChart;
export { RadialBarChart, RadialBarChartExample };
