# Monitor de Estoque Kanban Inteligente - WEIGHT Scenario

## Identificação do Candidato

- **Nome completo:** [Seu Nome Aqui]
- **GitHub:** [Seu GitHub Aqui]

---

## Visão Geral da Solução

O projeto implementa um **Monitor de Estoque Kanban Inteligente** usando ESP32 com sensor de peso HX711. O sistema monitora em tempo real o nível de insumos em uma caixa organizadora, detectando automaticamente estados de estoque (regular, vazio ou crítico) e gerando alertas para operações de reabastecimento.

O firmware executa uma máquina de estados não-bloqueante que lê continuamente o sensor HX711 e classifica o peso em diferentes faixas de segurança, impedindo paradas de linha de produção por falta de componentes.

---

## Arquitetura do Sistema Embarcado

### Fluxo Principal

```
BOOT (inicializa GPIO e Serial)
  ↓
Imprime: "Sistema Kanban Inicializado"
  ↓
MONITOR (loop principal não-bloqueante)
  ├─ Lê peso do HX711 a cada 100ms via GPIO19/GPIO18
  ├─ Compara com thresholds
  ├─ Atualiza máquina de estados
  └─ Imprime mensagens de transição (uma única vez por estado)
```

### Máquina de Estados

| Estado | Entrada | Ação | Saída |
|:---|:---|:---|:---|
| **ANOMALIA** | weight == 0g | Imprime alerta crítico (1x) | Aguarda > 0g |
| **VAZIO** | weight ≤ 150g | Imprime evento reposição (1x) | Aguarda ≥ 150g |
| **REGULAR** | 150g < weight < 5000g | Imprime status dinâmico | Aguarda mudança |
| **ABASTECIDO** | weight ≥ 5000g após VAZIO | Imprime conclusão (1x) | Retorna MONITOR |
| **MONITOR** | Padrão | Aguarda transição | Qualquer mudança |

### Temporização Não-Bloqueante

```python
# Loop principal (simplificado)
while True:
    current_time = time.ticks_ms()
    if current_time - last_read_time >= 100:  # 100ms
        weight = read_hx711()
        update_state_machine(weight)
        last_read_time = current_time
    time.sleep_ms(10)  # Cede CPU
```

---

## Componentes Utilizados na Simulação

### Hardware (diagram.json)

1. **ESP32 DevKit C v4** 
   - Microcontrolador principal
   - Clock: 80-160 MHz
   - GPIO: 34 pinos
   - Serial: UART 115200 baud

2. **HX711 - Conversor ADC para Célula de Carga**
   - ID: `hx711` (conforme CI)
   - Pino Data (DT): GPIO19
   - Pino Clock (SCK): GPIO18
   - Alimentação: 5V (ESP32)
   - GND: Comum
   - Leitura: 0-5000g (simulada)

3. **Serial Monitor**
   - Baudrate: 115200
   - Protocolo: UART
   - Função: Validação de strings pela CI

### Conexões (diagram.json)

```
ESP32 GPIO19 ──── HX711 DT
ESP32 GPIO18 ──── HX711 SCK
ESP32 5V ────────── HX711 VCC
ESP32 GND ────────── HX711 GND
ESP32 TX ──────────── Serial RX
ESP32 RX ──────────── Serial TX
```

---

## Funcionamento Detalhado

### Inicialização

1. ESP32 liga e executa `src/main.py`
2. Configura GPIO19 (DT) como entrada
3. Configura GPIO18 (SCK) como saída
4. Inicializa comunicação Serial (115200)
5. Imprime: `"Sistema Kanban Inicializado"`
6. Entra em loop principal

### Leitura de Peso

A cada 100ms:
1. `read_weight_safe()` lê GPIO19 e GPIO18
2. No Wokwi, retorna valor injetado pela API (0-5000g)
3. Passa para `update_state_machine(weight)`

### Transições com Flags

Para evitar repetição contínua:

