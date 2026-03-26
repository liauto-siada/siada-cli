#!/usr/bin/env node
/**
 * 38 Languages Syntax Highlighting Demo
 * Demonstrates all supported languages with code examples
 * 
 * Supported: arduino, bash, c, cpp, csharp, css, diff, go, graphql,
 * ini, java, javascript, json, kotlin, less, lua, makefile, markdown,
 * objectivec, perl, php, php-template, plaintext, python, python-repl,
 * r, ruby, rust, scss, shell, sql, swift, typescript, vbnet, wasm, xml, yaml
 */

import React, { useState } from 'react';
import { render, Box, Text } from '@jrichman/ink';
import { colorizeCode } from '../src/components/markdown/CodeColorizer.js';

const languages = [
  {
    name: 'arduino',
    code: `void setup() {
  Serial.begin(9600);
  pinMode(LED_BUILTIN, OUTPUT);
}

void loop() {
  digitalWrite(LED_BUILTIN, HIGH);
  delay(1000);
}`,
  },
  {
    name: 'bash',
    code: `#!/bin/bash
for i in {1..5}; do
  echo "Count: $i"
  sleep 1
done`,
  },
  {
    name: 'c',
    code: `#include <stdio.h>

int main() {
    printf("Hello, World!\\n");
    return 0;
}`,
  },
  {
    name: 'cpp',
    code: `#include <iostream>
using namespace std;

class HelloWorld {
public:
    void greet() {
        cout << "Hello, World!" << endl;
    }
};`,
  },
  {
    name: 'csharp',
    code: `using System;

class Program {
    static void Main() {
        Console.WriteLine("Hello, World!");
    }
}`,
  },
  {
    name: 'css',
    code: `.container {
  display: flex;
  justify-content: center;
  background-color: #f0f0f0;
}`,
  },
  {
    name: 'diff',
    code: `--- a/file.txt
+++ b/file.txt
@@ -1,3 +1,4 @@
 Line 1
-Line 2
+Line 2 modified
+Line 3 added`,
  },
  {
    name: 'go',
    code: `package main

import "fmt"

func main() {
    fmt.Println("Hello, World!")
}`,
  },
  {
    name: 'graphql',
    code: `type User {
  id: ID!
  name: String!
  email: String
}

query GetUser($id: ID!) {
  user(id: $id) {
    name
    email
  }
}`,
  },
  {
    name: 'ini',
    code: `[database]
host = localhost
port = 5432
user = admin

[server]
debug = true`,
  },
  {
    name: 'java',
    code: `public class HelloWorld {
    public static void main(String[] args) {
        System.out.println("Hello, World!");
    }
}`,
  },
  {
    name: 'javascript',
    code: `const greeting = "Hello, World!";

function sayHello(name) {
  console.log(\`Hello, \${name}!\`);
  return true;
}

sayHello("JavaScript");`,
  },
  {
    name: 'json',
    code: `{
  "name": "siada-cli-ui",
  "version": "0.1.0",
  "dependencies": {
    "lowlight": "^3.3.0",
    "react": "^19.2.3"
  }
}`,
  },
  {
    name: 'kotlin',
    code: `fun main() {
    val greeting = "Hello, World!"
    println(greeting)
}

data class User(val name: String, val age: Int)`,
  },
  {
    name: 'less',
    code: `@primary-color: #4CAF50;
@padding: 10px;

.button {
  background-color: @primary-color;
  padding: @padding;
  &:hover {
    opacity: 0.8;
  }
}`,
  },
  {
    name: 'lua',
    code: `function factorial(n)
  if n == 0 then
    return 1
  else
    return n * factorial(n - 1)
  end
end

print(factorial(5))`,
  },
  {
    name: 'makefile',
    code: `CC = gcc
CFLAGS = -Wall -O2

all: program

program: main.o utils.o
\t$(CC) $(CFLAGS) -o program main.o utils.o

clean:
\trm -f *.o program`,
  },
  {
    name: 'markdown',
    code: `# Heading 1
## Heading 2

- List item 1
- List item 2

**Bold** and *italic* text

\`\`\`code
example
\`\`\``,
  },
  {
    name: 'objectivec',
    code: `#import <Foundation/Foundation.h>

@interface Person : NSObject
@property (nonatomic, strong) NSString *name;
- (void)sayHello;
@end

@implementation Person
- (void)sayHello {
    NSLog(@"Hello, %@!", self.name);
}
@end`,
  },
  {
    name: 'perl',
    code: `#!/usr/bin/perl
use strict;
use warnings;

my $greeting = "Hello, World!";
print "$greeting\\n";

sub factorial {
    my ($n) = @_;
    return 1 if $n <= 1;
    return $n * factorial($n - 1);
}`,
  },
  {
    name: 'php',
    code: `<?php
class User {
    private $name;
    
    public function __construct($name) {
        $this->name = $name;
    }
    
    public function greet() {
        echo "Hello, {$this->name}!";
    }
}

$user = new User("PHP");
$user->greet();
?>`,
  },
  {
    name: 'python',
    code: `def fibonacci(n):
    """Calculate fibonacci number"""
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)

class Person:
    def __init__(self, name):
        self.name = name
    
    def greet(self):
        print(f"Hello, {self.name}!")`,
  },
  {
    name: 'python-repl',
    code: `>>> def add(a, b):
...     return a + b
...
>>> add(2, 3)
5
>>> print("Hello, Python!")
Hello, Python!`,
  },
  {
    name: 'r',
    code: `# R programming
fibonacci <- function(n) {
  if (n <= 1) {
    return(n)
  }
  return(fibonacci(n-1) + fibonacci(n-2))
}

result <- fibonacci(10)
print(result)`,
  },
  {
    name: 'ruby',
    code: `class Person
  attr_accessor :name
  
  def initialize(name)
    @name = name
  end
  
  def greet
    puts "Hello, #{@name}!"
  end
end

person = Person.new("Ruby")
person.greet`,
  },
  {
    name: 'rust',
    code: `fn main() {
    let greeting = "Hello, World!";
    println!("{}", greeting);
}

struct Person {
    name: String,
    age: u32,
}

impl Person {
    fn new(name: String, age: u32) -> Self {
        Person { name, age }
    }
}`,
  },
  {
    name: 'scss',
    code: `$primary-color: #333;
$padding: 15px;

.container {
  background: $primary-color;
  padding: $padding;
  
  .header {
    font-size: 24px;
    
    &:hover {
      opacity: 0.8;
    }
  }
}`,
  },
  {
    name: 'shell',
    code: `#!/bin/sh
echo "Starting deployment..."

for file in *.txt; do
  echo "Processing: $file"
  cat "$file" | wc -l
done

echo "Deployment complete!"`,
  },
  {
    name: 'sql',
    code: `CREATE TABLE users (
  id SERIAL PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  email VARCHAR(255) UNIQUE,
  created_at TIMESTAMP DEFAULT NOW()
);

SELECT u.name, COUNT(o.id) as order_count
FROM users u
LEFT JOIN orders o ON u.id = o.user_id
GROUP BY u.name
HAVING COUNT(o.id) > 5;`,
  },
  {
    name: 'swift',
    code: `import Foundation

class Person {
    var name: String
    
    init(name: String) {
        self.name = name
    }
    
    func greet() {
        print("Hello, \\(name)!")
    }
}

let person = Person(name: "Swift")
person.greet()`,
  },
  {
    name: 'typescript',
    code: `interface User {
  name: string;
  age: number;
}

class UserManager {
  private users: User[] = [];
  
  addUser(user: User): void {
    this.users.push(user);
  }
  
  getUsers(): User[] {
    return this.users;
  }
}

const manager = new UserManager();`,
  },
  {
    name: 'vbnet',
    code: `Module Program
    Sub Main()
        Dim greeting As String = "Hello, World!"
        Console.WriteLine(greeting)
    End Sub
    
    Function Add(a As Integer, b As Integer) As Integer
        Return a + b
    End Function
End Module`,
  },
  {
    name: 'xml',
    code: `<?xml version="1.0" encoding="UTF-8"?>
<project>
  <name>siada-cli-ui</name>
  <version>0.1.0</version>
  <dependencies>
    <dependency>
      <name>lowlight</name>
      <version>3.3.0</version>
    </dependency>
  </dependencies>
</project>`,
  },
  {
    name: 'yaml',
    code: `name: siada-cli-ui
version: 0.1.0

dependencies:
  lowlight: ^3.3.0
  react: ^19.2.3
  typescript: ^5.5.0

scripts:
  build: tsc
  test: vitest`,
  },
];

