"""
Modelo del sistema de pago de parqueaderos del Centro Comercial Supercentro.

Cada punto de salida tiene varios cajeros; cada cajero es una cola M/M/1 con su propia fila
(sin cambio de fila ni deserción). Los clientes son de 4 tipos con distinta velocidad.

Dos formas de generar las llegadas (decisión del grupo):
  - "un_flujo"   (supuesto BASE): un solo flujo de llegadas. Cuando llega un cliente se sortea
                  su tipo (25 / 20 / 27.5 / 27.5 %) y el tiempo hasta la siguiente llegada
                  usa la media de ese tipo. Así se cumplen los porcentajes del enunciado.
  - "por_tipo"   (escenario de SENSIBILIDAD): cada tipo llega por su cuenta, con su propia
                  media de llegada (como calcula el laboratorio). Hay mucha más demanda.
En ambos casos cada cliente se asigna al azar a uno de los cajeros.
"""
import numpy as np

TIPOS = ["Rápido", "Normal", "Lento", "Muy lento"]
SERVICIO = [1, 3, 4, 6]          # media del tiempo de servicio (min)
LLEGADA = [3, 3, 5, 7]           # media del tiempo entre llegadas (min)
PROB = [0.25, 0.20, 0.275, 0.275]
DURACION = 1000                  # minutos simulados por réplica (como el laboratorio)


def generar_llegadas(modo, duracion, rng, tipos_activos=None):
    """Devuelve una lista ordenada de (hora_llegada, tipo)."""
    tipos_activos = range(4) if tipos_activos is None else tipos_activos
    llegadas = []
    if modo == "un_flujo":
        t = 0.0
        while True:
            tipo = int(rng.choice(4, p=PROB))
            t += rng.exponential(LLEGADA[tipo])        # tiempo hasta este cliente
            if t > duracion:
                break
            llegadas.append((t, tipo))
    elif modo == "por_tipo":
        for tipo in tipos_activos:                     # cada tipo es un flujo de Poisson aparte
            t = rng.exponential(LLEGADA[tipo])
            while t <= duracion:
                llegadas.append((t, tipo))
                t += rng.exponential(LLEGADA[tipo])
        llegadas.sort()
    else:
        raise ValueError(modo)
    return llegadas


def simular(n_cajeros, modo, semilla, duracion=DURACION, tipos_activos=None):
    """Simula una réplica. Devuelve una lista con un registro por cliente."""
    rng = np.random.default_rng(semilla)
    llegadas = generar_llegadas(modo, duracion, rng, tipos_activos)
    libre_desde = [0.0] * n_cajeros                    # cuándo queda libre cada cajero
    clientes = []
    for n, (t, tipo) in enumerate(llegadas, start=1):
        cajero = int(rng.integers(n_cajeros))          # asignación al azar
        servicio = rng.exponential(SERVICIO[tipo])
        inicio = max(t, libre_desde[cajero])           # espera si el cajero está ocupado
        fin = inicio + servicio
        libre_desde[cajero] = fin
        clientes.append({"cliente": n, "cajero": cajero + 1, "tipo_usuario": TIPOS[tipo],
                         "llegada": t, "inicio": inicio, "fin": fin, "espera": inicio - t,
                         "servicio": servicio, "tiempo_sistema": fin - t})
    return clientes


def teorico(n_cajeros, modo):
    """Valores de referencia de la teoría M/M/1 para UN cajero (λ, μ, ρ, Wq, W, L, Lq)."""
    if modo == "un_flujo":
        lam_total = 1 / sum(p * m for p, m in zip(PROB, LLEGADA))
        es = sum(p * s for p, s in zip(PROB, SERVICIO))
    else:
        tasas = [1 / m for m in LLEGADA]
        lam_total = sum(tasas)
        es = sum(l * s for l, s in zip(tasas, SERVICIO)) / lam_total
    lam = lam_total / n_cajeros
    mu = 1 / es
    rho = lam / mu
    if rho >= 1:
        return {"lambda": lam, "mu": mu, "rho": rho, "Wq": np.inf, "W": np.inf, "L": np.inf, "Lq": np.inf}
    wq = rho / (mu - lam)
    w = 1 / (mu - lam)
    return {"lambda": lam, "mu": mu, "rho": rho, "Wq": wq, "W": w, "L": lam * w, "Lq": lam * wq}
