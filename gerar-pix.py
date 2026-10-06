#!/usr/bin/env python3
"""
Gera o BR Code (payload EMV) do Pix + QR em SVG, totalmente offline.

Por que offline e não um gerador na web:
  - a página de doação não pode depender de script de terceiro em runtime;
    se o CDN cai, o QR some e a doação morre junto.
  - nada do que a pessoa paga ou de onde vem trafega por serviço alheio.

Payload EMV do Pix (normativa):
  00 Payload Format Indicator  = "01"
  26 Merchant Account Info     = 00:"br.gov.bcb.pix" + 01:<chave> + 02:<descrição>
  52 Merchant Category Code     = "0000"
  53 Transaction Currency       = "986" (BRL)
  54 Transaction Amount         = OMITIDO de propósito — sem valor fixo, quem
                                  paga escolhe quanto. É o que um card de
                                  doação precisa.
  58 Country Code               = "BR"
  59 Merchant Name              = até 25
  60 Merchant City              = até 15
  62 Additional Data            = 05:txid ("***" = não informado)
  63 CRC16-CCITT                = 4 hex sobre tudo acima
"""
import sys, pathlib

PIX_KEY = "13974140538"
MERCHANT_NAME = "Kauê Leandro"      # campo 59, máx 25
MERCHANT_CITY = ""                  # campo 60, máx 15 — ver nota no README
TXID = "***"                        # campo 62.05 — "não informado"
DESCRIPTION = "Apoio Jarvis"         # campo 26.02


def tlv(id_: str, value: str) -> str:
    v = value.encode("utf-8")
    return f"{id_}{len(v):02d}{v.decode('utf-8')}"


def crc16(data) -> str:
    """CRC16-CCITT-FALSE (poly 0x1021, init 0xFFFF). Aceita str ou bytes.

    Aceitar bytes é o ponto: o payload é uma sequência de BYTES — "Kauê" tem
    5 bytes e 4 caracteres. Passar str e deixar o .encode() dentro esconderia
    qualquer erro de indexação.
    """
    data = data.encode("utf-8") if isinstance(data, str) else data
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def build_payload(key=PIX_KEY, name=MERCHANT_NAME, city=MERCHANT_CITY,
                  txid=TXID, desc=DESCRIPTION, amount=None) -> str:
    """amount=None → sem valor fixo (quem paga escolhe). amount=10.00 → 54 preenchido.

    Os TLVs são montados em ORDEM CRESCENTE de tag, como a规范 do EMV exige
    (00 < 26 < 52 < 53 < 54 < 58 < 59 < 60 < 62 < 63). Gerar o 54 no fim
    produz um payload que alguns validadores recusam.
    """
    mai = tlv("00", "br.gov.bcb.pix") + tlv("01", key)
    if desc:
        mai += tlv("02", desc[:99])

    fields = [tlv("00", "01"), tlv("26", mai), tlv("52", "0000"), tlv("53", "986")]
    if amount is not None:
        fields.append(tlv("54", f"{amount:.2f}"))
    fields.append(tlv("58", "BR"))
    fields.append(tlv("59", name[:25]))
    if city:
        fields.append(tlv("60", city[:15]))
    fields.append(tlv("62", tlv("05", txid)))

    p = "".join(fields) + "6304"        # campo 63 vazio, marcador pro CRC
    return p + crc16(p)


def ensure_qrcode():
    """Garante que `qrcode` esteja importável, sem depender de um venv externo.

    Antes este script exigia um venv em /tmp/opencode/.venv-pix. Esse diretório
    é temporário: quando some, o gerador falha e — pior — o passo seguinte
    re-embute artefatos VELHOS sem avisar, publicando uma chave trocada com CRC
    antigo. Um gerador que depende de /tmp é um gerador que vai te trair.
    """
    try:
        import qrcode  # noqa: F401
        return
    except ImportError:
        pass

    import subprocess
    import tempfile

    print("  'qrcode' ausente — criando um venv temporario…")
    venv = pathlib.Path(tempfile.gettempdir()) / "pix-venv"
    if not (venv / "bin" / "python").exists():
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    subprocess.run([str(venv / "bin" / "pip"), "install", "--quiet", "qrcode"], check=True)

    import subprocess as sp
    sp.run([str(venv / "bin" / "python"), __file__, *sys.argv[1:]], check=True)
    sys.exit(0)


AMOUNTS = [10, 25, 50, 100]


def validate(p: str, amount=None) -> None:
    """Re-parseia o payload em BYTES e confere tudo. Não confie no construtor."""
    b = p.encode("utf-8")
    i, seen, order = 0, {}, []
    while i < len(b):
        tag = b[i:i + 2].decode()
        n = int(b[i + 2:i + 4])
        seen[tag] = b[i + 4:i + 4 + n]
        order.append(tag)
        i += 4 + n

    assert b.startswith(b"000201"), "payload format indicator errado"
    assert seen["00"] == b"01", "payload format indicator != 01"

    # o GUI e a chave são sub-TLVs dentro do campo 26 (merchant account),
    # não campos do topo — o 00 do topo é o format indicator.
    mai, j, sub = seen["26"], 0, {}
    while j < len(mai):
        tag = mai[j:j + 2].decode()
        n = int(mai[j + 2:j + 4])
        sub[tag] = mai[j + 4:j + 4 + n]
        j += 4 + n
    assert sub["00"] == b"br.gov.bcb.pix", "GUI Pix ausente"
    assert sub["01"].decode() == PIX_KEY, "chave divergente"
    assert seen["53"] == b"986", "moeda não é BRL"
    assert seen["58"] == b"BR", "país ausente"
    assert seen["59"].decode() == MERCHANT_NAME, "merchant name corrompido"
    assert p.endswith(crc16(b[:-4])), "CRC não confere"
    assert order == sorted(order), f"tags fora de ordem: {order}"
    assert order[-1] == "63", "campo 63 não é o último"
    if amount is None:
        assert "54" not in seen, "há valor fixo no payload base"
    else:
        assert seen["54"].decode() == f"{amount:.2f}", "valor divergente"


def main():
    ensure_qrcode()
    out_dir = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = build_payload()
    validate(payload)
    (out_dir / "pix-payload.txt").write_text(payload + "\n")

    # Valores fixos gerados AQUI, não no browser.
    # Motivo: o payload é uma string de BYTES (o campo 59 tem "ê" = 2 bytes)
    # mas o JS indexa por unidade UTF-16. Qualquer surgery de string em JS
    # corrompe o payload silenciosamente. Dados estáticos gerados em build
    # time eliminam essa classe de bug inteira.
    amounts = {}
    for v in AMOUNTS:
        p = build_payload(amount=v)
        validate(p, amount=v)
        amounts[v] = p
    (out_dir / "pix-amounts.json").write_text(
        __import__("json").dumps(amounts, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    import qrcode, qrcode.image.svg
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage)
    img.save(out_dir / "pix-qr.svg")

    print("base    :", payload)
    print("valores :", ", ".join(f"R${v} -> {amounts[v][-8:]}" for v in AMOUNTS))
    print("crc base:", crc16(payload[:-4]))
    print("svg     :", out_dir / "pix-qr.svg")
    print("json    :", out_dir / "pix-amounts.json")


if __name__ == "__main__":
    main()
