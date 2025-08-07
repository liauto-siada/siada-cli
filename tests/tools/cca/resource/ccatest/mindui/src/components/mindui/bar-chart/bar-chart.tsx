import React, { useState, useEffect, useRef, useMemo } from "react";
import {
  ResponsiveContainer,
  BarChart as RechartsBarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Legend,
  Cell,
} from "recharts";
import type { DefaultLegendContentProps } from "recharts";
import { cn } from "@/lib/utils";
import "./bar-chart.css";

export interface DataPoint {
  [key: string]: string | number;
}

export interface BarChartProps {
  data: DataPoint[];
  dataKeys: string | string[]; // 支持单个或多个数据键
  selectedData?: string;
  xAxisKey?: string;
  orientation?: "vertical" | "horizontal"; // 支持横向和纵向
  margin?: {
    top?: number;
    right?: number;
    bottom?: number;
    left?: number;
  };
  colors?: string[]; // 自定义颜色
  showGrid?: boolean;
  showLegend?: boolean;
  showXAxis?: boolean;
  showYAxis?: boolean;
  className?: string;
  barSize?: number; // 柱子大小
  barGap?: number; // 柱子间距
  barCategoryGap?: number; // 分类间距
  unit?: string; // 新增：单位
}

function BarChart({
  data,
  dataKeys,
  selectedData,
  xAxisKey = "name",
  orientation = "vertical",
  margin = { top: 0, right: 0, left: 0, bottom: 0 },
  colors = ["var(--bar-color-blue)", "var(--bar-color-green)", "var(--bar-color-yellow)", "var(--bar-color-red)", "var(--bar-color-gay)"],
  showGrid = true,
  showLegend = true,
  showXAxis = true,
  showYAxis = true,
  className,
  barSize,
  barGap = 4,
  barCategoryGap = 10,
  unit = "", // 新增
}: BarChartProps) {
  const ref = useRef<HTMLDivElement>(null);
  const xRef = useRef<XAxis>(null);
  const yRef = useRef<YAxis>(null);
  const [dims, setDims] = useState({ width: 0, height: 0 });
  const [yAxisMax, setYAxisMax] = useState(0);
  const [xAxisMax, setXAxisMax] = useState(0);
  
  // 使用 ref 来存储临时值，避免在渲染过程中调用 setState
  const tempXAxisMax = useRef(0);
  const tempYAxisMax = useRef(0);
  const xAxisMaxRef = useRef(0);
  const yAxisMaxRef = useRef(0);

  const [responsiveConfig, setResponsiveConfig] = useState({
    showXAxis: true,
    showYAxis: true,
    showGrid: true,
    showLegend: true,
    barSize: 20,
  });

  // 将单个数据键转换为数组
  const keysArray = useMemo(() => {
    return Array.isArray(dataKeys) ? dataKeys : [dataKeys];
  }, [dataKeys]);

  const calculateBarSize = (typeCount: number): number => {
    if (typeCount === 1) return 80;
    if (typeCount === 2) return 32;
    if (typeCount === 3) return 24;
    return 16;
  };

  const autoBarSize = barSize || calculateBarSize(keysArray.length);

  // 监听容器大小变化，实现响应式
  useEffect(() => {
    if (!ref.current) return;
    const resizeObserver = new ResizeObserver((entries) => {
      if (entries[0]) {
        const { width, height } = entries[0].contentRect;
        setDims({ width, height });

        // 简化的响应式配置：只有小于300px才隐藏Y轴
        if (width < 300 || height < 300) {
          setResponsiveConfig({
            showXAxis: showXAxis,
            showYAxis: false, // 小于300px时隐藏Y轴
            showGrid: showGrid,
            showLegend: showLegend,
            barSize: autoBarSize,
          });
        } else {
          setResponsiveConfig({
            showXAxis: showXAxis,
            showYAxis: showYAxis, // 其他情况正常显示Y轴
            showGrid: showGrid,
            showLegend: showLegend,
            barSize: autoBarSize,
          });
        }
      }
    });
    resizeObserver.observe(ref.current);
    return () => {
      resizeObserver.disconnect();
    };
  }, [showXAxis, showYAxis, showGrid, showLegend, autoBarSize]);

  // 计算 X 轴和 Y 轴的最大值
  useEffect(() => {
    let maxX = 0;
    let maxY = 0;

    data.forEach((item) => {
      keysArray.forEach((key) => {
        const value = Number(item[key]);
        if (!Number.isNaN(value)) {
          if (orientation === "vertical") {
            // 垂直柱状图：X轴是数值，Y轴是分类
            maxX = Math.max(maxX, value);
          } else {
            // 水平柱状图：X轴是分类，Y轴是数值
            maxY = Math.max(maxY, value);
          }
        }
      });
    });

    setXAxisMax(maxX);
    setYAxisMax(maxY);
    xAxisMaxRef.current = maxX;
    yAxisMaxRef.current = maxY;
  }, [data, keysArray, orientation]);

  const tickFontSize = Math.round(dims.width * 0.037);

  // 根据字体大小动态计算 margin
  const dynamicMargin = {
    top: margin.top || 0,
    right: margin.right || 0,
    left: margin.left || tickFontSize,
    bottom: margin.bottom || tickFontSize * 0.5,
  };

  // 自定义 X 轴 tick 渲染

  const renderCustomXAxisTick = (
    props: React.SVGProps<SVGTextElement> & { payload?: { value: string } },
  ) => {
    const { style, payload, x = 0, y = 0, ...rest } = props;

    const {
      tickFormatter: _,
      index: __,
      viewBox: ___,
      coordinate: ____,
      verticalAnchor: _____,
      visibleTicksCount: ______,
      ...svgRest
    } = rest as Record<string, unknown>;
    const isSelected =
      selectedData && payload && payload.value === selectedData;
    const mergedStyle = {
      ...style,
      fontSize: tickFontSize, // 强制覆盖字体大小
      fill: isSelected 
        ? "var(--color-bar-chart-x-axis-selected, #000)" 
        : "var(--color-bar-chart-x-axis, #6b7280)",
    };

    if (Number.isNaN(Number(payload?.value))) {
      return (
        <text
          {...svgRest}
          x={Number(x)}
          y={Number(y) + tickFontSize}
          style={mergedStyle}
        >
          {payload && payload?.value}
        </text>
      );
    } else {
      const payloadValue = Number.isNaN(Number(payload?.value))
        ? 0
        : Number(payload?.value);
      const disPlayUnit = payloadValue === xAxisMaxRef.current;
      return (
        <text
          {...svgRest}
          x={Number(x)}
          y={Number(y) + tickFontSize}
          style={mergedStyle}
        >
          {!disPlayUnit ? payload?.value : ""}
          {disPlayUnit ? unit : ""}
        </text>
      );
    }
  };

  // 自定义 Y 轴 tick 渲染

  const renderCustomYAxisTick = (
    props: React.SVGProps<SVGTextElement> & { payload?: { value: string } },
  ) => {
    const { style, payload, x = 0, y = 0, ...rest } = props;

    const {
      tickFormatter: _,
      index: __,
      viewBox: ___,
      coordinate: ____,
      verticalAnchor: _____,
      visibleTicksCount: ______,
      ...svgRest
    } = rest as Record<string, unknown>;
    const isSelected =
      selectedData && payload && payload.value === selectedData;
    const mergedStyle = {
      ...style,
      fontSize: tickFontSize, // 强制覆盖字体大小
      fill: isSelected 
        ? "var(--color-bar-chart-y-axis-selected, #000)" 
        : "var(--color-bar-chart-y-axis, #6b7280)",
    };

    if (Number.isNaN(Number(payload?.value))) {
      return (
        <text
          {...svgRest}
          x={Number(x)}
          y={Number(y) + tickFontSize * 0.4}
          style={mergedStyle}
        >
          {payload && payload?.value}
        </text>
      );
    } else {
      const payloadValue = Number.isNaN(Number(payload?.value))
        ? 0
        : Number(payload?.value);
      const disPlayUnit = payloadValue === yAxisMaxRef.current;
      return (
        <text
          {...svgRest}
          x={Number(x)}
          y={Number(y) + tickFontSize * 0.4}
          style={mergedStyle}
        >
          {!disPlayUnit ? payload?.value : ""}
          {disPlayUnit ? unit : ""}
        </text>
      );
    }
  };

  return (
    <div
      ref={ref}
      className={cn(
        "pointer-events-none relative flex h-full w-full",
        className,
      )}
    >
      {/* 图表 */}
      <div className="flex-1" style={{ minWidth: 0, minHeight: 0 }}>
        <ResponsiveContainer width="100%" height="100%">
          <RechartsBarChart
            data={data}
            margin={dynamicMargin}
            barGap={barGap}
            barCategoryGap={barCategoryGap}
            layout={orientation}
          >
            {responsiveConfig.showGrid && (
              <CartesianGrid
                stroke="var(--color-cartesian-grid)"
                vertical={orientation === "vertical"}
                horizontal={orientation === "horizontal"}
              />
            )}

            {responsiveConfig.showXAxis && (
              <XAxis
                ref={xRef}
                type={orientation === "vertical" ? "number" : "category"}
                dataKey={orientation === "vertical" ? undefined : xAxisKey}
                axisLine={false}
                tickLine={false}
                tick={renderCustomXAxisTick}
                className="text-xs text-gray-500"
              />
            )}

            {responsiveConfig.showYAxis && (
              <YAxis
                ref={yRef}
                type={orientation === "vertical" ? "category" : "number"}
                dataKey={orientation === "vertical" ? xAxisKey : undefined}
                axisLine={false}
                tickLine={false}
                tick={renderCustomYAxisTick}
                className="text-xs text-gray-500"
              />
            )}

            {responsiveConfig.showLegend &&
              showLegend &&
              keysArray.length > 1 && <Legend content={CustomLegend} />}

            {keysArray.map((key, index) => {
              const color = colors[index % colors.length];
              return (
                <Bar
                  key={key}
                  dataKey={key}
                  barSize={autoBarSize}
                  radius={[10, 10, 10, 10]}
                  maxBarSize={responsiveConfig.barSize}
                  fill={color}
                >
                  {data.map((entry, entryIndex) => {
                    const isSelected =
                      selectedData && entry[xAxisKey] === selectedData;
                    const opacity = selectedData ? (isSelected ? 1 : 0.2) : 1;

                    return (
                      <Cell
                        key={`cell-${entryIndex}`}
                        fill={color}
                        fillOpacity={opacity}
                      />
                    );
                  })}
                </Bar>
              );
            })}
          </RechartsBarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

const CustomLegend = ({ payload }: DefaultLegendContentProps) => {
  if (!payload || payload.length === 0) return null;

  return (
    <div className="mt-2 flex flex-wrap justify-center gap-4">
      {payload.map(
        (
          entry: {
            color?: string;
            value: string | number | undefined;
          },
          index: number,
        ) => (
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
        ),
      )}
    </div>
  );
};

export default BarChart;

export { BarChart };

// 示例数据
const sampleData = [
  {
    name: "1月",
    A: 4000,
    B: 2400,
    C: 1600,
  },
  {
    name: "2月",
    A: 3000,
    B: 1398,
    C: 1602,
  },
  {
    name: "3月",
    A: 2000,
    B: 9800,
    C: 1200,
  },
  {
    name: "4月",
    A: 2780,
    B: 3908,
    C: 1872,
  },
  {
    name: "5月",
    A: 1890,
    B: 4800,
    C: 2910,
  },
  {
    name: "6月",
    A: 2390,
    B: 3800,
    C: 1410,
  },
  {
    name: "7月",
    A: 3490,
    B: 4300,
    C: 810,
  },
];

// 示例组件 - 纵向单类型
const VerticalSingleBarChartExample: React.FC = () => {
  return (
    <div className="h-[350px] w-full">
      <BarChart
        data={sampleData}
        dataKeys="A"
        selectedData="3月"
        xAxisKey="name"
        orientation="vertical"
        colors={["#0A5BFC"]}
        unit="(L)"
      />
    </div>
  );
};

// 示例组件 - 纵向多类型
const VerticalMultiBarChartExample: React.FC = () => {
  return (
    <div className="h-[700px] w-full">
      <BarChart
        data={sampleData}
        dataKeys={["A", "B"]}
        selectedData="3月"
        xAxisKey="name"
        orientation="vertical"
        unit="(L)"
      />
    </div>
  );
};

// 示例组件 - 横向单类型
const HorizontalSingleBarChartExample: React.FC = () => {
  return (
    <div className="h-[700px] w-full">
      <BarChart
        data={sampleData}
        dataKeys="A"
        selectedData="3月"
        xAxisKey="name"
        orientation="horizontal"
        colors={["#0A5BFC"]}
        unit="(L)"
      />
    </div>
  );
};

// 示例组件 - 横向多类型
const HorizontalMultiBarChartExample: React.FC = () => {
  return (
    <div className="h-[350px] w-full">
      <BarChart
        data={sampleData}
        dataKeys={["A", "B"]}
        selectedData="3月"
        xAxisKey="name"
        orientation="horizontal"
        unit="(L)"
      />
    </div>
  );
};

export {
  VerticalSingleBarChartExample,
  VerticalMultiBarChartExample,
  HorizontalSingleBarChartExample,
  HorizontalMultiBarChartExample,
};
