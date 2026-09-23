import http.client, io, json, threading, time, unittest, zipfile
from helpers import Fixture
from server import make_server
class ServerTests(unittest.TestCase):
    def setUp(self):
        self.f=Fixture();self.server=make_server(0,self.f.base);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.port=self.server.server_address[1];self.token=self.server.app.token
    def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join();self.f.close()
    def req(self,path,method='GET',data=None,auth=True,headers=None):
        c=http.client.HTTPConnection('127.0.0.1',self.port,timeout=10)
        h={'X-TCS-Token':self.token} if auth else {};h.update(headers or {})
        body=None
        if data is not None:body=json.dumps(data).encode();h['Content-Type']='application/json'
        c.request(method,path,body=body,headers=h);r=c.getresponse();raw=r.read();status=r.status;c.close();return status,raw
    def test_static_available(self):self.assertEqual(self.req('/',auth=False)[0],200)
    def test_auth_required(self):self.assertEqual(self.req('/api/state',auth=False)[0],403)
    def test_valid_token(self):self.assertEqual(self.req('/api/state')[0],200)
    def test_wrong_origin(self):self.assertEqual(self.req('/api/state',headers={'Origin':'https://evil.example'})[0],403)
    def test_wrong_host(self):self.assertEqual(self.req('/api/state',headers={'Host':'evil.example'})[0],403)
    def test_traversal_not_served(self):self.assertEqual(self.req('/../profile.json',auth=False)[0],404)
    def test_private_not_served(self):self.assertEqual(self.req('/.local/session.json',auth=False)[0],404)
    def test_no_generic_file_endpoint(self):self.assertEqual(self.req('/api/download?kind=../../../etc/passwd')[0],400)
    def test_explicit_install_confirmation(self):self.assertEqual(self.req('/api/install','POST',{'plan_id':'bad'})[0],400)
    def test_upload_rejects_exe(self):
        c=http.client.HTTPConnection('127.0.0.1',self.port);c.request('POST','/api/upload',body=b'MZ',headers={'X-TCS-Token':self.token,'Content-Type':'application/octet-stream','X-TCS-Filename':'evil.exe'})
        r=c.getresponse();self.assertEqual(r.status,400);r.read();c.close()
    def test_zip_upload_import(self):
        data=io.BytesIO()
        with zipfile.ZipFile(data,'w') as z:z.writestr('CHARS/test.txt','test')
        c=http.client.HTTPConnection('127.0.0.1',self.port);c.request('POST','/api/upload',body=data.getvalue(),headers={'X-TCS-Token':self.token,'Content-Type':'application/octet-stream','X-TCS-Filename':'Modern%20Overhaul.zip'})
        r=c.getresponse();self.assertEqual(r.status,200);r.read();c.close()
        for _ in range(100):
            _,raw=self.req('/api/job');j=json.loads(raw)
            if not j['running']:break
            time.sleep(.03)
        self.assertIsNone(j['error']);self.assertEqual(j['result']['guessed_module'],'modern-overhaul')
    def test_public_export(self):
        status,_=self.req('/api/export','POST',{});self.assertEqual(status,200)
        status,raw=self.req('/api/download?kind=installer');self.assertEqual(status,200);self.assertTrue(raw.startswith(b'PK'))
    def test_automation_endpoints_require_auth(self):
        for route in ('prepare','automation/start','automation/settings','nexus/connect','nxm/receive','shortcuts'):
            with self.subTest(route=route):self.assertEqual(self.req('/api/'+route,'POST',{},auth=False)[0],403)
    def test_preparation_requires_confirmation(self):self.assertEqual(self.req('/api/prepare','POST',{'game':str(self.f.game)})[0],400)
    def test_original_restore_requires_confirmation(self):self.assertEqual(self.req('/api/prepare/restore','POST',{'game':str(self.f.game)})[0],400)
    def test_stop_requests_safe_pause_during_file_job(self):
        self.server.app.job['running']=True
        self.assertEqual(self.req('/api/automation/stop','POST',{})[0],200)
        self.assertTrue(self.server.app.cancel_event.is_set())
        self.assertTrue(self.server.app.workflow.watch_paused)
        self.server.app.job['running']=False
    def test_automation_status_never_contains_api_key(self):
        self.server.app.workflow.nexus._key='synthetic-secret-not-a-real-key'
        status,body=self.req('/api/automation/status')
        self.assertEqual(status,200);self.assertNotIn(b'synthetic-secret',body)
    def test_audit_is_served_with_source_scope(self):
        status,body=self.req('/api/audit');self.assertEqual(status,200)
        self.assertIn('keine Prüfung',json.loads(body)['scope'])

    def test_diagnostics_requires_auth(self):
        self.assertEqual(self.req('/api/diagnostics',auth=False)[0],403)
    def test_diagnostic_export_has_no_session_token(self):
        code,data=self.req('/api/download?kind=diagnostics')
        self.assertEqual(code,200);self.assertNotIn(self.token.encode(),data)
        self.assertFalse(json.loads(data)['game_tested'])
    def test_settings_rejects_null_game_path(self):
        self.assertEqual(self.req('/api/settings','POST',{'game':None})[0],400)
    def test_request_body_must_be_object(self):
        self.assertEqual(self.req('/api/settings','POST',[])[0],400)
    def test_automatic_defaults_exposed_without_external_network(self):
        code,data=self.req('/api/defaults','POST',{})
        self.assertEqual(code,200);self.assertIn('games',json.loads(data))
