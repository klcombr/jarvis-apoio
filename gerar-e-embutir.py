#!/usr/bin/env python3
"""
Reescreve doar/index.html com o QR e os payloads gerados por gerar-pix.py.

Por que este script existe
-------------------------
O README do repo manda rodar "gerar-pix.py e depois gerar-e-embutir.py". Até
agora o segundo não existia — eu tinha feito a embutição na mão, via heredoc,
durante a construção. Isso significa que trocar a chave Pix exigia surgery
manual em três lugares e qualquer erro quebrava o CRC silenciosamente. O
README estava mentindo.

Como funciona
-------------
O index.html tem três regiões delimitadas por âncoras de comentário:

    <!-- PIX-QR:BEGIN -->  ...svg...  <!-- PIX-QR:END -->
    /* PIX-PAYLOADS:BEGIN */ var PAYLOADS = {...}; /* PIX-PAYLOADS:END */

Este script reescreve SÓ o conteúdo entre as âncoras. Idempotente: rodar sem
mudar nada produz um arquivo byte-idêntico.

Depois de escrever, ele revalida a página: re-parseia os payloads embutidos,
recalcula o CRC16 de cada um e confere que batem com o que gerar-pix.py
produziu. Página de doação não tem erro tolerável — uma chave com CRC errado é
dinheiro que não chega em lugar nenhum.

Uso
---
    ../gerar-pix.py .            # gera pix-qr.svg + pix-amounts.json
    python3 gerar-e-embutir.py   # reescreve index.html e revalida
"""
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
HTML = HERE / "index.html"
QR_SVG = HERE.parent / "pix-qr.svg"
PAYLOADS_JSON = HERE.parent / "pix-amounts.json"
PAYLOAD_TXT = HERE.parent / "pix-payload.txt"

ANCHORS = {
    "qr": ("<!-- PIX-QR:BEGIN -->", "<!-- PIX-QR:END -->"),
    "payloads": ("/* PIX-PAYLOADS:BEGIN */", "/* PIX-PAYLOADS:END */"),
}


def crc16(data: bytes) -> str:
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def splice(text: str, begin: str, end: str, body: str) -> str:
    """Substitui o que está entre as âncoras. Erro alto se a âncora sumiu —
    escrever por baixo dela apagaria o QR inteiro sem avisar ninguém."""
    i = text.find(begin)
    j = text.find(end)
    if i == -1 or j == -1 or j < i:
        raise SystemExit(
            f"ANCORA AUSENTE: {begin!r} .. {end!r}\n"
            "O index.html foi editado a mao e perdeu os marcadores. "
            "Restaure as ancoras ou recrie a pagina antes de rodar de novo."
        )
    return text[: i + len(begin)] + "\n" + body + "\n" + text[j:]


def extrair_chave(payload: str) -> str:
    """Extrai a chave Pix do payload EMV, parseando os TLVs em BYTES.

    Regex seria mais curto e estaria errado: chave Pix de telefone é só
    dígitos, então um padrão como `pix01(\\d{2})([^0-9]+?)` nunca casa. O
    campo 01 traz o COMPRIMENTO da chave — usar isso é o que funciona.
    """
    b = payload.encode("utf-8")
    i, campo26 = 0, None
    while i < len(b):
        tag = b[i:i + 2].decode()
        n = int(b[i + 2:i + 4])
        if tag == "26":
            campo26 = b[i + 4:i + 4 + n]
            break
        i += 4 + n
    if campo26 is None:
        return ""
    j = 0
    while j < len(campo26):
        tag = campo26[j:j + 2].decode()
        n = int(campo26[j + 2:j + 4])
        if tag == "01":
            return campo26[j + 4:j + 4 + n].decode("utf-8")
        j += 4 + n
    return ""


def chave_declarada() -> str:
    """Lê PIX_KEY direto do gerar-pix.py, sem importar o módulo.

    Importar executaria o código do topo do arquivo. Ler com regex é feio,
    mas é o único jeito de comparar sem disparar o gerador dentro do
    embutinidor.
    """
    src = (HERE.parent / "gerar-pix.py").read_text(encoding="utf-8")
    m = re.search(r'^PIX_KEY\s*=\s*"([^"]+)"', src, re.M)
    if not m:
        raise SystemExit("nao encontrei PIX_KEY no gerar-pix.py")
    return m.group(1)


