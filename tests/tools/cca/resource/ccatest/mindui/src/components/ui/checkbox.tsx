"use client"

import * as React from "react"
import { useState } from "react"
import * as CheckboxPrimitive from "@radix-ui/react-checkbox"
// @ts-ignore
import checkIcon from "../../assets/check-mark.svg"
import { motion, AnimatePresence } from 'framer-motion';

import { cn } from "@/lib/utils"

function Checkbox({
  className,
  ...props
}: React.ComponentProps<typeof CheckboxPrimitive.Root>) {
  const [check, setCheck] = useState(props.defaultChecked)
  const checked = props.checked ?? check
  return (
    <CheckboxPrimitive.Root
      data-slot="checkbox"
      className={cn(
        "relative w-14 h-14 peer aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive size-14 shrink-0 rounded-[20%] outline-none disabled:cursor-not-allowed disabled:opacity-50",
        className
      )}
      {...props}
      onClick={() => setCheck(!check)}
    >
      <AnimatePresence mode="sync" initial={false}>
        {checked
          ? (
            <motion.span
              key="checked"
              className="absolute inset-0 flex items-center justify-center text-current transition-none bg-blue-700 rounded-[20%]"
              initial={{ opacity: 0, scale: 0.5 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.5 }}
              transition={{
                opacity: { duration: 0.1, ease: [0.61, 1, 0.88, 1] },
                scale: { type: 'spring', damping: 45.03, stiffness: 512.028, mass: 1 }
              }}
            >
              <img src={checkIcon} alt="check" className="w-8/14 h-5.5/14" />
            </motion.span>
          ) : (
            <motion.span
              key="unchecked"
              className="absolute inset-0 flex items-center justify-center text-current transition-none bg-gray-200 rounded-[20%]"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.05, ease: [0.61, 1, 0.88, 1] }}
            />
          )
        }
      </AnimatePresence>
    </CheckboxPrimitive.Root>
  )
}

export { Checkbox }
