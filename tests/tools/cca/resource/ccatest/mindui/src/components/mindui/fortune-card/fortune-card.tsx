import React, { useState } from "react";
import { motion, type PanInfo } from "motion/react";
import "./fortune-card.css";

interface CardData {
  id: number;
  title: string;
  content: string;
  backContent: string;
  subText: string;
}

interface FortuneCardProps {
  cards: CardData[];
}

const FortuneCard: React.FC<FortuneCardProps> = ({ cards }) => {
  // 自动获取当前日期和星期
  const getCurrentDateInfo = () => {
    const now = new Date();
    const year = now.getFullYear();
    const month = String(now.getMonth() + 1).padStart(2, "0");
    const day = String(now.getDate()).padStart(2, "0");
    const date = `${year}/${month}/${day}`;

    const weekdays = [
      "星期日",
      "星期一",
      "星期二",
      "星期三",
      "星期四",
      "星期五",
      "星期六",
    ];
    const dayOfWeek = weekdays[now.getDay()];

    return { date, dayOfWeek };
  };

  const [currentIndex, setCurrentIndex] = useState(0); // 从中间开始
  const [flippedCards, setFlippedCards] = useState<Set<number>>(new Set());
  const [isDragging, setIsDragging] = useState(false);

  // 处理拖动
  const handleDragEnd = (
    event: MouseEvent | TouchEvent | PointerEvent,
    info: PanInfo,
  ) => {
    setIsDragging(false);
    const threshold = 50;

    if (info.offset.y > threshold) {
      // 向下拖动 - 切换到上一张
      setCurrentIndex((prev) => Math.max(0, prev - 1));
    } else if (info.offset.y < -threshold) {
      // 向上拖动 - 切换到下一张
      setCurrentIndex((prev) => Math.min(cards.length - 1, prev + 1));
    }
  };

  // 处理卡片点击翻转
  const handleCardClick = (cardId: number) => {
    if (isDragging) return; // 拖动时不触发点击

    setFlippedCards((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(cardId)) {
        newSet.delete(cardId);
      } else {
        newSet.add(cardId);
      }
      return newSet;
    });
  };

  // 计算卡片的位置和样式
  const getCardStyle = (index: number) => {
    const offset = index - currentIndex;
    const absOffset = Math.abs(offset);

    // 显示当前卡片前后各3张卡片（总共7张）
    if (absOffset > 3) {
      return { display: "none" as const };
    }

    let x: number = 0; // 添加X轴偏移
    let y: number = 0;
    let scale: number = 1;
    let opacity: number = 1;
    let z: number = 0;
    let rotateZ: number = 0;
    let transformOrigin: string = "center center"; // 旋转中心点

    if (offset === 0) {
      // 当前卡片
      x = 0;
      y = 0;
      scale = 1.0; // 当前卡片保持原始大小
      opacity = 1;
      z = 20;
      rotateZ = 0;
      transformOrigin = "center center";
    } else if (offset < 0) {
      // 上方卡片 - 顺时针扇形展开，整体向右偏移
      x = 10; // 上方卡片整体向右偏移
      y = -50; // 卡片偏移高度
      scale = 0.97 + offset * 0.05; // 更明显的缩放差异
      opacity = 1 + offset * 0.18;
      z = 20 + offset * 6;
      rotateZ = 5 + offset * 4; // 增大顺时针旋转角度
      transformOrigin = "top left"; // 所有上方卡片都围绕当前卡片的下边中心旋转
    } else {
      // 下方卡片 - 逆时针扇形展开，整体向左偏移
      x = -10; // 下方卡片整体向左偏移
      y = 50; // 卡片偏移高度
      scale = 0.97 - offset * 0.05; // 更明显的缩放差异
      opacity = 1 - offset * 0.18;
      z = 20 - offset * 6;
      rotateZ = 5 + offset * -4; // 增大逆时针旋转角度
      transformOrigin = "bottom right"; // 所有下方卡片都围绕当前卡片的上边中心旋转
    }

    return {
      x,
      y,
      scale,
      opacity,
      z,
      rotateZ,
      transformOrigin,
      zIndex: 100 - absOffset,
    };
  };

  return (
    <div className="relative w-full h-full flex items-center justify-center perspective-[1000px]">
      {/* 卡片容器 */}
      {/* 卡片上下叠放 */}
      <div className="relative flex items-center justify-center">
        {cards.map((card, index) => {
          const cardStyle = getCardStyle(index);
          if (cardStyle.display === "none") return null;

          const isActive = index === currentIndex;
          const isFlipped = flippedCards.has(card.id);
          const hasAnyFlipped = flippedCards.size > 0;

          // 如果有卡片翻转，只显示翻转的卡片
          if (hasAnyFlipped && !isFlipped) {
            return null;
          }

          // 获取当前日期信息
          const { date, dayOfWeek } = getCurrentDateInfo();

          return (
            <motion.div
              key={card.id}
              className={`absolute transform-3d ${isActive || isFlipped ? "cursor-pointer" : "cursor-default"}`}
              initial={false}
              animate={{
                x: isFlipped ? 0 : ((cardStyle as any).x ?? 0), // 添加X轴偏移
                y: isFlipped ? 0 : ((cardStyle as any).y ?? 0),
                scale: isFlipped ? 1 : ((cardStyle as any).scale ?? 1), // 翻转时不变大，只改变尺寸
                opacity: isFlipped ? 1 : ((cardStyle as any).opacity ?? 1),
                z: isFlipped ? 50 : ((cardStyle as any).z ?? 0),
                rotateY: isFlipped ? 180 : 0,
                rotateZ: isFlipped ? 0 : ((cardStyle as any).rotateZ ?? 0), // 修复类型报错，确保类型一致
              }}
              whileHover={
                isActive || isFlipped
                  ? {
                      x: isFlipped ? 0 : ((cardStyle as any).x ?? 0), // 保持X轴偏移
                      scale: isFlipped ? 1 : ((cardStyle as any).scale ?? 1) * 1.02,
                      y: isFlipped ? -5 : ((cardStyle as any).y ?? 0) - 5,
                      transition: { duration: 0.2 },
                    }
                  : {}
              }
              whileTap={
                isActive || isFlipped
                  ? {
                      x: isFlipped ? 0 : ((cardStyle as any).x ?? 0), // 保持X轴偏移
                      scale: isFlipped ? 1 : ((cardStyle as any).scale ?? 1) * 0.98,
                      transition: { duration: 0.1 },
                    }
                  : {}
              }
              drag={isActive && !hasAnyFlipped ? "y" : false}
              dragConstraints={{ top: -100, bottom: 100 }}
              dragElastic={0.2}
              onDragStart={() => setIsDragging(true)}
              onDragEnd={handleDragEnd}
              transition={{
                type: "spring",
                stiffness: 300,
                damping: 30,
                duration: 0.6,
              }}
              onClick={() =>
                isActive || isFlipped ? handleCardClick(card.id) : undefined
              }
              style={{
                width: isFlipped ? "833px" : "738px",
                height: isFlipped ? "997px" : "548px",
                zIndex: isFlipped ? 1000 : ((cardStyle as any).zIndex ?? 0),
                pointerEvents: isFlipped || isActive ? "auto" : "none",
                transformOrigin: isFlipped
                  ? "center center"
                  : ((cardStyle as any).transformOrigin ?? "center center"),
                transition: "width 0.3s ease-in-out, height 0.3s ease-in-out",
              }}
            >
              {/* 卡片正面 */}
              <motion.div
                className={`absolute inset-0 flex h-full w-full flex-col rounded-2xl bg-[var(--fortune-card-bg)] backface-hidden ${
                  isActive
                    ? "shadow-[0_25px_50px_-12px_rgba(0,0,0,0.25)]"
                    : "shadow-[0_10px_25px_-3px_rgba(0,0,0,0.1),0_4px_6px_-2px_rgba(0,0,0,0.05)]"
                }`}
                transition={{
                  duration: 0.4,
                  ease: "easeInOut",
                }}
              >
                {/* 卡片头部 */}
                <div className="mt-[28px] ml-[28px] flex items-center justify-between">
                  <div className="flex items-center space-x-2">
                    <span className="text-xl">🎁</span>
                    <span className="text-xl font-medium text-gray-600">
                      {card.title}
                    </span>
                  </div>
                </div>

                {/* 卡片主要内容 */}
                <div className="flex flex-1 items-center justify-center p-8">
                  <div className="text-center">
                    <h2 className="mb-6 text-[100px] leading-tight font-bold text-gray-900">
                      {card.content}
                    </h2>
                  </div>
                </div>

                {/* 卡片底部 */}
                <div className="mb-[45px] p-4 text-center">
                  <p className="text-2xl text-gray-400">点开看看藏了什么</p>
                </div>
              </motion.div>

              {/* 卡片背面 */}
              <motion.div
                className="absolute inset-0 flex h-full w-full flex-col rounded-2xl bg-[var(--fortune-card-bg)] shadow-[0_25px_50px_-12px_rgba(0,0,0,0.25)] backface-hidden"
                style={{
                  transform: "rotateY(180deg)",
                }}
                transition={{
                  duration: 0.4,
                  ease: "easeInOut",
                }}
              >
                {/* 背面头部 - 日期 */}
                <div className="mt-[65px] ml-[60px]">
                  <div className="mt-[15px] text-3xl text-gray-500">{date}</div>
                  <div className="text-3xl font-medium text-gray-600">
                    {dayOfWeek}
                  </div>
                </div>

                {/* 背面主要内容 */}
                <div className="flex flex-1 items-center justify-start px-[62px]">
                  <div className="text-left">
                    <h3 className="mb-8 text-[110px] leading-relaxed font-bold whitespace-pre-line text-gray-900">
                      {card.backContent}
                    </h3>
                  </div>
                </div>

                {/* 背面底部 */}
                <div className="mb-[50px] ml-[60px] text-left">
                  <p className="text-2xl text-gray-500">{card.subText}</p>
                </div>
              </motion.div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
};

// Example组件展示FortuneCard的使用
const FortuneCardExample = () => {
  // 默认卡片数据
  const defaultCards: CardData[] = [
    {
      id: 1,
      title: "001",
      content: '"不着急"',
      backContent: "今天已经比昨天/更靠近答案了",
      subText: "慢慢来也是种节奏",
    },
    {
      id: 2,
      title: "002",
      content: '"慢慢来"',
      backContent: "每一步都算数/每一天都有意义",
      subText: "进步不在于速度",
    },
    {
      id: 3,
      title: "003",
      content: '"好好生活"',
      backContent: "生活本身就是/最好的答案",
      subText: "珍惜当下的美好",
    },
    {
      id: 4,
      title: "004",
      content: '"保持热爱"',
      backContent: "热爱可以抵御/一切平庸",
      subText: "心中有火，眼里有光",
    },
    {
      id: 5,
      title: "005",
      content: '"相信自己"',
      backContent: "你比想象中/更有力量",
      subText: "每个人都是独特的存在",
    },
    {
      id: 6,
      title: "006",
      content: '"做自己"',
      backContent: "做自己/是一件很酷的事情",
      subText: "没有人能定义你",
    },
    {
      id: 7,
      title: "007",
      content: '"向前看"',
      backContent: "未来的路/总是充满希望",
      subText: "前方有更美好的风景",
    },
    {
      id: 8,
      title: "008",
      content: '"勇敢一点"',
      backContent: "勇气不是没有恐惧/而是战胜恐惧",
      subText: "勇敢是最美的品质",
    },
    {
      id: 9,
      title: "009",
      content: '"保持初心"',
      backContent: "最初的梦想/值得用一生去守护",
      subText: "初心是最珍贵的财富",
    },
    {
      id: 10,
      title: "010",
      content: '"拥抱改变"',
      backContent: "改变意味着/新的可能性",
      subText: "变化中蕴藏着机遇",
    },
    {
      id: 11,
      title: "011",
      content: '"学会感恩"',
      backContent: "感恩让生活/变得更加美好",
      subText: "感恩的心最温暖",
    },
    {
      id: 12,
      title: "012",
      content: '"享受过程"',
      backContent: "过程比结果/更值得珍惜",
      subText: "路上的风景最动人",
    },
    {
      id: 13,
      title: "013",
      content: '"保持好奇"',
      backContent: "好奇心是/智慧的开始",
      subText: "世界等待你去探索",
    },
    {
      id: 14,
      title: "014",
      content: '"坚持梦想"',
      backContent: "梦想是心灵的/指路明灯",
      subText: "永远不要放弃希望",
    },
    {
      id: 15,
      title: "015",
      content: '"温柔待己"',
      backContent: "对自己温柔一点/你值得被善待",
      subText: "自我关爱是智慧",
    },
  ];
  return (
    <div className="h-full w-full">
      <FortuneCard cards={defaultCards} />
    </div>
  );
};

export default FortuneCard;
export { FortuneCardExample, type CardData };
