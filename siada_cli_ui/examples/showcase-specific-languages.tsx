#!/usr/bin/env node
/**
 * Specific Languages Showcase
 * Demonstrates: markdown, objectivec, perl, php, php-template, plaintext
 * and other less common but important languages
 */

import React from 'react';
import { render, Box, Text } from '@jrichman/ink';
import { colorizeCode } from '../src/components/markdown/CodeColorizer.js';

const specificLanguages = [
  {
    name: 'Markdown',
    lang: 'markdown',
    description: '标记语言，用于文档编写',
    code: `# Heading 1
## Heading 2
### Heading 3

This is **bold** and this is *italic*.

- List item 1
- List item 2
- List item 3

1. Numbered item 1
2. Numbered item 2

\`\`\`javascript
const code = "example";
\`\`\`

[Link text](https://example.com)

> Blockquote text`,
  },
  {
    name: 'Objective-C',
    lang: 'objectivec',
    description: 'Apple 平台开发语言',
    code: `#import <Foundation/Foundation.h>

@interface Person : NSObject

@property (nonatomic, strong) NSString *name;
@property (nonatomic, assign) NSInteger age;

- (instancetype)initWithName:(NSString *)name 
                         age:(NSInteger)age;
- (void)sayHello;

@end

@implementation Person

- (instancetype)initWithName:(NSString *)name 
                         age:(NSInteger)age {
    self = [super init];
    if (self) {
        _name = name;
        _age = age;
    }
    return self;
}

- (void)sayHello {
    NSLog(@"Hello, my name is %@ and I'm %ld years old", 
          self.name, (long)self.age);
}

@end`,
  },
  {
    name: 'Perl',
    lang: 'perl',
    description: '强大的文本处理语言',
    code: `#!/usr/bin/perl
use strict;
use warnings;
use feature 'say';

# Perl example - text processing
my $greeting = "Hello, World!";
say $greeting;

# Subroutine
sub factorial {
    my ($n) = @_;
    return 1 if $n <= 1;
    return $n * factorial($n - 1);
}

# Array and hash
my @numbers = (1, 2, 3, 4, 5);
my %person = (
    name => "Alice",
    age => 30,
    city => "New York"
);

# Regular expression
if ($greeting =~ /World/) {
    say "Found World!";
}

# File handling
open(my $fh, '<', 'file.txt') or die "Cannot open: $!";
while (my $line = <$fh>) {
    chomp $line;
    say $line;
}
close($fh);`,
  },
  {
    name: 'PHP',
    lang: 'php',
    description: '服务器端脚本语言',
    code: `<?php
// PHP example - web development
namespace App\\Models;

use Illuminate\\Database\\Eloquent\\Model;

class User extends Model
{
    protected $fillable = ['name', 'email', 'password'];
    
    protected $hidden = ['password'];
    
    public function __construct(array $attributes = [])
    {
        parent::__construct($attributes);
    }
    
    public function posts()
    {
        return $this->hasMany(Post::class);
    }
    
    public static function findByEmail(string $email): ?User
    {
        return self::where('email', $email)->first();
    }
    
    public function getFullNameAttribute(): string
    {
        return "{$this->first_name} {$this->last_name}";
    }
}

// Usage
$user = new User([
    'name' => 'John Doe',
    'email' => 'john@example.com'
]);

$user->save();

echo "User created: {$user->name}\\n";
?>`,
  },
  {
    name: 'PHP Template',
    lang: 'php-template',
    description: 'PHP 模板语法',
    code: `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title><?php echo $pageTitle; ?></title>
</head>
<body>
    <header>
        <h1><?= htmlspecialchars($siteName) ?></h1>
        <nav>
            <?php foreach ($menuItems as $item): ?>
                <a href="<?= $item['url'] ?>">
                    <?= $item['label'] ?>
                </a>
            <?php endforeach; ?>
        </nav>
    </header>
    
    <main>
        <?php if (isset($user)): ?>
            <p>Welcome, <?= $user->name ?>!</p>
        <?php else: ?>
            <p>Please log in.</p>
        <?php endif; ?>
        
        <div class="content">
            <?php include 'partials/content.php'; ?>
        </div>
        
        <!-- Comments section -->
        <?php if (!empty($comments)): ?>
            <section class="comments">
                <?php foreach ($comments as $comment): ?>
                    <div class="comment">
                        <strong><?= $comment['author'] ?></strong>
                        <p><?= nl2br($comment['text']) ?></p>
                        <time><?= date('Y-m-d', $comment['timestamp']) ?></time>
                    </div>
                <?php endforeach; ?>
            </section>
        <?php endif; ?>
    </main>
    
    <footer>
        <p>&copy; <?= date('Y') ?> <?= $siteName ?></p>
    </footer>
</body>
</html>`,
  },
  {
    name: 'Plain Text',
    lang: 'plaintext',
    description: '纯文本（无语法高亮）',
    code: `This is plain text without any syntax highlighting.

It can contain anything:
- Numbers: 123, 456.789
- Symbols: @#$%^&*()
- Code-like text: function hello() { return "world"; }
- But no highlighting will be applied!

Use this when you want to display text as-is,
without any special formatting or colors.

Example use cases:
1. Log files
2. Plain documentation
3. ASCII art
4. Configuration dumps`,
  },
  {
    name: 'INI',
    lang: 'ini',
    description: '配置文件格式',
    code: `; Database configuration
[database]
host = localhost
port = 3306
username = admin
password = secret
database = myapp

; Redis cache
[redis]
host = 127.0.0.1
port = 6379
timeout = 30

; Application settings
[app]
debug = true
timezone = UTC
locale = en_US

[logging]
level = debug
file = /var/log/app.log
max_size = 10M`,
  },
  {
    name: 'Makefile',
    lang: 'makefile',
    description: '构建自动化工具',
    code: `# Makefile example
CC = gcc
CFLAGS = -Wall -O2 -std=c11
LDFLAGS = -lm
TARGET = myapp
SOURCES = main.c utils.c helpers.c
OBJECTS = $(SOURCES:.c=.o)

.PHONY: all clean test install

all: $(TARGET)

$(TARGET): $(OBJECTS)
\t$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS)

%.o: %.c
\t$(CC) $(CFLAGS) -c -o $@ $<

clean:
\trm -f $(OBJECTS) $(TARGET)
\trm -rf *.dSYM

test: $(TARGET)
\t./$(TARGET) --test

install: $(TARGET)
\tinstall -m 755 $(TARGET) /usr/local/bin/

run: $(TARGET)
\t./$(TARGET)`,
  },
  {
    name: 'Diff',
    lang: 'diff',
    description: '文件差异格式',
    code: `diff --git a/src/app.js b/src/app.js
index 1234567..abcdefg 100644
--- a/src/app.js
+++ b/src/app.js
@@ -1,10 +1,12 @@
 const express = require('express');
 const app = express();
+const morgan = require('morgan');
 
-const PORT = 3000;
+const PORT = process.env.PORT || 3000;
 
+app.use(morgan('combined'));
 app.use(express.json());
 
 app.get('/', (req, res) => {
-  res.send('Hello World');
+  res.json({ message: 'Hello World', version: '2.0' });
 });`,
  },
  {
    name: 'Arduino',
    lang: 'arduino',
    description: '嵌入式系统编程',
    code: `// Arduino LED blink example
const int LED_PIN = 13;
const int BUTTON_PIN = 2;
int ledState = LOW;
unsigned long previousMillis = 0;
const long interval = 1000;

void setup() {
  Serial.begin(9600);
  pinMode(LED_PIN, OUTPUT);
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  
  Serial.println("Arduino initialized");
}

void loop() {
  unsigned long currentMillis = millis();
  
  // Blink LED without blocking
  if (currentMillis - previousMillis >= interval) {
    previousMillis = currentMillis;
    ledState = !ledState;
    digitalWrite(LED_PIN, ledState);
  }
  
  // Read button
  if (digitalRead(BUTTON_PIN) == LOW) {
    Serial.println("Button pressed!");
    delay(50); // Debounce
  }
  
  // Read sensor
  int sensorValue = analogRead(A0);
  float voltage = sensorValue * (5.0 / 1023.0);
  Serial.print("Sensor: ");
  Serial.println(voltage);
}`,
  },
  {
    name: 'R',
    lang: 'r',
    description: '统计分析语言',
    code: `# R programming - statistical analysis
library(ggplot2)
library(dplyr)

# Create sample data
data <- data.frame(
  x = rnorm(100, mean = 50, sd = 10),
  y = rnorm(100, mean = 30, sd = 5),
  category = sample(c("A", "B", "C"), 100, replace = TRUE)
)

# Data manipulation
summary_stats <- data %>%
  group_by(category) %>%
  summarise(
    mean_x = mean(x),
    mean_y = mean(y),
    count = n()
  )

# Statistical test
t_test_result <- t.test(data$x, data$y)
print(t_test_result)

# Linear regression
model <- lm(y ~ x, data = data)
summary(model)

# Plotting
plot <- ggplot(data, aes(x = x, y = y, color = category)) +
  geom_point() +
  geom_smooth(method = "lm") +
  theme_minimal() +
  labs(title = "Scatter Plot with Regression")

print(plot)`,
  },
  {
    name: 'WebAssembly (WAT)',
    lang: 'wasm',
    description: 'WebAssembly 文本格式',
    code: `(module
  ;; Import console.log from JavaScript
  (import "console" "log" (func $log (param i32)))
  
  ;; Memory
  (memory 1)
  
  ;; Factorial function
  (func $factorial (param $n i32) (result i32)
    (local $result i32)
    (local.set $result (i32.const 1))
    
    (block $break
      (loop $continue
        ;; Check if n <= 1
        (br_if $break (i32.le_s (local.get $n) (i32.const 1)))
        
        ;; result = result * n
        (local.set $result
          (i32.mul (local.get $result) (local.get $n))
        )
        
        ;; n = n - 1
        (local.set $n
          (i32.sub (local.get $n) (i32.const 1))
        )
        
        (br $continue)
      )
    )
    
    (local.get $result)
  )
  
  ;; Export the factorial function
  (export "factorial" (func $factorial))
  
  ;; Main function
  (func $main
    (call $log (call $factorial (i32.const 5)))
  )
  
  (start $main)
)`,
  },
  {
    name: 'VB.NET',
    lang: 'vbnet',
    description: 'Visual Basic .NET',
    code: `Imports System
Imports System.Collections.Generic
Imports System.Linq

Namespace MyApplication
    Public Class Person
        ' Properties
        Public Property Name As String
        Public Property Age As Integer
        Private _email As String
        
        ' Property with custom getter/setter
        Public Property Email As String
            Get
                Return _email
            End Get
            Set(value As String)
                If value.Contains("@") Then
                    _email = value
                Else
                    Throw New ArgumentException("Invalid email")
                End If
            End Set
        End Property
        
        ' Constructor
        Public Sub New(name As String, age As Integer)
            Me.Name = name
            Me.Age = age
        End Sub
        
        ' Method
        Public Sub SayHello()
            Console.WriteLine($"Hello, my name is {Name}")
        End Sub
        
        ' Function
        Public Function IsAdult() As Boolean
            Return Age >= 18
        End Function
    End Class
    
    Module Program
        Sub Main()
            Dim person As New Person("Alice", 30)
            person.Email = "alice@example.com"
            person.SayHello()
            
            Console.WriteLine($"Is adult: {person.IsAdult()}")
        End Sub
    End Module
End Namespace`,
  },
];

