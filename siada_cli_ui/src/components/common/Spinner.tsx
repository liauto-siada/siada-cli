/**
 * Spinner Component
 * Loading animation component using ink-spinner
 */

import React from 'react';
import { Text } from '@jrichman/ink';
import InkSpinner from 'ink-spinner';

export interface SpinnerProps {
  /**
   * Loading text to display
   */
  text?: string;
  /**
   * Spinner type
   */
  type?: 'dots' | 'line' | 'arc' | 'arrow' | 'bounce' | 'circle';
  /**
   * Color of the spinner
   */
  color?: string;
}

/**
 * Spinner component for loading states
 */
export const Spinner: React.FC<SpinnerProps> = ({
  text = 'Loading...',
  type = 'dots',
  color = 'cyan',
}) => {
  return (
    <Text>
      <Text color={color}>
        <InkSpinner type={type} />
      </Text>
      {text && <Text> {text}</Text>}
    </Text>
  );
};

/**
 * Small inline spinner
 */
export const InlineSpinner: React.FC<{ color?: string }> = ({ color = 'cyan' }) => {
  return (
    <Text color={color}>
      <InkSpinner type="dots" />
    </Text>
  );
};

/**
 * Centered spinner with message
 */
export const CenteredSpinner: React.FC<SpinnerProps> = (props) => {
  return (
    <Text>
      <Spinner {...props} />
    </Text>
  );
};

/**
 * Spinner with custom message formatting
 */
export const FormattedSpinner: React.FC<{
  message: string;
  submessage?: string;
  color?: string;
}> = ({ message, submessage, color = 'cyan' }) => {
  return (
    <>
      <Text>
        <Text color={color}>
          <InkSpinner type="dots" />
        </Text>
        <Text bold> {message}</Text>
      </Text>
      {submessage && (
        <Text dimColor>  {submessage}</Text>
      )}
    </>
  );
};
