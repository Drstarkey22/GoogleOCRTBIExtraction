"""
Simple static file server to serve the frontend.
"""
import http.server
import socketserver
import os

PORT = 5000
DIRECTORY = "front_end"

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()

class ReuseAddrTCPServer(socketserver.TCPServer):
    allow_reuse_address = True

if __name__ == "__main__":
    with ReuseAddrTCPServer(("0.0.0.0", PORT), Handler) as httpd:
        print(f"Serving frontend at http://0.0.0.0:{PORT}")
        httpd.serve_forever()
