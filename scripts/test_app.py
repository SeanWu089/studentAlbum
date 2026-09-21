"""Integration tests use temporary databases, never the teacher's data."""
import io
import http.client
import json
from pathlib import Path
import secrets
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from PIL import Image
from storage import Store
from webserver import Application


class AlbumTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)
        self.app = Application(Path(__file__).resolve().parent.parent, self.store, {})
        self.admin = self.app.server(0)
        self.public = self.app.server(0, public=True)
        for server in (self.admin, self.public):
            threading.Thread(target=server.serve_forever, daemon=True).start()
        self.classes = self.store.add_classes({'term':'测试学期', 'names':['一班','二班']})['classes']

    def tearDown(self):
        for server in (self.admin, self.public):
            server.shutdown()
            server.server_close()
        self.store.close()
        self.temp.cleanup()

    def request(self, path, data=None, token='', admin=False, headers=None):
        server = self.admin if admin else self.public
        request_headers = {'X-Admin-Key':self.app.admin_key} if admin else {}
        if token:
            request_headers['Authorization'] = 'Bearer ' + token
        if data is not None:
            if isinstance(data, bytes):
                request_headers['Content-Type'] = 'image/jpeg'
            else:
                data = json.dumps(data).encode()
                request_headers['Content-Type'] = 'application/json'
        request_headers.update(headers or {})
        connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=10)
        connection.request('POST' if data is not None else 'GET', path, body=data, headers=request_headers)
        try:
            response = connection.getresponse()
            body = response.read()
            return response.status, json.loads(body) if 'application/json' in response.headers.get('Content-Type','') else body
        finally:
            connection.close()

    def register(self, index=0, number='001'):
        payload = {'classId':self.classes[index]['id'],'number':number,'name':'测试学生',
                   'code':'123456','requestId':secrets.token_hex(20)}
        status, result = self.request('/api/register', payload)
        self.assertEqual(status, 200, result)
        return payload, result

    def test_empty_database_and_classes(self):
        with tempfile.TemporaryDirectory() as directory:
            empty = Store(directory)
            self.assertEqual(empty.classes(), {'term':'','classes':[]})
            self.assertEqual(empty.students(), [])
            empty.close()
        status, result = self.request('/api/classes')
        self.assertEqual(status, 200)
        self.assertEqual(len(result['classes']), 2)
        status, _ = self.request('/api/admin/classes', {'term':'测试学期','names':['一班','三班']}, admin=True)
        self.assertEqual(status, 200)
        self.assertEqual(len(self.store.classes()['classes']), 3)

    def test_teacher_edit_recycle_restore_and_expiry(self):
        payload, result = self.register()
        sid, token = result['student']['id'], result['token']
        edit = dict(id=sid, classId=self.classes[1]['id'], number='002', name='修改姓名',
                    origin='浙江', subject='语文', ability='观察', message='期待新学期')
        self.assertEqual(self.request('/api/admin/edit', edit)[0], 404)
        status, saved = self.request('/api/admin/edit', edit, admin=True)
        self.assertEqual(status, 200)
        self.assertEqual(saved['student']['classId'], self.classes[1]['id'])
        self.assertEqual(saved['student']['message'], '期待新学期')
        self.assertEqual(self.request('/api/admin/delete', {'id':sid}, admin=True)[0], 200)
        self.assertEqual(self.store.students(), [])
        self.assertEqual(len(self.store.students(trash=True)), 1)
        self.assertEqual(self.request('/api/student', token=token)[0], 401)
        self.assertEqual(self.request('/api/login', dict(classId=edit['classId'],number='002',code=payload['code']))[0], 401)
        self.assertEqual(self.request('/api/admin/restore', {'id':sid}, admin=True)[0], 200)
        self.assertEqual(self.store.student(sid)['name'], '修改姓名')
        self.assertEqual(self.request('/api/login', dict(classId=edit['classId'],number='002',code=payload['code']))[0], 200)
        self.store.recycle(sid)
        with self.store.connect() as db:
            db.execute('UPDATE students SET deleted_at=1 WHERE id=?', (sid,))
        self.assertEqual(self.store.students(trash=True), [])

    def test_delete_class_moves_students_and_restores_them_as_a_group(self):
        first_payload, first = self.register(0, '001')
        _, second = self.register(0, '002')
        class_id = first_payload['classId']
        self.assertEqual(self.request('/api/admin/delete-class', {'id':class_id})[0], 404)
        status, result = self.request('/api/admin/delete-class', {'id':class_id}, admin=True)
        self.assertEqual(status, 200)
        self.assertEqual(result['moved'], 2)
        self.assertNotIn(class_id, [item['id'] for item in self.store.classes()['classes']])
        self.assertEqual(self.store.students(), [])
        self.assertEqual({item['id'] for item in self.store.students(trash=True)},
                         {first['student']['id'], second['student']['id']})
        self.assertEqual(self.request('/api/student', token=first['token'])[0], 401)
        status, restored = self.request('/api/admin/restore-class', {'id':class_id}, admin=True)
        self.assertEqual(status, 200)
        self.assertEqual(restored['restored'], 2)
        self.assertIn(class_id, [item['id'] for item in self.store.classes()['classes']])
        self.assertEqual(len(self.store.students()), 2)
        empty_class = self.classes[1]['id']
        status, result = self.request('/api/admin/delete-class', {'id':empty_class}, admin=True)
        self.assertEqual(status, 200)
        self.assertEqual(result['moved'], 0)
        with self.store.connect() as db:
            self.assertIsNone(db.execute('SELECT 1 FROM classes WHERE id=?', (empty_class,)).fetchone())

    def test_save_photo_teacher_and_restart(self):
        payload, result = self.register()
        token, sid = result['token'], result['student']['id']
        status, result = self.request('/api/student', {'origin':'浙江','subject':'数学','ability':'认真观察','message':'希望多交流'}, token)
        self.assertEqual(status, 200)
        self.assertFalse(result['student']['complete'])
        photo = io.BytesIO()
        Image.new('RGB',(24,24),'green').save(photo,'PNG')
        status, result = self.request('/api/student/photo', photo.getvalue(), token)
        self.assertEqual(status, 200, result)
        self.assertTrue(result['student']['complete'])
        status, overview = self.request('/api/admin/overview', admin=True)
        self.assertEqual(overview['students'][0]['origin'], '浙江')
        self.assertTrue(overview['students'][0]['hasPhoto'])
        status, saved_photo = self.request('/api/admin/photos/' + sid, admin=True)
        self.assertEqual(status, 200)
        self.assertTrue(saved_photo.startswith(b'\xff\xd8'))
        reopened = Store(self.temp.name)
        login = reopened.login({'classId':payload['classId'],'number':'001','code':'123456'})
        self.assertEqual(login['student']['ability'], '认真观察')
        self.assertTrue(login['student']['complete'])
        self.assertEqual(reopened.photo(sid), saved_photo)
        with reopened.connect() as db:
            row = db.execute('SELECT salt,code_hash FROM students').fetchone()
            self.assertNotEqual(row[1], '123456')
            self.assertNotIn('code_hash', json.dumps(overview))
        reopened.close()

    def test_snapshots_restore_complete_database_and_keep_latest_thirty(self):
        payload, result = self.register()
        sid, token = result['student']['id'], result['token']
        self.request('/api/student', {'origin':'原来的籍贯'}, token)
        original = self.store.flush_snapshot('自动保存')
        self.assertIsNotNone(original)
        edit = dict(id=sid, classId=payload['classId'], number='001', name='后来修改',
                    origin='新的籍贯', subject='', ability='', message='')
        self.assertEqual(self.request('/api/admin/edit', edit, admin=True)[0], 200)
        status, restored = self.request('/api/admin/restore-snapshot', {'id':original['id']}, admin=True)
        self.assertEqual(status, 200, restored)
        self.assertEqual(self.store.student(sid)['name'], '测试学生')
        self.assertEqual(self.store.student(sid)['origin'], '原来的籍贯')
        self.assertEqual(self.request('/api/student', token=token)[0], 401)
        reasons = [item['reason'] for item in self.store.snapshots()['items']]
        self.assertIn('恢复前', reasons)
        self.store.snapshot_limit = 3
        for index in range(5):
            self.store.create_snapshot(f'测试 {index}')
        self.assertEqual(len(self.store.snapshots()['items']), 3)

    def test_duplicate_idempotent_registration_and_class_scope(self):
        payload, result = self.register()
        self.assertEqual(self.request('/api/register', payload)[0], 200)
        self.assertEqual(len(self.store.students()), 1)
        altered = dict(payload, requestId=secrets.token_hex(20))
        self.assertEqual(self.request('/api/register', altered)[0], 409)
        self.register(1)
        self.assertEqual(len(self.store.students()), 2)

    def test_isolation_and_bad_credentials(self):
        payload, result = self.register()
        for path in ('/api/admin/bootstrap','/api/admin/overview','/admin.html','/.git/config','/data/album.sqlite3','/../README.md'):
            self.assertEqual(self.request(path)[0], 404, path)
        self.assertEqual(self.request('/api/student')[0], 401)
        self.assertEqual(self.request('/api/student/photo')[0], 401)
        self.assertEqual(self.request('/api/login', {'classId':payload['classId'],'number':'001','code':'000000'})[0], 401)
        self.assertEqual(self.request('/api/student', {'classId':self.classes[1]['id']}, result['token'])[0], 400)
        self.assertEqual(self.request('/api/admin/overview', admin=True, headers={'Origin':'https://evil.invalid'})[0], 403)
        self.assertEqual(self.request('/api/admin/bootstrap', admin=True, headers={'Host':'evil.invalid'})[0], 403)
        self.assertEqual(self.request('/api/admin/classes', {'term':'bad','names':[]}, admin=True, headers={'X-Admin-Key':''})[0], 401)

    def test_invalid_upload_and_reset_code(self):
        payload, result = self.register()
        self.assertEqual(self.request('/api/student/photo', b'<svg>not a photo</svg>', result['token'])[0], 400)
        self.assertFalse(self.store.student(result['student']['id'])['hasPhoto'])
        status, reset = self.request('/api/admin/reset-code', {'id':result['student']['id']}, admin=True)
        self.assertEqual(status, 200)
        self.assertEqual(self.request('/api/student', token=result['token'])[0], 401)
        self.assertEqual(self.request('/api/login', {'classId':payload['classId'],'number':'001','code':reset['code']})[0], 200)

    def test_guess_rate_limit(self):
        payload, _ = self.register()
        for _ in range(9):
            self.assertEqual(self.request('/api/login', {'classId':payload['classId'],'number':'001','code':'000000'})[0], 401)
        self.assertEqual(self.request('/api/login', {'classId':payload['classId'],'number':'001','code':'000000'})[0], 429)


if __name__ == '__main__':
    unittest.main()
