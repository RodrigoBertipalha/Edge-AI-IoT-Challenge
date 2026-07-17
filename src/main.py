"""
Monitor de Estoque Kanban Inteligente - WEIGHT Scenario
ESP32 + HX711 Weight Sensor
"""

import time
from machine import Pin


class HX711:
    """
    Driver HX711 para Wokwi (MicroPython).
    Implementa protocolo serial de 25 bits (24 dados + 1 controle).
    """
    def __init__(self, dout_pin=19, sck_pin=18):
        self.dout = Pin(dout_pin, Pin.IN)
        self.sck = Pin(sck_pin, Pin.OUT)
        self.sck.off()
        time.sleep_ms(100)
    
    def read_raw(self):
        """
        Lê 25 bits do HX711: 24 bits de dados + 1 bit de seleção de ganho/canal.
        Retorna valor bruto (inteiro de 24 bits com sinal).
        """
        try:
            # Aguardar DOUT = 0 (dados prontos)
            timeout = 0
            while self.dout.value() == 1 and timeout < 1000:
                timeout += 1
                time.sleep_us(10)
            
            if timeout >= 1000:
                return 0  # Timeout
            
            # Ler 25 bits
            data = 0
            for i in range(25):
                self.sck.on()
                time.sleep_us(1)
                data = (data << 1) | self.dout.value()
                self.sck.off()
                time.sleep_us(1)
            
            # Converter para inteiro com sinal (24 bits)
            # Se bit 23 (MSB) é 1, valor é negativo (complemento a 2)
            if data & 0x800000:  # Se bit 23 = 1
                data = data - 0x1000000  # Converter para negativo
            
            return data
        except:
            return 0
    
    def get_weight(self):
        """
        Lê peso em gramas.
        No Wokwi, o HX711 simula diretamente o valor injetado via set-control.
        """
        try:
            raw = self.read_raw()
            # Wokwi fornece valor aproximado diretamente
            # Conversão simplificada: raw ~= peso em gramas (para escala 5kg)
            # Ajustar scale conforme necessário
            weight = max(0, raw)  # Não permitir pesos negativos
            return weight
        except:
            return 0


# Inicialização
print("Sistema Kanban Inicializado")

# Configuração do HX711
try:
    hx711 = HX711(dout_pin=19, sck_pin=18)
except:
    hx711 = None

# Estados da máquina
STATE_BOOT = "BOOT"
STATE_MONITOR = "MONITOR"
STATE_VAZIO = "VAZIO"
STATE_REGULAR = "REGULAR"
STATE_ABASTECIDO = "ABASTECIDO"
STATE_ANOMALIA = "ANOMALIA"

# Thresholds
EMPTY_THRESHOLD = 150  # g
FULL_THRESHOLD = 5000  # g
ANOMALY_VALUE = 0  # g

# Variáveis de estado
current_state = STATE_BOOT
last_state = STATE_BOOT
last_weight = 5000
current_weight = 5000

# Flags para imprimir mensagens uma única vez
alerta_vazio_printed = False
alerta_abastecido_printed = False
alerta_anomalia_printed = False
status_regular_weight_printed = -1

# Timing
loop_delay_ms = 100
last_read_time = time.ticks_ms()


def read_weight_safe():
    """
    Lê peso do sensor com tratamento de erro.
    Retorna peso em gramas.
    """
    try:
        if hx711:
            weight = hx711.get_weight()
            return int(weight) if weight > 0 else 0
        return 5000
    except:
        return 5000


def handle_state_transition(new_state, weight):
    """
    Gerencia transições de estado e impressão de mensagens.
    """
    global current_state, last_state
    global alerta_vazio_printed, alerta_abastecido_printed
    global alerta_anomalia_printed, status_regular_weight_printed
    
    current_state = new_state
    
    if new_state == STATE_ANOMALIA:
        if not alerta_anomalia_printed:
            print("ALERTA: Caixa ausente ou erro de calibração no sensor HX711!")
            alerta_anomalia_printed = True
            alerta_vazio_printed = False
            alerta_abastecido_printed = False
            status_regular_weight_printed = -1
    
    elif new_state == STATE_VAZIO:
        if not alerta_vazio_printed:
            print("Evento de reposição disparado! Caixa vazia detectada.")
            alerta_vazio_printed = True
            alerta_anomalia_printed = False
            status_regular_weight_printed = -1
    
    elif new_state == STATE_REGULAR:
        if status_regular_weight_printed != weight:
            print(f"Status: Estoque Regular ({weight}g)")
            status_regular_weight_printed = weight
            alerta_anomalia_printed = False
    
    elif new_state == STATE_ABASTECIDO:
        if not alerta_abastecido_printed:
            print("Abastecimento concluído. Caixa cheia.")
            alerta_abastecido_printed = True
            alerta_vazio_printed = False
            alerta_anomalia_printed = False
            status_regular_weight_printed = -1


def update_state_machine(weight):
    """
    Atualiza máquina de estados baseado no peso lido.
    """
    global current_state, last_state, last_weight
    
    last_state = current_state
    
    # Detecção de anomalia (0g) - prioridade máxima
    if weight == ANOMALY_VALUE:
        if current_state != STATE_ANOMALIA:
            handle_state_transition(STATE_ANOMALIA, weight)
    
    # Detecção de caixa vazia
    elif weight <= EMPTY_THRESHOLD:
        if current_state != STATE_VAZIO and current_state != STATE_ANOMALIA:
            handle_state_transition(STATE_VAZIO, weight)
    
    # Detecção de reabastecimento (volta ao cheio após estar vazio)
    elif weight >= FULL_THRESHOLD:
        if current_state == STATE_VAZIO:
            handle_state_transition(STATE_ABASTECIDO, weight)
            # Depois volta a MONITOR
            current_state = STATE_MONITOR
        elif current_state != STATE_ABASTECIDO and current_state != STATE_BOOT:
            # Mantém estado regular ou monitor
            if current_state != STATE_REGULAR:
                handle_state_transition(STATE_MONITOR, weight)
    
    # Estado regular (entre limiares)
    elif EMPTY_THRESHOLD < weight < FULL_THRESHOLD:
        if current_state != STATE_REGULAR:
            handle_state_transition(STATE_REGULAR, weight)
        else:
            # Já está em regular, mas peso mudou
            if status_regular_weight_printed != weight:
                print(f"Status: Estoque Regular ({weight}g)")
                status_regular_weight_printed = weight
    
    # Monitor padrão
    else:
        if current_state == STATE_BOOT or current_state == STATE_MONITOR:
            current_state = STATE_MONITOR
    
    last_weight = weight


# Loop principal
def main_loop():
    """
    Loop principal não-bloqueante.
    """
    global last_read_time, current_weight
    
    while True:
        # Temporização não-bloqueante
        current_time = time.ticks_ms()
        
        if current_time - last_read_time >= loop_delay_ms:
            last_read_time = current_time
            
            # Lê peso do sensor
            current_weight = read_weight_safe()
            
            # Atualiza máquina de estados
            update_state_machine(current_weight)
        
        # Evita consumo excessivo de CPU
        time.sleep_ms(10)


# Executa loop principal
try:
    main_loop()
except KeyboardInterrupt:
    print("Sistema finalizado.")
except Exception as e:
    print(f"Erro: {e}")
