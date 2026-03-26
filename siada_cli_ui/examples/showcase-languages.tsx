#!/usr/bin/env node
/**
 * 38 Languages Showcase
 * Static display of all supported languages with syntax highlighting
 */

import React from 'react';
import { render, Box, Text } from '@jrichman/ink';
import { colorizeCode } from '../src/components/markdown/CodeColorizer.js';

// Featured languages showcase
const showcaseLanguages = [
  {
    name: 'JavaScript',
    lang: 'javascript',
    code: `const greeting = "Hello, World!";
function sayHello(name) {
  console.log(\`Hello, \${name}!\`);
}`,
  },
  {
    name: 'TypeScript',
    lang: 'typescript',
    code: `interface User {
  name: string;
  age: number;
}
const user: User = { name: "Alice", age: 30 };`,
  },
  {
    name: 'Python',
    lang: 'python',
    code: `def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)`,
  },
  {
    name: 'Bash',
    lang: 'bash',
    code: `#!/bin/bash
for i in {1..5}; do
  echo "Count: $i"
done`,
  },
  {
    name: 'Go',
    lang: 'go',
    code: `package main
import "fmt"
func main() {
    fmt.Println("Hello, World!")
}`,
  },
  {
    name: 'Rust',
    lang: 'rust',
    code: `fn main() {
    let greeting = "Hello, World!";
    println!("{}", greeting);
}`,
  },
  {
    name: 'Java',
    lang: 'java',
    code: `public class HelloWorld {
    public static void main(String[] args) {
        System.out.println("Hello, World!");
    }
}`,
  },
  {
    name: 'C++',
    lang: 'cpp',
    code: `#include <iostream>
int main() {
    std::cout << "Hello, World!" << std::endl;
    return 0;
}`,
  },
  {
    name: 'C#',
    lang: 'csharp',
    code: `using System;
class Program {
    static void Main() {
        Console.WriteLine("Hello, World!");
    }
}`,
  },
  {
    name: 'Ruby',
    lang: 'ruby',
    code: `class Person
  def initialize(name)
    @name = name
  end
end`,
  },
  {
    name: 'PHP',
    lang: 'php',
    code: `<?php
class User {
    public function greet() {
        echo "Hello!";
    }
}
?>`,
  },
  {
    name: 'Swift',
    lang: 'swift',
    code: `class Person {
    var name: String
    init(name: String) {
        self.name = name
    }
}`,
  },
  {
    name: 'Kotlin',
    lang: 'kotlin',
    code: `fun main() {
    val greeting = "Hello, World!"
    println(greeting)
}`,
  },
  {
    name: 'GraphQL',
    lang: 'graphql',
    code: `type User {
  id: ID!
  name: String!
}
query GetUser($id: ID!) {
  user(id: $id) { name }
}`,
  },
  {
    name: 'SQL',
    lang: 'sql',
    code: `SELECT u.name, COUNT(o.id)
FROM users u
LEFT JOIN orders o ON u.id = o.user_id
GROUP BY u.name;`,
  },
  {
    name: 'JSON',
    lang: 'json',
    code: `{
  "name": "siada-cli-ui",
  "version": "0.1.0",
  "dependencies": {
    "lowlight": "^3.3.0"
  }
}`,
  },
  {
    name: 'YAML',
    lang: 'yaml',
    code: `name: siada-cli-ui
version: 0.1.0
dependencies:
  lowlight: ^3.3.0
  react: ^19.2.3`,
  },
  {
    name: 'CSS',
    lang: 'css',
    code: `.container {
  display: flex;
  justify-content: center;
  background: #f0f0f0;
}`,
  },
  {
    name: 'SCSS',
    lang: 'scss',
    code: `$primary: #333;
.container {
  background: $primary;
  &:hover { opacity: 0.8; }
}`,
  },
  {
    name: 'Lua',
    lang: 'lua',
    code: `function factorial(n)
  if n == 0 then return 1
  else return n * factorial(n - 1)
  end
end`,
  },
];

const App: React.FC = () => {
  return (
    <Box flexDirection="column" padding={1}>
      <Text bold color="cyan">
        🌈 Syntax Highlighting - 38 Languages Supported
      </Text>
      <Text dimColor>
        Powered by lowlight (highlight.js AST library)
      </Text>
      <Text>{''}</Text>

      <Box flexDirection="column">
        {showcaseLanguages.slice(0, 6).map((item, index) => (
          <Box key={index} flexDirection="column" marginBottom={1}>
            <Box borderStyle="round" borderColor="yellow" paddingX={1}>
              <Text bold color="cyan">
                {item.name}
              </Text>
              <Text dimColor> ({item.lang})</Text>
            </Box>
            <Box paddingLeft={1}>
              {colorizeCode({
                code: item.code,
                language: item.lang,
                maxWidth: 70,
                hideLineNumbers: true,
              })}
            </Box>
          </Box>
        ))}
      </Box>

      <Text>{''}</Text>
      <Box borderStyle="double" borderColor="green" paddingX={1} flexDirection="column">
        <Text bold color="green">
          ✅ Complete Language Support (38 total):
        </Text>
        <Text dimColor>
          System: arduino, bash, c, cpp, csharp, makefile, shell
        </Text>
        <Text dimColor>
          Web: css, graphql, less, scss, xml, yaml
        </Text>
        <Text dimColor>
          Backend: go, java, kotlin, objectivec, perl, php, python, r, ruby, rust, swift
        </Text>
        <Text dimColor>
          Frontend: javascript, typescript
        </Text>
        <Text dimColor>
          Data: json, sql, yaml, ini
        </Text>
        <Text dimColor>
          Others: diff, lua, markdown, php-template, plaintext, python-repl, vbnet, wasm
        </Text>
      </Box>

      <Text>{''}</Text>
      <Box borderStyle="single" borderColor="gray" paddingX={1}>
        <Text bold>Language Aliases Supported:</Text>
        <Text dimColor>
          js/jsx → javascript, ts/tsx → typescript, sh → shell,
        </Text>
        <Text dimColor>
          py → python, yml → yaml, and 25+ more
        </Text>
      </Box>

      <Text>{''}</Text>
      <Text bold color="green">
        🎯 Features:
      </Text>
      <Text>• 📁 File path highlighting (cyan)</Text>
      <Text>• 💻 Bash command highlighting (green)</Text>
      <Text>• 🔤 Inline code highlighting (orange)</Text>
      <Text>• 🌈 Full syntax highlighting for 38 languages</Text>
      <Text>• 🔄 Language alias auto-detection</Text>
      <Text>• ⚡ High performance with caching</Text>

      <Text>{''}</Text>
      <Text dimColor>Press Ctrl+C to exit</Text>
    </Box>
  );
};

const { unmount, waitUntilExit } = render(<App />);

waitUntilExit().then(() => {
  unmount();
  process.exit(0);
});
