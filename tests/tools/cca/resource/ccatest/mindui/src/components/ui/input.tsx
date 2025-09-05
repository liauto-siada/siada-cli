import * as React from "react"
import { cn } from "@/lib/utils"
import { Search, X } from "lucide-react"
import { cva, type VariantProps } from "class-variance-authority"

// TODO: 待确认Input的尺寸是固定的，还是根据内容自适应
// FIXME: 宽高的变量应该设置到外层div，而不是input
const InputVariants = cva("", {
  variants: {
    size: {
      xs: "h-[80px] px-[50px] rounded-[20px] text-[28px] font-medium",
      sm: "h-[100px] px-[50px] rounded-[20px] text-[32px] font-medium",
      md: "h-[110px] px-[50px] rounded-[20px] text-[36px] font-medium",
      lg: "h-[120px] px-[60px] rounded-[20px] text-[36px] font-medium",
      xl: "h-[140px] px-[60px] rounded-[20px] text-[36px] font-medium",
    },
  },
  defaultVariants: {
    size: "md",
  },
})

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  variant?: "default" | "search"
  inputSize?: VariantProps<typeof InputVariants>["size"]
}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ value, placeholder, onChange, className, variant = "default", inputSize = "md", type, ...props }, ref) => {
    const [showClearButton, setShowClearButton] = React.useState(!!value && value !== "" && !props.disabled);
    const [inputValue, setInputValue] = React.useState(value);

    const handleClear = () => {
      setInputValue("");
      setShowClearButton(false);
      if (onChange) {
        onChange({ target: { value: "" } } as React.ChangeEvent<HTMLInputElement>);
      }
    };

    return (
      <div className="relative flex items-center ">
        {variant === "search" && type !== "date" && (
          <Search className="absolute left-7 top-1/2 -translate-y-1/2 text-black pointer-events-none" size={30} />
        )}

        <input
          type={type}
          data-slot="input"
          ref={ref}
          value={inputValue}
          onChange={(e) => {
            if (onChange) {
              onChange(e)
            }
            setInputValue(e.target.value);
            setShowClearButton(!!e.target.value && e.target.value !== "" && !props.disabled);
          }}
          placeholder={variant === "search" ? "搜索" : placeholder}
          className={cn(InputVariants({ size: inputSize }),
            "border-input text-black dark:text-white dark:border-gray-600",
            "focus-visible:border-white focus-visible:ring-white focus-visible:ring-opacity-50",
            "disabled:text-gray-400 disabled:cursor-not-allowed",
            "w-full h-full",
            "pr-[14px]", "border-4", "border-[rgba(169,178,199,0.3)]",
            className
          )}
          {...props}
        />

        {showClearButton && (
          <button
            type="button"
            onClick={handleClear}
            className="absolute right-7 top-1/2 -translate-y-1/2 text-black hover:text-gray-600"
          >
            <X />
          </button>
        )}
      </div>
    )
  }
)

Input.displayName = "Input"

export { Input }