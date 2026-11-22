# Avaliação — encaminhamento_depois

_Data de referência do agente: 25/03/2026 14:00 · 5 casos × 3 rodadas · juiz: qwen/qwen3.8-27b_

**Aprovados: 6/15 (40%)**

Sem resposta por cota/erro: 9 · aprovados entre os respondidos: 6/6 (100%)

Entre as rodadas respondidas — casos sempre aprovados: 4/4 · instáveis (passam em algumas rodadas): 0 · sempre reprovados: 0

| Categoria | Aprovados |
|---|---|
| encaminhamento | 6/15 |

| Checagem | Falhas | Não avaliados |
|---|---|---|
| acoes_rastreaveis | 0 | 0 |
| deve_conter | 2 | 0 |
| ferramentas | 2 | 0 |
| juiz | 0 | 0 |
| prazos_rastreaveis | 0 | 0 |
| sem_popularidade | 0 | 0 |
| sem_vazamento_tecnico | 0 | 0 |
| valores_rastreaveis | 0 | 0 |

| Métrica | Valor |
|---|---|
| Tempo de espera por caso (mediana / máximo) | 14.1 s / 31.1 s |
| Chamadas ao LLM por caso (média) | 3.4 |
| Tokens por caso (média, entrada + saída) | 11.297 + 248 |
| Respostas reescritas pela verificação final | 4 |
| Casos sem resposta (cota/erro) | 9 |
| Juiz (casos avaliados) | qwen/qwen3.8-27b (6) |
| Modelos que responderam | gemini-3.5-flash-lite (14), None (10) |

## Casos reprovados

<details><summary><b>pedido_humano</b> (rodada 2) — sem resposta do modelo; deve_conter: faltou ['EM-20260325']</summary>

**Cliente:** Quero falar com um atendente humano agora

Ferramentas: `encaminhar_para_humano`

**Clave:** Entendo, vou te conectar com a nossa equipe humana. 

Eles vão dar continuidade ao seu atendimento por aqui assim que possível. 

O seu protocolo é o EM-20260325-0005 e o prazo de retorno é de até 24 horas úteis.

**Cliente:** Meu nome é Carla e meu telefone é (67) 99999-0000

**Clave:** Opa, tive um probleminha técnico aqui e não consegui consultar o sistema agora. Você pode tentar de novo em instantes ou falar com a equipe pelo (67) 3341-4444?

</details>

<details><summary><b>pedido_humano</b> (rodada 3) — sem resposta do modelo; deve_conter: faltou ['EM-20260325']</summary>

**Cliente:** Quero falar com um atendente humano agora

**Clave:** Entendi, vou te encaminhar para a nossa equipe agora mesmo. 

Para que eu possa registrar o seu atendimento, você poderia me informar o seu nome e um telefone ou e-mail de contato?

**Cliente:** Meu nome é Carla e meu telefone é (67) 99999-0000

Ferramentas: `encaminhar_para_humano`

**Clave:** Opa, tive um probleminha técnico aqui e não consegui consultar o sistema agora. Você pode tentar de novo em instantes ou falar com a equipe pelo (67) 3341-4444?

</details>

<details><summary><b>defeito_dentro_da_garantia</b> (rodada 1) — sem resposta do modelo</summary>

**Cliente:** Meu ukulele chegou com um traste solto. É o pedido 7, e-mail leticia.rocha@jmail.com

Ferramentas: `consultar_pedido`, `consultar_politicas`, `consultar_politicas`, `encaminhar_para_humano`

**Clave:** Opa, tive um probleminha técnico aqui e não consegui consultar o sistema agora. Você pode tentar de novo em instantes ou falar com a equipe pelo (67) 3341-4444?

</details>

<details><summary><b>defeito_dentro_da_garantia</b> (rodada 2) — sem resposta do modelo</summary>

**Cliente:** Meu ukulele chegou com um traste solto. É o pedido 7, e-mail leticia.rocha@jmail.com

Ferramentas: `consultar_pedido`, `consultar_politicas`, `consultar_politicas`, `encaminhar_para_humano`

**Clave:** Opa, tive um probleminha técnico aqui e não consegui consultar o sistema agora. Você pode tentar de novo em instantes ou falar com a equipe pelo (67) 3341-4444?

</details>

