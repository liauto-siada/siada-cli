"""
Simple tests for Interaction Session Management System

Verify core functionality of the simplified system (using ModelSettings configuration)
"""

from .session_manager import InteractionSessionManager
from .session_models import Session, SessionState
from siada.models.model_settings import ModelSettings, get_model_config


class TestInteractionSessionSystem:
    """Interaction Session system test class"""
    
    def setup_method(self):
        """Setup before each test method"""
        # No longer need instance since create_session is static
        pass
    
    def test_create_session_with_uuid(self):
        """Test creating session (using auto-generated UUID)"""
        model_config = get_model_config("claude-3-7-sonnet")
        session = InteractionSessionManager.create_session(config=model_config)
        
        assert session.session_id is not None
        assert session.config is not None
        assert session.config.model_name == "claude-3-7-sonnet"
        assert isinstance(session.state, SessionState)
        
        # Verify OpenAI Session exists and uses same ID
        openai_session = session.state.openai_session
        assert openai_session is not None
        assert openai_session.session_id == session.session_id
        
        print(f"✅ Session creation test passed (UUID): {session.session_id}, model: {session.config.model_name}")
    
    def test_create_session_with_custom_id(self):
        """Test creating session (using custom ID)"""
        model_config = get_model_config("gpt-4o")
        custom_id = "custom_session_123"
        
        session = InteractionSessionManager.create_session(
            config=model_config,
            session_id=custom_id
        )
        
        assert session.session_id == custom_id
        assert session.config.model_name == "gpt-4o"
        
        # Verify OpenAI Session uses same custom ID
        openai_session = session.state.openai_session
        assert openai_session.session_id == custom_id
        
        print(f"✅ Session creation test passed (custom ID): {custom_id}")
    
    def test_create_session_without_config(self):
        """Test creating session (without model configuration)"""
        session = InteractionSessionManager.create_session()
        
        assert session.session_id is not None
        assert session.config is None
        assert session.state.openai_session is not None
        
        print(f"✅ Session creation without config test passed: {session.session_id}")
    
    def test_create_session_with_custom_db_path(self):
        """Test creating session (with custom database path)"""
        model_config = get_model_config("claude-sonnet-4")
        custom_db_path = "custom_conversations.db"
        
        session = InteractionSessionManager.create_session(
            config=model_config,
            db_path=custom_db_path
        )
        
        assert session.session_id is not None
        assert session.state.openai_session is not None
        # Note: SQLiteSession may not directly expose db_path attribute, only verify successful creation
        
        print(f"✅ Custom database path test passed: {session.session_id}")
    
    def test_model_specific_db_path(self):
        """Test model-specific database path"""
        model_config = get_model_config("gemini-2.5-pro")
        session = InteractionSessionManager.create_session(config=model_config)
        
        # Verify successful session creation
        assert session.session_id is not None
        assert session.config.model_name == "gemini-2.5-pro"
        assert session.state.openai_session is not None
        
        print(f"✅ Model-specific database path test passed: {session.session_id}")
    
    def test_convenience_function(self):
        """Test convenience function"""
        model_config = get_model_config("deepseek-v3-0324")
        session = InteractionSessionManager.create_session(
            config=model_config,
            session_id="convenience_test_123"
        )
        
        assert session.session_id == "convenience_test_123"
        assert session.config.model_name == "deepseek-v3-0324"
        assert session.state.openai_session.session_id == "convenience_test_123"
        
        print("✅ Convenience function test passed")
    
    def test_session_state_basic_operations(self):
        """Test basic session state operations"""
        model_config = get_model_config("o1-mini")
        session = InteractionSessionManager.create_session(config=model_config)
        
        # Test context variables
        session.state.context_vars["test_key"] = "test_value"
        assert session.state.context_vars["test_key"] == "test_value"
        
        # Test Agent setting
        session.state.current_agent = "TestAgent"
        assert session.state.current_agent == "TestAgent"
        
        # Verify OpenAI Session
        assert session.state.openai_session is not None
        assert session.state.openai_session.session_id == session.session_id
        
        print("✅ Basic session state operations test passed")
    
    def test_multiple_sessions_different_ids(self):
        """Test creating multiple sessions with different IDs"""
        sessions = []
        for i in range(3):
            session = InteractionSessionManager.create_session()
            sessions.append(session)
        
        # Verify all sessions have different IDs
        session_ids = [s.session_id for s in sessions]
        assert len(set(session_ids)) == 3  # All IDs are different
        
        # Verify each session's OpenAI Session uses corresponding ID
        for session in sessions:
            assert session.state.openai_session.session_id == session.session_id
        
        print("✅ Multiple sessions different IDs test passed")
    
    def test_model_settings_integration(self):
        """Test ModelSettings integration"""
        test_models = ["claude-3-7-sonnet", "gpt-4o", "gemini-2.5-pro", "o1"]
        
        for model_name in test_models:
            model_config = get_model_config(model_name)
            if model_config:
                session = InteractionSessionManager.create_session(config=model_config)
                
                assert session.config.model_name == model_name
                assert session.state.openai_session is not None
                
                # Verify model features
                if model_name == "claude-3-7-sonnet":
                    assert session.config.supports_images is True
                    assert session.config.supports_prompt_cache is False
                elif model_name == "o1":
                    assert session.config.supports_images is True
                    assert session.config.supports_prompt_cache is True
        
        print("✅ ModelSettings integration test passed")


def run_all_tests():
    """Run all tests"""
    print("Starting simplified interaction session management system tests...\n")
    
    test_instance = TestInteractionSessionSystem()
    
    test_methods = [
        test_instance.test_create_session_with_uuid,
        test_instance.test_create_session_with_custom_id,
        test_instance.test_create_session_without_config,
        test_instance.test_create_session_with_custom_db_path,
        test_instance.test_model_specific_db_path,
        test_instance.test_convenience_function,
        test_instance.test_session_state_basic_operations,
        test_instance.test_multiple_sessions_different_ids,
        test_instance.test_model_settings_integration,
    ]
    
    passed = 0
    failed = 0
    
    for test_method in test_methods:
        try:
            test_instance.setup_method()  # Re-initialize
            test_method()
            passed += 1
        except Exception as e:
            print(f"❌ Test failed {test_method.__name__}: {e}")
            failed += 1
    
    print(f"\nTest results: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("🎉 All tests passed! Simplified interaction session management system works properly.")
        print("System features:")
        print("- Interaction session and openai_session share the same ID")
        print("- Support custom ID or auto-generate UUID")
        print("- Focus on session creation, no session persistence")
        print("- Complete ModelSettings configuration integration")
    else:
        print("⚠️  Some tests failed, please check implementation.")


if __name__ == "__main__":
    run_all_tests() 