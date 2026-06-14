import socket
import time
import sys
import csv

PROXY_HOST  = '10.99.215.122'                                                     
PROXY_PORT  = 8080           # Must match PROXY_PORT in proxy.py

SERVER_HOST = '10.99.215.47'                               
SERVER_PORT = 9000           # Must match UDP_PORT in webserver.py

UDP_COUNT   = 10             
UDP_TIMEOUT = 1.0            

def mode_tcp(url='/index.html'):
    """
    HTTP mode: sends a GET request to the Proxy and prints the response
    use -mode tcp /page.html to request a different page
    """
    print(f"\n[TCP MODE] Sending GET {url} via Proxy ({PROXY_HOST}:{PROXY_PORT})")
    print("-" * 60)

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((PROXY_HOST, PROXY_PORT))

        # Build a proper HTTP GET request        
        request = (
            f"GET {url} HTTP/1.1\r\n"
            f"Host: {PROXY_HOST}:{PROXY_PORT}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        )
        s.send(request.encode())

        # Receive the full response
        response = b''
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            response += chunk
        s.close()

        # Split headers and body
        if b'\r\n\r\n' in response:
            headers, body = response.split(b'\r\n\r\n', 1)
            print("[HEADERS]")
            print(headers.decode('utf-8', errors='ignore'))
            print("\n[BODY]")            
            print(body.decode('utf-8', errors='ignore')[:2000])
        else:
            print(response.decode('utf-8', errors='ignore'))

    except ConnectionRefusedError:
        print(f"ERROR: Could not connect to Proxy at {PROXY_HOST}:{PROXY_PORT}")
        print("Make sure proxy.py is running first!")
    except Exception as e:
        print(f"ERROR: {e}")

def mode_udp():
    """
    QoS mode: sends UDP ping packets to the server and measures:
    - RTT per packet
    - Packet Loss %
    - Jitter
    - Throughput
    """
    print(f"\n[UDP MODE] Sending {UDP_COUNT} pings to {SERVER_HOST}:{SERVER_PORT}")
    print("-" * 60)

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(UDP_TIMEOUT)

    rtt_list = []
    lost = 0
    total_bytes = 0
    test_start = time.time()

    # Per-packet rows for CSV
    packet_rows = []

    for seq in range(1, UDP_COUNT + 1):
        timestamp = time.time()
        payload = f"Ping {seq} {timestamp}".encode()

        try:
            s.sendto(payload, (SERVER_HOST, SERVER_PORT))
            recv_data, _ = s.recvfrom(1024)
            recv_time = time.time()

            rtt = (recv_time - timestamp) * 1000
            rtt_list.append(rtt)
            total_bytes += len(recv_data)
            print(f"  Packet {seq:>2}: RTT = {rtt:.2f} ms")
            packet_rows.append({'seq': seq, 'status': 'received', 'rtt_ms': f"{rtt:.2f}"})

        except socket.timeout:
            lost += 1
            print(f"  Packet {seq:>2}: Request timed out")
            packet_rows.append({'seq': seq, 'status': 'lost', 'rtt_ms': ''})

    s.close()
    test_duration = time.time() - test_start

    print("\n" + "=" * 60)
    print("QoS STATISTICS")
    print("=" * 60)

    if rtt_list:
        min_rtt = min(rtt_list)
        max_rtt = max(rtt_list)
        avg_rtt = sum(rtt_list) / len(rtt_list)

        if len(rtt_list) > 1:
            diffs = [abs(rtt_list[i] - rtt_list[i-1]) for i in range(1, len(rtt_list))]
            avg_diff = sum(diffs) / len(diffs)
            jitter = (sum((d - avg_diff) ** 2 for d in diffs) / len(diffs)) ** 0.5
        else:
            jitter = 0.0

        throughput_kbps = (total_bytes * 8) / test_duration / 1000
        loss_percent = (lost / UDP_COUNT) * 100

        print(f"  Packets Sent     : {UDP_COUNT}")
        print(f"  Packets Received : {UDP_COUNT - lost}")
        print(f"  Packet Loss      : {loss_percent:.1f}%")
        print(f"  RTT Min          : {min_rtt:.2f} ms")
        print(f"  RTT Avg          : {avg_rtt:.2f} ms")
        print(f"  RTT Max          : {max_rtt:.2f} ms")
        print(f"  Jitter           : {jitter:.2f} ms")
        print(f"  Throughput       : {throughput_kbps:.2f} kbps")

        # ── CSV EXPORT ──────────────────────────────────────────
        csv_filename = f"qos_report_{time.strftime('%Y%m%d_%H%M%S')}.csv"

        with open(csv_filename, 'w', newline='') as f:
            writer = csv.writer(f)

            # Section 1: per-packet detail
            writer.writerow(['=== Per-Packet Detail ==='])
            writer.writerow(['Packet', 'Status', 'RTT (ms)'])
            for row in packet_rows:
                writer.writerow([row['seq'], row['status'], row['rtt_ms']])

            writer.writerow([])  # blank separator

            # Section 2: summary statistics
            writer.writerow(['=== Summary Statistics ==='])
            writer.writerow(['Metric', 'Value'])
            writer.writerow(['Server',           f"{SERVER_HOST}:{SERVER_PORT}"])
            writer.writerow(['Timestamp',         time.strftime('%Y-%m-%d %H:%M:%S')])
            writer.writerow(['Packets Sent',      UDP_COUNT])
            writer.writerow(['Packets Received',  UDP_COUNT - lost])
            writer.writerow(['Packet Loss (%)',   f"{loss_percent:.1f}"])
            writer.writerow(['RTT Min (ms)',       f"{min_rtt:.2f}"])
            writer.writerow(['RTT Avg (ms)',       f"{avg_rtt:.2f}"])
            writer.writerow(['RTT Max (ms)',       f"{max_rtt:.2f}"])
            writer.writerow(['Jitter (ms)',        f"{jitter:.2f}"])
            writer.writerow(['Throughput (kbps)', f"{throughput_kbps:.2f}"])

        print(f"\n  CSV saved → {csv_filename}")
        # ────────────────────────────────────────────────────────

    else:
        print("  All packets lost! Server may be down or firewall is blocking UDP.")
        print(f"  Packet Loss: 100%")

    print("=" * 60)

# --- Entry point ---
if __name__ == '__main__':
    # Usage:
    #   python client.py -mode tcp
    #   python client.py -mode tcp /about.html
    #   python client.py -mode udp

    if len(sys.argv) < 3:
        print("Usage:")
        print("  python client.py -mode tcp")
        print("  python client.py -mode tcp /page.html")
        print("  python client.py -mode udp")
        sys.exit(1)

    if sys.argv[1] == '-mode':
        mode = sys.argv[2].lower()

        if mode == 'tcp':
            # default page to request
            url = sys.argv[3] if len(sys.argv) > 3 else '/index.html'
            mode_tcp(url)

        elif mode == 'udp':
            mode_udp()

        else:
            print(f"Unknown mode '{mode}'. Use 'tcp' or 'udp'.")
    else:
        print("Usage: python client.py -mode tcp|udp")