from http.server import BaseHTTPRequestHandler, HTTPServer
from os import environ
from os import makedirs
from random import choice
from string import ascii_letters, digits
from time import time


class Security:
    def __init__(self):
        self.rates = {}
        self.password = environ.get(
            "SEMAPHORE_PASSWORD",
            "".join([choice(ascii_letters + digits) for _ in range(256)]),
        )
        self.limit = 1
        self.tracked_ips = 100


security = Security()


class Handler(BaseHTTPRequestHandler):
    def send_error(self, code, message=None, **kwargs):
        self.error_content_type = "text/plain"
        self.error_message_format = ""

    def do_GET(self):
        self.send_response(400)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(bytes("400 Bad Request", "ascii"))

    def do_POST(self):
        # rate limiting
        client = self.client_address[0]
        if client in security.rates:
            last_time = security.rates[client]
            security.rates[client] = time()
            if time() - last_time < security.limit:
                self.send_response(429)
                self.end_headers()
                return
        else:
            security.rates[client] = time()
            while len(security.rates) > security.tracked_ips:
                oldest_time = min(security.rates.values())
                oldest_key = [
                    k for k in security.rates.keys() if security.rates[k] <= oldest_time
                ]
                for key in oldest_key:
                    del security.rates[key]

        # authentication
        if self.path != f"/?{security.password}":
            self.send_response(401)
            self.end_headers()
            return

        # payload parsing
        content_length = int(self.headers["Content-Length"])
        post_data = self.rfile.read(content_length).decode("utf8")
        post_data = "".join(
            [c for c in post_data if c in ascii_letters + digits + "-_:./"]
        )[:128]
        makedirs("/data", exist_ok=True)
        with open("/data/data.txt", "a") as f:
            f.write("\n")
            f.write(post_data)

        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(bytes("200 OK", "ascii"))


if __name__ == "__main__":
    with HTTPServer(("", 8000), Handler) as server:
        server.serve_forever()
