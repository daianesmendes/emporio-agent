# Comparação de modelos

Falta de cota não é erro do modelo: as taxas são calculadas só sobre as execuções que tiveram resposta.

| Rótulo | Modelo(s) | Execuções | Sem resposta (cota) | Aprovadas / respondidas | Valores sem origem | Ações sem execução | Prazos sem respaldo | Reprovado pelo juiz | Casos instáveis | Tempo (mediana) | Tokens/caso |
|---|---|---|---|---|---|---|---|---|---|---|---|
| encaminhamento_antes | gemini-3.5-flash-lite | 15 | 2 | 4/13 (31%) | 0 | 2 | 2 | 8 | 4 | 8.8 s | 10.910 |
| encaminhamento_intermediario | gemini-3.5-flash-lite | 15 | 7 | 6/8 (75%) | 0 | 2 | 0 | 2 | 1 | 8.4 s | 11.569 |
| encaminhamento_depois | gemini-3.5-flash-lite | 15 | 9 | 6/6 (100%) | 0 | 0 | 0 | 0 | 0 | 16.8 s | 15.119 |
