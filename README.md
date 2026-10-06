# Apoie o Jarvis

Página de doação do Jarvis — agente de IA local, livre e auditável.
No ar em <https://klcombr.github.io/jarvis-apoio/>.

Identidade visual tirada do próprio produto (`~/painel jarvis/static/*.css`):
glass `rgba(9,28,54,.6)`, texto `#f1f7ff`, ciano `#00ffff`, Inter no texto e
IBM Plex Mono nos rótulos — as mesmas cores e a mesma mistura tipográfica do
painel, para o post e a página lerem como a mesma coisa.

## O QR Pix é gerado, nunca escrito à mão

    cd ~/projetos/ativos/jarvis/marketing
    ./gerar-pix.py .          # payload EMV + CRC16, valida re-parseando em bytes
    cd doar && python3 gerar-e-embutir.py

O primeiro monta o BR Code e emite `pix-qr.svg` + `pix-amounts.json`.
O segundo reescreve `index.html` entre as âncoras e revalida o que gravou.

**Trocar a chave Pix = editar `PIX_KEY` no `gerar-pix.py` e rodar os dois.**

O `gerar-pix.py` cria um venv temporário sozinho se faltar o `qrcode` — não
depende de nenhum diretório em `/tmp` que você configurou ontem.

### Por que os payloads são gerados, não calculados no browser

O payload EMV é uma sequência de **bytes**: "Kauê" tem 5 bytes e 4 caracteres.
JavaScript indexa por unidade UTF-16, então qualquer montagem de string no
browser corrompe o payload em silêncio — CRC errado é doação que não chega.
Os valores com valor fixo (R$ 10/25/50/100) são gerados em build time e
embutidos como dados.

### A guarda que impede o pior

O `gerar-e-embutir.py` compara a chave em `PIX_KEY` com a que está dentro de
`pix-payload.txt`. Se divergirem, ele **aborta sem escrever nada** e diz qual
chave está em cada lado.

Sem essa guarda, se o `gerar-pix.py` falhasse (sem `qrcode`, sem rede) os
JSONs antigos ficariam no lugar, o embutinidor re-verteria eles e reportaria
sucesso — publicando uma chave errada com CRC consistente, que só quebra na
hora do pagamento.

## Campo 60 (cidade) vazio, de propósito

Melhor nenhuma cidade do que uma errada aparecendo no app do banco. Se algum
app recusar o QR, é o primeiro lugar pra mexer: `MERCHANT_CITY` no
`gerar-pix.py`, e depois rode os dois scripts de novo.

## Pagamento

Pix direto, sem gateway e sem taxa. O QR não tem valor fixo — o app do banco
deixa a pessoa digitar o que quiser.
