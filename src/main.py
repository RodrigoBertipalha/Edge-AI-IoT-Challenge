import time
from machine import Pin


class HX711:
    SCALE = 420

    def __init__(self, dout_pin=19, sck_pin=18):
        self.dout = Pin(dout_pin, Pin.IN, Pin.PULL_UP)
        self.sck = Pin(sck_pin, Pin.OUT)
        self.sck.value(0)

    def _read_raw(self):
        start = time.ticks_ms()
        while self.dout.value() == 1:
            if time.ticks_diff(time.ticks_ms(), start) > 150:
                return None

        value = 0
        for _ in range(24):
            self.sck.value(1)
            value = (value << 1) | self.dout.value()
            self.sck.value(0)

        self.sck.value(1)
        self.sck.value(0)

        if value & 0x800000:
            value -= 0x1000000
        return value

    def read_weight_grams(self):
        raw = self._read_raw()
        if raw is None:
            return None
        return int(raw / self.SCALE)


EMPTY_THRESHOLD = 150
FULL_THRESHOLD = 5000
LOOP_INTERVAL_MS = 100

STATE_INIT = "INIT"
STATE_MONITOR = "MONITOR"
STATE_REGULAR = "REGULAR"
STATE_VAZIO = "VAZIO"
STATE_ABASTECIDO = "ABASTECIDO"
STATE_ANOMALIA = "ANOMALIA"


def reset_flags(keep, flags):
    if keep != "vazio":
        flags["vazio"] = False
    if keep != "abastecido":
        flags["abastecido"] = False
    if keep != "anomalia":
        flags["anomalia"] = False
    if keep != "regular":
        flags["regular_weight"] = None


def apply_transition(new_state, weight, state, flags):
    if new_state == STATE_ANOMALIA:
        if not flags["anomalia"]:
            print("ALERTA: Caixa ausente ou erro de calibração no sensor HX711!")
            reset_flags("anomalia", flags)
            flags["anomalia"] = True
    elif new_state == STATE_VAZIO:
        if not flags["vazio"]:
            print("Evento de reposição disparado! Caixa vazia detectada.")
            reset_flags("vazio", flags)
            flags["vazio"] = True
    elif new_state == STATE_ABASTECIDO:
        if not flags["abastecido"]:
            print("Abastecimento concluído. Caixa cheia.")
            reset_flags("abastecido", flags)
            flags["abastecido"] = True
    elif new_state == STATE_REGULAR:
        if flags["regular_weight"] != weight:
            print("Status: Estoque Regular ({}g)".format(weight))
            reset_flags("regular", flags)
            flags["regular_weight"] = weight

    state["current"] = new_state


def update_state(weight, state, flags):
    current = state["current"]

    if current == STATE_INIT:
        if weight is None or weight == 0:
            return
        if weight <= EMPTY_THRESHOLD:
            apply_transition(STATE_VAZIO, weight, state, flags)
        elif weight >= FULL_THRESHOLD:
            state["current"] = STATE_MONITOR
        else:
            apply_transition(STATE_REGULAR, weight, state, flags)
        return

    if weight is None:
        return

    if weight == 0:
        apply_transition(STATE_ANOMALIA, weight, state, flags)
        return

    if weight <= EMPTY_THRESHOLD:
        apply_transition(STATE_VAZIO, weight, state, flags)
        return

    if weight >= FULL_THRESHOLD:
        if current == STATE_VAZIO:
            apply_transition(STATE_ABASTECIDO, weight, state, flags)
        else:
            state["current"] = STATE_MONITOR
        return

    apply_transition(STATE_REGULAR, weight, state, flags)


def main():
    print("Sistema Kanban Inicializado")

    sensor = HX711(dout_pin=19, sck_pin=18)
    state = {"current": STATE_INIT}
    flags = {
        "vazio": False,
        "abastecido": False,
        "anomalia": False,
        "regular_weight": None,
    }

    last_tick = time.ticks_ms()
    while True:
        now = time.ticks_ms()
        if time.ticks_diff(now, last_tick) >= LOOP_INTERVAL_MS:
            last_tick = now
            weight = sensor.read_weight_grams()
            update_state(weight, state, flags)
        time.sleep_ms(10)


try:
    main()
except Exception as exc:
    print("Erro fatal: {}".format(exc))
