import React, { useState, useLayoutEffect, useRef } from "react";
import {
  ResponsiveContainer,
  LineChart as RechartsLineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Legend,
} from "recharts";
import type { DefaultLegendContentProps } from "recharts";
import { cn } from "@/lib/utils";
import "./line-chart.css";

// 保持与 BarChart 一致的数据结构
export interface DataPoint {
  [key: string]: string | number;
}

// LineChart 的 Props 定义
export interface LineChartProps {
  data: DataPoint[];
  dataKeys: string | string[]; // 支持单条或多条折线
  xAxisKey?: string;
  margin?: {
    top?: number;
    right?: number;
    bottom?: number;
    left?: number;
  };
  colors?: string[];
  showGrid?: boolean;
  showTooltip?: boolean;
  showLegend?: boolean;
  showXAxis?: boolean;
  showYAxis?: boolean;
  className?: string;
  strokeWidth?: number; // 折线宽度
  dot?: boolean; // 是否显示数据点
}

export default function LineChart({
  data,
  dataKeys,
  xAxisKey = "name",
  margin = { top: 5, right: 30, left: 20, bottom: 5 },
  colors = ["var(--line-color-blue)", "var(--line-color-green)", "var(--line-color-yellow)", "var(--line-color-red)", "var(--line-color-gay)"],
  showGrid = true,
  showLegend = true,
  showXAxis = true,
  showYAxis = true,
  className,
  strokeWidth,
}: LineChartProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [dims, setDims] = useState({ width: 0, height: 0 });

  // 响应式配置，移除 barSize
  const [responsiveConfig, setResponsiveConfig] = useState({
    showXAxis: true,
    showYAxis: true,
    showGrid: true,
    showLegend: true,
    strokeWidth: 8,
  });

  const keysArray = Array.isArray(dataKeys) ? dataKeys : [dataKeys];

  // 响应式逻辑，与 BarChart 保持一致
  useLayoutEffect(() => {
    if (!ref.current) return;
    const resizeObserver = new ResizeObserver((entries) => {
      if (entries[0]) {
        const { width, height } = entries[0].contentRect;
        setDims({ width, height });

        if (width > 500) {
          setResponsiveConfig({
            strokeWidth: strokeWidth || 8,
            showXAxis: showXAxis,
            showYAxis: showYAxis,
            showGrid: showGrid,
            showLegend: showLegend,
          });
        } else if (width > 300) {
          setResponsiveConfig({
            strokeWidth: strokeWidth || 6,
            showXAxis: false,
            showYAxis: false,
            showGrid: false,
            showLegend: false,
          });
        } else {
          setResponsiveConfig({
            strokeWidth: strokeWidth || 4,
            showXAxis: false,
            showYAxis: false,
            showGrid: false,
            showLegend: false,
          });
        }
      }
    });
    resizeObserver.observe(ref.current);
    return () => resizeObserver.disconnect();
  }, [showXAxis, showYAxis, showGrid, showLegend, strokeWidth]);

  const tickFontSize = dims.width * 0.03;

  return (
    <div ref={ref} className={cn("h-full w-full", className)}>
      <ResponsiveContainer>
        <RechartsLineChart data={data} margin={margin}>
          {responsiveConfig.showGrid && (
            <CartesianGrid
              stroke="var(--color-cartesian-grid)"
              vertical={false}
            />
          )}
          {responsiveConfig.showXAxis && (
            <XAxis
              dataKey={xAxisKey}
              axisLine={false}
              tickLine={false}
              tick={{
                fontSize: tickFontSize,
                fill: "var(--color-line-chart-x-axis)",
              }}
              padding={{ left: 15, right: 15 }}
            />
          )}
          {responsiveConfig.showYAxis && (
            <YAxis
              axisLine={false}
              tickLine={false}
              tick={{
                fontSize: tickFontSize,
                fill: "var(--color-line-chart-y-axis)",
              }}
            />
          )}
          {responsiveConfig.showLegend && keysArray.length > 1 && (
            <Legend content={CustomLegend} />
          )}
          {keysArray.map((key, index) => (
            <Line
              key={key}
              dataKey={key}
              type="linear"
              stroke={colors[index % colors.length]}
              strokeWidth={responsiveConfig.strokeWidth}
              dot={false}
            />
          ))}
        </RechartsLineChart>
      </ResponsiveContainer>
    </div>
  );
}

const CustomLegend = ({ payload }: DefaultLegendContentProps) => {
  if (!payload || !payload.length) return null;
  return (
    <div className="mt-2 flex flex-wrap justify-center gap-4">
      {payload.map((entry, index) => (
        <div key={`item-${index}`} className="flex items-center gap-2">
          <span
            className="inline-block h-4 w-4 rounded-full"
            style={{ backgroundColor: entry.color }}
            aria-hidden="true"
          />
          <span className="text-xl font-bold text-gray-600 dark:text-gray-400">
            {entry.value}
          </span>
        </div>
      ))}
    </div>
  );
};

// 示例数据，与 BarChart 保持一致
const sampleData = [
  { name: "1月", A: 4000, B: 2400, C: 1600 },
  { name: "2月", A: 3000, B: 1398, C: 1602 },
  { name: "3月", A: 2000, B: 9800, C: 1200 },
  { name: "4月", A: 2780, B: 3908, C: 1872 },
  { name: "5月", A: 1890, B: 4800, C: 2910 },
  { name: "6月", A: 2390, B: 3800, C: 1410 },
  { name: "7月", A: 3490, B: 4300, C: 810 },
];

// 单线图示例
const SingleLineChartExample: React.FC = () => (
  <div className="h-[350px] w-full">
    <LineChart
      data={sampleData}
      dataKeys="A"
      xAxisKey="name"
      colors={["#0A5BFC"]}
    />
  </div>
);

// 多线图示例
const MultiLineChartExample: React.FC = () => (
  <div className="h-[350px] w-full">
    <LineChart data={sampleData} dataKeys={["A", "B", "C"]} xAxisKey="name" />
  </div>
);

export { LineChart, SingleLineChartExample, MultiLineChartExample };
