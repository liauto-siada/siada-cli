"""
Sample Python file for testing ReadManyFiles tool.
"""

def hello_world():
    """Print hello world message"""
    print("Hello, World!")

class Calculator:
    """Simple calculator class"""
    
    def __init__(self):
        self.result = 0
    
    def add(self, x, y):
        """Add two numbers"""
        return x + y
    
    def subtract(self, x, y):
        """Subtract two numbers"""
        return x - y

if __name__ == "__main__":
    hello_world()
    calc = Calculator()
    print(f"2 + 3 = {calc.add(2, 3)}")
