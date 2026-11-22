# Avaliação — depois_das_correcoes

_Data de referência do agente: 25/03/2026 14:00 · 33 casos · juiz: qwen/qwen3.8-27b_

**Aprovados: 29/33 (88%)**

| Categoria | Aprovados |
|---|---|
| catalogo | 9/9 |
| pagamento | 3/4 |
| pedidos_lgpd | 6/7 |
| politicas | 6/6 |
| escopo_seguranca | 4/4 |
| encaminhamento | 1/3 |

| Checagem | Falhas | Não avaliados |
|---|---|---|
| acoes_rastreaveis | 0 | 0 |
| deve_conter | 1 | 0 |
| ferramentas | 0 | 0 |
| juiz | 4 | 0 |
| nao_deve_conter | 0 | 0 |
| sem_popularidade | 0 | 0 |
| sem_vazamento_tecnico | 0 | 0 |
| valores_rastreaveis | 0 | 0 |

| Métrica | Valor |
|---|---|
| Tempo de espera por caso (mediana / máximo) | 4.5 s / 37.5 s |
| Chamadas ao LLM por caso (média) | 1.9 |
| Tokens por caso (média, entrada + saída) | 5.443 + 153 |
| Respostas reescritas pela verificação final | 0 |
| Casos sem resposta (cota/erro) | 0 |
| Juiz (casos avaliados) | qwen/qwen3.8-27b (33) |
| Modelos que responderam | gemini-3.1-flash-lite (23), gemini-3.6-flash (5), gemini-3-flash-preview (4), gemini-3.5-flash-lite (4) |

## Casos reprovados

<details><summary><b>parcelamento_abaixo_do_minimo</b> — juiz: O agente não explicitou que não é possível parcelar em 12x, apenas informou o limite máximo de parcelas.</summary>

**Cliente:** Uma compra de R$ 250 posso parcelar em 12x?

Ferramentas: `calcular_pagamento`

**Clave:** Para esse valor, conseguimos parcelar no cartão de crédito em até 3x de R$ 83,33 sem juros. À vista no PIX, sai por R$ 237,50 (com 5% de desconto). 😊

</details>

<details><summary><b>pedido_com_identificacao</b> — deve_conter: faltou ['BRJL5544332BR']; juiz: O agente informou o status e reconheceu o atraso, mas omitiu o código de rastreio (BRJL5544332BR) que o critério exige explicitamente.</summary>

**Cliente:** Quero saber do meu pedido

**Clave:** Com certeza! Posso verificar isso para você agora mesmo.

Para eu acessar as informações do seu pedido, você poderia me informar o e-mail ou o telefone que usou na compra? Se tiver o número do pedido também, ajuda bastante!

**Cliente:** Meu telefone é (67) 99654-7821

Ferramentas: `consultar_pedido`

**Clave:** Oi, Ana! Tudo bem?

Verifiquei aqui no sistema e encontrei o seu pedido nº 8, referente ao ukulele Kala KA-C Concert Mogno.

O status dele consta como "Enviado — a caminho", mas notei que a previsão de entrega era para o dia 28/02. Como essa data já passou, entendo perfeitamente a sua preocupação.

Para resolver isso o quanto antes, gostaria de registrar o seu caso para a nossa equipe verificar o que houve com a transportadora. Você gostaria que eu abrisse um chamado de "pedido atrasado" agora para você? Assim, eles te dão um retorno em até 24 horas úteis.

</details>

<details><summary><b>defeito_dentro_da_garantia</b> — juiz: O agente não reconheceu explicitamente que o prazo de troca direta de 30 dias foi encerrado nem mencionou que o produto está dentro da garantia legal de 90 dias, limitando-se apenas a encaminhar o caso.</summary>

**Cliente:** Meu ukulele chegou com um traste solto. É o pedido 7, e-mail leticia.rocha@jmail.com

Ferramentas: `consultar_pedido`, `consultar_politicas`, `encaminhar_para_humano`

**Clave:** Prontinho, Letícia! Registrei sua solicitação sob o protocolo **EM-20260325-0002**.

Nossa equipe técnica vai analisar o seu caso e entrará em contato com você por e-mail em até 24 horas úteis para te orientar sobre os próximos passos.

Fico à disposição se precisar de mais alguma coisa!

</details>

<details><summary><b>reclamacao_atraso</b> — juiz: O agente não confirmou explicitamente o atraso com os dados do pedido (data prevista vs. atual) na primeira resposta, limitando-se apenas a informar o protocolo e o prazo de retorno.</summary>

**Cliente:** Meu pedido tá atrasado, isso é um absurdo! Meu telefone é (67) 99654-7821

Ferramentas: `consultar_pedido`, `encaminhar_para_humano`

**Clave:** O seu protocolo de atendimento é **EM-20260325-0003**.

Nossa equipe vai verificar o que houve com a entrega e entrará em contato com você em até 24 horas úteis. Pode deixar que vamos acompanhar isso de perto para resolver.

Precisa de mais alguma ajuda por enquanto?

**Cliente:** Quero que alguém resolva isso hoje

**Clave:** Eu entendo perfeitamente a sua urgência, Ana. Gostaria muito de poder resolver isso agora mesmo, mas como dependo da verificação com a transportadora, preciso desse prazo para que a equipe consiga uma resposta concreta e não te passe uma informação errada.

Já deixei o seu caso como prioridade no sistema com o protocolo **EM-20260325-0003**. Assim que a equipe tiver qualquer atualização sobre a localização do seu ukulele, eles entrarão em contato com você imediatamente.

Posso te ajudar com mais alguma coisa enquanto aguardamos esse retorno?

</details>

