"""
测试用例：验证 litellm.num_retries=3 对 Anthropic provider 的 RateLimitError (429) 是否生效。

背景：
- siada_client.py 调用 litellm.acompletion() 时 custom_llm_provider="anthropic"
- 上游代理返回 429 QPS 限流错误
- litellm.num_retries=3 在 entrypoint/__init__.py 中设置
- 期望：litellm 的 @client wrapper (utils.py) 应该通过 acompletion_with_retries 触发重试

本测试模拟上游返回 429，观察 litellm 是否真的重试了请求。
"""

import asyncio
import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import time


class Mock429Handler(BaseHTTPRequestHandler):
    """模拟上游代理返回 429 QPS 限流"""
    request_count = 0

    def do_POST(self):
        Mock429Handler.request_count += 1
        # 模拟你们代理返回的 429 错误格式
        error_body = json.dumps({
            "code": 4000003,
            "message": "QPS已达上限，请求过于频繁",
            "data": "QpsOverLimitException(model=aws-claude-sonnet-4-6, httpCode=429)"
        })
        self.send_response(429)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(error_body.encode())

    def log_message(self, format, *args):
        pass  # suppress logs


class Mock429ThenSuccessHandler(BaseHTTPRequestHandler):
    """前 N 次返回 429，之后返回成功"""
    request_count = 0
    fail_count = 2  # 前2次失败，第3次成功

    def do_POST(self):
        Mock429ThenSuccessHandler.request_count += 1
        if Mock429ThenSuccessHandler.request_count <= Mock429ThenSuccessHandler.fail_count:
            error_body = json.dumps({
                "code": 4000003,
                "message": "QPS已达上限，请求过于频繁",
                "data": "QpsOverLimitException(model=aws-claude-sonnet-4-6, httpCode=429)"
            })
            self.send_response(429)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(error_body.encode())
        else:
            # 模拟 Anthropic 成功响应
            success_body = json.dumps({
                "id": "msg_test123",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "Hello!"}],
                "model": "claude-sonnet-4-6",
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 5}
            })
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(success_body.encode())

    def log_message(self, format, *args):
        pass


def start_mock_server(handler_class, port):
    server = HTTPServer(("127.0.0.1", port), handler_class)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    return server


