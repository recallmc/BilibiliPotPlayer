# -*- coding: utf-8 -*-
"""
Bilibili CDN 本地转发服务
================================================================
背景
----
PotPlayer 26.x 的 AngelScript 扩展 API（HostSetUrlHeaderHTTP / HostSetUrlRefererHTTP）
会把设置写入注册表，但实际播放时并不会把 Referer 应用到请求上。
而 B站 CDN（upos-*.bilivideo.com）强制校验 Referer，缺失即返回 403，
PotPlayer 因此报「服务器已关闭或地址错误 / 在渲染下列 Pin 时失败了」。

本服务在本地做一次中转：
    PotPlayer  ──►  http://127.0.0.1:18999/p/<id>
                          │
                          ├─ 补上 Referer / UA / Origin
                          ▼
                    B站 CDN（返回 206 视频流）
                          │
                          ▼
                    流式转发回 PotPlayer

因为 PotPlayer 面对的是本机地址，不需要任何 header 校验，问题被彻底绕开。

接口
----
GET /ping                存活检查，返回 pong
GET /reg?u=<urlencoded>  注册一个 CDN 地址，返回纯文本 id
GET /p/<id>              转发视频流（支持 Range 拖动进度）
HEAD /p/<id>             同上，仅返回响应头

依赖
----
仅需 Python 3.6+ 标准库，无需 pip 安装任何第三方包。

用法
----
    python bili_proxy.py
或双击同目录的 start_proxy.bat（无窗口后台运行）
"""

import sys
import time
import threading
import urllib.request
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ---------------------------------------------------------------- 配置
PORT = 18999
BIND = "127.0.0.1"

# 伪装成普通浏览器，避免 B站 对特殊 UA 的额外风控
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
REFERER = "https://www.bilibili.com"
ORIGIN = "https://www.bilibili.com"

# 从上游原样转发的响应头
FWD_HEADERS = ("content-type", "content-length", "content-range",
               "accept-ranges", "last-modified", "etag")

CHUNK = 262144          # 262KB，兼顾吞吐与内存
IDLE_TTL = 3 * 3600     # 3 小时未使用的映射自动清理

# ---------------------------------------------------------------- 状态
_store = {}             # id(str) -> CDN url
_last_used = {}         # id(str) -> 最后访问时间戳
_lock = threading.Lock()
_counter = [0]


def log(msg):
    """带时间戳输出到控制台；pythonw 下 stdout 为 None 时静默失败"""
    try:
        print(time.strftime("[%H:%M:%S] ") + str(msg), flush=True)
    except Exception:
        pass


def _cleanup_locked():
    """清理过期映射（调用方需已持锁）"""
    now = time.time()
    stale = [k for k, t in _last_used.items() if now - t > IDLE_TTL]
    for k in stale:
        _store.pop(k, None)
        _last_used.pop(k, None)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        # 屏蔽默认的每请求日志，避免刷屏
        pass

    # ------------------------------------------------------------ 工具
    def _send_text(self, code, body):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            self.wfile.write(data)
        except Exception:
            pass

    # ------------------------------------------------------------ /reg
    def _handle_reg(self, query):
        params = urllib.parse.parse_qs(query, keep_blank_values=True)
        target = params.get("u", [""])[0]
        if not target:
            self._send_text(400, "missing param u")
            return

        with _lock:
            _cleanup_locked()
            _counter[0] += 1
            sid = str(_counter[0])
            _store[sid] = target
            _last_used[sid] = time.time()

        host = target.split("/")[2] if "//" in target else "?"
        log("REG #%s -> %s" % (sid, host))
        self._send_text(200, sid)

    # ------------------------------------------------------------ /p/<id>
    def _handle_proxy(self, sid, head_only=False):
        with _lock:
            target = _store.get(sid)
            if target:
                _last_used[sid] = time.time()

        if not target:
            self._send_text(404, "unknown id")
            return

        # 关键：补上 B站 CDN 要求的请求头
        headers = {
            "Referer": REFERER,
            "Origin": ORIGIN,
            "User-Agent": UA,
        }
        # 透传 Range，PotPlayer 拖动进度条依赖此头
        rng = self.headers.get("Range")
        if rng:
            headers["Range"] = rng

        req = urllib.request.Request(target, headers=headers)

        try:
            resp = urllib.request.urlopen(req, timeout=30)
        except urllib.error.HTTPError as e:
            log("UPSTREAM HTTP %s (#%s)" % (e.code, sid))
            self._send_text(e.code, "upstream returned %s" % e.code)
            return
        except Exception as e:
            log("UPSTREAM ERROR (#%s): %s" % (sid, e))
            self._send_text(502, "upstream error")
            return

        # 上游返回 200(整段) 或 206(分段)，原样回给 PotPlayer
        self.send_response(resp.status)
        for k, v in resp.headers.items():
            if k.lower() in FWD_HEADERS:
                self.send_header(k, v)
        self.send_header("Connection", "close")
        self.end_headers()

        if head_only:
            try:
                resp.close()
            except Exception:
                pass
            return

        sent = 0
        try:
            while True:
                chunk = resp.read(CHUNK)
                if not chunk:
                    break
                self.wfile.write(chunk)
                sent += len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            # PotPlayer 主动断开（切集/关窗），正常现象
            pass
        except Exception as e:
            log("STREAM ERROR (#%s): %s" % (sid, e))
        finally:
            try:
                resp.close()
            except Exception:
                pass

        log("DONE #%s %d bytes (%.1f MB)" % (sid, sent, sent / 1048576.0))

    # ------------------------------------------------------------ 路由
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path, query = parsed.path, parsed.query

        if path == "/ping":
            self._send_text(200, "pong")
        elif path == "/reg":
            self._handle_reg(query)
        elif path.startswith("/p/"):
            self._handle_proxy(path[3:])
        else:
            self._send_text(404, "not found")

    def do_HEAD(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.startswith("/p/"):
            self._handle_proxy(parsed.path[3:], head_only=True)
        elif parsed.path == "/ping":
            self._send_text(200, "pong")
        else:
            self._send_text(404, "not found")


def main():
    try:
        srv = ThreadingHTTPServer((BIND, PORT), Handler)
    except OSError as e:
        log("无法监听 %s:%d -> %s" % (BIND, PORT, e))
        log("可能已有实例在运行，本窗口将退出")
        time.sleep(3)
        sys.exit(1)

    srv.daemon_threads = True
    log("Bilibili CDN proxy listening on http://%s:%d" % (BIND, PORT))
    log("保持本服务运行，关闭后 PotPlayer 将无法播放 B站 视频")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        log("stopped")


if __name__ == "__main__":
    main()
