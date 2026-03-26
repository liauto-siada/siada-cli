"""Lark OAuth Authorization Service"""

import asyncio
import webbrowser
import time
import socket
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode
from typing import Optional, Dict, Any
import requests
from siada.foundation.logging import logger
from .oauth_utils import generate_pkce_pair, generate_state


class LarkOAuthService:
    """Lark OAuth Authorization Service"""
    
    AUTHORIZATION_URL = "https://accounts.feishu.cn/open-apis/authen/v1/authorize"
    TOKEN_URL = "https://open.feishu.cn/open-apis/authen/v2/oauth/token"
    
    def __init__(
        self, 
        client_id: str, 
        client_secret: str,
        redirect_uris: Optional[list] = None
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        # Support multiple redirect URIs as fallbacks when ports are occupied
        self.redirect_uris = redirect_uris or []
        self.redirect_port: Optional[int] = None
        self.redirect_uri: Optional[str] = None
        self.code_verifier: Optional[str] = None
        self.code_challenge: Optional[str] = None
        self.state: Optional[str] = None
    
    async def start_oauth_flow(
        self,
        scopes: Optional[list] = None
    ) -> Dict[str, Any]:
        """
        Start the OAuth authorization flow
        
        Args:
            scopes: List of authorization scopes
        
        Returns:
            Token data dictionary
        
        Raises:
            RuntimeError: Authorization failed
        """
        if scopes is None:
            scopes = []
        
        try:
            # 1. Generate PKCE parameters
            self.code_verifier, self.code_challenge = generate_pkce_pair()
            self.state = generate_state()
            logger.debug("PKCE parameters generated")
            
            # 2. Find available port and corresponding redirect URI
            # redirect_uris are passed in from LarkOAuthManager's DEFAULT_REDIRECT_URIS
            self.redirect_uri = self._find_available_redirect_uri()
            # Extract port from URI
            from urllib.parse import urlparse as url_parse
            parsed = url_parse(self.redirect_uri)
            self.redirect_port = parsed.port or 80
            
            logger.info(f"Using redirect URI: {self.redirect_uri}")
            redirect_uri = self.redirect_uri
            
            # 3. Start local callback server
            callback_future = asyncio.Future()
            server = await self._start_callback_server(callback_future)
            
            # 4. Build authorization URL
            auth_url = self._build_authorization_url(redirect_uri, scopes)
            
            # 5. Open browser
            logger.info("Opening browser for authorization...")
            webbrowser.open(auth_url)
            
            # 6. Wait for callback (1 minute timeout)
            try:
                code = await asyncio.wait_for(callback_future, timeout=60.0)
                logger.info("Authorization code received")
            except asyncio.TimeoutError:
                raise RuntimeError("Authorization timeout (1 minute)")
            finally:
                # Shut down server in a non-blocking manner
                # server.shutdown() may block waiting for serve_forever() to end
                # since serve_forever keeps waiting for new requests after handling the current one
                import threading
                shutdown_thread = threading.Thread(target=server.shutdown)
                shutdown_thread.start()
                shutdown_thread.join(timeout=2.0)  # Wait at most 2 seconds
                if shutdown_thread.is_alive():
                    logger.debug("Server shutdown taking longer than 2s, continuing anyway")
            
            # 7. Exchange token
            token_data = await self._exchange_token(code, redirect_uri)
            logger.info("Token exchange successful")
            
            return token_data
            
        except Exception as e:
            logger.error(f"OAuth flow failed: {e}")
            raise
    
    def _build_authorization_url(
        self,
        redirect_uri: str,
        scopes: list
    ) -> str:
        """Build the authorization URL"""
        params = {
            'client_id': self.client_id,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'state': self.state,
            'code_challenge': self.code_challenge,
            'code_challenge_method': 'S256'
        }
        
        if scopes:
            params['scope'] = ' '.join(scopes)
        
        return f"{self.AUTHORIZATION_URL}?{urlencode(params)}"
    
    def _find_available_redirect_uri(self) -> str:
        """
        Find an available URI from the configured redirect URI list
        
        Note: This only checks if the port is available without occupying it.
        The port will be occupied when the HTTP server is started later.
        
        Returns:
            An available redirect URI
        
        Raises:
            RuntimeError: If all ports are occupied
        """
        import socket
        from urllib.parse import urlparse as url_parse
        
        for redirect_uri in self.redirect_uris:
            parsed = url_parse(redirect_uri)
            port = parsed.port or 80
            
            # Check if port is available (using SO_REUSEADDR to avoid TIME_WAIT issues)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(('localhost', port))
                sock.close()
                logger.debug(f"Port {port} is available for redirect URI: {redirect_uri}")
                return redirect_uri
            except OSError as e:
                sock.close()
                logger.debug(f"Port {port} is occupied ({e}), trying next redirect URI")
                continue
        
        # All ports are occupied
        ports = [url_parse(uri).port for uri in self.redirect_uris]
        raise RuntimeError(f"All configured redirect ports are occupied: {ports}")
    
    async def _start_callback_server(
        self,
        callback_future: asyncio.Future
    ) -> HTTPServer:
        """Start the local HTTP callback server"""
        
        service = self
        # Save event loop reference for cross-thread Future result setting
        # Use get_running_loop() to get the currently running event loop
        loop = asyncio.get_running_loop()
        
        logger.debug(f"Event loop for callback: {loop}, is_running: {loop.is_running()}")
        
        class CallbackHandler(BaseHTTPRequestHandler):
            def do_GET(handler_self):
                # Parse URL
                parsed = urlparse(handler_self.path)
                logger.debug(f"Callback received: path={parsed.path}, query={parsed.query}")
                
                if parsed.path != '/callback':
                    logger.warning(f"Invalid callback path: {parsed.path}")
                    handler_self.send_response(404)
                    handler_self.end_headers()
                    return
                
                # Parse parameters
                params = parse_qs(parsed.query)
                code = params.get('code', [None])[0]
                state = params.get('state', [None])[0]
                
                logger.debug(f"Callback params: code={'***' if code else None}, state={'***' if state else None}")
                
                # Verify state
                if state != service.state:
                    logger.error(f"State mismatch: expected={service.state[:10]}..., got={state[:10] if state else None}...")
                    handler_self.send_response(400)
                    handler_self.send_header('Content-Type', 'text/html; charset=utf-8')
                    handler_self.end_headers()
                    handler_self.wfile.write(service._build_error_html("State parameter mismatch, possible CSRF attack").encode('utf-8'))
                    # Use call_soon_threadsafe for cross-thread exception setting
                    loop.call_soon_threadsafe(
                        callback_future.set_exception,
                        RuntimeError("State mismatch")
                    )
                    return
                
                if not code:
                    logger.error("No authorization code in callback")
                    handler_self.send_response(400)
                    handler_self.send_header('Content-Type', 'text/html; charset=utf-8')
                    handler_self.end_headers()
                    handler_self.wfile.write(service._build_error_html("No authorization code received").encode('utf-8'))
                    # Use call_soon_threadsafe for cross-thread exception setting
                    loop.call_soon_threadsafe(
                        callback_future.set_exception,
                        RuntimeError("No authorization code")
                    )
                    return
                
                logger.info("Authorization code received successfully")
                
                # Return success page
                handler_self.send_response(200)
                handler_self.send_header('Content-Type', 'text/html; charset=utf-8')
                handler_self.end_headers()
                handler_self.wfile.write(service._build_success_html().encode('utf-8'))
                
                # Use call_soon_threadsafe for cross-thread Future result setting
                # The HTTP server runs in a separate thread,
                # but the Future belongs to the main thread's event loop, so thread-safe methods are required
                if not callback_future.done():
                    try:
                        loop.call_soon_threadsafe(callback_future.set_result, code)
                    except Exception as e:
                        logger.error(f"Failed to set future result: {e}")
            
            def log_message(handler_self, format, *args):
                # Suppress log output
                pass
        
        # Create custom HTTPServer class with SO_REUSEADDR support
        class ReuseAddrHTTPServer(HTTPServer):
            allow_reuse_address = True
        
        # Create server
        server = ReuseAddrHTTPServer(('localhost', self.redirect_port), CallbackHandler)
        
        logger.info(f"Creating callback server on port {self.redirect_port}")
        
        # Run server in a separate thread
        import threading
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        
        # Wait for server to start up
        await asyncio.sleep(0.2)
        
        # Verify server started successfully
        try:
            test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_sock.settimeout(1)
            result = test_sock.connect_ex(('localhost', self.redirect_port))
            test_sock.close()
            if result == 0:
                logger.info(f"Callback server started successfully on port {self.redirect_port}")
            else:
                logger.warning(f"Callback server may not be ready, connect result: {result}")
        except Exception as e:
            logger.warning(f"Could not verify server startup: {e}")
        
        return server
    
    async def _exchange_token(
        self,
        code: str,
        redirect_uri: str
    ) -> Dict[str, Any]:
        """Exchange authorization code for token"""
        
        data = {
            'grant_type': 'authorization_code',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'code': code,
            'redirect_uri': redirect_uri,
            'code_verifier': self.code_verifier
        }
        
        # Execute synchronous request in a separate thread
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: requests.post(self.TOKEN_URL, json=data, timeout=10)
        )
        
        result = response.json()
        logger.debug(f"Token exchange response: {result}")
        
        # Lark OAuth v2 API returns two formats:
        # 1. On success: token data directly (access_token, refresh_token, etc.)
        # 2. On failure: error/error_description or code/msg
        
        # Check for errors
        if response.status_code != 200:
            error_msg = result.get('error_description') or result.get('msg') or result.get('error') or response.text
            logger.error(f"Token exchange HTTP error: {response.status_code}, body: {response.text}")
            raise RuntimeError(f"Token exchange failed: {error_msg}")
        
        # Check OAuth standard error format
        if 'error' in result:
            error_msg = result.get('error_description') or result.get('error')
            logger.error(f"Token exchange OAuth error: {error_msg}")
            raise RuntimeError(f"Token exchange failed: {error_msg}")
        
        # Check Lark legacy API error format
        if result.get('code') and result.get('code') != 0:
            logger.error(f"Token exchange API error: code={result.get('code')}, msg={result.get('msg')}")
            raise RuntimeError(f"Token exchange failed: {result.get('msg', 'Unknown error')}")
        
        # Lark OAuth v2 API returns token data directly on success, not wrapped in a data field
        # But it may also be wrapped in a data field (compatible with both formats)
        if 'access_token' in result:
            token_data = result
        else:
            token_data = result.get('data', {})
        
        if not token_data or 'access_token' not in token_data:
            logger.error(f"No access_token in response: {result}")
            raise RuntimeError("access_token not found in response")
        
        # Add creation time
        token_data['token_created_time'] = int(time.time() * 1000)
        
        logger.info(f"Token received: access_token length={len(token_data.get('access_token', ''))}, "
                   f"has_refresh_token={bool(token_data.get('refresh_token'))}")
        
        return token_data
    
    def _build_success_html(self) -> str:
        """Build the authorization success HTML page"""
        return """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Authorization Successful</title>
    <style>
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
            text-align: center; 
            padding: 0; 
            margin: 0;
            background: #f5f5f5; 
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
        }
        .container { 
            background: white; 
            padding: 40px; 
            border-radius: 8px; 
            box-shadow: 0 4px 20px rgba(0,0,0,0.1); 
            max-width: 400px;
            width: 90%;
        }
        .icon { 
            width: 64px;
            height: 64px;
            background: #28a745;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 20px;
            color: white;
            font-size: 32px;
        }
        .success { 
            color: #333; 
            font-size: 20px; 
            font-weight: 600;
            margin-bottom: 16px; 
        }
        .description {
            color: #666;
            font-size: 14px;
            line-height: 1.5;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="icon">&#10003;</div>
        <div class="success">Authorization Successful</div>
        <div class="description">You can close this page and return to VSCode.</div>
    </div>
    <script>
        setTimeout(() => {
            window.close();
        }, 3000);
    </script>
</body>
</html>"""

    def _build_error_html(self, message: str = "") -> str:
        """
        Build the authorization failure HTML page
        
        Args:
            message: Error description message
        """
        import html
        safe_message = html.escape(message) if message else ""
        description = safe_message if safe_message else "Please return to VSCode and try again."
        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Authorization Failed</title>
    <style>
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
            text-align: center; 
            padding: 0; 
            margin: 0;
            background: #f5f5f5; 
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
        }}
        .container {{ 
            background: white; 
            padding: 40px; 
            border-radius: 8px; 
            box-shadow: 0 4px 20px rgba(0,0,0,0.1); 
            max-width: 400px;
            width: 90%;
        }}
        .icon {{ 
            width: 64px;
            height: 64px;
            background: #dc3545;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 20px;
            color: white;
            font-size: 32px;
        }}
        .error {{ 
            color: #333; 
            font-size: 20px; 
            font-weight: 600;
            margin-bottom: 16px; 
        }}
        .description {{
            color: #666;
            font-size: 14px;
            line-height: 1.5;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="icon">&#10007;</div>
        <div class="error">Authorization Failed</div>
        <div class="description">{description}</div>
    </div>
</body>
</html>"""

    async def refresh_token(
        self,
        refresh_token: str
    ) -> Dict[str, Any]:
        """
        Refresh the access token
        
        Args:
            refresh_token: The refresh token
        
        Returns:
            New token data
        """
        data = {
            'grant_type': 'refresh_token',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'refresh_token': refresh_token
        }
        
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: requests.post(self.TOKEN_URL, json=data, timeout=10)
        )
        
        result = response.json()
        logger.debug(f"Token refresh response: {result}")
        
        # Check for errors
        if response.status_code != 200:
            error_msg = result.get('error_description') or result.get('msg') or result.get('error') or response.text
            raise RuntimeError(f"Token refresh failed: {error_msg}")
        
        # Check OAuth standard error format
        if 'error' in result:
            error_msg = result.get('error_description') or result.get('error')
            raise RuntimeError(f"Token refresh failed: {error_msg}")
        
        # Check Lark legacy API error format
        if result.get('code') and result.get('code') != 0:
            raise RuntimeError(f"Token refresh failed: {result.get('msg', 'Unknown error')}")
        
        # Lark OAuth v2 API returns token data directly on success
        if 'access_token' in result:
            token_data = result
        else:
            token_data = result.get('data', {})
        
        if not token_data or 'access_token' not in token_data:
            logger.error(f"No access_token in refresh response: {result}")
            raise RuntimeError("access_token not found in refresh response")
        
        # Add creation time
        token_data['token_created_time'] = int(time.time() * 1000)
        
        return token_data
