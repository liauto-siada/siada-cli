"""OAuth utility functions module"""

import hashlib
import secrets
import base64
import socket
from typing import Tuple


def generate_pkce_pair() -> Tuple[str, str]:
    """
    Generate a PKCE parameter pair
    
    Returns:
        (code_verifier, code_challenge)
    """
    # Generate code_verifier (43-128 characters)
    code_verifier = base64.urlsafe_b64encode(
        secrets.token_bytes(32)
    ).decode('utf-8').rstrip('=')
    
    # Generate code_challenge (SHA256)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode('utf-8')).digest()
    ).decode('utf-8').rstrip('=')
    
    return code_verifier, code_challenge


def generate_state() -> str:
    """Generate state parameter (CSRF protection)"""
    return base64.urlsafe_b64encode(
        secrets.token_bytes(16)
    ).decode('utf-8').rstrip('=')


def get_token_fingerprint(token: str) -> str:
    """Get SHA-256 fingerprint (first 8 chars) of a token for logging"""
    return hashlib.sha256(token.encode()).hexdigest()[:8]


def find_available_port(start_port: int = 8077, end_port: int = 8083) -> int:
    """
    Find an available port
    
    Args:
        start_port: Start port
        end_port: End port (exclusive)
    
    Returns:
        Available port number
    
    Raises:
        RuntimeError: If no available port is found
    """
    for port in range(start_port, end_port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(('localhost', port))
                return port
            except OSError:
                continue
    
    raise RuntimeError(f"No available port in range {start_port}-{end_port}")
