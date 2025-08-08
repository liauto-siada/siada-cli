import React, { useState, useEffect, useRef } from "react";
import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
} from "recharts";
import { cn } from "@/lib/utils";
import "./area-chart.css";

export interface DataPoint {
  [key: string]: string | number;
}

export interface AreaChartProps {
  data: DataPoint[];
  dataKey: string;
  name?: string;
  fillOpacity?: number;
  connectNulls?: boolean;
  xAxisKey?: string;
  margin?: {
    top?: number;
    right?: number;
    bottom?: number;
    left?: number;
  };
  className?: string;
}

function AreaChart({
  data,
  dataKey,
  name,
  fillOpacity = 0.6,
  connectNulls = false,
  xAxisKey = "name",
  margin = { top: 0, right: 0, left: 0, bottom: 0 },
  className,
}: AreaChartProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [dims, setDims] = useState({ width: 0, height: 0 });
  const [responsiveConfig, setResponsiveConfig] = useState({
    strokeWidth: 8,
    showXAxis: true,
    showYAxis: true,
    showGrid: true,
  });

  // 监听容器大小变化
  useEffect(() => {
    if (!ref.current) return;

    const resizeObserver = new ResizeObserver((entries) => {
      if (entries[0]) {
        const { width, height } = entries[0].contentRect;
        setDims({ width, height });

        // 根据宽度设置响应式配置
        if (width > 500) {
          setResponsiveConfig({
            strokeWidth: 8,
            showXAxis: true,
            showYAxis: true,
            showGrid: true,
          });
        } else if (width > 300) {
          setResponsiveConfig({
            strokeWidth: 6,
            showXAxis: false,
            showYAxis: false,
            showGrid: false,
          });
        } else {
          setResponsiveConfig({
            strokeWidth: 4,
            showXAxis: false,
            showYAxis: false,
            showGrid: false,
          });
        }
      }
    });

    resizeObserver.observe(ref.current);

    return () => {
      resizeObserver.disconnect();
    };
  }, []);

  // 安全获取首末数据值
  const firstValue = data.length > 0 ? Number(data[0][dataKey]) : 0;
  const lastValue =
    data.length > 0 ? Number(data[data.length - 1][dataKey]) : 0;

  // 判断趋势：上升为红色，下降为绿色
  const isRising = firstValue < lastValue;
  const areaColor = isRising ? "var(--area-color-rising)" : "var(--area-color-falling)";
  const lineColor = isRising ? "var(--line-color-rising)" : "var(--line-color-falling)";

  // 生成唯一的渐变 ID
  const gradientId = `gradient-${dataKey.replace(/\s+/g, "-").toLowerCase()}`;

  // 为每个数据点添加参考线数据
  const dataWithReference = data.map((item) => ({
    ...item,
    [`${dataKey}_reference`]: firstValue,
  }));

  const tickFontSize = dims.width * 0.03;

  return (
    <div ref={ref} className={cn("h-full w-full", className)}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={dataWithReference} margin={margin}>
          {/* 定义渐变色 */}
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={areaColor} stopOpacity={1} />
              <stop offset="100%" stopColor={areaColor} stopOpacity={0} />
            </linearGradient>
          </defs>

          {responsiveConfig.showGrid && (
            <CartesianGrid
              vertical={false}
              stroke="var(--color-cartesian-grid)"
            />
          )}
          {responsiveConfig.showXAxis && (
            <XAxis
              dataKey={xAxisKey}
              axisLine={false}
              tickLine={false}
              padding={{ left: 10, right: 10 }}
              tick={{
                fontSize: tickFontSize,
                fill: "var(--color-area-chart-x-axis)",
              }}
            />
          )}
          {responsiveConfig.showYAxis && (
            <YAxis
              axisLine={false}
              tickLine={false}
              tick={{
                fontSize: tickFontSize,
                fill: "var(--color-area-chart-y-axis)",
              }}
            />
          )}

          {/* 渲染面积图 */}
          <Area
            type="linear"
            dataKey={dataKey}
            name={name || dataKey}
            stroke={lineColor}
            fill={`url(#${gradientId})`}
            strokeWidth={responsiveConfig.strokeWidth}
            fillOpacity={fillOpacity}
            connectNulls={connectNulls}
          />

          {/* 渲染参考线 */}
          <Line
            type="linear"
            dataKey={`${dataKey}_reference`}
            stroke={lineColor}
            strokeDasharray="14 14"
            strokeWidth={responsiveConfig.strokeWidth}
            connectNulls={false}
            dot={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

export default AreaChart;

// 示例数据
const sampleData = [
  { name: "1月", price: 2400 },
  { name: "2月", price: 1398 },
  { name: "3月", price: 9800 },
  { name: "4月", price: 3908 },
  { name: "5月", price: 4800 },
  { name: "6月", price: 3800 },
  { name: "7月", price: 4300 },
];

// 示例组件
const AreaChartsExample: React.FC = () => {
  return <AreaChart data={sampleData} dataKey="price" xAxisKey="name" />;
};

export { AreaChartsExample };
