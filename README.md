# Monitor de Estoque Kanban — Cenário WEIGHT

## Identificação do Candidato

- **Nome completo:** Rodrigo Otavio Bertipalha de Paula Martins
- **GitHub:** https://github.com/RodrigoBertipalha

## Visão Geral

Firmware em MicroPython para ESP32 que monitora o peso de uma caixa Kanban através de uma célula de carga com HX711. A cada leitura, o sistema classifica o estado do estoque (regular, vazio, reabastecido ou anomalia) e emite os eventos via UART. Não há interação direta do usuário: o sistema apenas reage às variações de peso injetadas pela CI do Wokwi.

## Arquitetura

O `main.py` é dividido em três blocos: driver do HX711 (bit-bang de 24 bits), máquina de estados e loop principal.

O firmware inicia em `INIT`, aguarda a primeira leitura válida do sensor e, em seguida, classifica o sistema entre `REGULAR`, `VAZIO`, `ABASTECIDO` e `ANOMALIA`, de acordo com o peso e com a transição anteriormente registrada. Esse gate inicial evita que o alerta de anomalia dispare antes do primeiro `set-control` do cenário, quando a leitura ainda é zero.

O loop principal é não-bloqueante: a leitura ocorre a cada 100 ms usando `time.ticks_diff`, sem `sleep` longo. Cada mensagem tem uma flag que garante uma única emissão por transição de estado; as flags são resetadas quando o estado muda.

## Componentes

| Componente | Papel |
|---|---|
| `board-esp32-devkit-c-v4` | Microcontrolador principal |
| `wokwi-hx711` (`type: 50kg`) | ADC de célula de carga, controlado via `load` na CI |

### Ligações

| Origem | Destino | Função |
|---|---|---|
| ESP32 19 | HX711 DT | Dados |
| ESP32 18 | HX711 SCK | Clock |
| ESP32 5V | HX711 VCC | Alimentação |
| ESP32 GND.1 | HX711 GND | Referência elétrica |

As mensagens são enviadas pela UART padrão do ESP32 e capturadas pelo monitor serial do Wokwi e pela CI, sem ligação explícita no `diagram.json`.

## Decisões técnicas

**Escala do HX711.** No modelo de 50 kg do Wokwi, a leitura bruta varia de 0 a 21000, correspondendo a aproximadamente 420 unidades por quilograma. Como os cenários automatizados deste desafio injetam os valores conforme a escala definida nos arquivos YAML, o firmware aplica o fator de conversão adotado pelos testes (`raw / 420`) para produzir as leituras esperadas em gramas. O comportamento foi confirmado no repositório oficial `wokwi/wokwi-part-tests`.

**Gate de estabilização.** O estado `INIT` só cede lugar aos outros quando a primeira leitura não-zero chega. Sem isso, a leitura inicial (0 g antes do primeiro `set-control`) dispararia o alerta de anomalia e travaria o `wait-serial` do teste 3.

**Máquina de estados enxuta.** As transições ficam concentradas em `update_state`, e o efeito colateral (print) fica em `apply_transition`. Assim adicionar um estado novo é local, sem espalhar `if` pelo loop.

**Sem uso de `sleep` longo.** A CI do Wokwi injeta eventos em janelas curtas; qualquer bloqueio maior perderia o `set-control` seguinte.

## Resultados

Os três cenários (`test_1`, `test_2`, `test_3`) exercitam:

1. Transição para regular com peso dinâmico (`Status: Estoque Regular (2500g)`).
2. Ciclo completo vazio → reabastecido.
3. Anomalia por leitura zero após operação normal.

Todas as strings esperadas pela CI são emitidas exatamente como especificado no `WEIGHT.md`.

## Comentários adicionais

O maior tempo do desafio foi identificar que o tipo correto da parte no diagrama é `wokwi-hx711` (não `hx711`) e que os pinos do ESP32 no Wokwi são referenciados por número puro (`19`, `18`) e não `GPIOxx`. A primeira execução na Actions falhou por causa disso — a peça não era reconhecida, o driver lia sempre zero e o alerta de anomalia disparava no boot, antes do `wait-serial` do teste começar a escutar.
