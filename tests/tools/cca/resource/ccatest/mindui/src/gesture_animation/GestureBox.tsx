import { motion } from 'framer-motion';
import React, { useState } from 'react';

interface GestureBoxProps {
  children: React.ReactNode;
  borderRadius?: string;
  scale?: number;
  disabled?: boolean;
  className?: string;
  [key: string]: any;
}
const TapBox: React.FC<GestureBoxProps> = ({
  children,
  borderRadius = 'rounded-[0px]',
  scale = 0.95,
  disabled = false,
  mask = true,
  className = '',
  onClick,
  // AI 使用是不允许设置 style 的，但为了保证设置了 style 的车控组件正常工作，保留 props
  ...props
}) => {
  const [active, setActive] = useState(false);

  return (
    <motion.div
      whileTap={{ scale }}
      transition={{ type: 'spring', damping: 26.87, stiffness: 405.823, mass: 1 }}
      className={`${className} ${borderRadius} relative inline-block ${disabled ? 'pointer-events-none' : ''}`}
      onTapStart={() => setActive(true)}
      onTapCancel={() => setActive(false)}
      onTap={() => {
        setActive(false)
        if (onClick) {
          onClick();
        }
      }}
      {...props}
    >
      {children}
      {mask && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: active ? 1 : 0 }}
          transition={{ type: 'spring', damping: 26.87, stiffness: 405.823, mass: 1 }}
          className="absolute inset-0 pointer-events-none"
          style={{
            boxShadow: 'inset 0 0 0 1000px var(--color-gray-100)',
            borderRadius: 'inherit',
          }}
        />
      )}
    </motion.div>
  );
};

export default TapBox;
