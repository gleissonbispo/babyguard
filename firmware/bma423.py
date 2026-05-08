"""
BMA423 Accelerometer Driver for MicroPython.

Driver simplificado para o BabyGuard — foca em leitura de aceleração
e detecção de orientação.

Autor: BabyGuard Project
Referência: BMA423 Datasheet — Bosch Sensortec
"""
from machine import I2C
import struct
import time

# Constantes
BMA423_ADDR = 0x19
GRAVITY = 9.80665  # m/s²

# Registradores
REG_CHIP_ID   = 0x00
REG_ACC_DATA  = 0x12  # 6 bytes: X_LSB, X_MSB, Y_LSB, Y_MSB, Z_LSB, Z_MSB
REG_ACC_CONF  = 0x40
REG_ACC_RANGE = 0x41
REG_PWR_CONF  = 0x7C
REG_PWR_CTRL  = 0x7D
REG_CMD       = 0x7E

# Configurações de range
RANGE_2G  = 0x00  # ±2g  (mais sensível)
RANGE_4G  = 0x01  # ±4g
RANGE_8G  = 0x02  # ±8g
RANGE_16G = 0x03  # ±16g

# Fator de escala por range (LSB → g)
SCALE_FACTOR = {
    RANGE_2G:  2.0 / 2048.0,
    RANGE_4G:  4.0 / 2048.0,
    RANGE_8G:  8.0 / 2048.0,
    RANGE_16G: 16.0 / 2048.0,
}


class BMA423:
    """Driver do acelerômetro BMA423."""

    def __init__(self, i2c: I2C, addr: int = BMA423_ADDR, acc_range: int = RANGE_2G):
        self.i2c = i2c
        self.addr = addr
        self.acc_range = acc_range
        self.scale = SCALE_FACTOR[acc_range]

        # Verificar se o chip está presente
        chip_id = self._read_byte(REG_CHIP_ID)
        if chip_id not in (0x11, 0x13):
            raise RuntimeError(
                f"BMA42x não encontrado! Chip ID: 0x{chip_id:02X} (esperado: 0x11 ou 0x13)"
            )
        chip_name = "BMA423" if chip_id == 0x11 else "BMA425"
        print(f"{chip_name} detectado (Chip ID: 0x{chip_id:02X})")

        # Inicializar o acelerômetro
        self._init_sensor()

    def _read_byte(self, reg: int) -> int:
        """Lê 1 byte de um registrador."""
        return self.i2c.readfrom_mem(self.addr, reg, 1)[0]

    def _write_byte(self, reg: int, value: int):
        """Escreve 1 byte em um registrador."""
        self.i2c.writeto_mem(self.addr, reg, bytes([value]))

    def _read_bytes(self, reg: int, length: int) -> bytes:
        """Lê múltiplos bytes a partir de um registrador."""
        return self.i2c.readfrom_mem(self.addr, reg, length)

    def _init_sensor(self):
        """Inicializa o BMA423 para leitura de aceleração."""
        # 1. Desabilitar advance power save (necessário para leitura contínua)
        self._write_byte(REG_PWR_CONF, 0x00)
        time.sleep_ms(10)

        # 2. Habilitar o acelerômetro
        self._write_byte(REG_PWR_CTRL, 0x04)
        time.sleep_ms(10)

        # 3. Configurar taxa de amostragem e modo
        # Bits [3:0] = ODR (Output Data Rate): 0x08 = 100Hz
        # Bits [6:4] = bandwidth: 0x02 = normal mode
        # Bit  [7]   = perf_mode: 1 = continuous mode
        self._write_byte(REG_ACC_CONF, 0xA8)  # 100Hz, normal, continuous
        time.sleep_ms(10)

        # 4. Configurar range (±2g por padrão — mais sensível)
        self._write_byte(REG_ACC_RANGE, self.acc_range)
        time.sleep_ms(10)

        print(f"BMA423 inicializado — Range: ±{2 << self.acc_range}g, ODR: 100Hz")

    def read_raw(self) -> tuple:
        """
        Lê os valores raw do acelerômetro.

        Returns:
            tuple: (raw_x, raw_y, raw_z) — valores de -2048 a +2047
        """
        data = self._read_bytes(REG_ACC_DATA, 6)

        # Os dados são little-endian, 12 bits com sinal, justificados à esquerda
        # Precisamos fazer shift right de 4 bits
        raw_x = struct.unpack_from('<h', data, 0)[0] >> 4
        raw_y = struct.unpack_from('<h', data, 2)[0] >> 4
        raw_z = struct.unpack_from('<h', data, 4)[0] >> 4

        return (raw_x, raw_y, raw_z)

    def read_accel(self) -> tuple:
        """
        Lê a aceleração em m/s².

        Returns:
            tuple: (ax, ay, az) em m/s²
        """
        raw_x, raw_y, raw_z = self.read_raw()

        ax = raw_x * self.scale * GRAVITY
        ay = raw_y * self.scale * GRAVITY
        az = raw_z * self.scale * GRAVITY

        return (ax, ay, az)

    def read_g(self) -> tuple:
        """
        Lê a aceleração em unidades de g (1g = 9.8 m/s²).

        Returns:
            tuple: (gx, gy, gz) em g
        """
        raw_x, raw_y, raw_z = self.read_raw()

        gx = raw_x * self.scale
        gy = raw_y * self.scale
        gz = raw_z * self.scale

        return (gx, gy, gz)

    def get_position(self) -> str:
        """
        Determina a posição do dispositivo baseado no eixo Z.

        Returns:
            str: "UP" (barriga pra cima), "DOWN" (barriga pra baixo), "SIDE" (de lado)
        """
        _, _, az = self.read_accel()

        if az > 6.0:    # Z positivo → display para cima
            return "UP"
        elif az < -6.0:  # Z negativo → display para baixo
            return "DOWN"
        else:
            return "SIDE"

    def get_full_reading(self) -> dict:
        """
        Retorna leitura completa formatada para envio.

        Returns:
            dict: {ax, ay, az, position}
        """
        ax, ay, az = self.read_accel()

        if az > 6.0:
            position = "UP"
        elif az < -6.0:
            position = "DOWN"
        else:
            position = "SIDE"

        return {
            "ax": round(ax, 2),
            "ay": round(ay, 2),
            "az": round(az, 2),
            "pos": position,
        }