def main() -> int:
    for f in (HTML, QR_SVG, PAYLOADS_JSON, PAYLOAD_TXT):
        if not f.exists():
            print(f"FALTA: {f}\nRode ../gerar-pix.py . antes.", file=sys.stderr)
            return 1

    # ---- freshness: o artefato tem que ser da chave ATUAL ----
    # Sem esta checagem o pior cenário é silencioso: se o gerar-pix.py falhar
    # (sem `qrcode`, sem rede), os JSONs antigos ficam no lugar, este script
    # re-embute eles e reporta sucesso — publicando uma chave ERRADA com CRC
    # consistente, que só quebra na hora do pagamento.
    base_txt = PAYLOAD_TXT.read_text(encoding="utf-8").strip()
    chave_artefato = extrair_chave(base_txt)
    chave_fonte = chave_declarada()

    if chave_artefato != chave_fonte:
        print(
            "ARTEFATO DESATUALIZADO — nada foi escrito.\n"
            f"  chave no gerar-pix.py : {chave_fonte}\n"
            f"  chave no pix-payload.txt: {chave_artefato or '(nao achei)'}\n"
            "  O gerar-pix.py nao rodou (ou rodou com outra chave). "
            "Rode `../gerar-pix.py .` antes de embutir.",
            file=sys.stderr,
        )
        return 1

    html = HTML.read_text(encoding="utf-8")
    antes = html

    # ---- QR ----
    svg = QR_SVG.read_text(encoding="utf-8")
    svg = svg[svg.index("<svg"):]          # descarta o cabecalho <?xml ...?>
    svg = svg.replace("<svg ", '<svg style="display:block" ', 1) if False else svg
    html = splice(html, *ANCHORS["qr"], svg)

    # ---- payloads ----
    amts = json.loads(PAYLOADS_JSON.read_text(encoding="utf-8"))
    base = PAYLOAD_TXT.read_text(encoding="utf-8").strip()
    payload_map = {"base": base}
    payload_map.update({str(k): v for k, v in amts.items()})

    # valida ANTES de escrever: nao grava HTML com CRC quebrado
    for nome, p in payload_map.items():
        raw = p.encode("utf-8")
        if not raw.startswith(b"000201"):
            raise SystemExit(f"payload '{nome}' nao comeca com 000201")
        if not p.endswith(crc16(raw[:-4])):
            raise SystemExit(f"payload '{nome}' com CRC invalido — nada foi escrito")

    blob = "var PAYLOADS = " + json.dumps(payload_map, ensure_ascii=False, indent=2) + ";"
    html = splice(html, *ANCHORS["payloads"], blob)

    HTML.write_text(html, encoding="utf-8")

    # ---- revalida o que ficou no arquivo ----
    final = HTML.read_text(encoding="utf-8")
    m = re.search(
        re.escape(ANCHORS["payloads"][0]) + r".*?var PAYLOADS = (\{.*?\}).*?" + re.escape(ANCHORS["payloads"][1]),
        final, re.S,
    )
    if not m:
        print("ERRO: nao consegui reler os payloads do arquivo gravado", file=sys.stderr)
        return 1
    lido = json.loads(m.group(1))
    if lido != payload_map:
        print("ERRO: o que foi gravado difere do que foi gerado", file=sys.stderr)
        return 1
    if "<svg" not in final[final.find(ANCHORS["qr"][0]): final.find(ANCHORS["qr"][1])]:
        print("ERRO: o QR nao esta entre as ancoras", file=sys.stderr)
        return 1

    mudou = "SIM" if final != antes else "NAO (ja estava em dia)"
    print(f"index.html reescrito · mudou: {mudou}")
    print(f"  chave no payload base: {lido['base'][lido['base'].find('0111')+4:lido['base'].find('0111')+19]}")
    print(f"  variantes com valor   : {sorted(k for k in lido if k != 'base')}")
    print(f"  CRC de todas validado : {all(p.endswith(crc16(p.encode()[:-4])) for p in lido.values())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
