import React from "react";
// @ts-ignore
import "../../index.css"

interface TextLinkProps extends React.HTMLAttributes<HTMLAnchorElement> {
  content: string;
  href: string;
  className?: string;
}

// 文字链接，字体永远为蓝色
const TextLink: React.FC<TextLinkProps> = ({ content, href, className, ...props }) => {
  return (
    <a href={href} className={"!text-blue-700 " + className} {...props}>{content}</a>
  );
};

export default TextLink;
