import React, {
  useRef,
  useMemo,
} from "react";
import {
  ResponsiveContainer,
  PieChart as RechartsPieChart,
  Pie,
  Cell,
} from "recharts";
import { cn } from "../../lib/utils";

export interface PieChartData {
  name: string;
  value: number;
  color?: string;
}

export interface PieChartProps {
  data: PieChartData[];
  showLegend?: boolean;
  innerRadius?: number | string;
  outerRadius?: number | string;
  paddingAngle?: number;
  startAngle?: number;
  endAngle?: number;
  className?: string;
  colors?: string[];
  legendFormatter?: (value: string, name: string) => string;
  legendPosition?: "bottom" | "right";
}

// 默认颜色配置
const DEFAULT_COLORS = [
  "#00803E", // 绿色
  "#1D68FF", // 蓝色
  "#CF9C0E", // 黄色
  "#AD231E", // 红色
  "#222732", // 深灰
  "#0E50D3", // 深蓝
  "#AC7414", // 橙色
  "#1A79FF", // 浅蓝
  "#151E32", // 深色
  "#A9B2C7", // 浅灰
  "#B93A3A", // 深红
];

function PieChart({
  data,
  showLegend = true,
  innerRadius = "70%",
  outerRadius = "100%",
  paddingAngle = 0,
  startAngle = 90,
  endAngle = -270,
  className = "",
  colors = DEFAULT_COLORS,
  legendFormatter,
  legendPosition = "bottom",
}: PieChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  // 验证数据有效性
  const validData = useMemo(() => {
    if (!data || data.length === 0) return [];

    return data.filter(
      (item) =>
        item &&
        typeof item.value === "number" &&
        item.value > 0 &&
        typeof item.name === "string" &&
        item.name.trim() !== "",
    );
  }, [data]);

  // 缓存处理后的数据
  const dataWithColors = useMemo(
    () =>
      validData.map((item, index) => ({
        ...item,
        color: item.color || colors[index % colors.length],
      })),
    [validData, colors],
  );

  // 缓存总数值
  const total = useMemo(
    () => validData.reduce((sum, item) => sum + item.value, 0),
    [validData],
  );

  // 验证数据
  if (validData.length === 0) {
    const message = data.length === 0 ? "暂无数据" : "数据格式无效";
    return (
      <div
        className={cn(
          "flex h-full w-full items-center justify-center text-gray-500 dark:text-gray-400",
          className,
        )}
        role="img"
        aria-label={message}
      >
        {message}
      </div>
    );
  }

  const LegendContent = () => (
    <div
      className={cn(
        "flex",
        legendPosition === "right"
          ? "flex-col items-start gap-y-2"
          : "flex-wrap justify-center gap-x-6 gap-y-2 pt-4",
      )}
      role="list"
      aria-label="图表图例"
    >
      {dataWithColors.map((item, index) => {
        const percent = total > 0 ? Math.round((item.value / total) * 100) : 0;
        const displayName = legendFormatter
          ? legendFormatter(item.name, item.name)
          : item.name;

        return (
          <div
            key={`legend-${index}`}
            className="flex items-center gap-2"
            role="listitem"
          >
            <span
              className="inline-block h-3 w-3 flex-shrink-0 rounded-full"
              style={{ backgroundColor: item.color }}
              aria-hidden="true"
            />
            <span className="text-xl font-bold text-gray-600">
              {displayName} {percent}%
            </span>
          </div>
        );
      })}
    </div>
  );

  return (
    <div
      ref={containerRef}
      className={cn(
        "flex h-full w-full",
        legendPosition === "right"
          ? "flex-row items-center justify-center gap-x-8"
          : "flex-col items-center justify-center",
        className,
      )}
      role="img"
      aria-label={`饼图显示${validData.length}个数据项`}
    >
      <div
        className={cn(
          legendPosition === "right"
            ? "h-full aspect-square"
            : "w-full flex-1",
        )}
      >
        <ResponsiveContainer width="100%" height="100%">
          <RechartsPieChart className="pointer-events-none">
            <Pie
              data={dataWithColors}
              cx="50%"
              cy="50%"
              innerRadius={innerRadius}
              outerRadius={outerRadius}
              paddingAngle={paddingAngle}
              startAngle={startAngle}
              endAngle={endAngle}
              dataKey="value"
            >
              {dataWithColors.map((entry, index) => (
                <Cell
                  key={`cell-${index}`}
                  fill={entry.color}
                  stroke="none"
                  className="transition-opacity hover:opacity-80"
                />
              ))}
            </Pie>
          </RechartsPieChart>
        </ResponsiveContainer>
      </div>
      {showLegend && <LegendContent />}
    </div>
  );
}

export default PieChart;

// 示例数据
const sampleData: PieChartData[] = [
  { name: "驱动", value: 63 },
  { name: "电器", value: 23 },
  { name: "空调", value: 14 },
];

// 示例组件
const PieChartExample: React.FC = () => {
  return (
    <div className="flex w-full flex-col items-center gap-8">
      <div className="h-[320px] w-full">
        <PieChart data={sampleData} legendPosition="bottom" />
      </div>
      <div className="h-[180px] w-[600px]">
        <PieChart data={sampleData} legendPosition="right" />
      </div>
    </div>
  );
};

export { PieChart, PieChartExample };