class TestLitellmRetryOnRateLimit:
    """验证 litellm.num_retries 对 anthropic 429 的重试行为"""

    @pytest.mark.asyncio
    async def test_acompletion_anthropic_429_does_retry_with_num_retries(self):
        """
        场景复现：
        - litellm.num_retries = 3
        - 调用 litellm.acompletion() with custom_llm_provider="anthropic"
        - 上游持续返回 429
        - 验证：litellm 是否尝试了重试（通过请求计数验证）
        """
        import litellm

        # 启动 mock server 模拟持续 429
        port = 19876
        Mock429Handler.request_count = 0
        server = start_mock_server(Mock429Handler, port)

        try:
            # 设置 litellm.num_retries = 3（和你的 entrypoint/__init__.py 一样）
            original_num_retries = litellm.num_retries
            litellm.num_retries = 3
            litellm.set_verbose = True  # 打开 verbose 看日志

            try:
                response = await litellm.acompletion(
                    model="anthropic/claude-sonnet-4-6",
                    messages=[{"role": "user", "content": "Hello"}],
                    api_key="fake-key",
                    base_url=f"http://127.0.0.1:{port}",
                    timeout=5,
                )
                # 如果成功了说明重试生效且最终成功（但我们这里持续429，不应到这里）
                pytest.fail("Expected RateLimitError but got success response")
            except Exception as e:
                print(f"\n{'='*60}")
                print(f"异常类型: {type(e).__name__}")
                print(f"异常信息: {e}")
                print(f"实际请求次数: {Mock429Handler.request_count}")
                print(f"{'='*60}")

                # 关键断言：如果 litellm.num_retries=3 生效，
                # 应该有 >1 次请求（原始请求 + 重试）
                if Mock429Handler.request_count == 1:
                    print("\n⚠️  结论：litellm.num_retries=3 对 Anthropic 429 没有触发重试！")
                    print("   请求只发出了 1 次，没有任何重试。")
                    print("   这就是日志中 elapsed=83ms 且 token-hook 只触发一次的原因。")
                else:
                    print(f"\n✅ litellm 确实重试了，总共请求了 {Mock429Handler.request_count} 次")

                # 这个断言预期会失败，证明 retry 没有生效
                assert Mock429Handler.request_count > 1, (
                    f"litellm.num_retries=3 未生效！"
                    f"期望 >1 次请求，实际只有 {Mock429Handler.request_count} 次。"
                    f"说明 @client wrapper 的重试逻辑对 anthropic 429 不工作。"
                )
            finally:
                litellm.num_retries = original_num_retries
                litellm.set_verbose = False
        finally:
            server.shutdown()

    @pytest.mark.asyncio
    async def test_acompletion_anthropic_429_then_success_with_retries(self):
        """
        场景：前2次 429，第3次成功
        如果重试生效，应该最终返回成功响应
        """
        import litellm

        port = 19877
        Mock429ThenSuccessHandler.request_count = 0
        Mock429ThenSuccessHandler.fail_count = 2
        server = start_mock_server(Mock429ThenSuccessHandler, port)

        try:
            original_num_retries = litellm.num_retries
            litellm.num_retries = 3

            try:
                response = await litellm.acompletion(
                    model="anthropic/claude-sonnet-4-6",
                    messages=[{"role": "user", "content": "Hello"}],
                    api_key="fake-key",
                    base_url=f"http://127.0.0.1:{port}",
                    timeout=5,
                )
                print(f"\n✅ 重试成功！总请求次数: {Mock429ThenSuccessHandler.request_count}")
                print(f"   响应: {response}")
                assert Mock429ThenSuccessHandler.request_count == 3, (
                    f"期望 3 次请求（2次失败+1次成功），实际 {Mock429ThenSuccessHandler.request_count} 次"
                )
            except Exception as e:
                print(f"\n{'='*60}")
                print(f"异常类型: {type(e).__name__}")
                print(f"异常信息: {e}")
                print(f"实际请求次数: {Mock429ThenSuccessHandler.request_count}")
                print(f"{'='*60}")

                if Mock429ThenSuccessHandler.request_count <= Mock429ThenSuccessHandler.fail_count:
                    print("\n⚠️  重试未生效：请求次数 <= 失败次数，说明没有重试到成功")
                    pytest.fail(
                        f"litellm.num_retries=3 未能让请求重试到成功。"
                        f"请求了 {Mock429ThenSuccessHandler.request_count} 次，"
                        f"前 {Mock429ThenSuccessHandler.fail_count} 次是 429。"
                    )
            finally:
                litellm.num_retries = original_num_retries
        finally:
            server.shutdown()

    @pytest.mark.asyncio
    async def test_siada_client_429_no_retry(self):
        """
        场景复现：模拟 SiadaClient._acompletion 的完整调用链
        验证 _max_retries=0 时遇到 429 的行为
        """
        import litellm
        from litellm.exceptions import RateLimitError

        port = 19878
        Mock429Handler.request_count = 0
        server = start_mock_server(Mock429Handler, port)

        try:
            original_num_retries = litellm.num_retries
            litellm.num_retries = 3

            # 模拟 SiadaClient 的逻辑（_max_retries=0）
            _max_retries = 0
            _base_delay = 10.0
            _t0 = time.perf_counter()

            try:
                for _attempt in range(_max_retries + 1):
                    try:
                        ret = await litellm.acompletion(
                            model="anthropic/claude-sonnet-4-6",
                            messages=[{"role": "user", "content": "Hello"}],
                            api_key="fake-key",
                            base_url=f"http://127.0.0.1:{port}",
                            timeout=5,
                        )
                        break
                    except RateLimitError as exc:
                        if _attempt < _max_retries:
                            _delay = _base_delay * (2 ** _attempt)
                            await asyncio.sleep(_delay)
                        else:
                            elapsed_ms = (time.perf_counter() - _t0) * 1000
                            print(f"\n{'='*60}")
                            print(f"[siada_client 模拟] FINAL FAILURE")
                            print(f"  elapsed={elapsed_ms:.0f}ms")
                            print(f"  异常: {type(exc).__name__}: {exc}")
                            print(f"  litellm 内部请求次数: {Mock429Handler.request_count}")
                            print(f"{'='*60}")

                            if Mock429Handler.request_count == 1:
                                print("\n⚠️  确认：即使 litellm.num_retries=3，")
                                print("   Anthropic 429 也只发了 1 次请求，没有重试。")
                                print("   这与用户日志 elapsed=83ms 完全吻合。")
                            else:
                                print(f"\n   litellm 内部重试了 {Mock429Handler.request_count} 次")
                            raise
            finally:
                litellm.num_retries = original_num_retries
        finally:
            server.shutdown()


    @pytest.mark.asyncio
    async def test_acompletion_anthropic_429_with_stream_true(self):
        """
        关键场景：stream=True 时 litellm.num_retries 是否还能生效？
        这才是 siada_client chat_complete_stream 的真实调用方式！
        """
        import litellm

        port = 19879
        Mock429Handler.request_count = 0
        server = start_mock_server(Mock429Handler, port)

        try:
            original_num_retries = litellm.num_retries
            litellm.num_retries = 3

            try:
                response = await litellm.acompletion(
                    model="anthropic/claude-sonnet-4-6",
                    messages=[{"role": "user", "content": "Hello"}],
                    api_key="fake-key",
                    base_url=f"http://127.0.0.1:{port}",
                    stream=True,  # <-- 关键差异！模拟 chat_complete_stream
                    timeout=5,
                )
                # 如果返回了 stream 对象，尝试消费它
                if hasattr(response, '__aiter__'):
                    async for chunk in response:
                        pass
                pytest.fail("Expected RateLimitError but got success response")
            except Exception as e:
                print(f"\n{'='*60}")
                print(f"[stream=True] 异常类型: {type(e).__name__}")
                print(f"[stream=True] 异常信息: {e}")
                print(f"[stream=True] 实际请求次数: {Mock429Handler.request_count}")
                print(f"{'='*60}")

                if Mock429Handler.request_count == 1:
                    print("\n⚠️  结论：stream=True 时 litellm.num_retries=3 没有触发重试！")
                    print("   这就是生产环境 chat_complete_stream 不重试的根因！")
                else:
                    print(f"\n✅ stream=True 也重试了，总共请求了 {Mock429Handler.request_count} 次")

                # 验证 stream=True 是否影响重试
                assert Mock429Handler.request_count > 1, (
                    f"stream=True 时 litellm.num_retries=3 未生效！"
                    f"期望 >1 次请求，实际只有 {Mock429Handler.request_count} 次。"
                    f"这证明 stream=True 是导致重试不生效的根因！"
                )
            finally:
                litellm.num_retries = original_num_retries
        finally:
            server.shutdown()


    @pytest.mark.asyncio
    async def test_acompletion_with_production_litellm_config(self):
        """
        完全模拟生产环境 _configure_litellm_logging() 的设置后，
        验证 litellm.num_retries 是否仍然生效。

        生产环境设置：
        - litellm.set_verbose = False
        - litellm.turn_off_message_logging = True
        - litellm.suppress_debug_info = True
        - litellm.drop_params = True
        - litellm.num_retries = 3
        - litellm.success_callback = []
        - litellm.failure_callback = []
        - 注册了 CustomLogger (token refresh callback)
        """
        import litellm
        from litellm.integrations.custom_logger import CustomLogger

        port = 19880
        Mock429Handler.request_count = 0
        server = start_mock_server(Mock429Handler, port)

        try:
            # 保存原始状态
            original_state = {
                'num_retries': litellm.num_retries,
                'turn_off_message_logging': litellm.turn_off_message_logging,
                'suppress_debug_info': litellm.suppress_debug_info,
                'drop_params': litellm.drop_params,
                'success_callback': litellm.success_callback,
                'failure_callback': litellm.failure_callback,
                'callbacks': litellm.callbacks[:] if litellm.callbacks else [],
            }

            # 完全模拟 _configure_litellm_logging() 的设置
            litellm.set_verbose = False
            litellm.turn_off_message_logging = True
            litellm.suppress_debug_info = True
            litellm.drop_params = True
            litellm.num_retries = 3
            litellm.turn_off_message_logging = True
            litellm.success_callback = []
            litellm.failure_callback = []

            # 模拟注册 token refresh callback
            class _MockTokenRefreshCallback(CustomLogger):
                hook_call_count = 0

                async def async_pre_call_deployment_hook(self, kwargs, call_type):
                    _MockTokenRefreshCallback.hook_call_count += 1

            _MockTokenRefreshCallback.hook_call_count = 0
            callback_instance = _MockTokenRefreshCallback()
            litellm.callbacks.append(callback_instance)

            try:
                response = await litellm.acompletion(
                    model="anthropic/claude-sonnet-4-6",
                    messages=[{"role": "user", "content": "Hello"}],
                    api_key="fake-key",
                    base_url=f"http://127.0.0.1:{port}",
                    stream=True,
                    timeout=5,
                )
                if hasattr(response, '__aiter__'):
                    async for chunk in response:
                        pass
                pytest.fail("Expected RateLimitError but got success")
            except Exception as e:
                print(f"\n{'='*60}")
                print(f"[生产环境配置] 异常类型: {type(e).__name__}")
                print(f"[生产环境配置] 异常信息: {e}")
                print(f"[生产环境配置] 实际请求次数: {Mock429Handler.request_count}")
                print(f"[生产环境配置] token-hook 触发次数: {_MockTokenRefreshCallback.hook_call_count}")
                print(f"{'='*60}")

                if Mock429Handler.request_count == 1:
                    print("\n⚠️  生产环境配置下 litellm.num_retries=3 没有触发重试！")
                    print("   说明是 litellm 的某个配置导致了重试失效。")
                else:
                    print(f"\n✅ 生产环境配置下也重试了，请求 {Mock429Handler.request_count} 次")
                    print(f"   token-hook 触发了 {_MockTokenRefreshCallback.hook_call_count} 次")
            finally:
                # 恢复原始状态
                litellm.num_retries = original_state['num_retries']
                litellm.turn_off_message_logging = original_state['turn_off_message_logging']
                litellm.suppress_debug_info = original_state['suppress_debug_info']
                litellm.drop_params = original_state['drop_params']
                litellm.success_callback = original_state['success_callback']
                litellm.failure_callback = original_state['failure_callback']
                litellm.callbacks = original_state['callbacks']
        finally:
            server.shutdown()


    @pytest.mark.asyncio
    async def test_num_retries_state_pollution_after_first_429(self):
        """
        关键测试：验证 litellm.num_retries 在第一次 429 重试后是否被污染为 None

        litellm/utils.py line 2017:
            litellm.num_retries = None  # set retries to None to prevent infinite loops

        这意味着：在长驻进程中，第一次 429 会触发重试（正常），
        但之后 litellm.num_retries 被永久设为 None，
        后续所有请求遇到 429 都不会再重试！

        这就是生产环境的根因：
        - 第一次 429 → 重试 3 次 → 重试期间 litellm.num_retries 被设为 None
        - 后续所有 429 → 不重试，直接失败（elapsed=83ms）
        """
        import litellm

        port = 19881
        Mock429Handler.request_count = 0
        server = start_mock_server(Mock429Handler, port)

        try:
            original_num_retries = litellm.num_retries
            litellm.num_retries = 3

            print(f"\n[初始状态] litellm.num_retries = {litellm.num_retries}")

            # === 第一次调用：应该重试 ===
            try:
                await litellm.acompletion(
                    model="anthropic/claude-sonnet-4-6",
                    messages=[{"role": "user", "content": "Hello"}],
                    api_key="fake-key",
                    base_url=f"http://127.0.0.1:{port}",
                    stream=True,
                    timeout=5,
                )
            except Exception as e:
                first_call_requests = Mock429Handler.request_count
                print(f"[第1次调用] 请求次数: {first_call_requests}")
                print(f"[第1次调用后] litellm.num_retries = {litellm.num_retries}")

            # === 关键检查：litellm.num_retries 是否被污染 ===
            num_retries_after_first = litellm.num_retries
            if num_retries_after_first is None:
                print("\n🔴 确认！litellm.num_retries 被设为 None 了！")
                print("   后续请求将不会再重试。")
            else:
                print(f"\n   litellm.num_retries 仍为 {num_retries_after_first}")

            # === 第二次调用：验证是否还能重试 ===
            Mock429Handler.request_count = 0
            try:
                await litellm.acompletion(
                    model="anthropic/claude-sonnet-4-6",
                    messages=[{"role": "user", "content": "Hello again"}],
                    api_key="fake-key",
                    base_url=f"http://127.0.0.1:{port}",
                    stream=True,
                    timeout=5,
                )
            except Exception as e:
                second_call_requests = Mock429Handler.request_count
                print(f"\n[第2次调用] 请求次数: {second_call_requests}")
                print(f"[第2次调用] 异常: {e}")

                if second_call_requests == 1:
                    print("\n⚠️⚠️⚠️ 根因确认！⚠️⚠️⚠️")
                    print("   第2次调用只发了 1 次请求，没有重试。")
                    print("   原因：litellm.num_retries 在第1次重试后被设为 None。")
                    print("   这就是生产环境用户日志 elapsed=83ms 的根因：")
                    print("   之前某个请求已经触发过重试，污染了全局状态。")
                else:
                    print(f"   第2次调用也重试了 {second_call_requests} 次")

            # 最终断言
            assert num_retries_after_first is None, (
                f"预期 litellm.num_retries 被设为 None，实际为 {num_retries_after_first}"
            )
            assert second_call_requests == 1, (
                f"预期第2次调用不重试（1次请求），实际 {second_call_requests} 次"
            )

            litellm.num_retries = original_num_retries
        finally:
            server.shutdown()


    @pytest.mark.asyncio
    async def test_fix_pass_num_retries_as_kwarg_survives_pollution(self):
        """
        验证修复方案：显式传 num_retries=3 作为 kwarg，
        即使 litellm.num_retries 被污染为 None 也能正常重试。
        """
        import litellm

        port = 19882
        Mock429Handler.request_count = 0
        server = start_mock_server(Mock429Handler, port)

        try:
            # 模拟已被污染的全局状态
            original_num_retries = litellm.num_retries
            litellm.num_retries = None  # 已被之前的请求污染

            try:
                response = await litellm.acompletion(
                    model="anthropic/claude-sonnet-4-6",
                    messages=[{"role": "user", "content": "Hello"}],
                    api_key="fake-key",
                    base_url=f"http://127.0.0.1:{port}",
                    stream=True,
                    timeout=5,
                    num_retries=3,  # <-- 方案2: 显式传入，不依赖全局变量
                )
                if hasattr(response, '__aiter__'):
                    async for chunk in response:
                        pass
            except Exception as e:
                print(f"\n{'='*60}")
                print(f"[修复验证] litellm.num_retries = None (已被污染)")
                print(f"[修复验证] 但显式传了 num_retries=3")
                print(f"[修复验证] 实际请求次数: {Mock429Handler.request_count}")
                print(f"[修复验证] 异常: {e}")
                print(f"{'='*60}")

                assert Mock429Handler.request_count == 4, (
                    f"修复后应该重试 3 次（共 4 次请求），"
                    f"实际 {Mock429Handler.request_count} 次"
                )
                print("\n✅ 修复有效！即使全局状态被污染，显式传 num_retries=3 仍然触发重试。")
            finally:
                litellm.num_retries = original_num_retries
        finally:
            server.shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
