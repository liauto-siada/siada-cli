// @ts-ignore
import "../../index.css"

interface BubbleProps {
  content: string;
}

export default function Bubble({ content }: BubbleProps) {
  return (
    <div
      className="
        bg-[#CED5E0]
        dark:bg-[#242424]
        rounded-[100px]
        h-[119px]
        inline-flex
        items-center
        justify-center
        px-[55px]
        text-[28px]
        text-center
        text-[#222732]
        dark:text-[#FFFFFF]
        "
      style={{ minWidth: 0 }}
    >
      {content}
    </div>
  );
}
