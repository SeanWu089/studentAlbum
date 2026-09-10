"""SQLite persistence for classes, student records, credentials and photos."""
import hashlib
import hmac
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


class Problem(Exception):
    def __init__(self, message, status=400):
        self.message, self.status = message, status


def clean(value, label, limit=100, required=True):
    if not isinstance(value, str) or len(value) > limit:
        raise Problem(f'{label}格式不正确，最多 {limit} 个字。')
    value = value.strip()
    if required and not value:
        raise Problem(f'请填写{label}。')
    return value


def hash_code(code, salt):
    return hashlib.scrypt(code.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()


class Store:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.directory / 'album.sqlite3'
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT OR IGNORE INTO settings VALUES('term', '');
                CREATE TABLE IF NOT EXISTS classes(
                    id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS students(
                    id TEXT PRIMARY KEY, class_id TEXT NOT NULL REFERENCES classes(id),
                    number TEXT NOT NULL, name TEXT NOT NULL, salt TEXT NOT NULL, code_hash TEXT NOT NULL,
                    request_key TEXT NOT NULL UNIQUE, origin TEXT NOT NULL DEFAULT '',
                    subject TEXT NOT NULL DEFAULT '', ability TEXT NOT NULL DEFAULT '',
                    photo BLOB, photo_name TEXT NOT NULL DEFAULT '', photo_version TEXT NOT NULL DEFAULT '',
                    created REAL NOT NULL, updated REAL NOT NULL,
                    UNIQUE(class_id, number));
                CREATE TABLE IF NOT EXISTS sessions(
                    token_hash TEXT PRIMARY KEY, student_id TEXT NOT NULL REFERENCES students(id), expires REAL NOT NULL);
            ''')
            if 'message' not in {row[1] for row in db.execute('PRAGMA table_info(students)')}:
                db.execute("ALTER TABLE students ADD COLUMN message TEXT NOT NULL DEFAULT ''")
            if 'deleted_at' not in {row[1] for row in db.execute('PRAGMA table_info(students)')}:
                db.execute('ALTER TABLE students ADD COLUMN deleted_at REAL')
            if 'deleted_at' not in {row[1] for row in db.execute('PRAGMA table_info(classes)')}:
                db.execute('ALTER TABLE classes ADD COLUMN deleted_at REAL')
        self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def classes(self):
        with self.connect() as db:
            return {'term': db.execute("SELECT value FROM settings WHERE key='term'").fetchone()[0],
                    'classes': [dict(row) for row in db.execute(
                        'SELECT id,name FROM classes WHERE deleted_at IS NULL ORDER BY created,name')]}

    def add_classes(self, data):
        term = clean(data.get('term'), '学期', 60)
        names = data.get('names', [])
        if not isinstance(names, list) or len(names) > 100:
            raise Problem('每次最多添加 100 个班级。')
        names = list(dict.fromkeys(clean(name, '班级名称', 60) for name in names))
        with self.connect() as db:
            db.execute("UPDATE settings SET value=? WHERE key='term'", (term,))
            for name in names:
                existing = db.execute('SELECT id FROM classes WHERE name=?', (name,)).fetchone()
                if existing:
                    db.execute('UPDATE classes SET deleted_at=NULL WHERE id=?', (existing['id'],))
                else:
                    db.execute('INSERT INTO classes(id,name,created,deleted_at) VALUES(?,?,?,NULL)',
                               (secrets.token_hex(16), name, time.time()))
        return self.classes()

    def _session(self, db, student_id):
        token = secrets.token_urlsafe(32)
        db.execute('DELETE FROM sessions WHERE expires < ?', (time.time(),))
        db.execute('INSERT INTO sessions VALUES(?,?,?)',
                   (hashlib.sha256(token.encode()).hexdigest(), student_id, time.time() + 86400))
        return token

    def register(self, data):
        class_id = clean(data.get('classId'), '班级', 40)
        number = clean(data.get('number'), '学号', 40)
        name = clean(data.get('name'), '姓名', 60)
        code = clean(data.get('code'), '续填口令', 6)
        request_key = clean(data.get('requestId'), '请求凭证', 80)
        if len(code) != 6 or not code.isascii() or not code.isdigit() or len(request_key) < 32:
            raise Problem('建档凭证格式不正确，请刷新后重试。')
        salt = secrets.token_hex(16)
        code_hash = hash_code(code, salt)
        now, sid = time.time(), secrets.token_hex(16)
        with self.connect() as db:
            if not db.execute('SELECT 1 FROM classes WHERE id=? AND deleted_at IS NULL', (class_id,)).fetchone():
                raise Problem('请选择老师已设置的班级。')
            existing = db.execute('SELECT * FROM students WHERE class_id=? AND number=?', (class_id, number)).fetchone()
            if existing:
                if (existing['request_key'] != request_key or existing['name'] != name or
                        not hmac.compare_digest(existing['code_hash'], hash_code(code, existing['salt']))):
                    raise Problem('这个班级的学号已建档，请使用续填口令继续，或联系老师。', 409)
                sid = existing['id']
            else:
                try:
                    db.execute('''INSERT INTO students(id,class_id,number,name,salt,code_hash,request_key,created,updated)
                                  VALUES(?,?,?,?,?,?,?,?,?)''',
                               (sid, class_id, number, name, salt, code_hash, request_key, now, now))
                except sqlite3.IntegrityError:
                    raise Problem('建档请求已处理，请使用续填口令继续。', 409)
            token = self._session(db, sid)
        return {'token': token, 'student': self.student(sid)}

    def login(self, data):
        class_id = clean(data.get('classId'), '班级', 40)
        number = clean(data.get('number'), '学号', 40)
        code = clean(data.get('code'), '续填口令', 6)
        with self.connect() as db:
            row = db.execute('SELECT * FROM students WHERE class_id=? AND number=?', (class_id, number)).fetchone()
            # Perform the same password work for unknown and known records.
            candidate = hash_code(code, row['salt'] if row else '00' * 16)
            if not row or row['deleted_at'] is not None or not hmac.compare_digest(candidate, row['code_hash']):
                raise Problem('班级、学号或续填口令不正确。', 401)
            token = self._session(db, row['id'])
        return {'token': token, 'student': self.student(row['id'])}

    def authorize(self, token):
        with self.connect() as db:
            row = db.execute('SELECT student_id FROM sessions WHERE token_hash=? AND expires>?',
                             (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()
        if not row:
            raise Problem('填写会话已过期，请用续填口令重新进入。', 401)
        return row[0]

    def students(self, sid=None, trash=False):
        with self.connect() as db:
            expired = time.time() - 30 * 86400
            db.execute('DELETE FROM sessions WHERE student_id IN (SELECT id FROM students WHERE deleted_at < ?)', (expired,))
            db.execute('DELETE FROM students WHERE deleted_at < ?', (expired,))
            db.execute('''DELETE FROM classes WHERE deleted_at IS NOT NULL
                          AND NOT EXISTS(SELECT 1 FROM students WHERE students.class_id=classes.id)''')
            rows = db.execute('''SELECT s.id,s.class_id AS classId,c.name AS className,s.number,s.name,
                s.origin,s.subject,s.ability,s.message,s.photo_name AS photoName,s.photo_version AS photoVersion,
                s.photo IS NOT NULL AS hasPhoto,s.updated AS updatedAt,s.deleted_at AS deletedAt
                FROM students s JOIN classes c ON c.id=s.class_id''' +
                (' WHERE s.deleted_at IS NOT NULL' if trash else ' WHERE s.deleted_at IS NULL AND c.deleted_at IS NULL') +
                (' AND s.id=?' if sid else '') + ' ORDER BY s.updated DESC', (sid,) if sid else ()).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item['hasPhoto'] = bool(item['hasPhoto'])
            item['complete'] = all(item[k] for k in ('origin', 'subject', 'ability', 'message', 'hasPhoto'))
            result.append(item)
        return result

    def student(self, sid):
        rows = self.students(sid)
        if not rows:
            raise Problem('档案不存在。', 404)
        return rows[0]

    def update(self, sid, data):
        if not data or any(key not in ('origin', 'subject', 'ability', 'message') for key in data):
            raise Problem('只能修改档案作答内容。')
        limits = {'origin': ('籍贯', 100), 'subject': ('科目', 80), 'ability': ('个人特点', 1000), 'message': ('想对老师说的话', 2000)}
        values = {key: clean(value, *limits[key], required=False) for key, value in data.items()}
        with self.connect() as db:
            db.execute('UPDATE students SET ' + ','.join(f'{key}=?' for key in values) + ',updated=? WHERE id=?',
                       (*values.values(), time.time(), sid))
        return {'student': self.student(sid)}

    def save_photo(self, sid, photo):
        with self.connect() as db:
            db.execute('UPDATE students SET photo=?,photo_name=?,photo_version=?,updated=? WHERE id=?',
                       (photo, '个人照片.jpg', secrets.token_hex(8), time.time(), sid))
        return {'student': self.student(sid)}

    def photo(self, sid):
        with self.connect() as db:
            row = db.execute('SELECT photo FROM students WHERE id=?', (sid,)).fetchone()
        if not row or row[0] is None:
            raise Problem('尚未上传照片。', 404)
        return row[0]

    def reset_code(self, sid):
        self.student(sid)
        code, salt = f'{secrets.randbelow(1000000):06}', secrets.token_hex(16)
        with self.connect() as db:
            db.execute('UPDATE students SET salt=?,code_hash=? WHERE id=?', (salt, hash_code(code, salt), sid))
            db.execute('DELETE FROM sessions WHERE student_id=?', (sid,))
        return {'code': code}

    def recycle(self, sid, restore=False):
        with self.connect() as db:
            row = db.execute('SELECT deleted_at FROM students WHERE id=?', (sid,)).fetchone()
            if not row:
                raise Problem('档案不存在。', 404)
            if restore and row[0] is not None and row[0] < time.time() - 30 * 86400:
                raise Problem('档案已超过 30 天保留期。', 410)
            if not restore and row[0] is not None:
                return {'ok': True}
            if restore:
                db.execute('''UPDATE classes SET deleted_at=NULL
                              WHERE id=(SELECT class_id FROM students WHERE id=?)''', (sid,))
            db.execute('UPDATE students SET deleted_at=?,updated=? WHERE id=?',
                       (None if restore else time.time(), time.time(), sid))
            db.execute('DELETE FROM sessions WHERE student_id=?', (sid,))
        return {'ok': True}

    def delete_class(self, class_id):
        class_id = clean(class_id, '班级编号', 40)
        now = time.time()
        with self.connect() as db:
            row = db.execute('SELECT name FROM classes WHERE id=? AND deleted_at IS NULL', (class_id,)).fetchone()
            if not row:
                raise Problem('班级不存在。', 404)
            total = db.execute('SELECT COUNT(*) FROM students WHERE class_id=?', (class_id,)).fetchone()[0]
            moved = db.execute('SELECT COUNT(*) FROM students WHERE class_id=? AND deleted_at IS NULL', (class_id,)).fetchone()[0]
            if total:
                db.execute('UPDATE classes SET deleted_at=? WHERE id=?', (now, class_id))
                db.execute('UPDATE students SET deleted_at=?,updated=? WHERE class_id=? AND deleted_at IS NULL',
                           (now, now, class_id))
                db.execute('DELETE FROM sessions WHERE student_id IN (SELECT id FROM students WHERE class_id=?)',
                           (class_id,))
            else:
                db.execute('DELETE FROM classes WHERE id=?', (class_id,))
        return {'ok': True, 'moved': moved}

    def restore_class(self, class_id):
        class_id = clean(class_id, '班级编号', 40)
        with self.connect() as db:
            if not db.execute('SELECT 1 FROM classes WHERE id=?', (class_id,)).fetchone():
                raise Problem('班级不存在或已超过保留期。', 404)
            restored = db.execute('SELECT COUNT(*) FROM students WHERE class_id=? AND deleted_at IS NOT NULL',
                                  (class_id,)).fetchone()[0]
            db.execute('UPDATE classes SET deleted_at=NULL WHERE id=?', (class_id,))
            db.execute('UPDATE students SET deleted_at=NULL,updated=? WHERE class_id=? AND deleted_at IS NOT NULL',
                       (time.time(), class_id))
        return {'ok': True, 'restored': restored}

    def admin_update(self, data):
        sid = clean(data.get('id'), '档案编号', 40)
        self.student(sid)
        fields = {'classId': ('班级', 40), 'number': ('学号', 40), 'name': ('姓名', 60),
                  'origin': ('籍贯', 100), 'subject': ('科目', 80), 'ability': ('个人特点', 1000), 'message': ('想对老师说的话', 2000)}
        values = {k: clean(data.get(k), *v, required=k in ('classId', 'number', 'name')) for k,v in fields.items()}
        with self.connect() as db:
            if not db.execute('SELECT 1 FROM classes WHERE id=? AND deleted_at IS NULL', (values['classId'],)).fetchone():
                raise Problem('请选择有效班级。')
            try:
                db.execute('UPDATE students SET class_id=?,number=?,name=?,origin=?,subject=?,ability=?,message=?,updated=? WHERE id=?',
                           (*values.values(), time.time(), sid))
            except sqlite3.IntegrityError:
                raise Problem('该班级已有这个学号（包括回收站），请检查后重试。', 409)
        return {'student': self.student(sid)}