```python
# Flag: alerta_vazio_printed (False → True → reset)
if weight <= 150 and not alerta_vazio_printed:
    print("Evento de reposição disparado! Caixa vazia detectada.")
    alerta_vazio_printed = True
```

Flags resetam ao sair do estado.

### Exemplo: Ciclo VAZIO → ABASTECIDO

```
T=100ms: weight=5000g → MONITOR (sem ação)
T=200ms: weight=150g → VAZIO
        print("Evento de reposição disparado! Caixa vazia detectada.")
        alerta_vazio_printed=True
T=300ms: weight=150g → VAZIO (sem ação, flag=True)
T=1000ms: weight=5000g → ABASTECIDO
         print("Abastecimento concluído. Caixa cheia.")
         alerta_abastecido_printed=True
         current_state=MONITOR
T=1100ms: weight=5000g → MONITOR (reinicia ciclo)
```

---

## Especificação de Strings Serial (Exatas)

As strings abaixo são **case-sensitive** e validadas caractere por caractere pela CI:

| ID | Mensagem | Contexto | Flag | Test |
|:---|:---|:---|:---|:---|
| S1 | `Sistema Kanban Inicializado` | Boot | - | Todos |
| S2 | `Status: Estoque Regular (XXg)` | REGULAR (dinâmico) | `status_regular_weight_printed` | test_1 |
| S3 | `Evento de reposição disparado! Caixa vazia detectada.` | VAZIO | `alerta_vazio_printed` | test_2 |
| S4 | `Abastecimento concluído. Caixa cheia.` | ABASTECIDO | `alerta_abastecido_printed` | test_2 |
| S5 | `ALERTA: Caixa ausente ou erro de calibração no sensor HX711!` | ANOMALIA (0g) | `alerta_anomalia_printed` | test_3 |

**Nota:** String S2 usa f-string dinâmica: `f"Status: Estoque Regular ({weight}g)"` sem decimais.

---

## Decisões Técnicas Relevantes

### 1. Temporização Não-Bloqueante

**Decisão:** Usar `time.ticks_ms()` em vez de `time.sleep()` longo.

**Justificativa:**
- Wokwi injeta eventos durante execução (não espera `sleep()`)
- Loops bloqueantes causam timeout nos testes
- Permite resposta rápida a mudanças de peso

**Código:**
```python
if current_time - last_read_time >= 100:
    # Processar leitura
    last_read_time = current_time
```

### 2. Flags de Transição Única

**Decisão:** Bandeira booleana por alerta (não imprimir repetidamente).

**Justificativa:**
- CI aguarda string exata via `wait-serial`
- Múltiplas impressões = confusão no parser
- Flags resetam ao sair do estado

### 3. Thresholds Fixos (Confirmados nos Testes)

```python
EMPTY_THRESHOLD = 150    # test_2: caixa vazia
FULL_THRESHOLD = 5000    # Carga máxima nominal
ANOMALY_VALUE = 0        # test_3: erro de hardware
```

### 4. String Dinâmica para Status Regular

**Implementação:**
```python
print(f"Status: Estoque Regular ({weight}g)")
```

**Por quê:** test_1 aguarda exatamente `"Status: Estoque Regular (2500g)"` com peso variável.

### 5. Anomalia Independente de Vazio

**Decisão:** 0g **não** dispara evento de reposição.

**Justificativa:**
- 0g = ausência de caixa (erro crítico, não estoque vazio)
- Evita reabastecimento automático para falha de hardware
- Requer intervenção manual de manutenção

---

## Testes Automatizados (CI)

### Test 1: Consumo Parcial (test_1.yaml)

```yaml
Sequência:
  1. Aguarda: "Sistema Kanban Inicializado"
  2. Set hx711 load=5000, delay 1s
  3. Set hx711 load=2500, delay 2s
  4. Aguarda: "Status: Estoque Regular (2500g)"

Máquina de Estados:
  BOOT → MONITOR (print init)
  ─→ weight=5000g (nenhuma ação)
  ─→ weight=2500g (REGULAR, imprime status)

Validação: ✅ String com peso dinâmico
```

