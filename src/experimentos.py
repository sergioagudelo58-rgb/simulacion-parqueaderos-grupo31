"""
Experimentos del problema de parqueaderos (Supercentro).

Pasos que hace este script (uso: python src/experimentos.py, desde la carpeta raíz):
  1. Estado estable: corre réplicas piloto, grafica el promedio móvil del tiempo en el sistema
     y encuentra el punto de corte del periodo de calentamiento (warm-up).
  2. Número de réplicas: calcula cuántas réplicas hacen falta para un error relativo del 5 %.
  3. Corre todos los escenarios con ese número de réplicas.
  4. Calcula lo que piden los Puntos 1 a 5 y guarda tablas (Excel/CSV) y gráficas (Matplotlib).
"""
import os
import sys
import math
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parqueadero import simular, teorico, TIPOS, PROB, DURACION

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
RES = os.path.join(RAIZ, "resultados")
FIG = os.path.join(RAIZ, "figuras")

SEMILLA_BASE = 1000      # réplica r usa la semilla 1000 + r
REPLICAS_PILOTO = 20     # réplicas para ver el estado estable
INTERVALO = 10           # ancho de cada intervalo de tiempo (min) para el promedio móvil
VENTANA = 5              # ventana del promedio móvil (en intervalos) = 50 min
TOLERANCIA = 0.05        # el estado estable empieza cuando la curva llega al 95 % de su nivel final
ERROR_OBJETIVO = 0.05    # error relativo deseado para la media (5 %)
CRITERIOS = {"Wq": 3, "W": 5, "rho_max": 0.85, "Lq": 3, "p_espera_5": 0.10}   # tabla del laboratorio

ESCENARIOS = [  # (nombre, cajeros, modo de llegadas)
    ("Base_3_cajeros", 3, "un_flujo"),
    ("Base_4_cajeros", 4, "un_flujo"),
    ("Base_5_cajeros", 5, "un_flujo"),
    ("Sensibilidad_3_cajeros", 3, "por_tipo"),
    ("Sensibilidad_4_cajeros", 4, "por_tipo"),
]
AZUL, NARANJA, AQUA, AMARILLO, GRIS = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#888780"


def ic95(x):
    x = np.asarray(x, dtype=float)
    m, s, n = x.mean(), x.std(ddof=1), len(x)
    h = stats.t.ppf(0.975, n - 1) * s / math.sqrt(n)
    return m, s, m - h, m + h


def correr(cajeros, modo, replicas):
    dfs = []
    for r in range(1, replicas + 1):
        df = pd.DataFrame(simular(cajeros, modo, SEMILLA_BASE + r))
        df.insert(0, "replica", r)
        dfs.append(df)
    return pd.concat(dfs, ignore_index=True)


