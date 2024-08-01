from flask import Flask, request, jsonify, send_from_directory
import math
import webbrowser
import threading
import time
import signal
import sys

app = Flask(__name__, static_folder='static')

@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')
def ceil_round(number, decimal_places=0):
    factor = 10 ** decimal_places
    return math.ceil(number * factor) / factor

q_e = 0.9 # Эталонный расход ВВ, q_э [кг/м^3]
e_array = [1, 1, 1.15, 1.1, 1.15, 1.1, 1.15, 1.1, 1.15] # Переводной коэффициент, e
size_array = [0.25, 0.5, 0.75, 1, 1.25, 1.5]
K_d_array = [1.3, 1, 0.85, 0.75, 0.7, 0.65]

zar_values = [77.12, 77.12, 77, 67, 77, 67, 77, 67, 77]  # Цены зарядов по вариантам
patron_values = [106.14, 106.14, 106.14, 106.14, 106.14, 106.14, 106.14, 106.14, 120] # Цены патронов по вариантам
volnovod_values_1 = [325.33, 325.33, 325.33, 325.33, 325.33, 325.33, 261.33, 261.33, 325.33] # Волновод первый
volnovod_values_2 = [261.33, 261.33, 261.33, 261.33, 0, 0, 0, 0, 261.33]
def round_down_to_nearest(value, size_options, kd_options):
    if value < size_options[0]:
        return kd_options[0], size_options[0]  # Return the smallest K_d if value is smaller than the smallest size
    for i in range(len(size_options) - 1, -1, -1):
        if value >= size_options[i]:
            return kd_options[i], size_options[i]
    return kd_options[-1], size_options[-1]  # Return the smallest value if none is greater than or equal

