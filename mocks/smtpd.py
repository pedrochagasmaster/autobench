#!/usr/bin/env python3
"""Small SMTP catcher for Dispatch development mode."""

from __future__ import annotations

import socketserver
import sys
import time
from pathlib import Path


class SMTPHandler(socketserver.StreamRequestHandler):
    output_dir: Path = Path("sent_emails")

    def handle(self) -> None:
        recipients: list[str] = []
        sender = ""
        self._send("220 dispatch mock smtp")
        while True:
            line = self.rfile.readline().decode("utf-8", errors="replace").rstrip("\r\n")
            upper = line.upper()
            if upper.startswith("HELO") or upper.startswith("EHLO"):
                self._send("250 dispatch mock")
            elif upper.startswith("MAIL FROM:"):
                sender = line.split(":", 1)[1].strip()
                self._send("250 ok")
            elif upper.startswith("RCPT TO:"):
                recipients.append(line.split(":", 1)[1].strip())
                self._send("250 ok")
            elif upper == "DATA":
                self._send("354 end with <CR><LF>.<CR><LF>")
                payload = self._read_data()
                self._write_message(sender, recipients, payload)
                self._send("250 stored")
            elif upper == "QUIT":
                self._send("221 bye")
                return
            else:
                self._send("250 ok")

    def _send(self, line: str) -> None:
        self.wfile.write(f"{line}\r\n".encode("utf-8"))

    def _read_data(self) -> bytes:
        chunks = []
        while True:
            line = self.rfile.readline()
            if line in {b".\r\n", b".\n", b""}:
                break
            chunks.append(line)
        return b"".join(chunks)

    def _write_message(self, sender: str, recipients: list[str], payload: bytes) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%dT%H%M%S")
        path = self.output_dir / f"{timestamp}_{len(list(self.output_dir.glob('*.eml'))):04d}.eml"
        path.write_bytes(payload)
        print(f"captured email {path} from={sender} to={','.join(recipients)}", flush=True)


def main() -> int:
    root = Path(__file__).resolve().parent
    SMTPHandler.output_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "sent_emails"
    with socketserver.TCPServer(("127.0.0.1", 2525), SMTPHandler) as server:
        print(f"mock SMTP listening on 127.0.0.1:2525; writing to {SMTPHandler.output_dir}", flush=True)
        server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
