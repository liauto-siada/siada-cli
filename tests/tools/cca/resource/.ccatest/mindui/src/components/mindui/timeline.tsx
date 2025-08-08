import * as React from "react";
import { useLayoutEffect, useRef, useState } from "react";

export interface TimelineItem {
  title: string;
  description?: string;
  date?: string;
}

export interface TimelineProps {
  items?: TimelineItem[];
  reverse?: boolean;
  className?: string;
}

const Timeline: React.FC<TimelineProps> = ({
  items = [],
  reverse = false,
  className,
}) => {
  const timelineItems: TimelineItem[] =
    items && items.length ? (reverse ? [...items].reverse() : items) : [];

  const ref = useRef<HTMLOListElement>(null);
  const [dims, setDims] = useState({ width: 0, height: 0 });

  useLayoutEffect(() => {
    const container = ref.current;
    if (!container) return;
    const resizeObserver = new ResizeObserver((entries) => {
      if (entries[0]) {
        const { width, height } = entries[0].contentRect;
        setDims({ width, height });
      }
    });
    resizeObserver.observe(container);
    return () => resizeObserver.disconnect();
  }, []);

  const dotSize = dims.width * 0.02;
  // const titleSize = dims.width * 0.07;
  // const dateSize = dims.width * 0.04;
  // const descriptionSize = dims.width * 0.05;

  return (
    <ol ref={ref} className={`relative flex flex-col py-8 ${className || ""}`}>
      {timelineItems.map((item, idx) => (
        <li key={idx} className="relative flex min-h-[40px]">
          {/* 左侧：圆点和虚线 */}
          <div
            className="relative mr-[40px] flex flex-col items-center"
            // style={{ marginTop: titleSize / 2 }}
            style={{ marginTop: 21 }}
          >
            {/* 圆点 */}
            <span
              className="z-10 block rounded-full bg-gray-950"
              style={{
                width: dotSize,
                height: dotSize,
                marginTop: dotSize / 2,
              }}
            />
            {/* 虚线（非最后一个才显示） */}
            {idx !== timelineItems.length - 1 && (
              <span
                className="absolute top-3 left-1/2 z-0 w-1.5 -translate-x-1/2 border-l-3 border-dotted border-gray-100"
                // style={{ height: `calc(100% + ${titleSize / 2}px)` }}
                style={{ height: `calc(100% + 21px)` }}
              />
            )}
          </div>
          {/* 右侧内容：dot和title同行，dot用mt-[5px]微调 */}
          <div className="mb-[70px] flex-1">
            <div className="flex">
              <span
                className="text-5xl leading-[72px] font-bold text-gray-900"
                // style={{ fontSize: titleSize }}
              >
                {item.title}
              </span>
            </div>
            {item.date && (
              <div
                className="mt-1 text-2xl text-gray-400"
                // style={{ fontSize: dateSize }}
              >
                {item.date}
              </div>
            )}
            {item.description && (
              <div
                className="mt-6 text-3xl leading-[48px] text-gray-600"
                // style={{ fontSize: descriptionSize }}
              >
                {item.description}
              </div>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
};

export default Timeline;

export { Timeline };

// 示例：混合模式
export const TimelineDemo = () => {
  const items = [
    { title: "俄罗斯全面入侵乌克兰" },
    {
      title: "布查惨案曝光",
      date: "2022年4月26日",
      description:
        "俄军从基辅周边撤退后，在布查等城市发现大量平民遇害的证据，引发国际社会强烈谴责，多国指控俄罗斯犯下战争罪。",
    },
    { title: "马里乌波尔亚速钢铁厂陷落" },
  ];
  return (
    <div className="h-[500px] w-[600px]">
      <Timeline items={items} />
    </div>
  );
};
