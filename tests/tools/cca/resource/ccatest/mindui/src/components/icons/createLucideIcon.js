/**
 * @license lucide-react v0.0.1 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */

import { forwardRef, createElement } from 'react';
import { mergeClasses, toKebabCase, toPascalCase } from './utils.js';
import Icon from './Icon.js';

const createLucideIcon = (iconName, iconNode, viewBox) => {
  const Component = forwardRef(
    ({ className, ...props }, ref) => createElement(Icon, {
      ref,
      iconNode,
      className: mergeClasses(
        `lucide-${toKebabCase(toPascalCase(iconName))}`,
        `lucide-${iconName}`,
        className
      ),
      viewBox: viewBox || "0 0 72 72",
      ...props
    })
  );
  Component.displayName = toPascalCase(iconName);
  return Component;
};

export { createLucideIcon as default };