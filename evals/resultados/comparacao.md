# Comparação de modelos

Falta de cota não é erro do modelo: as taxas são calculadas só sobre as execuções que tiveram resposta.

| Rótulo | Modelo(s) | Execuções | Sem resposta (cota) | Aprovadas / respondidas | Valores sem origem | Ações sem execução | Prazos sem respaldo | Reprovado pelo juiz | Casos instáveis | Tempo (mediana) | Tokens/caso |
|---|---|---|---|---|---|---|---|---|---|---|---|
| cmp_gemini-3.1-flash-lite | gemini-3.1-flash-lite | 36 | 15 | 17/21 (81%) | 0 | 0 | 0 | 4 | 1 | 5.7 s | 6.573 |
| cmp_gemini-3.5-flash-lite | gemini-3.5-flash-lite | 36 | 7 | 23/29 (79%) | 0 | 0 | 1 | 6 | 3 | 13.7 s | 7.634 |
| cmp_gpt-oss-120b | openai/gpt-oss-120b | 12 | 1 | 7/11 (64%) | 0 | 0 | 0 | 4 | 0 | 1.8 s | 6.292 |
| ajustes_gemini-3.5-flash-lite | gemini-3.5-flash-lite | 9 | 1 | 8/8 (100%) | 0 | 0 | 0 | 0 | 0 | 15.8 s | 7.969 |