const App: React.FC = () => {
  return (
    <Box flexDirection="column" padding={1}>
      <Text bold color="cyan">
        🎯 Specific Languages Showcase
      </Text>
      <Text dimColor>
        markdown, objectivec, perl, php, php-template, plaintext, and more
      </Text>
      <Text>{''}</Text>

      {specificLanguages.map((item, index) => (
        <Box key={index} flexDirection="column" marginBottom={1}>
          <Box borderStyle="round" borderColor="yellow" paddingX={1}>
            <Text bold color="cyan">
              {item.name}
            </Text>
            <Text color="gray"> ({item.lang})</Text>
          </Box>
          <Text dimColor color="green">  {item.description}</Text>
          <Box paddingLeft={1} marginTop={1}>
            {colorizeCode({
              code: item.code,
              language: item.lang,
              maxWidth: 75,
              hideLineNumbers: true,
            })}
          </Box>
        </Box>
      ))}

      <Text>{''}</Text>
      <Box borderStyle="double" borderColor="green" paddingX={1} flexDirection="column">
        <Text bold color="green">
          ✅ Featured Languages (13 shown):
        </Text>
        <Text dimColor>
          • markdown - Document writing and formatting
        </Text>
        <Text dimColor>
          • objectivec - Apple platform development
        </Text>
        <Text dimColor>
          • perl - Text processing and system administration
        </Text>
        <Text dimColor>
          • php - Server-side web development
        </Text>
        <Text dimColor>
          • php-template - PHP templating syntax
        </Text>
        <Text dimColor>
          • plaintext - Raw text without highlighting
        </Text>
        <Text dimColor>
          • ini - Configuration files
        </Text>
        <Text dimColor>
          • makefile - Build automation
        </Text>
        <Text dimColor>
          • diff - File differences and patches
        </Text>
        <Text dimColor>
          • arduino - Embedded systems programming
        </Text>
        <Text dimColor>
          • r - Statistical computing and graphics
        </Text>
        <Text dimColor>
          • wasm - WebAssembly text format
        </Text>
        <Text dimColor>
          • vbnet - Visual Basic .NET
        </Text>
      </Box>

      <Text>{''}</Text>
      <Box borderStyle="single" borderColor="gray" paddingX={1}>
        <Text bold>🌈 Total: 38 Languages Supported</Text>
        <Text dimColor>
          See LANGUAGES_SHOWCASE.md for complete list
        </Text>
      </Box>

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
