import { motion } from 'framer-motion';

/**
 * Plus1 得分动画组件
 * 
 * 用于显示游戏中的得分反馈效果，在指定位置显示 "+1" 文字，
 * 带有缩放、上浮和淡出的动画效果。
 * 
 * @component
 * @example
 * ```tsx
 * 当得分变化时，可以使用 Plus1 组件来显示 "+1" 动画：
 * { score !== 0 && (
 *     <Plus1
 *       key={score}
 *       position={{ left: plus1Pos.left, top: plus1Pos.top }}
 *     />
 *   )}
 * ```
 * 
 * @param {number} props.position.left - 距离左边的像素距离
 * @param {number} props.position.top - 距离顶部的像素距离
 * 
 * @description
 * 动画效果：
 *   - 缩放从0到1（0.3秒，弹性缓动）
 *   - 向上移动15像素（0.6秒，缓出）
 *   - 透明度在前2/3时间保持1，最后1/3时间淡出到0
 *   - 总动画时长：0.6秒
 */
export interface Plus1Props {
  position: { left: number; top: number };
}

export const Plus1 = ({ position }: Plus1Props) => {
  return (
    <motion.div
      className="absolute text-9xl font-bold text-black dark:text-white pointer-events-none select-none"
      style={{
        left: position.left,
        top: position.top,
        zIndex: 10,
      }}
      initial={{ scale: 0, opacity: 1, y: 0 }}
      animate={{
        scale: 1,
        y: -15,
        opacity: [1, 1, 0],
        transition: {
          scale: { duration: 0.3, ease: [0.3, 1.3, 0.3, 1] },
          y: { duration: 0.6, ease: 'easeOut' },
          opacity: { times: [0, 0.666, 1], duration: 0.6, ease: 'linear', delay: 0 },
        }
      }}
    >
      +1
    </motion.div>
  )
}
