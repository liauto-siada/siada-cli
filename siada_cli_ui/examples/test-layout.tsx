#!/usr/bin/env node
/**
 * Test Layout Example
 * Demonstrates the new single-render header architecture
 */

import React from 'react';
import { render } from '@jrichman/ink';
import { MainLayout } from '../src/components/layouts/MainLayout.js';
import { Message } from '../src/types/index.js';

// Sample messages for testing
const sampleMessages: Message[] = [
  {
    id: '1',
    type: 'user',
    content: 'Hello, Siada!',
    timestamp: Date.now(),
  },
  {
    id: '2',
    type: 'agent',
    content: 'Hello! How can I help you today?',
    timestamp: Date.now() + 1000,
    metadata: { subtype: 'answer' },
  },
  {
    id: '3',
    type: 'user',
    content: 'Can you explain the new header architecture?',
    timestamp: Date.now() + 2000,
  },
  {
    id: '4',
    type: 'agent',
    content: '▶ **THINKING**\nAnalyzing the header architecture...',
    timestamp: Date.now() + 3000,
    metadata: { subtype: 'thinking' },
  },
  {
    id: '5',
    type: 'agent',
    content: 'The new header uses Ink\'s Static component to render once and stay fixed at the top. This improves performance and ensures the header never re-renders during message updates.',
    timestamp: Date.now() + 4000,
    metadata: { subtype: 'answer' },
  },
];

const TestApp: React.FC = () => {
  const [messages, setMessages] = React.useState<Message[]>(sampleMessages);
  const [loading, setLoading] = React.useState(false);

  const handleSendMessage = (message: string) => {
    const newMessage: Message = {
      id: `${Date.now()}`,
      type: 'user',
      content: message,
      timestamp: Date.now(),
    };
    setMessages([...messages, newMessage]);

    // Simulate agent response
    setLoading(true);
    setTimeout(() => {
      const response: Message = {
        id: `${Date.now()}`,
        type: 'agent',
        content: `Echo: ${message}`,
        timestamp: Date.now(),
        metadata: { subtype: 'answer' },
      };
      setMessages((prev) => [...prev, response]);
      setLoading(false);
    }, 1000);
  };

  return (
    <MainLayout
      version="1.6.0"
      workingDir="/Users/caoxin/test-project"
      agent="coder"
      provider="li"
      model="claude-3-5-sonnet-20241022"
      prePlanMode={true}
      messages={messages}
      loading={loading}
      isReady={true}
      onSendMessage={handleSendMessage}
    />
  );
};

// Render the test app
render(<TestApp />);
