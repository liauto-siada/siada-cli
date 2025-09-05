import { motion, AnimatePresence } from 'framer-motion';
import React from 'react';

/**
 * ShowingBox 显示容器组件
 * 
 * 一个带有进入和退出动画的容器组件，可以控制内容的显示和隐藏。
 * 支持普通退出动画和强调退出动画两种模式。
 * 
 * @component
 * @example
 * ```tsx
 * const [isVisible, setIsVisible] = useState(false);
 * const [useEmphasis, setUseEmphasis] = useState(false);
 * 
 * return (
 *   <div className="relative h-screen">
 *     <button onClick={() => setIsVisible(!isVisible)}>
 *       切换显示
 *     </button>
 *     <button onClick={() => setUseEmphasis(!useEmphasis)}>
 *       切换强调动画: {useEmphasis ? '开启' : '关闭'}
 *     </button>
 *     
 *     <ShowingBox 
 *       showing={isVisible}
 *       emphasisAnimation={useEmphasis}
 *       className="bg-white rounded-lg shadow-lg"
 *     >
 *       <div className="p-8">
 *         <h2>弹窗内容</h2>
 *         <p>这里是要显示的内容</p>
 *       </div>
 *     </ShowingBox>
 *   </div>
 * );
 * ```
 * 
 * @param {ShowingBoxProps} props - 组件属性
 * @param {React.ReactNode} props.children - 要显示的子元素内容
 * @param {string} [props.className] - 可选的CSS类名，用于自定义样式
 * @param {Boolean} props.showing - 控制组件的显示和隐藏状态
 * @param {Boolean} [props.emphasisAnimation=false] - 可选的强调动画模式，影响退出动画效果
 * 
 * @description
 * 功能特点：
 * - 使用绝对定位，内容居中显示
 * - 进入时带有淡入和缩放动画
 * - 退出时支持两种动画模式：普通缩小淡出 / 强调放大后缩小淡出
 * - 根据显示状态自动管理用户交互（pointer-events）
 * - 需要父容器设置相对定位（relative）
 */
interface ShowingBoxProps {
  children: React.ReactNode;
  className?: string;
  showing: Boolean;
  emphasisAnimation?: Boolean;
}
const ShowingBox: React.FC<ShowingBoxProps> = ({
  children,
  className = '',
  showing,
  emphasisAnimation = false,
}) => {
  return (
    <AnimatePresence>
      {showing && (
        <motion.div
          className={`absolute inset-0 flex items-center justify-center ${className} ${showing ? 'pointer-events-auto' : 'pointer-events-none'}`}
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1, transition: { opacity: { duration: 0.3, ease: 'linear' }, scale: { duration: 0.3, ease: [0.3, 1.3, 0.3, 1] } } }}
          exit={
            emphasisAnimation
              ? {
                  opacity: [1, 0],
                  scale: [1, 1.2, 0],
                  transition: {
                    opacity: { duration: 0.25, ease: 'linear', delay: 0.15 },
                    scale: {
                      duration: 0.4,
                      times: [0, 0.375, 1],
                      ease: ['easeOut', [0.45, 0, 0.55, 1]],
                    },
                  }
                }
              : {
                opacity: 0,
                scale: 0,
                transition: {
                  opacity: { duration: 0.25, ease: 'linear'},
                  scale: { duration: 0.25, ease: [0.45, 0, 0.55, 1] },
                },
              }
          }
        >
          {children}
        </motion.div>
  )}
    </AnimatePresence>

  );
};

export default ShowingBox;
