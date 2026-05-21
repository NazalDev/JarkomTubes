import socket
import threading
import os
import datetime

HOST           = '0.0.0.0'      # Listen on all interfaces
PROXY_PORT     = 8080           # Port that clients connect to

SERVER_HOST    = '127.0.0.1'    # IP address of the real web server (localhost if on same machine)
SERVER_PORT    = 8000           # Must match TCP_PORT in webserver.py

CACHE_DIR      = './cache'      # Folder where cached responses are saved
SERVER_TIMEOUT = 5              

# Lock to prevent race conditions when multiple threads access the cache
cache_lock = threading.Lock()

def log(message):
    """Prints a timestamped log message."""
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] [PROXY] {message}")

def url_to_cache_path(url):
    """
    Converts a URL path to a safe local file path for caching.
    e.g. '/index.html'  → './cache/index.html'
         '/css/main.css'→ './cache/css_main.css'  (flattened)
    """
    # Remove leading slash and replace remaining slashes with underscores
    safe_name = url.lstrip('/').replace('/', '_')
    if not safe_name:
        safe_name = 'index.html'   # default cache filename for '/'
    return os.path.join(CACHE_DIR, safe_name)

def get_from_cache(url):
    """Returns cached response bytes if it exists, or None if not cached."""
    cache_path = url_to_cache_path(url)
    with cache_lock:
        if os.path.exists(cache_path):
            with open(cache_path, 'rb') as f:
                return f.read()
    return None

def save_to_cache(url, response):
    """Saves a response to the cache folder."""
    cache_path = url_to_cache_path(url)
    with cache_lock:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(cache_path, 'wb') as f:
            f.write(response)

def forward_to_server(request):
    """
    Sends an HTTP request to the real web server.
    Returns the full response bytes, or None if server unreachable.
    Raises socket.timeout if server takes too long.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(SERVER_TIMEOUT)
    try:
        s.connect((SERVER_HOST, SERVER_PORT))
        s.send(request)

        # Receive the full response        
        response = b''
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            response += chunk
        return response
    finally:
        s.close()

def parse_url_from_request(raw_request):
    """Extracts the URL path from the first line of an HTTP request."""
    try:
        first_line = raw_request.decode('utf-8', errors='ignore').split('\n')[0]
        parts = first_line.split()
        if len(parts) >= 2:
            return parts[1]  # e.g. '/index.html'
    except Exception:
        pass
    return '/'

def handle_client(conn, addr):
    """
    Handles one client connection in its own thread.
    1. Receive HTTP request from client
    2. Check cache
    3. If HIT → send cached response
    4. If MISS → forward to server, cache it, send to client
    """
    start_time = datetime.datetime.now()
    try:
        # Step 1: Receive request from client
        request = conn.recv(4096)
        if not request:
            return

        url = parse_url_from_request(request)
        log(f"Request from {addr[0]} | URL: {url}")

        # Step 2: Check cache
        cached = get_from_cache(url)

        if cached:
            # --- CACHE HIT ---
            conn.send(cached)
            elapsed = (datetime.datetime.now() - start_time).total_seconds() * 1000
            log(f"CACHE HIT  | {addr[0]} | {url} | {elapsed:.1f}ms")

        else:
            # --- CACHE MISS ---
            try:
                response = forward_to_server(request)

                # Check if server returned an error status                
                save_to_cache(url, response)
                conn.send(response)
                elapsed = (datetime.datetime.now() - start_time).total_seconds() * 1000
                log(f"CACHE MISS | {addr[0]} | {url} | {elapsed:.1f}ms (forwarded to server)")

            except socket.timeout:
                # Server took too long → 504 Gateway Timeout
                body = b"<h1>504 Gateway Timeout</h1>"
                error_response = (
                    f"HTTP/1.1 504 Gateway Timeout\r\n"
                    f"Content-Type: text/html\r\n"
                    f"Content-Length: {len(body)}\r\n"
                    f"\r\n"
                ).encode() + body
                conn.send(error_response)
                log(f"504 TIMEOUT | {addr[0]} | {url}")

            except ConnectionRefusedError:
                # Server is down → 502 Bad Gateway
                body = b"<h1>502 Bad Gateway</h1>"
                error_response = (
                    f"HTTP/1.1 502 Bad Gateway\r\n"
                    f"Content-Type: text/html\r\n"
                    f"Content-Length: {len(body)}\r\n"
                    f"\r\n"
                ).encode() + body
                conn.send(error_response)
                log(f"502 BAD GATEWAY | {addr[0]} | {url}")

    except Exception as e:
        log(f"Error handling {addr}: {e}")
    finally:
        conn.close()

# --- Entry point ---
if __name__ == '__main__':
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PROXY_PORT))
    server.listen(10)  # max queued connections
    log(f"Proxy listening on port {PROXY_PORT} | Forwarding to {SERVER_HOST}:{SERVER_PORT}")
    log(f"Cache directory: {os.path.abspath(CACHE_DIR)}")

    while True:
        conn, addr = server.accept()
        log(f"New connection from {addr[0]}:{addr[1]}")
        # Spawn a new thread per client — this is how concurrency works
        t = threading.Thread(target=handle_client, args=(conn, addr))
        t.daemon = True
        t.start()