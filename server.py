from http.server import BaseHTTPRequestHandler, HTTPServer
from config import PORT

class DummyServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write("Sosaltix2 Cluster Active!".encode("utf-8"))

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()

    def log_message(self, format, *args):
        return

def run_dummy_server():
    server = HTTPServer(("0.0.0.0", PORT), DummyServer)
    server.serve_forever()