# ------------------------------------------------------------------ 1. estado estable
def promedio_movil(df):
    """Tiempo en el sistema promedio por intervalo de 10 min (promediando réplicas) y su promedio móvil."""
    d = df.assign(intervalo=(df["llegada"] // INTERVALO).astype(int))
    serie = d.groupby("intervalo")["tiempo_sistema"].mean()
    movil = serie.rolling(VENTANA, min_periods=1).mean()
    return serie, movil


def punto_de_corte(movil):
    """Primer instante en que el promedio móvil llega al 95 % del nivel estable (media de la 2.ª mitad).
    Si la curva sigue creciendo (2.ª mitad mucho mayor que la 1.ª), no hay estado estable."""
    n = len(movil)
    nivel = movil.iloc[n // 2:].mean()
    crece = movil.iloc[3 * n // 4:].mean() > 1.20 * movil.iloc[n // 4: n // 2].mean()
    if crece:
        return None, nivel
    k = int(np.argmax(movil.values >= (1 - TOLERANCIA) * nivel))
    return (k + 1) * INTERVALO, nivel


def replicas_necesarias(valores):
    m, s, _, _ = ic95(valores)
    t = stats.t.ppf(0.975, len(valores) - 1)
    return math.ceil((t * s / (ERROR_OBJETIVO * m)) ** 2)


def main():
    os.makedirs(RES, exist_ok=True)
    os.makedirs(FIG, exist_ok=True)

    # ---- 1. Estado estable con réplicas piloto
    cortes, curvas = {}, {}
    for nombre, c, modo in ESCENARIOS:
        piloto = correr(c, modo, REPLICAS_PILOTO)
        serie, movil = promedio_movil(piloto)
        corte, nivel = punto_de_corte(movil)
        cortes[nombre] = corte
        curvas[nombre] = (serie, movil, corte, nivel)
    estado = pd.DataFrame([{"escenario": n, "punto_corte_min": cortes[n] if cortes[n] is not None else "No estable",
                            "nivel_estable_W_min": round(curvas[n][3], 3)} for n, _, _ in ESCENARIOS])

    # ---- 2. Número de réplicas (escenario base, sin el transitorio)
    piloto_base = correr(3, "un_flujo", REPLICAS_PILOTO)
    piloto_base = piloto_base[piloto_base["llegada"] >= cortes["Base_3_cajeros"]]
    w_por_rep = piloto_base.groupby("replica")["tiempo_sistema"].mean()
    n_req = replicas_necesarias(w_por_rep)
    REPLICAS = max(n_req, 10)
    print(f"Punto de corte (base): {cortes['Base_3_cajeros']} min | réplicas necesarias: {n_req} -> se usan {REPLICAS}")

    # ---- 3. Corridas finales
    datos = {n: correr(c, modo, REPLICAS) for n, c, modo in ESCENARIOS}
    def estable(nombre):
        corte = cortes[nombre] or 0
        return datos[nombre][datos[nombre]["llegada"] >= corte]

    base = estable("Base_3_cajeros")

    # ---- Punto 1: tiempo de atención por cajero (escenario base)
    p1 = []
    for caj, g in base.groupby("cajero"):
        por_rep = g.groupby("replica")["servicio"].mean()
        m, s, lo, hi = ic95(por_rep)
        p1.append({"cajero": caj, "clientes_promedio": round(len(g) / REPLICAS, 1), "media_min": m, "de_min": s,
                   "min_individual": g["servicio"].min(), "max_individual": g["servicio"].max(),
                   "ic95_inf": lo, "ic95_sup": hi})
    p1 = pd.DataFrame(p1)
    anova = stats.f_oneway(*[g.groupby("replica")["servicio"].mean() for _, g in base.groupby("cajero")])

    # ---- Punto 2: usuarios por tipo (escenario base)
    conteo = base.groupby(["replica", "tipo_usuario"]).size().unstack(fill_value=0)[TIPOS]
    p2 = []
    for i, tipo in enumerate(TIPOS):
        m, s, lo, hi = ic95(conteo[tipo])
        g = base[base["tipo_usuario"] == tipo]
        p2.append({"tipo_usuario": tipo, "usuarios_promedio": m, "de": s, "ic95_inf": lo, "ic95_sup": hi,
                   "porcentaje_simulado": conteo[tipo].sum() / conteo.values.sum(), "porcentaje_esperado": PROB[i],
                   "servicio_prom_min": g["servicio"].mean(), "espera_prom_min": g["espera"].mean(),
                   "sistema_prom_min": g["tiempo_sistema"].mean()})
    p2 = pd.DataFrame(p2)
    chi = stats.chisquare(conteo.sum().values, f_exp=np.array(PROB) * conteo.values.sum())

    # ---- Punto 3: escenarios frente a los criterios del laboratorio
    p3 = []
    for nombre, c, modo in ESCENARIOS:
        d = estable(nombre)
        inicio = cortes[nombre] or 0
        dur = DURACION - inicio
        w = d.groupby("replica")["tiempo_sistema"].mean()
        wq = d.groupby("replica")["espera"].mean()
        rho = d.groupby("replica")["servicio"].sum() / (dur * c)
        lq = d.groupby("replica")["espera"].sum() / (dur * c)        # cola promedio por cajero
        p5 = (d["espera"] > 5).mean()
        fila = {"escenario": nombre, "cajeros": c, "llegadas": modo, "estado_estable": cortes[nombre] is not None,
                "Wq_min": wq.mean(), "Wq_ic95": f"[{ic95(wq)[2]:.2f}, {ic95(wq)[3]:.2f}]", "W_min": w.mean(),
                "rho": rho.mean(), "Lq": lq.mean(), "P_espera_mayor_5min": p5,
                "Wq_teorico_MM1": teorico(c, modo)["Wq"], "rho_teorico": teorico(c, modo)["rho"]}
        fila["cumple_criterios"] = (fila["Wq_min"] < CRITERIOS["Wq"] and fila["W_min"] < CRITERIOS["W"]
                                    and fila["rho"] <= CRITERIOS["rho_max"] and fila["Lq"] < CRITERIOS["Lq"]
                                    and fila["P_espera_mayor_5min"] < CRITERIOS["p_espera_5"]
                                    and fila["estado_estable"])
        p3.append(fila)
    p3 = pd.DataFrame(p3)

    # ---- Punto 4: verificación y validación
    # (a) Verificación: un cajero con solo usuarios rápidos es un M/M/1 puro (λ=1/3, μ=1) -> W=1.5, Wq=0.5
    ver = []
    for r in range(1, 11):
        v = pd.DataFrame(simular(1, "por_tipo", 5000 + r, duracion=20000, tipos_activos=[0]))
        v = v[v["llegada"] >= 200]
        ver.append({"replica": r, "W": v["tiempo_sistema"].mean(), "Wq": v["espera"].mean(),
                    "rho": v["servicio"].sum() / (20000 - 200)})
    ver = pd.DataFrame(ver)
    teo_v = {"W": 1.5, "Wq": 0.5, "rho": 1 / 3}
    p4 = []
    for k in ["W", "Wq", "rho"]:
        t_stat, pval = stats.ttest_1samp(ver[k], teo_v[k])
        m, s, lo, hi = ic95(ver[k])
        p4.append({"prueba": "Verificación M/M/1 puro (usuarios rápidos)", "metrica": k, "simulado": m,
                   "teorico": teo_v[k], "ic95_inf": lo, "ic95_sup": hi, "p_valor": pval,
                   "resultado": "Coincide (p > 0.05)" if pval > 0.05 else "Difiere"})
    # (b) Validación del modelo base frente a la teoría
    rho_b = base.groupby("replica")["servicio"].sum() / ((DURACION - cortes["Base_3_cajeros"]) * 3)
    lam_b = base.groupby("replica").size() / ((DURACION - cortes["Base_3_cajeros"]) * 3)
    teo_b = teorico(3, "un_flujo")
    for k, serie, ref in [("rho", rho_b, teo_b["rho"]), ("lambda_por_cajero", lam_b, teo_b["lambda"])]:
        t_stat, pval = stats.ttest_1samp(serie, ref)
        m, s, lo, hi = ic95(serie)
        p4.append({"prueba": "Validación escenario base (3 cajeros)", "metrica": k, "simulado": m, "teorico": ref,
                   "ic95_inf": lo, "ic95_sup": hi, "p_valor": pval,
                   "resultado": "Coincide (p > 0.05)" if pval > 0.05 else "Difiere"})
    p4.append({"prueba": "Validación escenario base (3 cajeros)", "metrica": "proporciones de usuarios (chi²)",
               "simulado": None, "teorico": None, "ic95_inf": None, "ic95_sup": None, "p_valor": chi.pvalue,
               "resultado": "Coincide (p > 0.05)" if chi.pvalue > 0.05 else "Difiere"})
    p4 = pd.DataFrame(p4)

    # ---- Punto 5: antes y después de eliminar el transitorio
    p5 = []
    for nombre, c, modo in ESCENARIOS:
        if cortes[nombre] is None:
            continue
        todo, est = datos[nombre], estable(nombre)
        for k, col in [("W", "tiempo_sistema"), ("Wq", "espera")]:
            antes = todo.groupby("replica")[col].mean()
            despues = est.groupby("replica")[col].mean()
            p5.append({"escenario": nombre, "metrica": k, "punto_corte_min": cortes[nombre],
                       "con_transitorio": antes.mean(), "sin_transitorio": despues.mean(),
                       "cambio_%": 100 * (despues.mean() - antes.mean()) / antes.mean(),
                       "de_con": antes.std(ddof=1), "de_sin": despues.std(ddof=1)})
    p5 = pd.DataFrame(p5)

    # ---- Guardar tablas
    todos = pd.concat([d.assign(escenario=n) for n, d in datos.items()], ignore_index=True)
    todos.to_csv(os.path.join(RES, "clientes.csv"), index=False, encoding="utf-8-sig")
    resumen_rep = pd.DataFrame([{"parametro": "réplicas piloto", "valor": REPLICAS_PILOTO},
                                {"parametro": "réplicas necesarias (error 5 %)", "valor": n_req},
                                {"parametro": "réplicas usadas", "valor": REPLICAS},
                                {"parametro": "duración por réplica (min)", "valor": DURACION},
                                {"parametro": "punto de corte base (min)", "valor": cortes["Base_3_cajeros"]},
                                {"parametro": "ANOVA atención por cajero (p)", "valor": anova.pvalue},
                                {"parametro": "chi² proporciones (p)", "valor": chi.pvalue}])
    with pd.ExcelWriter(os.path.join(RES, "resultados_parqueaderos.xlsx")) as xl:
        resumen_rep.to_excel(xl, sheet_name="parametros", index=False)
        estado.to_excel(xl, sheet_name="estado_estable", index=False)
        p1.round(4).to_excel(xl, sheet_name="punto1_cajeros", index=False)
        p2.round(4).to_excel(xl, sheet_name="punto2_tipos", index=False)
        conteo.reset_index().to_excel(xl, sheet_name="punto2_conteo_replica", index=False)
        p3.round(4).to_excel(xl, sheet_name="punto3_escenarios", index=False)
        p4.round(4).to_excel(xl, sheet_name="punto4_validacion", index=False)
        p5.round(4).to_excel(xl, sheet_name="punto5_transitorio", index=False)
        todos.round(4).to_excel(xl, sheet_name="clientes", index=False)

    graficas(curvas, cortes, p1, p2, p3, p4, p5)

    pd.set_option("display.width", 220)
    print("\nEstado estable:\n", estado.to_string(index=False))
    print("\nPunto 1 - atención por cajero (base):\n", p1[["cajero", "media_min", "de_min", "ic95_inf", "ic95_sup"]].round(3).to_string(index=False),
          f"\n  ANOVA p = {anova.pvalue:.3f}")
    print("\nPunto 2 - usuarios por tipo (base):\n", p2[["tipo_usuario", "usuarios_promedio", "porcentaje_simulado", "porcentaje_esperado"]].round(3).to_string(index=False),
          f"\n  chi² p = {chi.pvalue:.3f}")
    print("\nPunto 3 - escenarios:\n", p3[["escenario", "estado_estable", "Wq_min", "W_min", "rho", "Lq", "P_espera_mayor_5min", "cumple_criterios"]].round(3).to_string(index=False))
    print("\nPunto 4 - verificación y validación:\n", p4[["prueba", "metrica", "simulado", "teorico", "p_valor", "resultado"]].round(4).to_string(index=False))
    print("\nPunto 5 - antes y después del transitorio:\n", p5[["escenario", "metrica", "con_transitorio", "sin_transitorio", "cambio_%"]].round(3).to_string(index=False))
    print("\nArchivos guardados en resultados/ y figuras/")


def estilo(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.25)


def graficas(curvas, cortes, p1, p2, p3, p4, p5):
    plt.rcParams.update({"font.size": 10, "axes.titlesize": 11})

    # Estado estable (escenario base y sensibilidad)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), sharey=False)
    for ax, nombres, titulo in [(axes[0], ["Base_3_cajeros"], "Escenario base, 3 cajeros"),
                                (axes[1], ["Sensibilidad_4_cajeros", "Sensibilidad_3_cajeros"], "Escenario de sensibilidad")]:
        for nombre, color in zip(nombres, [AZUL, NARANJA]):
            serie, movil, corte, nivel = curvas[nombre]
            x = (serie.index + 1) * INTERVALO
            ax.plot(x, serie.values, color=color, alpha=0.25, linewidth=1)
            ax.plot(x, movil.values, color=color, linewidth=2, label=f"{nombre.replace('_', ' ')} (promedio móvil)")
            if corte:
                ax.axvline(corte, color=color, linestyle="--", linewidth=1.2)
                ax.annotate(f"corte: {corte} min", (corte, movil.max() * 0.95), xytext=(6, 0),
                            textcoords="offset points", fontsize=9, color="#444441")
        ax.set_title(titulo); ax.set_xlabel("Tiempo de simulación (min)"); ax.set_ylabel("Tiempo promedio en el sistema (min)")
        ax.legend(frameon=False, fontsize=9); estilo(ax)
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "fig_estado_estable.png"), dpi=300); plt.close(fig)

    # Punto 1
    fig, ax = plt.subplots(figsize=(7, 4.2))
    err = [p1["media_min"] - p1["ic95_inf"], p1["ic95_sup"] - p1["media_min"]]
    ax.bar(p1["cajero"].astype(str), p1["media_min"], color=AZUL, width=0.55, yerr=err, capsize=6, ecolor="#444441")
    for x, v in zip(range(len(p1)), p1["media_min"]):
        ax.text(x, v / 2, f"{v:.2f}", ha="center", color="white", fontsize=10)
    ax.set_xlabel("Cajero"); ax.set_ylabel("Tiempo promedio de atención (min)")
    ax.set_title("Punto 1. Tiempo promedio de atención por cajero (IC 95 %)"); estilo(ax)
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "fig_punto1_atencion_cajero.png"), dpi=300); plt.close(fig)

    # Punto 2
    fig, ax = plt.subplots(figsize=(8, 4.2))
    x = np.arange(len(TIPOS)); w = 0.38
    ax.bar(x - w / 2, 100 * p2["porcentaje_simulado"], w, color=AZUL, label="Simulado")
    ax.bar(x + w / 2, 100 * p2["porcentaje_esperado"], w, color=GRIS, label="Esperado (enunciado)")
    for i, (u, ps) in enumerate(zip(p2["usuarios_promedio"], p2["porcentaje_simulado"])):
        ax.text(i - w / 2, 100 * ps + 0.6, f"{u:.0f} usuarios", ha="center", fontsize=8.5)
    ax.set_xticks(x, TIPOS); ax.set_ylabel("Porcentaje de usuarios (%)")
    ax.set_title("Punto 2. Usuarios promedio por tipo en la totalidad de cajeros"); ax.set_ylim(0, 33)
    ax.legend(frameon=False, ncol=2, loc="upper left"); estilo(ax)
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "fig_punto2_usuarios_tipo.png"), dpi=300); plt.close(fig)

    # Punto 3 (dos paneles: espera y utilización, cada uno con su criterio)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    etiquetas = [n.replace("_cajeros", " cajeros").replace("_", "\n", 1) for n in p3["escenario"]]
    colores = [AZUL if m == "un_flujo" else NARANJA for m in p3["llegadas"]]
    wq = p3["Wq_min"].clip(upper=30)
    axes[0].bar(etiquetas, wq, color=colores)
    axes[0].axhline(CRITERIOS["Wq"], color="#444441", linestyle="--", linewidth=1)
    axes[0].text(len(etiquetas) - 0.5, CRITERIOS["Wq"] + 0.5, "criterio: Wq < 3 min", ha="right", fontsize=9)
    for i, v in enumerate(p3["Wq_min"]):
        axes[0].text(i, min(v, 30) + 0.5, f"{v:.1f}" if v < 30 else f"{v:.0f} (sin estado estable)", ha="center", fontsize=8.5)
    axes[0].set_ylabel("Espera promedio en cola, Wq (min)"); axes[0].set_title("Espera promedio por escenario")
    axes[1].bar(etiquetas, 100 * p3["rho"], color=colores)
    axes[1].axhline(85, color="#444441", linestyle="--", linewidth=1)
    axes[1].text(len(etiquetas) - 0.5, 87, "criterio: ρ ≤ 85 %", ha="right", fontsize=9)
    axes[1].set_ylabel("Utilización por cajero, ρ (%)"); axes[1].set_title("Utilización por escenario")
    for ax in axes:
        ax.tick_params(axis="x", labelsize=8.5); estilo(ax)
    from matplotlib.patches import Patch
    axes[1].legend(handles=[Patch(color=AZUL, label="Base (un solo flujo)"), Patch(color=NARANJA, label="Sensibilidad (flujo por tipo)")],
                   frameon=False, fontsize=9, loc="upper left")
    fig.suptitle("Punto 3. Comparación de escenarios frente a los criterios de decisión", fontsize=11)
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "fig_punto3_escenarios.png"), dpi=300); plt.close(fig)

    # Punto 4: verificación (simulado vs teórico, M/M/1 puro)
    v = p4[p4["prueba"].str.startswith("Verificación")]
    fig, ax = plt.subplots(figsize=(7, 4.2))
    x = np.arange(len(v)); w = 0.38
    ax.bar(x - w / 2, v["simulado"], w, color=AZUL, label="Simulado (IC 95 %)",
           yerr=[v["simulado"] - v["ic95_inf"], v["ic95_sup"] - v["simulado"]], capsize=5, ecolor="#444441")
    ax.bar(x + w / 2, v["teorico"], w, color=GRIS, label="Teoría M/M/1")
    ax.set_xticks(x, ["W (min)", "Wq (min)", "ρ"]); ax.legend(frameon=False)
    ax.set_title("Punto 4. Verificación: simulación frente a la teoría M/M/1\n(cajero con solo usuarios rápidos, λ = 1/3, μ = 1)"); estilo(ax)
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "fig_punto4_verificacion.png"), dpi=300); plt.close(fig)

    # Punto 5: antes y después
    d = p5[p5["metrica"] == "W"]
    fig, ax = plt.subplots(figsize=(8, 4.2))
    x = np.arange(len(d)); w = 0.38
    ax.bar(x - w / 2, d["con_transitorio"], w, color=GRIS, label="Con transitorio")
    ax.bar(x + w / 2, d["sin_transitorio"], w, color=AZUL, label="Sin transitorio")
    for i, (a, b) in enumerate(zip(d["con_transitorio"], d["sin_transitorio"])):
        ax.text(i - w / 2, a + 0.15, f"{a:.2f}", ha="center", fontsize=8.5)
        ax.text(i + w / 2, b + 0.15, f"{b:.2f}", ha="center", fontsize=8.5)
    ax.set_xticks(x, [n.replace("_cajeros", " cajeros").replace("_", "\n", 1) for n in d["escenario"]], fontsize=8.5)
    ax.set_ylabel("Tiempo promedio en el sistema, W (min)")
    ax.set_title("Punto 5. Tiempo en el sistema antes y después de eliminar el transitorio"); ax.legend(frameon=False); estilo(ax)
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "fig_punto5_antes_despues.png"), dpi=300); plt.close(fig)


if __name__ == "__main__":
    main()
