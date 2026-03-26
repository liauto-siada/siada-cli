/**
 * Box Component
 * Enhanced wrapper around Ink's Box component with additional utilities
 * 
 * FLICKER PREVENTION:
 * This component automatically constrains height props to prevent rendering
 * content that equals or exceeds terminal height, which causes flickering.
 */

import React, { ReactNode } from 'react';
import { Box as InkBox, BoxProps as InkBoxProps } from '@jrichman/ink';
import { constrainHeight } from '../../utils/terminalHeight.js';

export interface BoxProps extends InkBoxProps {
  /**
   * Children elements
   */
  children?: ReactNode;
  /**
   * Add border around the box
   */
  bordered?: boolean;
  /**
   * Border color
   */
  borderColor?: string;
  /**
   * Border style
   */
  borderStyle?: 'single' | 'double' | 'round' | 'bold' | 'singleDouble' | 'doubleSingle' | 'classic';
  /**
   * Title for the box (displayed in border)
   */
  title?: string;
  /**
   * Desired height (constrained internally to prevent flickering)
   */
  height?: number;
}

/**
 * Enhanced Box component with border support and automatic height constraint
 * to prevent terminal flickering
 */
export const Box: React.FC<BoxProps> = ({
  bordered = false,
  borderColor,
  borderStyle = 'single',
  title,
  children,
  height,
  ...props
}) => {
  // Constrain height to prevent flickering when height >= terminal rows
  const safeHeight = constrainHeight(height, 'Box');

  if (bordered) {
    return (
      <InkBox
        borderStyle={borderStyle}
        borderColor={borderColor}
        height={safeHeight}
        {...props}
      >
        {children}
      </InkBox>
    );
  }

  return <InkBox height={safeHeight} {...props}>{children}</InkBox>;
};

/**
 * Centered box with height constraint
 */
export const CenteredBox: React.FC<BoxProps> = ({ children, height, ...props }) => {
  const safeHeight = constrainHeight(height, 'CenteredBox');
  
  return (
    <InkBox
      justifyContent="center"
      alignItems="center"
      flexDirection="column"
      height={safeHeight}
      {...props}
    >
      {children}
    </InkBox>
  );
};

/**
 * Padded box with height constraint
 */
export const PaddedBox: React.FC<BoxProps & { padding?: number }> = ({
  children,
  padding = 1,
  height,
  ...props
}) => {
  const safeHeight = constrainHeight(height, 'PaddedBox');
  
  return (
    <InkBox
      paddingX={padding}
      paddingY={padding}
      height={safeHeight}
      {...props}
    >
      {children}
    </InkBox>
  );
};

/**
 * Flex column box with height constraint
 */
export const Column: React.FC<BoxProps> = ({ children, height, ...props }) => {
  const safeHeight = constrainHeight(height, 'Column');
  
  return (
    <InkBox flexDirection="column" height={safeHeight} {...props}>
      {children}
    </InkBox>
  );
};

/**
 * Flex row box with height constraint
 */
export const Row: React.FC<BoxProps> = ({ children, height, ...props }) => {
  const safeHeight = constrainHeight(height, 'Row');
  
  return (
    <InkBox flexDirection="row" height={safeHeight} {...props}>
      {children}
    </InkBox>
  );
};

/**
 * Scrollable box with height constraint
 */
export const ScrollBox: React.FC<BoxProps & { maxHeight?: number }> = ({
  children,
  maxHeight,
  height,
  ...props
}) => {
  // Apply constraint to both maxHeight and height
  const safeMaxHeight = constrainHeight(maxHeight, 'ScrollBox');
  const safeHeight = constrainHeight(height, 'ScrollBox');
  
  return (
    <InkBox
      flexDirection="column"
      overflow="hidden"
      height={safeMaxHeight ?? safeHeight}
      {...props}
    >
      {children}
    </InkBox>
  );
};

/**
 * Panel box with title
 */
export const Panel: React.FC<{
  title?: string;
  bordered?: boolean;
  children: React.ReactNode;
}> = ({ title, bordered = true, children }) => {
  return (
    <InkBox
      flexDirection="column"
      borderStyle={bordered ? 'single' : undefined}
      borderColor="gray"
    >
      {title && (
        <InkBox paddingX={1}>
          <InkBox flexGrow={1} />
        </InkBox>
      )}
      <InkBox padding={1}>{children}</InkBox>
    </InkBox>
  );
};

/**
 * Split view box
 */
export const SplitView: React.FC<{
  left: React.ReactNode;
  right: React.ReactNode;
  leftWidth?: number | string;
  rightWidth?: number | string;
}> = ({ left, right, leftWidth, rightWidth }) => {
  return (
    <InkBox>
      <InkBox width={leftWidth} flexShrink={0}>
        {left}
      </InkBox>
      <InkBox width={rightWidth} flexGrow={1}>
        {right}
      </InkBox>
    </InkBox>
  );
};

/**
 * Card box with padding and border
 */
export const Card: React.FC<{
  children: React.ReactNode;
  padding?: number;
  borderColor?: string;
}> = ({ children, padding = 1, borderColor = 'gray' }) => {
  return (
    <InkBox
      borderStyle="round"
      borderColor={borderColor}
      padding={padding}
      flexDirection="column"
    >
      {children}
    </InkBox>
  );
};

/**
 * Spacer component with height constraint
 */
export const Spacer: React.FC<{ size?: number }> = ({ size = 1 }) => {
  const safeSize = constrainHeight(size, 'Spacer');
  return <InkBox height={safeSize} />;
};

/**
 * Divider component
 */
export const Divider: React.FC<{ color?: string; char?: string }> = ({
  color = 'gray',
  char = '─',
}) => {
  return (
    <InkBox>
      <InkBox flexGrow={1} />
    </InkBox>
  );
};
