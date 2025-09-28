import pytest
import litellm
from agents.models.chatcmpl_converter import Converter


class TestLiteLLMTokenCounterReal:
    """Test real litellm token_counter functionality without mocks"""
    
    def test_litellm_token_counter_with_text(self):
        """Test litellm token_counter with text parameter"""
        # Arrange
        test_text = "Hello, world! This is a test message."
        model_name = "claude-4-sonnet"  # Use a real model name
        
        # Act
        try:
            result = litellm.token_counter(model=model_name, text=test_text)
            
            # Assert
            assert isinstance(result, int)
            assert result > 0
            print(f"Text: '{test_text}' -> Tokens: {result}")
            
        except Exception as e:
            pytest.fail(f"litellm.token_counter failed with text: {e}")
    
    def test_litellm_token_counter_with_messages(self):
        """Test litellm token_counter with messages parameter"""
        # Arrange
        test_messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there! How can I help you today?"}
        ]
        model_name = "claude-4-sonnet"
        
        # Act
        try:
            result = litellm.token_counter(model=model_name, messages=test_messages)
            
            # Assert
            assert isinstance(result, int)
            assert result > 0
            print(f"Messages: {test_messages} -> Tokens: {result}")
            
        except Exception as e:
            pytest.fail(f"litellm.token_counter failed with messages: {e}")
    
    def test_litellm_token_counter_different_models(self):
        """Test litellm token_counter with different model names"""
        # Arrange
        test_text = "This is a test message for token counting."
        test_models = [
            "claude-4-sonnet",
            "gpt-4",
            "gpt-3.5-turbo"
        ]
        
        results = {}
        
        for model in test_models:
            try:
                # Act
                result = litellm.token_counter(model=model, text=test_text)
                
                # Assert
                assert isinstance(result, int)
                assert result > 0
                results[model] = result
                print(f"Model: {model} -> Tokens: {result}")
                
            except Exception as e:
                print(f"Model {model} failed: {e}")
                # Don't fail the test if a specific model is unavailable
                continue
        
        # At least one model should have worked
        assert len(results) > 0, "No models were able to count tokens"
    
    def test_litellm_token_counter_empty_text(self):
        """Test litellm token_counter with empty text"""
        # Arrange
        test_text = ""
        model_name = "claude-4-sonnet"
        
        # Act
        try:
            result = litellm.token_counter(model=model_name, text=test_text)
            
            # Assert
            assert isinstance(result, int)
            assert result >= 0
            print(f"Empty text -> Tokens: {result}")
            
        except Exception as e:
            pytest.fail(f"litellm.token_counter failed with empty text: {e}")
    
    def test_litellm_token_counter_long_text(self):
        """Test litellm token_counter with longer text"""
        # Arrange
        test_text = """
        This is a longer test message to see how litellm handles token counting
        with more substantial content. We're testing the token counter functionality
        to ensure it works correctly with various input sizes and content types.
        The message includes multiple sentences, punctuation, and different word lengths.
        """
        model_name = "claude-4-sonnet"
        
        # Act
        try:
            result = litellm.token_counter(model=model_name, text=test_text)
            
            # Assert
            assert isinstance(result, int)
            assert result > 20  # Should be more tokens for longer text
            print(f"Long text ({len(test_text)} chars) -> Tokens: {result}")
            
        except Exception as e:
            pytest.fail(f"litellm.token_counter failed with long text: {e}")
    
    def test_litellm_token_counter_with_converter_items(self):
        """Test litellm token_counter with Converter.items_to_messages"""
        # Arrange
        from siada.agent_hub.context_filter.utils import compute_message_signature
        
        # Mock some items that would come from the message state
        test_items = [
            {"role": "user", "content": "What is the weather like?"},
            {"role": "assistant", "content": "I don't have access to current weather data."}
        ]
        
        model_name = "claude-3-sonnet-20240229"
        
        # Act
        try:
            # Convert items to messages format
            messages = Converter.items_to_messages(test_items)
            result = litellm.token_counter(model=model_name, messages=messages)
            
            # Assert
            assert isinstance(result, int)
            assert result > 0
            print(f"Converted items -> Messages: {messages}")
            print(f"Messages -> Tokens: {result}")
            
            # Also test signature computation for these items
            for i, item in enumerate(test_items):
                signature = compute_message_signature(item)
                print(f"Item {i} signature: {signature}")
                assert len(signature) == 32  # MD5 hash length
                
        except Exception as e:
            pytest.fail(f"litellm.token_counter failed with converted items: {e}")
    
    def test_litellm_token_counter_comparison_text_vs_messages(self):
        """Compare token counts between text and messages format"""
        # Arrange
        content = "Hello, how are you doing today?"
        model_name = "claude-4-sonnet"
        
        # Test with text format
        try:
            text_tokens = litellm.token_counter(model=model_name, text=content)
            
            # Test with messages format
            messages = [{"role": "user", "content": content}]
            message_tokens = litellm.token_counter(model=model_name, messages=messages)
            
            print(f"Text format: '{content}' -> {text_tokens} tokens")
            print(f"Messages format: {messages} -> {message_tokens} tokens")
            
            # Messages format typically includes role tokens, so should be >= text tokens
            assert text_tokens > 0
            assert message_tokens > 0
            assert message_tokens >= text_tokens
            
        except Exception as e:
            pytest.fail(f"Token count comparison failed: {e}")


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v", "-s"])  # -s to see print outputs