@app.route('/calculate', methods=['POST'])
def calculate():
    data = request.json
    d = float(data['d'])
    V = float(data['V'])
    a = float(data['a'])
    b = float(data['b'])
    gamma = float(data['gamma'])
    H = float(data['H'])
    l_per = float(data['l_per'])
    l_zab = float(data['l_zab'])
    del_value = float(data['del'])
    zp_sr_vzriv = float(data['zp_sr_vzriv'])
    zp_sr_gor = float(data['zp_sr_gor'])
    variant_index = int(data['variant']) - 1  # Convert to zero-based index
    e = e_array[variant_index]
    zar_value = zar_values[variant_index]
    patron_value = patron_values[variant_index]
    volnovod_value_1 = volnovod_values_1[variant_index]
    volnovod_value_2 = volnovod_values_2[variant_index]

    size = float(data['size'])
    K_d, nearest_size = round_down_to_nearest(size, size_array, K_d_array)

    ZP_byr = 65.24 # З/п машиниста буровой установки
    ZR_byr_fot = ZP_byr * 0.337 # Отчисления от ФОТ
    toplivo = 126.18
    instr = 69.82 # Инструменты
    remont = 131.74
    byr_metr = ZP_byr + ZR_byr_fot + toplivo + instr + remont

    ZP_vzriv_metr = zp_sr_vzriv / 70280 # з/п взрывника за 1 м3
    ZP_gor_metr = zp_sr_gor / 70280 # з/п горного мастера за 1 м3
    FOT_vzriv = ZP_vzriv_metr * V * 5
    FOT_gor = ZP_gor_metr * V * 1
    minus_FOT_vzriv = 0.337 * FOT_vzriv # Отчисления от ФОТ
    minus_FOT_gor = 0.337 * FOT_gor
    ZP_vzriv = FOT_vzriv + minus_FOT_vzriv # з/п взрывника
    ZP_gor = FOT_gor + minus_FOT_gor # з/п горного мастера

    # formulas
    n = ceil_round(V / (a * b * H), 0)  # Кол-во взрываемых скважин, n [шт.]
    l_byr = n * (H + l_per) # Кол-во буро-метров, l_бур [п.м.]
    l_zar = H + l_per - l_zab # Длина заряда, l_зар [м]
    P = round(((math.pi * d**2) / 4) * del_value, 2) # Вместимость скважины, P [кг/м]
    Q_z = l_zar * P # Масса сплошного заряда в скважине, Q_з [кг]
    q_p = round(q_e * e * K_d * gamma / 2.6, 2) # Расчетный удельный расход ВВ, q_p [кг/м^3]
    Q_all = Q_z * n # Общий расход ВВ, Q_общ [кг]
    ZAR_COST = Q_all * zar_value
    PATRON_COST = n * patron_value * 2
    VOLNOVOD_COST = n * volnovod_value_1 + n * volnovod_value_2
    VV_total = ZAR_COST + PATRON_COST + VOLNOVOD_COST
    BYR_COST = l_byr * byr_metr
    ZP_COST = ZP_vzriv + ZP_gor
    total_COST = VV_total + BYR_COST + ZP_COST

    L = H + l_per # глубина скважины
    n_z = ceil_round(l_zar / L, 2) # Коэффициент заполнения скважин взрывчатым веществом
    l_n = L - l_zar # Длина, свободная от заряда
    n_zab = l_zab / l_n # Коэффициент заполнения скважин забойкой
    f = 14 # Коэффициент крепости пород
    K_gr = 1.5 # Коэффициент, зависящий от группы пород по СНиП
    K_t = 1.5 # Коэффициент, зависящий от времени замедления между группами одновременно взрываемых зарядов
    K_z = l_zab / d # Коэффициент, зависящий от отношения длины забойки к диаметру скважины
    K_r = 12 # Коэффициент, зависящий от свойств грунтов в основании охраняемого здания
    K_t = 1 # Коэффициент, учитывающий температуру воздуха (при отрицательной 1,5)
    N = 2 # Максимальное число скважин в группе
    r_c_dop = 2000 # Расстояние от места взрыва до охраняемого здания
    E_v = 12 * P * d * K_z * N # Эквивалентная масса заряда
    Q_gr = Q_z * N # Вес суммарного максимального заряда в одной группе скважин
    N_gr = Q_all / Q_gr # Количество групп
    U = 0.37 # Допустимая скорость колебания грунта в основании охраняемых зданий для дома № 2, ул. Песчаная и здания средней школы
    K_c = 2 # Коэффициент, зависящий от типа сооружения
    alp = 2 # Коэффициент, зависящий от условий взрывания

    proverka_1 = 1250 * n_z * math.sqrt((f/(1+n_zab)*d/a)) # Расстояние, опасное для людей по разлету отдельных кусков породы
    proverka_3 = ((K_r * K_c * alp) / N_gr ** (1. / 4) * Q_all ** (1. / 3)) * 2 # Сейсмически безопасное расстояние по методике ФНиП от места взрыва до охраняемого здания
    proverka_4 = (Q_gr / (U/470)**(1.93)) ** (1. / 3)

    print(f"proverka 1: {proverka_1}")
    print(f"proverka 3: {proverka_3}")
    print(f"proverka 4: {proverka_4}")
    print(f"r_c_dop: {r_c_dop}")

    return jsonify({
        'n': n,
        'l_byr': l_byr,
        'l_zar': l_zar,
        'P': P,
        'Q_z': Q_z,
        'q_p': q_p,
        'Q_all': Q_all,
        'ZAR_COST': ZAR_COST,
        'PATRON_COST': PATRON_COST,
        'VOLNOVOD_COST': VOLNOVOD_COST,
        'VV_total': VV_total,
        'BYR_COST': BYR_COST,
        'ZP_COST': ZP_COST,
        'total_COST': total_COST,
        'proverka_1': proverka_1,
        'proverka_3': proverka_3,
        'proverka_4': proverka_4,
        'r_c_dop': r_c_dop
    })

def open_browser():
    time.sleep(1)  # Wait for the server to start
    webbrowser.open("http://127.0.0.1:5000")

def run_app():
    threading.Thread(target=open_browser).start()
    app.run(debug=False)

def signal_handler(sig, frame):
    print('Exiting...')
    sys.exit(0)

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    run_app()