---

### Test 2: Ciclo Completo (test_2.yaml)

```yaml
Sequência:
  1. Aguarda: "Sistema Kanban Inicializado"
  2. Set hx711 load=150
  3. Aguarda: "Evento de reposição disparado! Caixa vazia detectada."
  4. Delay 1s
  5. Set hx711 load=5000
  6. Aguarda: "Abastecimento concluído. Caixa cheia."

Máquina de Estados:
  BOOT → MONITOR (print init)
  ─→ weight=150g (VAZIO, alerta 1x, flag=True)
  ─→ weight=5000g (ABASTECIDO, conclusão 1x, flag=True)
  ─→ Retorna MONITOR

Validação: ✅ Ambas strings na sequência correta
```

---

### Test 3: Anomalia de Leitura (test_3.yaml)

```yaml
Sequência:
  1. Aguarda: "Sistema Kanban Inicializado"
  2. Set hx711 load=5000, delay 1s
  3. Set hx711 load=0
  4. Aguarda: "ALERTA: Caixa ausente ou erro de calibração no sensor HX711!"

Máquina de Estados:
  BOOT → MONITOR (print init)
  ─→ weight=5000g (nenhuma ação)
  ─→ weight=0g (ANOMALIA, alerta crítico 1x, flag=True)

Validação: ✅ Detecção de 0g com alerta exato
```

---

## Ambiguidades Resolvidas

### A. "Dinâmico" em "Status: Estoque Regular (XXg)"?

**Resposta:** Sim, peso muda dinamicamente via f-string. Sem decimais (int).  
Exemplo: `"Status: Estoque Regular (2500g)"` não `"Status: Estoque Regular (2500.0g)"`

### B. Anomalia (0g) pode ocorrer após Vazio (150g)?

**Resposta:** Sim. Se peso pula 150→0, ambas as flags resetam e ANOMALIA ativa.

### C. Reabastecimento (5000g) direto de REGULAR?

**Resposta:** Não dispara ABASTECIDO. ABASTECIDO só ocorre após VAZIO. Se peso pula 2500→5000, vai direto a MONITOR.

### D. Qual baudrate?

**Resposta:** 115200 (padrão Wokwi/ESP32). Hardcoded em MicroPython.

### E. Loop roda indefinidamente?

**Resposta:** Sim, até Ctrl+C ou reset. CI mata processo após timeout do teste.

---

## Arquivos Alterados e Status

✅ **src/main.py**
- Implementação completa de máquina de estados
- 5 classes/funções principais: HX711, read_weight_safe, handle_state_transition, update_state_machine, main_loop
- ~200 linhas de código

✅ **diagram.json**
- ESP32 DevKit C v4
- HX711 com ID="hx711", GPIO19/GPIO18
- Conexões seriais e de alimentação

✅ **scenarios/WEIGHT.txt**
- Arquivo indicador vazio (ativa seleção WEIGHT na CI)

✅ **README.md**
- Este relatório técnico completo
- Substitui template original

---

## Resumo de Implementação

**Componentes:**
- ESP32 + HX711 (SPI simulado)
- Serial 115200 baud

**Estados:**
- BOOT → MONITOR → {ANOMALIA | VAZIO | REGULAR | ABASTECIDO}

**Strings Exatas (5):**
- Boot message
- Dynamic status (2 exemplos: 2500g, etc)
- Empty event
- Replenishment conclusion  
- Critical alert

**Testes:**
- Test 1: Peso regular dinâmico
- Test 2: Ciclo completo (vazio + reabastecimento)
- Test 3: Anomalia de hardware

**Temporização:**
- 100ms por leitura (não-bloqueante)
- Flags evitam repetição
- CI valida em ~2-3 segundos por teste

O sistema está pronto para commit e execução na GitHub Actions. ✅