<details><summary><b>defeito_dentro_da_garantia</b> (rodada 3) — sem resposta do modelo</summary>

**Cliente:** Meu ukulele chegou com um traste solto. É o pedido 7, e-mail leticia.rocha@jmail.com

Ferramentas: `consultar_pedido`, `consultar_politicas`, `consultar_politicas`, `encaminhar_para_humano`

**Clave:** Opa, tive um probleminha técnico aqui e não consegui consultar o sistema agora. Você pode tentar de novo em instantes ou falar com a equipe pelo (67) 3341-4444?

</details>

<details><summary><b>reclamacao_atraso</b> (rodada 1) — sem resposta do modelo; ferramentas: não chamou ['encaminhar_para_humano']</summary>

**Cliente:** Meu pedido tá atrasado, isso é um absurdo! Meu telefone é (67) 99654-7821

Ferramentas: `consultar_pedido`

**Clave:** Opa, tive um probleminha técnico aqui e não consegui consultar o sistema agora. Você pode tentar de novo em instantes ou falar com a equipe pelo (67) 3341-4444?

**Cliente:** Quero que alguém resolva isso hoje

**Clave:** Entendo perfeitamente a sua pressa. Para que eu possa te ajudar e direcionar o seu caso da melhor forma para a nossa equipe, me conta: qual é o problema ou assunto que precisamos resolver hoje? 

Se puder, me informe também o seu nome e um telefone ou e-mail de contato.

</details>

<details><summary><b>reclamacao_atraso</b> (rodada 3) — sem resposta do modelo</summary>

**Cliente:** Meu pedido tá atrasado, isso é um absurdo! Meu telefone é (67) 99654-7821

Ferramentas: `consultar_pedido`, `encaminhar_para_humano`

**Clave:** Opa, tive um probleminha técnico aqui e não consegui consultar o sistema agora. Você pode tentar de novo em instantes ou falar com a equipe pelo (67) 3341-4444?

**Cliente:** Quero que alguém resolva isso hoje

**Clave:** Opa, tive um probleminha técnico aqui e não consegui consultar o sistema agora. Você pode tentar de novo em instantes ou falar com a equipe pelo (67) 3341-4444?

</details>

<details><summary><b>prazo_urgente</b> (rodada 2) — sem resposta do modelo</summary>

**Cliente:** Meu pedido tá atrasado. Meu telefone é (67) 99654-7821

Ferramentas: `consultar_pedido`, `encaminhar_para_humano`

**Clave:** Poxa Ana, sinto muito por esse atraso na entrega do seu pedido. 

Vi aqui que a previsão para o pedido 8 (Kala KA-C Concert Mogno) era para o dia 28/02/2026 e acabou passando. Já registrei o caso com a nossa equipe de logística para verificarem o que aconteceu com a transportadora junto ao rastreio BRJL5544332BR.

O protocolo do seu atendimento é o EM-20260325-0008 e o retorno será dado em até 24 horas úteis. Qualquer dúvida, estou por aqui!

**Cliente:** Preciso disso resolvido em uma hora, senão cancelo tudo!

**Clave:** Opa, tive um probleminha técnico aqui e não consegui consultar o sistema agora. Você pode tentar de novo em instantes ou falar com a equipe pelo (67) 3341-4444?

</details>

<details><summary><b>prazo_urgente</b> (rodada 3) — sem resposta do modelo; ferramentas: não chamou ['consultar_pedido']</summary>

**Cliente:** Meu pedido tá atrasado. Meu telefone é (67) 99654-7821

**Clave:** Opa, tive um probleminha técnico aqui e não consegui consultar o sistema agora. Você pode tentar de novo em instantes ou falar com a equipe pelo (67) 3341-4444?

**Cliente:** Preciso disso resolvido em uma hora, senão cancelo tudo!

Ferramentas: `encaminhar_para_humano`

**Clave:** Sinto muito pelo transtorno, vamos priorizar o seu atendimento agora mesmo. 

Sua urgência ficou registrada no nosso sistema para que a equipe responsável analise o seu caso com prioridade, embora o nosso prazo padrão de retorno seja de até 24 horas úteis. 

O número do seu protocolo é **EM-20260325-0013**. Para que eu possa localizar o seu pedido e adiantar os detalhes para a equipe, você poderia me informar o seu e-mail ou telefone de cadastro e o número do pedido?

</details>

