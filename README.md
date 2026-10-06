# Apoie o Jarvis

Página de doação do Jarvis — agente de IA local, livre e auditável.
Fonte editável em `~/projetos/ativos/jarvis/marketing/doar/`.

## O QR Pix é gerado, não escrito à mão

    ~/projetos/ativos/jarvis/marketing/gerar-pix.py .

Gera o payload EMV (BR Code) com CRC16-CCITT, valida re-parseando em bytes,
e emite `pix-qr.svg` + `pix-amounts.json`. Depois `doar/gerar-e-embutir.py`
reescreve `index.html` com o QR e os payloads.

**Ao trocar a chave Pix, rode os dois scripts e commite.** O HTML carrega os
payloads embutidos — editar a chave no HTML direto quebra o CRC.

Campo `60` (cidade) fica vazio de propósito: melhor nenhuma cidade do que uma
errada aparecendo no app do banco. Se algum app recusar o QR, é o primeiro
lugar pra mexer (`MERCHANT_CITY` no `gerar-pix.py`).
