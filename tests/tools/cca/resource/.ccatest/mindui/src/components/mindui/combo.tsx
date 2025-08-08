import { motion, AnimatePresence } from 'framer-motion'

/**
 * Combo 连击动画组件
 * 
 * 用于显示游戏中的连击效果，当连击数大于1时显示弹跳动画，
 * 当连击结束时显示消失动画。
 * 
 * @component
 * @example
 * ```tsx
 * const [combo, setCombo] = useState(0);
 * const [lastCombo, setLastCombo] = useState(0);
 * 
 * // 在游戏逻辑中更新连击数
 * const handleHit = () => {
 *   setLastCombo(combo);
 *   setCombo(combo + 1);
 * };
 * 
 * const handleMiss = () => {
 *   setLastCombo(combo);
 *   setCombo(0);
 * };
 * 
 * return (
 *   <div className="relative">
 *     <Combo combo={combo} lastCombo={lastCombo} />
 *     // 其他游戏内容
 *   </div>
 * );
 * ```
 * 
 * @param {ComboProps} props - 组件属性
 * @param {number} props.combo - 当前连击数，大于1时显示连击动画
 * @param {number} props.lastCombo - 上一次的连击数，用于显示连击结束时的退出动画
 * 
 * @description
 * 动画行为：
 * - 当 combo > 1 时：显示 "{combo}X连击!" 文字，带有缩放弹跳动画
 * - 当 combo === 0 且 lastCombo !== 0 时：显示 "{lastCombo}X连击!" 文字，带有淡出缩小动画
 */

interface ComboProps {
  combo: number;
  lastCombo: number;
}

export const Combo = ({ combo, lastCombo }: ComboProps) => {
  return(
    <AnimatePresence>
      {/* combo > 1 时，每次 combo 变化都弹一下 */}
      {combo > 1 && (
        <motion.div
          key={combo}
          className="absolute text-center text-7xl font-bold text-[#222732] dark:text-[#FFFFFFe6] pointer-events-none"
          initial={{ opacity: 1, scale: 1 }}
          animate={{
            opacity: 1,
            scale: [1, 1.2, 1],
            transition: {
              scale: { times: [0, 0.5, 1], duration: 0.4, ease: [0.42, 0, 0.58, 1] },
              opacity: { duration: 0.4 }
            }
          }}
        >
          {combo}X连击!
        </motion.div>
      )}
      {/* combo 变为 0 时，渲染一个 exit 动画 */}
      {combo === 0 && lastCombo !== 0 && (
        <motion.div
          className="absolute text-center text-7xl font-bold text-gray-950 pointer-events-none"
          initial={{ opacity: 1, scale: 1 }}
          animate={{
            opacity: 0,
            scale: 0,
            transition: {
              opacity: { duration: 0.3, ease: 'linear' },
              scale: { duration: 0.3, ease: [0.32, 0, 0.67, 0] }
            }
          }}
        >
          {lastCombo}X连击!
        </motion.div>
      )}
    </AnimatePresence>
  )
}
