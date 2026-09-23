import json
import unittest
from unittest.mock import patch
from helpers import Fixture
from server import App
from workflow import automatic_roots
from safety import BuildError

class MappingTests(unittest.TestCase):
    def test_one_main_root(self):self.assertEqual(automatic_roots(['Data'],'main'),['Data'])
    def test_multiple_main_roots_need_review(self):self.assertEqual(automatic_roots(['A','B'],'main'),[])
    def test_classic_needs_icon_choice(self):self.assertEqual(automatic_roots(['Common'],'classic'),[])
    def test_common_and_classic(self):self.assertEqual(automatic_roots(['Common','Classic Icons','Modern Icons'],'classic'),['Common','Classic Icons'])
    def test_two_classic_variants_need_review(self):self.assertEqual(automatic_roots(['Common','Classic Icons A','Classic Icons B'],'classic'),[])
    def test_optional_not_selected(self):self.assertEqual(automatic_roots(['Optional/Film Accurate'],'main'),[])

class WorkflowTests(unittest.TestCase):
    def setUp(self):self.f=Fixture();self.app=App(self.f.base);self.w=self.app.workflow
    def tearDown(self):self.f.close()
    def test_optional_modules_off_by_default(self):
        self.assertFalse(self.w.engine.state['selections']['ep3-additions']['enabled']);self.assertFalse(self.w.engine.state['selections']['infinities-vader-patch']['enabled'])
    def test_automation_never_armed_by_default(self):self.assertFalse(self.w.public()['automation']['armed'])
    def test_no_silent_tool_download(self):
        with self.assertRaises(BuildError):self.w.tool_consent()
    def test_restart_does_not_resume_write_permission(self):
        self.w.engine.state['automation']['armed']=True;self.w.engine.save();again=App(self.f.base)
        self.assertFalse(again.workflow.public()['automation']['armed'])
    def test_explicit_mapping_consent_required(self):
        path=self.f.root/'Lego Star Wars The Complete Saga Modern Overhaul';(path/'CHARS').mkdir(parents=True);(path/'CHARS/a.txt').write_text('a')
        r=self.w.import_data(str(path),log=lambda _:None)
        self.assertFalse(r['auto_mapping_accepted'])
    def test_approved_unique_mapping(self):
        self.w.configure({'auto_mapping':True})
        path=self.f.root/'Lego Star Wars The Complete Saga Modern Overhaul';(path/'CHARS').mkdir(parents=True);(path/'CHARS/a.txt').write_text('a')
        r=self.w.import_data(str(path),log=lambda _:None)
        self.assertTrue(r['auto_mapping_accepted']);self.assertFalse(r['authenticity_verified'])
    def test_unknown_variant_not_auto_confirmed(self):
        self.w.configure({'auto_mapping':True})
        path=self.f.root/'Additional Levels';(path/'CHARS').mkdir(parents=True);(path/'CHARS/a.txt').write_text('a')
        r=self.w.import_data(str(path),log=lambda _:None)
        self.assertFalse(r['auto_mapping_accepted'])
    def test_queue_limited(self):
        for i in range(10):self.w.receive_nxm('nxm://legostarwarsthecompletesaga/mods/54/files/583')
        with self.assertRaises(BuildError):self.w.receive_nxm('nxm://legostarwarsthecompletesaga/mods/54/files/583')
    def test_signed_url_not_in_public_state(self):
        self.w.receive_nxm('nxm://legostarwarsthecompletesaga/mods/54/files/583?key=secret&expires=9999999999')
        self.assertNotIn('secret',json.dumps(self.w.public()))
    def test_failed_preparation_disarms_automation(self):
        self.w.engine.state['options']['clean_target_confirmed']=True
        self.w.configure({'allow_tools':True})
        with patch('workflow.require_windows'),patch.object(self.w,'prepare',side_effect=BuildError('simulated download failure')):
            with self.assertRaises(BuildError):self.w.arm('PREPARE_AND_INSTALL',lambda _:None)
        self.assertFalse(self.w.engine.state['automation']['armed'])
    def test_wrong_start_confirmation_does_not_arm(self):
        with patch('workflow.require_windows'):
            with self.assertRaises(BuildError):self.w.arm('wrong',lambda _:None)
        self.assertFalse(self.w.engine.state['automation']['armed'])
