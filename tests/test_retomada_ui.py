"""Real-browser regression tests for resumption, reduced plans and patient-authored summaries.
Run: python -m unittest tests.test_retomada_ui -v
Optional: AGORA_CHROMIUM_EXECUTABLE=/usr/bin/chromium
"""
import os
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'server'))
import server
from config import Config


class RetomadaUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.srv = ThreadingHTTPServer(('127.0.0.1', 0), server.cria_handler(server.API(
            server.Banco(str(Path(cls.tmp.name) / 'db.sqlite')), Config(ambiente='desenvolvimento', agendador=False))))
        cls.url = f'http://127.0.0.1:{cls.srv.server_address[1]}'
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(executable_path=os.environ.get('AGORA_CHROMIUM_EXECUTABLE'))

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.tmp.cleanup()

    def setUp(self):
        self.ctx = self.browser.new_context(viewport={'width': 390, 'height': 844}, reduced_motion='reduce')
        self.pg = self.ctx.new_page()
        self.errors = []
        self.pg.on('pageerror', lambda e: self.errors.append(str(e)))
        self.pg.goto(self.url + '/app/')
        self.pg.wait_for_selector('.now')
        self.pg.evaluate("""() => {
          S = vazio('Pessoa de teste');
          S.tasks = [{id:'t', title:'Ler um capítulo', steps:[], type:'estudo', energy:'media', priority:'alta', done:false, created:hoje()}];
          S.courses = [{id:'c', name:'Curso teste', done:2, total:8, priority:'media', created:hoje()}];
          lsSet(S); go('agora');
        }""")

    def tearDown(self):
        self.assertEqual(self.errors, [])
        self.ctx.close()

    def finish(self, choice='avancei'):
        self.pg.evaluate('FOCO.end = Date.now(); tick()')
        self.pg.wait_for_selector('#fProx')
        self.pg.fill('#fAvanco', 'Li até a página 12 <img src=x onerror=alert(1)>')
        self.pg.fill('#fMaterial', 'apostila.pdf, página 12')
        self.pg.fill('#fProx', 'Escrever uma pergunta')
        self.pg.click(f'[data-fim={choice}]')
        self.pg.wait_for_timeout(250)

    def test_task_resume_persists_without_duplicate_steps(self):
        self.pg.click('[data-act=focus]')
        self.finish()
        self.assertIn('apostila.pdf, página 12', self.pg.locator('.resume-context').inner_text())
        self.assertEqual(self.pg.locator('.resume-context img').count(), 0)
        self.pg.reload()
        self.pg.wait_for_selector('.resume-context')
        self.assertIn('Escrever uma pergunta', self.pg.locator('.resume-context').inner_text())
        self.pg.click('[data-act=focus]')
        self.finish()
        self.assertEqual(self.pg.evaluate('S.tasks[0].steps.length'), 0)
        self.assertFalse(self.pg.evaluate('S.tasks[0].done'))
        self.pg.click('[data-act=done]')
        self.assertFalse(self.pg.evaluate("'parou' in S.tasks[0]"))

    def test_course_resume_and_summary_with_lessons_already_done(self):
        self.pg.evaluate("S.tasks=[]; S.courses[0].pin=true; go('agora')")
        self.pg.click('[data-act=focus]')
        self.finish()
        self.assertIn('página 12', self.pg.locator('.resume-context').inner_text())
        self.pg.evaluate("go('preparo')")
        self.assertIn('Curso teste', self.pg.locator('#prevPrep').input_value())
        self.pg.evaluate("go('agora')")
        self.pg.click('[data-act=done]')
        self.assertEqual(self.pg.evaluate('S.courses[0].done'), 3)
        self.assertFalse(self.pg.evaluate("'parou' in S.courses[0]"))

    def test_small_step_preserves_task_and_default_duration(self):
        self.pg.click('[data-act=small]')
        self.pg.fill('#smPasso', '')
        self.pg.click('#smIniciar')
        self.assertEqual(self.pg.locator('#smPasso').count(), 1)
        self.pg.fill('#smPasso', 'Abrir o livro')
        self.pg.click('#smIniciar')
        self.assertEqual(self.pg.evaluate('FOCO.total'), 120)
        self.assertEqual(self.pg.evaluate('S.settings.focusMin'), 25)
        self.finish('feita')
        self.assertFalse(self.pg.evaluate('S.tasks[0].done'))
        self.assertEqual(self.pg.evaluate('S.sessions.at(-1).fim'), 'passo')
        self.assertEqual(self.pg.evaluate('S.sessions.at(-1).min'), 2)

    def test_small_routine_preserves_original_and_marks_partial(self):
        self.pg.evaluate("""S.routines=[{id:'r',name:'Arrumar a mesa',steps:[{t:'Separar livro',min:2},{t:'Guardar papéis',min:3}]}]; sheetRotinaMenor(S.routines[0]);""")
        self.pg.click('#srIniciar')
        self.pg.click('#rNext')
        self.assertEqual(self.pg.evaluate('S.routines[0].steps.length'), 2)
        self.assertEqual(self.pg.evaluate('S.routineRuns[0].done'), 1)
        self.assertEqual(self.pg.evaluate('S.routineRuns[0].total'), 2)
        self.assertTrue(self.pg.evaluate('S.routineRuns[0].reduzida'))

    def test_summary_manual_edits_export_and_privacy(self):
        self.pg.evaluate("go('preparo')")
        self.assertFalse(self.pg.locator('[data-prep-incl=bem]').is_checked())
        self.pg.fill('#pr1', 'Rascunho privado')
        self.pg.fill('#prevPrep', 'Só quero compartilhar esta frase.')
        self.pg.wait_for_timeout(250)
        self.pg.reload()
        self.pg.wait_for_selector('#prevPrep')
        self.assertEqual(self.pg.locator('#prevPrep').input_value(), 'Só quero compartilhar esta frase.')
        self.assertFalse(self.pg.evaluate("'preparo' in snapshot()"))
        with self.pg.expect_download() as info:
            self.pg.click('#prBaixar')
        self.assertEqual(Path(info.value.path()).read_text(), 'Só quero compartilhar esta frase.')
        self.pg.check('[data-prep-incl=bem]')
        self.assertTrue(self.pg.locator('#prBaixar').is_disabled())
        self.assertEqual(self.pg.locator('#prevPrep').input_value(), 'Só quero compartilhar esta frase.')
        self.pg.click('#prGerar')
        self.pg.click('.sheet [data-close]')
        self.assertEqual(self.pg.locator('#prevPrep').input_value(), 'Só quero compartilhar esta frase.')
        self.pg.click('#prGerar')
        self.pg.click('#prConfirmarGerar')
        self.assertIn('BEM-ESTAR', self.pg.locator('#prevPrep').input_value())
        self.assertFalse(self.pg.locator('#prBaixar').is_disabled())
        self.assertLessEqual(self.pg.evaluate('document.documentElement.scrollWidth'), 390)

    def test_explicit_send_uses_edited_text_and_cancel_sends_nothing(self):
        self.pg.evaluate("API=location.origin; S.link={token:'test',pro:'Profissional exemplo'}; go('preparo')")
        self.pg.fill('#prevPrep', 'Texto revisado')
        sent = []
        def accept(route):
            sent.append(route.request.post_data_json)
            route.fulfill(status=200, content_type='application/json', body='{"ok":true}')
        self.pg.route('**/api/paciente/preparo', accept)
        self.pg.click('#prEnviar')
        self.pg.click('.sheet [data-close]')
        self.assertEqual(sent, [])
        self.pg.click('#prEnviar')
        self.pg.click('#prConfirmarEnvio')
        self.pg.wait_for_selector('.toast:has-text("Enviado")')
        self.assertEqual(sent, [{'texto':'Texto revisado'}])

    def test_cloud_restore_keeps_local_draft(self):
        self.pg.evaluate("prep().atrapalhou='Só neste aparelho'; S.link={token:'test'}; API=location.origin; nuvemRestaurar(false)")
        self.pg.route('**/api/nuvem', lambda route: route.fulfill(status=200, content_type='application/json', body=self.pg.evaluate("JSON.stringify({dados:vazio(),versao:2})")))
        self.pg.click('.sheet #ok')
        self.pg.wait_for_selector('.toast:has-text("Seus dados voltaram")')
        self.assertEqual(self.pg.evaluate('S.preparo.atrapalhou'), 'Só neste aparelho')


if __name__ == '__main__':
    unittest.main()