interface LanguageDemoProps {
  language: string;
  code: string;
}

const LanguageDemo: React.FC<LanguageDemoProps> = ({ language, code }) => {
  const highlighted = colorizeCode({
    code,
    language,
    maxWidth: 80,
    hideLineNumbers: false,
  });

  return (
    <Box flexDirection="column" marginBottom={1}>
      <Box borderStyle="round" borderColor="cyan" paddingX={1}>
        <Text bold color="yellow">
          {language.toUpperCase()}
        </Text>
      </Box>
      <Box paddingLeft={1}>{highlighted}</Box>
    </Box>
  );
};

const App: React.FC = () => {
  const [currentIndex, setCurrentIndex] = useState(0);
  const currentLang = languages[currentIndex];

  return (
    <Box flexDirection="column" padding={1}>
      <Text bold color="cyan">
        🌈 38 Programming Languages - Syntax Highlighting Demo
      </Text>
      <Text dimColor>
        Powered by lowlight (highlight.js) - Language {currentIndex + 1} of {languages.length}
      </Text>
      <Text>{''}</Text>

      <LanguageDemo language={currentLang.name} code={currentLang.code} />

      <Box borderStyle="single" paddingX={1} borderColor="gray">
        <Text dimColor>
          Press Ctrl+C to exit | Showing: {currentLang.name}
        </Text>
      </Box>

      <Text>{''}</Text>
      <Text bold color="green">
        ✅ All 38 languages supported:
      </Text>
      <Text dimColor>
        arduino, bash, c, cpp, csharp, css, diff, go, graphql, ini, java,
      </Text>
      <Text dimColor>
        javascript, json, kotlin, less, lua, makefile, markdown, objectivec,
      </Text>
      <Text dimColor>
        perl, php, php-template, plaintext, python, python-repl, r, ruby,
      </Text>
      <Text dimColor>
        rust, scss, shell, sql, swift, typescript, vbnet, wasm, xml, yaml
      </Text>
    </Box>
  );
};

// Render with auto-rotation through languages
let currentIndex = 0;
const { unmount, rerender, waitUntilExit } = render(<App />);

const interval = setInterval(() => {
  currentIndex = (currentIndex + 1) % languages.length;
  rerender(<App />);
}, 3000); // Change language every 3 seconds

// Handle cleanup
waitUntilExit().then(() => {
  clearInterval(interval);
  unmount();
  process.exit(0);
});
