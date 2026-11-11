"""Testes com a API do Instagram simulada. Rodar: python -m pytest -q"""
import json
from datetime import datetime, timedelta, timezone

import pytest
from PIL import Image

from jn import fila, instagram, painel, publicar


class Resp:
    def __init__(self, dados, status=200):
        self._d, self.status_code, self.text = dados, status, json.dumps(dados)

    def json(self):
        return self._d


class FakeHTTP:
    """Simula graph.instagram.com e registra as chamadas."""

    def __init__(self, falhar_publish=False):
        self.chamadas, self.n, self.falhar = [], 0, falhar_publish

    def get(self, url, params=None, timeout=None):
        self.chamadas.append(("GET", url, params))
        if url.endswith("/me/accounts"):
            return Resp({"data": [{"id": "PG", "access_token": "PAGETOK", "instagram_business_account": {"id": "999"}}]})
        if url.endswith("/me"):
            return Resp({"user_id": "999", "username": "jn_.higienizacao"})
        return Resp({"status_code": "FINISHED"})

    def post(self, url, data=None, timeout=None):
        self.chamadas.append(("POST", url, data))
        if "/PG/" in url:
            return Resp({"id": "FB_" + url.rsplit("/", 1)[1], "post_id": "PG_POST"})
        if url.endswith("media_publish"):
            if self.falhar:
                return Resp({"error": {"message": "Token inválido"}}, 400)
            return Resp({"id": "MEDIA123"})
        self.n += 1
        return Resp({"id": f"C{self.n}"})


