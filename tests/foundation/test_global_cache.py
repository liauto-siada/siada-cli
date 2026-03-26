"""
Test Global Cache Module

Tests the thread-safe global cache for cross-thread data sharing.
"""

import threading
import time
import pytest

from siada.foundation.global_cache import (
    GlobalCache,
    set_global_cache,
    get_global_cache,
    remove_global_cache,
    clear_global_cache,
    has_global_cache,
    LAST_MEMORY_NAME
)


def test_basic_operations():
    """Test basic set, get, remove operations"""
    # Clear cache first
    clear_global_cache()
    
    # Set and get
    set_global_cache("test_key", "test_value")
    assert get_global_cache("test_key") == "test_value"
    
    # Get with default
    assert get_global_cache("nonexistent", "default") == "default"
    
    # Has
    assert has_global_cache("test_key") is True
    assert has_global_cache("nonexistent") is False
    
    # Remove
    remove_global_cache("test_key")
    assert get_global_cache("test_key") is None
    assert has_global_cache("test_key") is False


def test_clear_cache():
    """Test clearing all cache"""
    clear_global_cache()
    
    set_global_cache("key1", "value1")
    set_global_cache("key2", "value2")
    set_global_cache("key3", "value3")
    
    clear_global_cache()
    
    assert get_global_cache("key1") is None
    assert get_global_cache("key2") is None
    assert get_global_cache("key3") is None


def test_thread_safety_concurrent_writes():
    """Test thread safety with concurrent writes"""
    clear_global_cache()
    
    num_threads = 10
    num_writes_per_thread = 100
    
    def writer(thread_id):
        for i in range(num_writes_per_thread):
            set_global_cache(f"thread_{thread_id}_key_{i}", f"value_{i}")
    
    threads = []
    for i in range(num_threads):
        t = threading.Thread(target=writer, args=(i,))
        threads.append(t)
        t.start()
    
    for t in threads:
        t.join()
    
    # Verify all values were written
    for thread_id in range(num_threads):
        for i in range(num_writes_per_thread):
            key = f"thread_{thread_id}_key_{i}"
            expected_value = f"value_{i}"
            assert get_global_cache(key) == expected_value, f"Thread {thread_id} key {i} failed"


def test_thread_safety_concurrent_reads_writes():
    """Test thread safety with concurrent reads and writes"""
    clear_global_cache()
    
    # Pre-populate some data
    for i in range(100):
        set_global_cache(f"key_{i}", f"initial_value_{i}")
    
    num_readers = 5
    num_writers = 5
    duration = 2  # Run for 2 seconds
    
    stop_flag = threading.Event()
    errors = []
    
    def reader(reader_id):
        try:
            while not stop_flag.is_set():
                for i in range(100):
                    value = get_global_cache(f"key_{i}")
                    # Value should either be initial or updated by writer
                    if value is not None:
                        assert value.startswith("initial_value_") or value.startswith("updated_value_")
        except Exception as e:
            errors.append(f"Reader {reader_id}: {e}")
    
    def writer(writer_id):
        try:
            while not stop_flag.is_set():
                for i in range(100):
                    set_global_cache(f"key_{i}", f"updated_value_{i}_{writer_id}")
                time.sleep(0.01)  # Small delay
        except Exception as e:
            errors.append(f"Writer {writer_id}: {e}")
    
    # Start all threads
    threads = []
    
    for i in range(num_readers):
        t = threading.Thread(target=reader, args=(i,))
        threads.append(t)
        t.start()
    
    for i in range(num_writers):
        t = threading.Thread(target=writer, args=(i,))
        threads.append(t)
        t.start()
    
    # Run for specified duration
    time.sleep(duration)
    stop_flag.set()
    
    # Wait for all threads
    for t in threads:
        t.join(timeout=5)
    
    # Check for errors
    assert len(errors) == 0, f"Errors occurred: {errors}"


def test_cross_thread_visibility():
    """Test that data set in one thread is visible in another"""
    clear_global_cache()
    
    set_global_cache("test_key", "initial")
    
    result = {"success": False}
    
    def worker():
        # Read value set in main thread
        value = get_global_cache("test_key")
        if value == "initial":
            # Modify it
            set_global_cache("test_key", "modified")
            result["success"] = True
    
    t = threading.Thread(target=worker)
    t.start()
    t.join()
    
    assert result["success"] is True
    assert get_global_cache("test_key") == "modified"


def test_last_memory_name_constant():
    """Test the LAST_MEMORY_NAME constant"""
    clear_global_cache()
    
    memory_path = "/path/to/memory/file.md"
    set_global_cache(LAST_MEMORY_NAME, memory_path)
    
    assert get_global_cache(LAST_MEMORY_NAME) == memory_path
    
    remove_global_cache(LAST_MEMORY_NAME)
    assert get_global_cache(LAST_MEMORY_NAME) is None


def test_cache_instance_operations():
    """Test GlobalCache class instance operations"""
    cache = GlobalCache()
    
    # Set and get
    cache.set("key1", "value1")
    assert cache.get("key1") == "value1"
    
    # Has
    assert cache.has("key1") is True
    assert cache.has("nonexistent") is False
    
    # Keys
    cache.set("key2", "value2")
    cache.set("key3", "value3")
    keys = cache.keys()
    assert len(keys) == 3
    assert "key1" in keys
    assert "key2" in keys
    assert "key3" in keys
    
    # Length
    assert len(cache) == 3
    
    # Remove
    cache.remove("key1")
    assert cache.has("key1") is False
    assert len(cache) == 2
    
    # Clear
    cache.clear()
    assert len(cache) == 0


def test_different_data_types():
    """Test storing different data types"""
    clear_global_cache()
    
    # String
    set_global_cache("str", "string_value")
    assert get_global_cache("str") == "string_value"
    
    # Integer
    set_global_cache("int", 42)
    assert get_global_cache("int") == 42
    
    # List
    set_global_cache("list", [1, 2, 3])
    assert get_global_cache("list") == [1, 2, 3]
    
    # Dict
    set_global_cache("dict", {"key": "value"})
    assert get_global_cache("dict") == {"key": "value"}
    
    # None
    set_global_cache("none", None)
    assert get_global_cache("none") is None


def test_overwrite_value():
    """Test overwriting existing value"""
    clear_global_cache()
    
    set_global_cache("key", "value1")
    assert get_global_cache("key") == "value1"
    
    set_global_cache("key", "value2")
    assert get_global_cache("key") == "value2"
    
    set_global_cache("key", {"new": "value"})
    assert get_global_cache("key") == {"new": "value"}


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
