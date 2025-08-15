"""
Sample Python file for testing @ command functionality
"""

def hello_world():
    """A simple hello world function"""
    print("Hello, World!")
    return "success"

def add_numbers(a, b):
    """Add two numbers together"""
    return a + b

class Calculator:
    """A simple calculator class"""
    
    def __init__(self):
        self.result = 0
    
    def add(self, value):
        self.result += value
        return self.result
    
    def multiply(self, value):
        self.result *= value
        return self.result

if __name__ == "__main__":
    hello_world()
    calc = Calculator()
    print(calc.add(5))
    print(calc.multiply(3))