@pytest.fixture
def raiz(tmp_path, monkeypatch):
    monkeypatch.setattr(fila, "RAIZ", tmp_path)
    monkeypatch.setattr(fila, "CONTEUDO", tmp_path / "conteudo")
    monkeypatch.setattr(fila, "PUBLICADO", tmp_path / "publicado")
    monkeypatch.setenv("MIDIA_BASE_URL", "https://jn.github.io/jn-robo/midia")
    monkeypatch.setenv("IG_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("IG_USER_ID", "")
    monkeypatch.setattr(publicar, "midia_no_ar", lambda u: True)
    return tmp_path


def criar(raiz, nome, tipo="post", arquivos=("01.jpg",), aprovado=True, minutos=-5):
    p = raiz / "conteudo" / nome
    p.mkdir(parents=True)
    for a in arquivos:
        if a.endswith(".jpg"):
            Image.new("RGB", (1080, 1350), "blue").save(p / a)
        else:
            (p / a).write_bytes(b"\0")
    quando = datetime.now(timezone.utc) + timedelta(minutes=minutos)
    it = fila.Item(p, {"tipo": tipo, "publicar_em": quando.isoformat(), "legenda": "Oi #juazeirodonorte",
                       "arquivos": list(arquivos), "aprovado": aprovado})
    it.salvar()
    return it


def usar_fake(monkeypatch, fake):
    orig = instagram.Instagram.__init__

    def init(self, token, ig_user_id=None, sessao=None):
        orig(self, token, ig_user_id, sessao=fake)

    monkeypatch.setattr(instagram.Instagram, "__init__", init)


def test_publica_somente_aprovado_e_no_horario(raiz, monkeypatch):
    criar(raiz, "a-pronto")
    criar(raiz, "b-nao-aprovado", aprovado=False)
    criar(raiz, "c-futuro", minutos=120)
    fake = FakeHTTP()
    usar_fake(monkeypatch, fake)
    assert publicar.main([]) == 0
    assert (raiz / "publicado" / "a-pronto").exists()
    assert (raiz / "conteudo" / "b-nao-aprovado").exists()
    assert (raiz / "conteudo" / "c-futuro").exists()
    dados = json.loads((raiz / "publicado" / "a-pronto" / "post.json").read_text())
    assert dados["media_id"] == "MEDIA123"
    criou = [c for c in fake.chamadas if c[0] == "POST" and c[1].endswith("/999/media")][0]
    assert criou[2]["image_url"] == "https://jn.github.io/jn-robo/midia/a-pronto/01.jpg"
    assert criou[1].startswith("https://graph.facebook.com/")
    fila_md = (raiz / "FILA.md").read_text()
    assert "aguardando aprovação" in fila_md and "publicado" in fila_md


def test_carrossel_cria_filhos_e_container(raiz, monkeypatch):
    criar(raiz, "carro", tipo="carrossel", arquivos=("01.jpg", "02.jpg", "03.jpg"))
    fake = FakeHTTP()
    usar_fake(monkeypatch, fake)
    publicar.main([])
    posts = [c[2] for c in fake.chamadas if c[0] == "POST" and c[1].endswith("/media")]
    assert sum(1 for p in posts if p.get("is_carousel_item") == "true") == 3
    assert posts[-1]["media_type"] == "CAROUSEL" and posts[-1]["children"] == "C1,C2,C3"


def test_reel_e_story(raiz, monkeypatch):
    criar(raiz, "reel", tipo="reel", arquivos=("01.mp4",))
    criar(raiz, "story", tipo="story", arquivos=("01.jpg",))
    fake = FakeHTTP()
    usar_fake(monkeypatch, fake)
    publicar.main([])
    posts = [c[2] for c in fake.chamadas if c[0] == "POST" and c[1].endswith("/media")]
    tipos = {p["media_type"] for p in posts}
    assert {"REELS", "STORIES"} <= tipos
    assert all("caption" not in p for p in posts if p["media_type"] == "STORIES")


def test_erro_conta_tentativas_e_para_em_3(raiz, monkeypatch):
    criar(raiz, "ruim")
    usar_fake(monkeypatch, FakeHTTP(falhar_publish=True))
    for _ in range(3):
        assert publicar.main([]) == 1
    d = json.loads((raiz / "conteudo" / "ruim" / "post.json").read_text())
    assert d["tentativas"] == 3 and d["falhou"] and "Token" in d["ultimo_erro"]
    assert fila.prontos_para_publicar() == []


def test_validacao(raiz):
    it = criar(raiz, "png", arquivos=("01.jpg",))
    it.dados["arquivos"] = ["arte.png"]
    (it.pasta / "arte.png").write_bytes(b"x")
    assert any("JPG" in e for e in it.validar())
    it.dados.update(arquivos=["01.jpg"], tipo="reel")
    assert any("reel" in e for e in it.validar())


def test_novo_post_converte_png(raiz, tmp_path):
    from jn import novo_post
    png = tmp_path / "arte.png"
    Image.new("RGBA", (800, 800), "red").save(png)
    novo_post.main(["--tipo", "post", "--quando", "2026-11-13 19:00", "--legenda", "Teste", str(png)])
    pasta = next((raiz / "conteudo").iterdir())
    assert pasta.name.startswith("2026-11-13-1900-post")
    assert Image.open(pasta / "01.jpg").size == (1080, 1350)
    d = json.loads((pasta / "post.json").read_text())
    assert d["publicar_em"] == "2026-11-13T19:00:00-03:00" and d["aprovado"] is False


def test_aprovar(raiz):
    from jn import aprovar
    criar(raiz, "x", aprovado=False)
    aprovar.main(["todos"])
    assert json.loads((raiz / "conteudo" / "x" / "post.json").read_text())["aprovado"] is True


def test_token_instagram_usa_graph_instagram():
    fake = FakeHTTP()
    ig = instagram.Instagram("IGQVJ_teste", sessao=fake)
    assert ig.ig_id == "999" and ig.base.startswith("https://graph.instagram.com/")


def test_recusado_nao_publica(raiz):
    it = criar(raiz, "rec")
    it.dados["recusado"] = True
    it.salvar()
    assert fila.prontos_para_publicar() == []
    assert fila.carregar()[0].status == "recusado"


def test_midia_em_transito_so_o_que_sai_em_breve(raiz, tmp_path):
    from jn import midia
    robo = tmp_path / "robo"
    robo.mkdir()
    criar(raiz, "ja", minutos=-1)                       # aprovado, já no horário
    criar(raiz, "logo", minutos=10)                     # aprovado, sai em 10 min
    criar(raiz, "depois", minutos=180)                  # aprovado, mas só daqui a 3 h
    criar(raiz, "rascunho", aprovado=False, minutos=5)  # não aprovado
    assert midia.sincronizar(robo) is True
    assert sorted(p.name for p in (robo / "midia").iterdir() if p.is_dir()) == ["ja", "logo"]
    assert midia.sincronizar(robo) is False             # nada mudou
    fila.mover_para_publicado(fila.carregar()[0])       # "ja" foi publicado
    assert midia.sincronizar(robo) is True
    assert not (robo / "midia" / "ja").exists()


def test_raiz_dos_dados_vem_do_ambiente(tmp_path, monkeypatch):
    import importlib
    monkeypatch.setenv("JN_DADOS", str(tmp_path))
    import jn.fila as f
    importlib.reload(f)
    assert f.RAIZ == tmp_path.resolve() and f.CONTEUDO == tmp_path.resolve() / "conteudo"
    monkeypatch.delenv("JN_DADOS")
    importlib.reload(f)


def test_tambem_publica_no_facebook(raiz, monkeypatch):
    monkeypatch.setenv("FACEBOOK", "1")
    from jn import facebook
    criar(raiz, "foto")
    criar(raiz, "car", tipo="carrossel", arquivos=("01.jpg", "02.jpg"))
    criar(raiz, "st", tipo="story")
    fake = FakeHTTP()
    usar_fake(monkeypatch, fake)
    orig = facebook.Facebook.__init__
    monkeypatch.setattr(facebook.Facebook, "__init__", lambda self, t, sessao=None, page_id=None: orig(self, t, fake, page_id))
    publicar.main([])
    fb = [c for c in fake.chamadas if c[0] == "POST" and "/PG/" in c[1]]
    assert any(c[1].endswith("/PG/photos") and c[2]["published"] == "true" for c in fb)   # post
    assert any(c[1].endswith("/PG/feed") and "attached_media[1]" in c[2] for c in fb)     # carrossel
    assert all(c[2]["access_token"] == "PAGETOK" for c in fb)
    d = json.loads((raiz / "publicado" / "foto" / "post.json").read_text())
    assert d["facebook_id"] == "PG_POST"
    st = json.loads((raiz / "publicado" / "st" / "post.json").read_text())
    assert "facebook_id" not in st                                                         # story só no IG


def test_falha_no_facebook_nao_afeta_instagram(raiz, monkeypatch):
    monkeypatch.setenv("FACEBOOK", "1")
    from jn import facebook
    criar(raiz, "foto")
    usar_fake(monkeypatch, FakeHTTP())
    def quebra(self, *a, **k):
        raise facebook.ErroInstagram("Facebook: sem permissão")
    monkeypatch.setattr(facebook.Facebook, "__init__", quebra)
    assert publicar.main([]) == 0
    d = json.loads((raiz / "publicado" / "foto" / "post.json").read_text())
    assert d["media_id"] == "MEDIA123" and "sem permissão" in d["facebook_erro"]


def test_story_manual_nunca_e_publicado_pelo_robo(raiz, monkeypatch, tmp_path):
    from jn import midia
    it = criar(raiz, "caixinha", tipo="story")
    it.dados["manual"] = True
    it.salvar()
    assert fila.carregar()[0].status == "manual"
    assert fila.prontos_para_publicar() == []
    robo = tmp_path / "robo"; robo.mkdir()
    midia.sincronizar(robo)
    assert not (robo / "midia" / "caixinha").exists()        # mídia não vai para o público
    it.dados["postado_manual"] = "2026-11-10T19:02:00-03:00"
    it.salvar()
    assert fila.carregar()[0].status == "publicado"


def test_facebook_desligado_por_padrao(raiz, monkeypatch):
    from jn import facebook
    monkeypatch.delenv("FACEBOOK", raising=False)
    chamou = []
    monkeypatch.setattr(facebook.Facebook, "__init__", lambda *a, **k: chamou.append(1))
    criar(raiz, "so-ig")
    usar_fake(monkeypatch, FakeHTTP())
    assert publicar.main([]) == 0
    d = json.loads((raiz / "publicado" / "so-ig" / "post.json").read_text())
    assert d["media_id"] == "MEDIA123" and "facebook_id" not in d and not chamou


def test_mais_de_5_hashtags_nao_publica(raiz):
    it = criar(raiz, "tags")
    it.dados["legenda"] = "Oi #a #b #c #d #e #f"
    assert any("hashtags" in e for e in it.validar())
    it.dados["legenda"] = "Oi #a #b #c #d #e"
    assert not any("hashtags" in e for e in it.validar())
