"""Testes da versão publicável (protótipo estático e PWA).

Rodar:  python3 -m unittest tests.test_publicacao -v
Gera o protótipo, serve como site estático (inclusive numa subpasta) e confere o que um visitante encontra.
"""
import functools
import http.server
import json
import re
import subprocess
import sys
import threading
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PROTO = RAIZ / "prototipo"


class Silencioso(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def servir(pasta):
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Silencioso, directory=str(pasta)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


class TestPublicacao(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run([sys.executable, str(RAIZ / "ferramentas" / "gerar_prototipo.py")], check=True, capture_output=True)
        cls.raiz = servir(RAIZ)    # protótipo em /prototipo/ (como GitHub Pages de projeto)
        cls.proto = servir(PROTO)  # protótipo na raiz (como Netlify)
        from playwright.sync_api import sync_playwright
        cls.pw = sync_playwright().start()
        cls.b = cls.pw.chromium.launch(args=["--host-resolver-rules=MAP agora.test 127.0.0.1"])

    @classmethod
    def tearDownClass(cls):
        cls.b.close()
        cls.pw.stop()
        for srv in (cls.raiz, cls.proto):
            srv.shutdown()
            srv.server_close()

    def test_01_paginas_legais_sem_lacunas(self):
        for nome in ("privacidade.html", "termos.html", "excluir-conta.html"):
            html = (PROTO / nome).read_text(encoding="utf-8")
            self.assertNotRegex(html, r"\[[A-ZÁÉÍÓÚ ]{3,}", f"{nome}: campo entre colchetes")
            self.assertNotIn("{{", html)
            self.assertIn("mailto:", html)
        self.assertIn("CRP-04/65709", (PROTO / "privacidade.html").read_text(encoding="utf-8"))
        self.assertIn("188", (PROTO / "privacidade.html").read_text(encoding="utf-8"))
        md = (RAIZ / "PRIVACIDADE.md").read_text(encoding="utf-8")  # política pública do app Android (link padrão)
        self.assertNotIn("{{", md)
        sys.path.insert(0, str(RAIZ / "server"))
        from config import Config
        self.assertIn(Config().contato_publico, md, "mesmo contato do app")
        for trecho in ("CRP-04/65709", "Notificações", "não tem anúncios".replace("não tem", "**não** tem"), "188", "18 anos"):
            self.assertIn(trecho, md)

    def test_02_links_relativos_e_noindex(self):
        for arq in PROTO.rglob("*.html"):
            html = arq.read_text(encoding="utf-8")
            absolutos = re.findall(r'(?:href|src)="(/[^/"][^"]*)"', html)
            self.assertEqual(absolutos, [], f"{arq.name}: caminho absoluto quebra em subpasta")
            self.assertIn('name="robots" content="noindex"', html, arq.name)

    def test_03_pwa_instalavel_e_offline_em_subpasta(self):
        ctx = self.b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True)
        pg = ctx.new_page()
        erros, externos = [], []
        pg.on("pageerror", lambda e: erros.append(str(e)))
        pg.on("request", lambda r: not r.url.startswith(("http://127.0.0.1", "data:", "blob:")) and externos.append(r.url))
        base = f"http://127.0.0.1:{self.raiz.server_port}/prototipo/app/index.html"
        pg.goto(base)
        pg.wait_for_selector(".now")
        man = pg.evaluate("fetch(document.querySelector('link[rel=manifest]').href).then(r => r.json())")
        self.assertEqual((man["display"], man["start_url"], man["scope"]), ("standalone", "./index.html", "./"))
        self.assertTrue(any(i.get("purpose") == "maskable" and i["sizes"] == "512x512" for i in man["icons"]))
        for ic in man["icons"]:
            st = pg.evaluate(f"fetch(new URL({json.dumps(ic['src'])}, document.querySelector('link[rel=manifest]').href)).then(r => r.status)")
            self.assertEqual(st, 200, ic["src"])
        self.assertEqual(pg.evaluate("fetch('apple-touch-icon.png').then(r => r.status)"), 200)
        pg.evaluate("navigator.serviceWorker.ready.then(() => true)")
        pg.reload()
        pg.wait_for_selector(".now")
        self.assertTrue(pg.evaluate("!!navigator.serviceWorker.controller"), "service worker controla a página")
        ctx.set_offline(True)
        pg.reload()
        pg.wait_for_selector(".now", timeout=10000)
        pg.click("[data-go=diario]")
        self.assertGreater(pg.locator("main").inner_text().__len__(), 50, "app abre e navega sem internet")
        ctx.set_offline(False)
        ctx.close()
        self.assertEqual(erros, [])
        self.assertEqual(externos, [], "nenhum pedido para fora do site")

    def test_04_boas_vindas_em_endereco_publico(self):
        ctx = self.b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True)
        pg = ctx.new_page()
        pg.goto(f"http://agora.test:{self.proto.server_port}/app/index.html")
        pg.wait_for_selector(".sheet:has-text('Bem-vindo ao Agora')")
        pg.fill("#nn", "Bia")
        pg.fill("#nd", "responder o RH\nmarcar dentista")
        pg.click(".sheet #ok")
        pg.wait_for_selector(".now")
        self.assertIn("responder o RH", pg.locator(".now").inner_text())
        pg.reload()
        pg.wait_for_selector(".now")
        self.assertEqual(pg.evaluate("S.tasks.length"), 2, "o que a pessoa escreveu fica salvo")
        self.assertEqual(pg.locator(".sheet:has-text('Bem-vindo')").count(), 0, "boas-vindas só na primeira vez")
        ctx.close()
        ctx = self.b.new_context(viewport={"width": 390, "height": 844})
        pg = ctx.new_page()
        pg.goto(f"http://agora.test:{self.proto.server_port}/app/index.html")
        pg.wait_for_selector("#exemplo")
        pg.click("#exemplo")
        self.assertEqual(pg.locator(".banner:has-text('Dados de exemplo')").count(), 1, "exemplo a um toque")
        ctx.close()

    def test_05_vitrine_e_site(self):
        pg = self.b.new_page(viewport={"width": 390, "height": 844})
        base = f"http://127.0.0.1:{self.proto.server_port}/"
        pg.goto(base + "app/index.html#servicos")
        pg.wait_for_selector(".svc")
        self.assertEqual(pg.locator(".svc").count(), 9, "app: só a linha Para você")
        self.assertEqual(pg.locator(".svc a[href^='mailto:']").count(), 9)
        for pag in ("index.html", "comecar.html", "servicos.html", "privacidade.html", "termos.html", "excluir-conta.html", "app/pro.html"):
            r = pg.goto(base + pag)
            self.assertEqual(r.status, 200, pag)
            self.assertLessEqual(pg.evaluate("document.documentElement.scrollWidth"), 390, f"{pag}: rolagem lateral")
            for href in pg.evaluate("[...document.querySelectorAll('a[href]')].map(a => a.href).filter(h => h.startsWith(location.origin))"):
                self.assertEqual(pg.request.get(href.split("#")[0]).status, 200, f"link quebrado em {pag}: {href}")
        pg.close()

    def test_06_android_sem_servidor(self):
        # build da Play sem AGORA_API_URL: nada de conta, planos ou vínculo; vitrine só com atendimento e e-mail
        www = RAIZ / "android" / "www"
        subprocess.run([sys.executable, str(RAIZ / "android" / "preparar-www.py")], check=True, capture_output=True)
        self.assertNotIn("api", (www / "config.js").read_text(encoding="utf-8").split("AGORA_CONFIG = ")[1].split('"privacidade"')[0])
        for fora in ("pro.html", "admin.html", "checkout-simulado.html", "sw.js"):
            self.assertFalse((www / fora).exists(), fora)
        man = (RAIZ / "android" / "android" / "app" / "src" / "main" / "AndroidManifest.xml").read_text(encoding="utf-8")
        self.assertIn('android.permission.SCHEDULE_EXACT_ALARM" tools:node="remove"', man, "sem alarme exato (evita declaração na Play)")
        self.assertIn("isExactNotification: false", (RAIZ / "app" / "index.html").read_text(encoding="utf-8"))
        srv = servir(www)
        try:
            ctx = self.b.new_context(viewport={"width": 360, "height": 740}, is_mobile=True)
            pg = ctx.new_page()
            erros, externos = [], []
            pg.on("pageerror", lambda e: erros.append(str(e)))
            pg.on("request", lambda r: not r.url.startswith(("http://agora.test", "data:", "blob:")) and externos.append(r.url))
            pg.goto(f"http://agora.test:{srv.server_port}/index.html")
            pg.wait_for_selector("#exemplo")
            pg.click("#exemplo")
            pg.click("[data-go=mais]")
            for sec in ("#sec-conta", "#sec-planos", "#sec-vinculo"):
                self.assertEqual(pg.locator(sec).count(), 0, f"{sec} não aparece sem servidor no Android")
            texto = pg.locator("main").inner_text()
            for proibido in ("Assinar", "Assinaturas", "Plus", "Pix", "cartão"):
                self.assertNotIn(proibido, texto, f"Android sem venda de digital: {proibido}")
            href = pg.get_attribute("main a:has-text('Política de privacidade')", "href")
            self.assertEqual(href, "https://github.com/Ridd1kulusC0d3r/tdah/blob/main/PRIVACIDADE.md", "link padrão público")
            pg.click("[data-act=servicos]")
            pg.wait_for_selector(".svc")
            ids = pg.evaluate("[...document.querySelectorAll('.svc')].map(e => e.id)")
            self.assertEqual(sorted(ids), ["svc-aula", "svc-opc", "svc-terapia"], "só atendimento 1:1 e aula aberta")
            self.assertEqual(pg.locator(".svc a[href^='mailto:']").count(), 3)
            self.assertLessEqual(pg.evaluate("document.documentElement.scrollWidth"), 360)
            ctx.close()
            self.assertEqual(erros, [])
            self.assertEqual(externos, [], "nenhum pedido para fora do app")
        finally:
            srv.shutdown()
            srv.server_close()

    def test_07_kit_da_play(self):
        T = RAIZ / "play" / "textos"
        limites = {"titulo.txt": 30, "descricao-curta.txt": 80, "descricao-completa.txt": 4000}
        notas = (T / "novidades.txt").read_text(encoding="utf-8")
        self.assertLessEqual(len(notas.split("<pt-BR>")[1].split("</pt-BR>")[0].strip()), 500, "notas da versão")
        for nome, lim in limites.items():
            texto = (T / nome).read_text(encoding="utf-8")
            self.assertLessEqual(len(texto), lim, nome)
        desc = (T / "descricao-completa.txt").read_text(encoding="utf-8")
        self.assertIn("não é um dispositivo médico", desc.lower(), "aviso exigido pela política de apps de saúde")
        self.assertIn("188", desc)
        for vetada in ("cura", "garant", "comprovad", "melhor app", "100%"):
            self.assertNotIn(vetada, desc.lower().replace("trata, cura nem previne", ""), vetada)
        I = RAIZ / "play" / "imagens"
        def tamanho(f):  # lê largura e altura sem bibliotecas: PNG (IHDR) e JPEG (SOF)
            b = f.read_bytes()
            if b[:8] == b"\x89PNG\r\n\x1a\n":
                return int.from_bytes(b[16:20], "big"), int.from_bytes(b[20:24], "big")
            i = 2
            while i < len(b):
                m, n = b[i + 1], int.from_bytes(b[i + 2:i + 4], "big")
                if m in (0xC0, 0xC2):
                    return int.from_bytes(b[i + 7:i + 9], "big"), int.from_bytes(b[i + 5:i + 7], "big")
                i += 2 + n
        self.assertEqual(tamanho(I / "icone-512.png"), (512, 512))
        self.assertEqual(tamanho(I / "destaque-1024x500.jpg"), (1024, 500))
        caps = sorted(I.glob("celular-*.jpg"))
        self.assertGreaterEqual(len(caps), 2)
        for c in caps:
            self.assertEqual(tamanho(c), (1080, 1920), c.name)


if __name__ == "__main__":
    unittest.main()
