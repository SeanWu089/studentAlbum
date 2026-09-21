"""Separate local teacher and public student HTTP surfaces."""
import functools
import hmac
import http.server
import io
import json
import secrets
import threading
import time
from collections import defaultdict, deque
from urllib.parse import urlsplit

from PIL import Image, ImageOps, UnidentifiedImageError
from storage import Problem

Image.MAX_IMAGE_PIXELS = 25_000_000
STUDENT_FILES = {'/', '/index.html', '/styles.css', '/app.js'}
ADMIN_FILES = {'/admin.html', '/admin.css', '/admin.js'}


class Application:
    def __init__(self, root, store, state, tunnel=None):
        self.root, self.store, self.state, self.tunnel = root, store, state, tunnel
        self.admin_key = secrets.token_urlsafe(32)
        self.limits = defaultdict(deque)
        self.limit_lock = threading.Lock()

    def limit(self, key, maximum, seconds):
        now = time.monotonic()
        with self.limit_lock:
            if len(self.limits) > 10000:
                self.limits = defaultdict(deque, {k: v for k, v in self.limits.items() if v and v[-1] > now - 600})
            queue = self.limits[key]
            while queue and queue[0] < now - seconds:
                queue.popleft()
            if len(queue) >= maximum:
                raise Problem('操作太频繁，请稍后再试。', 429)
            queue.append(now)

    def server(self, port, public=False, host='127.0.0.1'):
        server = http.server.ThreadingHTTPServer((host, port), functools.partial(Handler, app=self, public=public))
        server.daemon_threads = True
        return server


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = 'StudentAlbum'

    def __init__(self, *args, app, public, **kwargs):
        self.app, self.public = app, public
        super().__init__(*args, **kwargs)

    def setup(self):
        super().setup()
        self.connection.settimeout(20)

    def log_message(self, *_):
        pass

    def send(self, payload, status=200, content_type='application/json; charset=utf-8'):
        if not isinstance(payload, bytes):
            payload = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' blob:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(payload)

    def local_guard(self):
        expected = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
        if self.headers.get('Host') not in expected:
            raise Problem('管理页面只允许本机访问。', 403)
        origin = self.headers.get('Origin')
        if origin and origin not in {'http://' + host for host in expected}:
            raise Problem('请从本机管理页面操作。', 403)
        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
            raise Problem('请从本机管理页面操作。', 403)

    def admin(self):
        if self.public:
            raise Problem('页面不存在。', 404)
        self.local_guard()
        if not hmac.compare_digest(self.headers.get('X-Admin-Key', ''), self.app.admin_key):
            raise Problem('管理会话已更新，请刷新页面。', 401)

    def sid(self):
        bearer = self.headers.get('Authorization', '')
        if not bearer.startswith('Bearer '):
            raise Problem('请先进入自己的档案。', 401)
        return self.app.store.authorize(bearer[7:])

    def body(self, maximum=16000, raw=False):
        if self.headers.get('Transfer-Encoding'):
            raise Problem('不支持此上传方式。')
        try:
            size = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            raise Problem('请求长度无效。')
        if not 0 < size <= maximum:
            raise Problem('上传内容为空或超过大小限制。', 413)
        content = self.rfile.read(size)
        if len(content) != size:
            raise Problem('内容未传输完整，请重试。')
        if raw:
            return content
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            raise Problem('请求格式应为 JSON。', 415)
        try:
            data = json.loads(content)
        except (ValueError, UnicodeError):
            raise Problem('请求内容无效。')
        if not isinstance(data, dict):
            raise Problem('请求内容无效。')
        return data

    def dispatch(self):
        path = urlsplit(self.path).path
        store = self.app.store
        if not self.public:
            self.local_guard()
        if self.public and (path.startswith('/api/admin') or path in ADMIN_FILES or path == '/api/status'):
            raise Problem('页面不存在。', 404)
        if self.command in ('GET', 'HEAD'):
            if path in STUDENT_FILES | (set() if self.public else ADMIN_FILES):
                file = self.app.root / 'demo' / ('index.html' if path == '/' else path[1:])
                types = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8'}
                return self.send(file.read_bytes(), content_type=types[file.suffix])
            if path == '/api/classes':
                return self.send(store.classes())
            if path == '/api/student':
                return self.send({'student': store.student(self.sid())})
            if path == '/api/student/photo':
                return self.send(store.photo(self.sid()), content_type='image/jpeg')
            if path == '/api/admin/bootstrap':
                return self.send({'key': self.app.admin_key})
            if path == '/api/admin/overview':
                self.admin()
                return self.send({**store.classes(), 'students': store.students(), 'trash': store.students(trash=True),
                                  'snapshots': store.snapshots(), 'connection': dict(self.app.state)})
            if path.startswith('/api/admin/photos/'):
                self.admin()
                return self.send(store.photo(path.rsplit('/', 1)[-1]), content_type='image/jpeg')
        if self.command == 'POST':
            if path in ('/api/register', '/api/login'):
                data = self.body()
                identity = (str(data.get('classId')), str(data.get('number')))
                peer = self.headers.get('X-Forwarded-For', self.client_address[0]).split(',')[-1].strip()
                self.app.limit(('auth-peer', peer), 60, 60)
                self.app.limit(('auth-record', *identity), 10, 300)
                return self.send(store.register(data) if path == '/api/register' else store.login(data))
            if path == '/api/student':
                sid = self.sid()
                self.app.limit(('save', sid), 120, 60)
                return self.send(store.update(sid, self.body()))
            if path == '/api/student/photo' or path.startswith('/api/admin/photo-upload/'):
                if path.startswith('/api/admin/'):
                    self.admin()
                    sid = path.rsplit('/', 1)[-1]
                    store.student(sid)
                else:
                    sid = self.sid()
                self.app.limit(('photo', sid), 10, 60)
                raw = self.body(8 * 1024 * 1024, raw=True)
                try:
                    with Image.open(io.BytesIO(raw)) as source:
                        if source.format not in ('JPEG', 'PNG', 'WEBP'):
                            raise Problem('请上传 JPG、PNG 或 WebP 照片。')
                        source.load()
                        photo = ImageOps.exif_transpose(source).convert('RGB')
                        photo.thumbnail((1800, 1800))
                        output = io.BytesIO()
                        photo.save(output, 'JPEG', quality=88)
                except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
                    raise Problem('图片无法读取或尺寸过大，请换一张 JPG / PNG 照片。')
                return self.send(store.save_photo(sid, output.getvalue()))
            if path.startswith('/api/admin/'):
                self.admin()
                data = self.body()
                if path == '/api/admin/classes':
                    return self.send(store.add_classes(data))
                if path == '/api/admin/edit':
                    return self.send(store.admin_update(data))
                if path in ('/api/admin/delete', '/api/admin/restore'):
                    return self.send(store.recycle(data.get('id', ''), restore=path.endswith('/restore')))
                if path == '/api/admin/delete-class':
                    return self.send(store.delete_class(data.get('id', '')))
                if path == '/api/admin/restore-class':
                    return self.send(store.restore_class(data.get('id', '')))
                if path == '/api/admin/restore-snapshot':
                    return self.send(store.restore_snapshot(data.get('id', '')))
                if path == '/api/admin/reset-code':
                    return self.send(store.reset_code(data.get('id', '')))
                if path == '/api/admin/tunnel' and self.app.tunnel:
                    token = data.get('token', '')
                    if not isinstance(token, str) or len(token) > 500 or any(c.isspace() for c in token):
                        raise Problem('ngrok 令牌格式不正确。')
                    self.app.tunnel.start(token)
                    return self.send({'ok': True})
        raise Problem('页面不存在。', 404)

    def handle_request(self):
        try:
            self.dispatch()
        except Problem as error:
            self.send({'error': error.message}, error.status)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as error:
            print(f'请求处理失败：{type(error).__name__}', flush=True)
            self.send({'error': '暂时无法保存，请稍后重试；已保存资料仍保留。'}, 500)

    do_GET = do_HEAD = do_POST = handle_request
