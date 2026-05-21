import socket
import threading
import os
import datetime

HOST = '0.0.0.0'       # Listen on all interfaces (don't change unless you know why)
TCP_PORT = 8000        # Port for HTTP requests from Proxy
UDP_PORT = 9000        # Port for UDP echo (QoS testing)
FILES_DIR = './'       # Folder where your HTML files are stored (same folder as this script)

def get_content_type(filename):
    """Returns the correct Content-Type based on file extension."""
    if filename.endswith('.html'):
        return 'text/html; charset=utf-8'
    elif filename.endswith('.css'):
        return 'text/css'
    elif filename.endswith('.js'):
        return 'application/javascript'
    elif filename.endswith('.png'):
        return 'image/png'
    elif filename.endswith('.jpg') or filename.endswith('.jpeg'):
        return 'image/jpeg'
    else:
        return 'application/octet-stream'

def log(message):
    """Prints a timestamped log message."""
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] [WEBSERVER] {message}")

def handle_tcp_client(conn, addr):
    """
    Handles one HTTP client connection in its own thread.
    Receives GET request, finds the file, sends HTTP response.
    """
    try:
        # Receive the raw HTTP request
        request = conn.recv(4096).decode('utf-8', errors='ignore')
        if not request:
            return

        # --- Parse the request line (e.g. "GET /index.html HTTP/1.1") ---
        first_line = request.split('\n')[0]
        parts = first_line.split()
        if len(parts) < 2:
            conn.close()
            return

        method = parts[0]   # e.g. "GET"
        url    = parts[1]   # e.g. "/index.html"
        
        if method != 'GET':
            response = "HTTP/1.1 405 Method Not Allowed\r\n\r\n"
            conn.send(response.encode())
            return

        # Convert URL path to local file path
        # e.g. "/index.html" → "./index.html"
        if url == '/':
            url = '/index.html'   # 🔧 TUNE: change default page if needed
        filepath = os.path.join(FILES_DIR, url.lstrip('/'))

        # --- Try to read and send the file ---
        try:
            with open(filepath, 'rb') as f:
                content = f.read()

            content_type = get_content_type(filepath)
            response_header = (
                f"HTTP/1.1 200 OK\r\n"
                f"Content-Type: {content_type}\r\n"
                f"Content-Length: {len(content)}\r\n"
                f"\r\n"
            )
            conn.send(response_header.encode() + content)
            log(f"200 OK | {addr[0]} | {url}")

        except FileNotFoundError:
            # --- 404 Not Found ---
            body = b"<h1>404 Not Found</h1>"
            response = (
                f"HTTP/1.1 404 Not Found\r\n"
                f"Content-Type: text/html\r\n"
                f"Content-Length: {len(body)}\r\n"
                f"\r\n"
            ).encode() + body
            conn.send(response)
            log(f"404 NOT FOUND | {addr[0]} | {url}")

        except Exception as e:
            # --- 500 Internal Server Error ---
            body = b"<h1>500 Internal Server Error</h1>"
            response = (
                f"HTTP/1.1 500 Internal Server Error\r\n"
                f"Content-Type: text/html\r\n"
                f"Content-Length: {len(body)}\r\n"
                f"\r\n"
            ).encode() + body
            conn.send(response)
            log(f"500 ERROR | {addr[0]} | {url} | {e}")

    except Exception as e:
        log(f"Connection error from {addr}: {e}")
    finally:
        conn.close()

def start_tcp_server():
    """Main TCP server loop. Accepts connections and spawns a thread for each."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, TCP_PORT))
    server.listen(10)  # 🔧 TUNE: max queued connections (10 is fine for assignment)
    log(f"TCP HTTP Server running on port {TCP_PORT}")

    while True:
        conn, addr = server.accept()
        log(f"New TCP connection from {addr[0]}:{addr[1]}")
        # Spawn a new thread for each client so we don't block
        t = threading.Thread(target=handle_tcp_client, args=(conn, addr))
        t.daemon = True
        t.start()

def start_udp_server():
    """UDP echo server. Receives a packet and sends it straight back."""
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind((HOST, UDP_PORT))
    log(f"UDP Echo Server running on port {UDP_PORT}")

    while True:        
        data, addr = server.recvfrom(1024)
        server.sendto(data, addr)  # Echo back unchanged
        log(f"UDP echo | {addr[0]}:{addr[1]} | payload: {data.decode(errors='ignore')}")

# --- Entry point ---
if __name__ == '__main__':
    log("Starting Web Server...")

    # Run UDP server in a background thread
    udp_thread = threading.Thread(target=start_udp_server)
    udp_thread.daemon = True
    udp_thread.start()

    # Run TCP server in the main thread (blocks here forever)
    start_tcp_server()