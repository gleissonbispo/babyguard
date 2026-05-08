"""
boot.py — Executado automaticamente quando o ESP32 liga.
Não colocamos lógica pesada aqui, apenas configurações básicas.
O main.py é executado logo depois.
"""
import gc

# Liberar memória
gc.collect()

print("\n  🍼 BabyGuard T-Watch 2020")
print(f"  Memória livre: {gc.mem_free()} bytes")