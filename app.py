from datetime import date, datetime, timedelta
import os
import random
import requests
from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash
import sqlalchemy

app = Flask(__name__)
# Configuración segura de clave secreta y credenciales de correo
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'clave_secreta_super_segura')

# Ajuste seguro de la ruta de la base de datos
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'prestamos.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# ==========================================
# CONFIGURACIÓN DE CORREO (API HTTPS DE BREVO)
# ==========================================
# Render bloquea el tráfico saliente por los puertos SMTP (25, 465, 587) en los
# servicios web gratuitos desde el 26/09/2025, por lo que Flask-Mail (SMTP) nunca
# logra conectar y las peticiones se quedan colgadas o terminan en timeout/caída.
# Brevo (antes Sendinblue) envía correos vía HTTPS (puerto 443), que Render sí permite.
BREVO_API_KEY = os.environ.get('BREVO_API_KEY')
BREVO_SENDER_EMAIL = os.environ.get('BREVO_SENDER_EMAIL', os.environ.get('MAIL_USERNAME'))
BREVO_SENDER_NAME = 'Fenix Credit'

db = SQLAlchemy(app)


def enviar_correo(destinatario, asunto, cuerpo_texto):
    """Envía un correo transaccional usando la API HTTPS de Brevo.
    Devuelve True si Brevo confirmó el envío, False en caso contrario."""
    if not BREVO_API_KEY:
        app.logger.warning('BREVO_API_KEY no está configurada; no se pudo enviar el correo.')
        return False
    try:
        resp = requests.post(
            'https://api.brevo.com/v3/smtp/email',
            headers={
                'api-key': BREVO_API_KEY,
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            },
            json={
                'sender': {'name': BREVO_SENDER_NAME, 'email': BREVO_SENDER_EMAIL},
                'to': [{'email': destinatario}],
                'subject': asunto,
                'textContent': cuerpo_texto,
            },
            timeout=10,
        )
        if resp.status_code in (200, 201):
            return True
        app.logger.warning(f'Brevo respondió {resp.status_code}: {resp.text}')
        return False
    except requests.RequestException as e:
        app.logger.warning(f'Error de red al enviar correo con Brevo: {e}')
        return False


# ==========================================
# MODELOS DE BASE DE DATOS
# ==========================================

class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)


class Ruta(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False, unique=True)
    descripcion = db.Column(db.String(250), nullable=True)
    color = db.Column(db.String(30), default='Azul')
    cobrador = db.Column(db.String(100), nullable=True)
    estado = db.Column(db.String(20), default='Activa')
    
    clientes = db.relationship('Cliente', backref='ruta', lazy=True)


class Cliente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    telefono = db.Column(db.String(20), nullable=False)
    
    ruta_id = db.Column(db.Integer, db.ForeignKey('ruta.id'), nullable=True)
    orden_ruta = db.Column(db.Integer, default=0)
    
    prestamos = db.relationship('Prestamo', backref='cliente', lazy=True, cascade="all, delete-orphan")


class Prestamo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=False)
    capital_inicial = db.Column(db.Float, nullable=False)
    capital_actual = db.Column(db.Float, nullable=False, default=0.0)
    tasa_interes = db.Column(db.Float, nullable=False)
    cuotas_totales = db.Column(db.Integer, nullable=True)
    modalidad = db.Column(db.String(50), default='MENSUAL')
    tipo_amortizacion = db.Column(db.String(50), default='CAPITAL AL FINAL')
    porcentaje_mora = db.Column(db.Float, default=0.0)
    porcentaje_comision = db.Column(db.Float, default=0.0)
    
    codeudor_nombre = db.Column(db.String(100), nullable=True)
    codeudor_identificacion = db.Column(db.String(50), nullable=True)
    codeudor_telefono = db.Column(db.String(30), nullable=True)
    codeudor_direccion = db.Column(db.String(200), nullable=True)

    proximo_pago = db.Column(db.String(20), nullable=False)
    estado = db.Column(db.String(20), default='Activo')
    
    cuotas = db.relationship('CuotaPrestamo', backref='prestamo', lazy=True, cascade="all, delete-orphan")
    pagos = db.relationship('Pago', backref='prestamo', lazy=True, cascade="all, delete-orphan")


class CuotaPrestamo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    prestamo_id = db.Column(db.Integer, db.ForeignKey('prestamo.id'), nullable=False)
    numero_cuota = db.Column(db.Integer, nullable=False)
    fecha_vencimiento = db.Column(db.String(20), nullable=False)
    valor_cuota = db.Column(db.Float, nullable=False)
    interes_esperado = db.Column(db.Float, nullable=False)
    capital_esperado = db.Column(db.Float, nullable=False)
    estado = db.Column(db.String(20), default='Pendiente')


class Pago(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    prestamo_id = db.Column(db.Integer, db.ForeignKey('prestamo.id'), nullable=False)
    concepto = db.Column(db.String(100), nullable=False)
    fecha = db.Column(db.String(20), nullable=False)
    fecha_vencimiento = db.Column(db.String(20), nullable=False)
    total_pago = db.Column(db.Float, nullable=False)
    capital = db.Column(db.Float, default=0.0)
    interes = db.Column(db.Float, default=0.0)
    mora = db.Column(db.Float, default=0.0)


class SolicitudPrestamo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    telefono = db.Column(db.String(30), nullable=False)
    email = db.Column(db.String(120), nullable=True)
    monto_solicitado = db.Column(db.Float, nullable=False)
    cuotas = db.Column(db.Integer, nullable=True)
    motivo = db.Column(db.String(250), nullable=True)
    estado = db.Column(db.String(30), default='Pendiente')
    fecha_solicitud = db.Column(db.String(20), default=lambda: date.today().strftime('%Y-%m-%d'))


# ==========================================
# INICIALIZACIÓN DE LA BASE DE DATOS
# ==========================================

with app.app_context():
    db.create_all()


# ==========================================
# FUNCIONES AUXILIARES
# ==========================================

def obtener_multiplicador_meses(modalidad):
    mod = (modalidad or '').upper()
    if 'BIMESTRAL' in mod:
        return 2.0
    elif 'TRIMESTRAL' in mod:
        return 3.0
    elif 'QUINCENAL' in mod:
        return 15.0 / 30.0
    elif 'SEMANAL' in mod:
        return 7.0 / 30.0
    elif 'DIARIO' in mod:
        return 1.0 / 30.0
    else:  
        return 1.0
 
 
def validar_password(pwd):
    if len(pwd) < 8:
        return 'La contraseña debe tener al menos 8 caracteres.'
    if not any(c.isupper() for c in pwd):
        return 'Debe incluir al menos una letra mayúscula.'
    if not any(c.islower() for c in pwd):
        return 'Debe incluir al menos una letra minúscula.'
    if not any(c.isdigit() for c in pwd):
        return 'Debe incluir al menos un número.'
    return None


# ==========================================
# RUTAS DE AUTENTICACIÓN Y REGISTRO DIRECTO
# ==========================================

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = Usuario.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            return redirect(url_for('dashboard'))
        flash('Correo o contraseña incorrectos.', 'error')
    return render_template('login.html')


@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        # Validación estricta de contraseñas coincidentes
        if password != confirm_password:
            flash('Invalido: Las contraseñas no coinciden.', 'error')
            return redirect(url_for('registro'))

        error_pwd = validar_password(password)
        if error_pwd:
            flash(error_pwd, 'error')
            return redirect(url_for('registro'))

        user_exist = Usuario.query.filter_by(email=email).first()
        if user_exist:
            flash('Este correo ya está registrado.', 'error')
            return redirect(url_for('registro'))

        # Crear el usuario directamente en la base de datos sin verificación por correo[cite: 5, 6]
        nuevo_usuario = Usuario(
            email=email,
            password=generate_password_hash(password)
        )
        db.session.add(nuevo_usuario)
        db.session.commit()

        flash('¡Cuenta creada exitosamente! Ya puedes iniciar sesión.', 'success')
        return redirect(url_for('login'))

    return render_template('registro.html')


@app.route('/verificar-codigo', methods=['GET', 'POST'])
def verificar_codigo():
    return redirect(url_for('login'))


@app.route('/reenviar-codigo', methods=['POST'])
def reenviar_codigo():
    return redirect(url_for('login'))


# ==========================================
# RUTAS DEL SISTEMA PRINCIPAL
# ==========================================

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    clientes_count = Cliente.query.count()
    prestamos_activos = Prestamo.query.filter_by(estado='Activo').count()

    capital_prestado = db.session.query(db.func.sum(Prestamo.capital_inicial)).filter_by(estado='Activo').scalar() or 0.0

    prestamos_activos_lista = Prestamo.query.filter_by(estado='Activo').all()
    
    total_interes_proyectado = 0.0
    for p in prestamos_activos_lista:
        if p.tipo_amortizacion.upper() in ['CAPITAL AL FINAL', 'CAPITAL_FINAL']:
            mult_meses = obtener_multiplicador_meses(p.modalidad)
            total_interes_proyectado += (p.capital_inicial * (p.tasa_interes / 100.0) * mult_meses) * (p.cuotas_totales or 1)
        else:
            total_interes_proyectado += sum(c.interes_esperado for c in p.cuotas)

    hoy_str = date.today().strftime('%Y-%m-%d')
    cobros_hoy = (
        db.session.query(db.func.sum(Pago.total_pago))
        .filter_by(fecha_vencimiento=hoy_str)
        .scalar()
        or 0.0
    )

    ingresos_meses = [0.0] * 12
    todos_los_pagos = Pago.query.all()
    for p in todos_los_pagos:
        try:
            partes_fecha = p.fecha.split('-')
            if len(partes_fecha) >= 2:
                mes = int(partes_fecha[1])
                if 1 <= mes <= 12:
                    ingresos_meses[mes - 1] += p.total_pago
        except Exception:
            pass

    prestamos = Prestamo.query.all()
    clientes = Cliente.query.all()

    return render_template(
        'dashboard.html',
        clientes_count=clientes_count,
        prestamos_activos=prestamos_activos,
        capital_prestado=capital_prestado,
        total_interes_proyectado=total_interes_proyectado,
        cobros_hoy=cobros_hoy,
        ingresos_meses=ingresos_meses,
        prestamos=prestamos,
        clientes=clientes,
    )


# --- MÓDULO CLIENTES ---
@app.route('/clientes')
def clientes():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    lista_clientes = Cliente.query.all()
    return render_template('clientes.html', clientes=lista_clientes)


@app.route('/clientes/nuevo', methods=['GET', 'POST'])
def agregar_cliente():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        apellidos = request.form.get('apellidos', '')
        nombre_completo = f"{nombre} {apellidos}".strip()
        telefono = request.form.get('telefono')
        
        if not nombre or not telefono:
            flash('Faltan datos obligatorios (Nombre o Teléfono).', 'error')
            return redirect(url_for('agregar_cliente'))
            
        cliente_existente = Cliente.query.filter_by(telefono=telefono).first()
        if cliente_existente:
            flash('Ya existe un cliente registrado con ese número de teléfono.', 'error')
            return redirect(url_for('agregar_cliente'))
            
        nuevo_cliente = Cliente(nombre=nombre_completo, telefono=telefono)
        db.session.add(nuevo_cliente)
        db.session.commit()
        
        flash('¡Cliente registrado exitosamente!', 'success')
        return redirect(url_for('clientes'))
        
    return render_template('agregar_cliente.html')


@app.route('/clientes/borrar/<int:id>', methods=['GET', 'POST'], endpoint='eliminar_cliente')
def borrar_cliente(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    cliente = Cliente.query.get_or_404(id)
    db.session.delete(cliente)
    db.session.commit()
    flash('Cliente eliminado correctamente.', 'success')
    return redirect(url_for('clientes'))


# --- MÓDULO PRÉSTAMOS ---
@app.route('/prestamos')
def prestamos():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    lista_prestamos = Prestamo.query.all()
    prestamos_activos = Prestamo.query.filter_by(estado='Activo').count()
    capital_prestado = db.session.query(db.func.sum(Prestamo.capital_inicial)).scalar() or 0.0
    cobros_hoy = 0.0 
    clientes_count = Cliente.query.count()

    return render_template(
        'prestamos.html', 
        prestamos=lista_prestamos,
        prestamos_activos=prestamos_activos,
        capital_prestado=capital_prestado,
        cobros_hoy=cobros_hoy,
        clientes_count=clientes_count
    )


@app.route('/nuevo_prestamo', methods=['POST'])
def nuevo_prestamo():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    cliente_id = request.form.get('cliente_id')
    nombre = request.form.get('nombre')
    telefono = request.form.get('telefono')

    cliente = None
    if cliente_id:
        cliente = Cliente.query.get(cliente_id)

    if not cliente and nombre and telefono:
        cliente = Cliente.query.filter_by(telefono=telefono).first()
        if not cliente:
            cliente = Cliente(nombre=nombre, telefono=telefono)
            db.session.add(cliente)
            db.session.commit()

    if not cliente:
        flash('Debe seleccionar o registrar un cliente válido.', 'error')
        return redirect(url_for('dashboard'))

    try:
        capital_raw = request.form.get('capital')
        capital = float(capital_raw) if capital_raw and capital_raw.strip() != '' else 0.0

        tasa_raw = request.form.get('tasa')
        tasa = float(tasa_raw) if tasa_raw and tasa_raw.strip() != '' else 0.0

        cuotas_raw = request.form.get('cuotas')
        if cuotas_raw and cuotas_raw.strip() != '':
            cuotas_cant = int(cuotas_raw)
        else:
            cuotas_cant = None
    except ValueError:
        flash('Capital, tasa y cuotas deben ser valores numéricos válidos.', 'error')
        return redirect(url_for('prestamos'))

    if capital <= 0:
        flash('El capital del préstamo debe ser mayor a cero.', 'error')
        return redirect(url_for('prestamos'))

    modalidad = request.form.get('modalidad', 'MENSUAL')
    tipo_amortizacion = request.form.get('tipo_amortizacion', 'interes_fijo')
    proximo_pago = request.form.get('proximo_pago')
    
    mora_raw = request.form.get('mora')
    porcentaje_mora = float(mora_raw) if mora_raw and mora_raw.strip() != '' else 0.0

    comision_raw = request.form.get('comision')
    porcentaje_comision = float(comision_raw) if comision_raw and comision_raw.strip() != '' else 0.0

    codeudor_nombre = request.form.get('codeudor_nombre')
    codeudor_identificacion = request.form.get('codeudor_identificacion')
    codeudor_telefono = request.form.get('codeudor_telefono')
    codeudor_direccion = request.form.get('codeudor_direccion')

    prestamo = Prestamo(
        cliente_id=cliente.id,
        capital_inicial=capital,
        capital_actual=capital,
        tasa_interes=tasa,
        cuotas_totales=cuotas_cant,
        modalidad=modalidad,
        tipo_amortizacion=tipo_amortizacion,
        porcentaje_mora=porcentaje_mora,
        porcentaje_comision=porcentaje_comision,
        codeudor_nombre=codeudor_nombre,
        codeudor_identificacion=codeudor_identificacion,
        codeudor_telefono=codeudor_telefono,
        codeudor_direccion=codeudor_direccion,
        proximo_pago=proximo_pago,
        estado='Activo',
    )
    db.session.add(prestamo)
    db.session.commit()

    fecha_base = datetime.strptime(proximo_pago, '%Y-%m-%d')
    multiplicador_meses = obtener_multiplicador_meses(modalidad)
    i_tasa = (tasa / 100.0) * multiplicador_meses

    def calcular_fecha_vencimiento(f_base, index, mod):
        mod_upper = (mod or '').upper()
        if 'DIARIO' in mod_upper:
            return (f_base + timedelta(days=index)).strftime('%Y-%m-%d')
        elif 'SEMANAL' in mod_upper:
            return (f_base + timedelta(days=7 * index)).strftime('%Y-%m-%d')
        elif 'QUINCENAL' in mod_upper:
            return (f_base + timedelta(days=15 * index)).strftime('%Y-%m-%d')
        elif 'BIMESTRAL' in mod_upper:
            meses_totales = f_base.month - 1 + (2 * index)
            anio = f_base.year + meses_totales // 12
            mes = meses_totales % 12 + 1
            dia = min(f_base.day, [31, 29 if anio % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mes-1])
            return date(anio, mes, dia).strftime('%Y-%m-%d')
        elif 'TRIMESTRAL' in mod_upper:
            meses_totales = f_base.month - 1 + (3 * index)
            anio = f_base.year + meses_totales // 12
            mes = meses_totales % 12 + 1
            dia = min(f_base.day, [31, 29 if anio % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mes-1])
            return date(anio, mes, dia).strftime('%Y-%m-%d')
        else:
            meses_totales = f_base.month - 1 + index
            anio = f_base.year + meses_totales // 12
            mes = meses_totales % 12 + 1
            dia = min(f_base.day, [31, 29 if anio % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mes-1])
            return date(anio, mes, dia).strftime('%Y-%m-%d')

    if cuotas_cant is None or cuotas_cant <= 0:
        val_cuota = capital * i_tasa
        interes_por_cuota = val_cuota
        cap_cuota = 0.0
        nueva_cuota = CuotaPrestamo(
            prestamo_id=prestamo.id,
            numero_cuota=1,
            fecha_vencimiento=proximo_pago,
            valor_cuota=val_cuota,
            interes_esperado=interes_por_cuota,
            capital_esperado=cap_cuota,
            estado='Pendiente'
        )
        db.session.add(nueva_cuota)

    elif tipo_amortizacion == 'cuota_fija' or tipo_amortizacion == 'francesa':
        n = cuotas_cant
        if i_tasa > 0:
            val_cuota = capital * (i_tasa * (1 + i_tasa)**n) / ((1 + i_tasa)**n - 1)
        else:
            val_cuota = capital / n

        capital_pendiente = capital

        for c_num in range(1, cuotas_cant + 1):
            fecha_venc = calcular_fecha_vencimiento(fecha_base, c_num, modalidad)

            interes_esperado = capital_pendiente * i_tasa
            capital_esperado = val_cuota - interes_esperado
            
            if c_num == cuotas_cant:
                capital_esperado = capital_pendiente
                val_cuota = capital_esperado + interes_esperado

            capital_pendiente -= capital_esperado

            nueva_cuota = CuotaPrestamo(
                prestamo_id=prestamo.id,
                numero_cuota=c_num,
                fecha_vencimiento=fecha_venc,
                valor_cuota=round(val_cuota, 2),
                interes_esperado=round(interes_esperado, 2),
                capital_esperado=round(capital_esperado, 2),
                estado='Pendiente'
            )
            db.session.add(nueva_cuota)

    elif tipo_amortizacion.upper() in ['CAPITAL AL FINAL', 'CAPITAL_FINAL']:
        interes_periodico = capital * i_tasa

        for c_num in range(1, cuotas_cant + 1):
            fecha_venc = calcular_fecha_vencimiento(fecha_base, c_num, modalidad)

            if c_num < cuotas_cant:
                capital_esperado = 0.0
                interes_esperado = interes_periodico
                val_cuota = interes_periodico
            else:
                capital_esperado = capital
                interes_esperado = interes_periodico
                val_cuota = capital + interes_periodico

            nueva_cuota = CuotaPrestamo(
                prestamo_id=prestamo.id,
                numero_cuota=c_num,
                fecha_vencimiento=fecha_venc,
                valor_cuota=round(val_cuota, 2),
                interes_esperado=round(interes_esperado, 2),
                capital_esperado=round(capital_esperado, 2),
                estado='Pendiente'
            )
            db.session.add(nueva_cuota)

    else:
        interes_total_esperado = capital * (tasa / 100.0)
        cap_cuota = capital / cuotas_cant
        interes_por_cuota = interes_total_esperado / cuotas_cant
        val_cuota_calculada = cap_cuota + interes_por_cuota

        for i in range(1, cuotas_cant + 1):
            fecha_venc = calcular_fecha_vencimiento(fecha_base, i, modalidad)

            nueva_cuota = CuotaPrestamo(
                prestamo_id=prestamo.id,
                numero_cuota=i,
                fecha_vencimiento=fecha_venc,
                valor_cuota=round(val_cuota_calculada, 2),
                interes_esperado=round(interes_por_cuota, 2),
                capital_esperado=round(cap_cuota, 2),
                estado='Pendiente'
            )
            db.session.add(nueva_cuota)

    db.session.commit()

    flash('Préstamo y calendario de cuotas generado con éxito.', 'success')
    return redirect(url_for('dashboard'))


@app.route('/prestamo/<int:id>')
def detalle_prestamo(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    prestamo = Prestamo.query.get_or_404(id)
    mult_meses = obtener_multiplicador_meses(prestamo.modalidad)

    if prestamo.tipo_amortizacion.upper() in ['CAPITAL AL FINAL', 'CAPITAL_FINAL']:
        total_intereses_esperados = (prestamo.capital_inicial * (prestamo.tasa_interes / 100.0) * mult_meses) * (prestamo.cuotas_totales or 1)
    else:
        total_intereses_esperados = sum(c.interes_esperado for c in prestamo.cuotas)

    total_abonado = sum(p.total_pago for p in prestamo.pagos)
    saldo_total_pendiente = sum(c.capital_esperado for c in prestamo.cuotas if c.estado == 'Pendiente') + sum(c.interes_esperado for c in prestamo.cuotas if c.estado == 'Pendiente')
    
    return render_template(
        'detalle_prestamo.html', 
        prestamo=prestamo,
        total_intereses=total_intereses_esperados,
        total_abonado=total_abonado,
        saldo_total_pendiente=saldo_total_pendiente
    )


@app.route('/prestamo/<int:id>/abonar', methods=['POST'])
def registrar_abono(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    prestamo = Prestamo.query.get_or_404(id)
    concepto = request.form.get('concepto', 'Abono / Pago')

    try:
        total_pago_raw = request.form.get('total_pago')
        total_pago = float(total_pago_raw) if total_pago_raw and total_pago_raw.strip() != '' else 0.0

        capital_raw = request.form.get('capital')
        capital_abonado = float(capital_raw) if capital_raw and capital_raw.strip() != '' else 0.0

        interes_raw = request.form.get('interes')
        interes_abonado = float(interes_raw) if interes_raw and interes_raw.strip() != '' else 0.0

        mora_raw = request.form.get('mora')
        mora_abonada = float(mora_raw) if mora_raw and mora_raw.strip() != '' else 0.0
    except ValueError:
        flash('Los valores del pago deben ser numéricos válidos.', 'error')
        return redirect(url_for('detalle_prestamo', id=id))

    if total_pago <= 0:
        flash('El total del pago debe ser mayor a cero.', 'error')
        return redirect(url_for('detalle_prestamo', id=id))

    fecha_pago = request.form.get('fecha', date.today().strftime('%Y-%m-%d'))
    
    nuevo_pago = Pago(
        prestamo_id=prestamo.id,
        concepto=concepto,
        fecha=fecha_pago,
        fecha_vencimiento=prestamo.proximo_pago,
        total_pago=total_pago,
        capital=capital_abonado,
        interes=interes_abonado,
        mora=mora_abonada
    )
    db.session.add(nuevo_pago)
    
    if capital_abonado > 0:
        prestamo.capital_actual = max(0.0, prestamo.capital_actual - capital_abonado)
        if prestamo.capital_actual == 0:
            prestamo.estado = 'Pagado'

    cuota_pendiente = CuotaPrestamo.query.filter_by(prestamo_id=prestamo.id, estado='Pendiente').order_by(CuotaPrestamo.numero_cuota.asc()).first()
    
    if cuota_pendiente:
        cuota_pendiente.estado = 'Pagada'
        
        f_actual = datetime.strptime(prestamo.proximo_pago, '%Y-%m-%d')
        mod = prestamo.modalidad.upper()
        
        if 'DIARIO' in mod:
            nueva_fecha = f_actual + timedelta(days=1)
        elif 'SEMANAL' in mod:
            nueva_fecha = f_actual + timedelta(days=7)
        elif 'QUINCENAL' in mod:
            nueva_fecha = f_actual + timedelta(days=15)
        elif 'BIMESTRAL' in mod:
            meses_totales = f_actual.month - 1 + 2
            anio = f_actual.year + meses_totales // 12
            mes = meses_totales % 12 + 1
            dia = min(f_actual.day, [31, 29 if anio % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mes-1])
            nueva_fecha = date(anio, mes, dia)
        elif 'TRIMESTRAL' in mod:
            meses_totales = f_actual.month - 1 + 3
            anio = f_actual.year + meses_totales // 12
            mes = meses_totales % 12 + 1
            dia = min(f_actual.day, [31, 29 if anio % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mes-1])
            nueva_fecha = date(anio, mes, dia)
        else:
            meses_totales = f_actual.month - 1 + 1
            anio = f_actual.year + meses_totales // 12
            mes = meses_totales % 12 + 1
            dia = min(f_actual.day, [31, 29 if anio % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mes-1])
            nueva_fecha = date(anio, mes, dia)
            
        prestamo.proximo_pago = nueva_fecha.strftime('%Y-%m-%d')

    db.session.commit()
    flash('Pago registrado y ciclo de cobro actualizado correctamente.', 'success')
    return redirect(url_for('detalle_prestamo', id=prestamo.id))


# --- MÓDULO PAGOS ---
@app.route('/pagos')
def pagos():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    todos_pagos = Pago.query.all()
    return render_template('pagos.html', pagos=todos_pagos)


@app.route('/pago/<int:id>/recibo')
def ver_recibo_pago(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    pago = Pago.query.get_or_404(id)
    prestamo = pago.prestamo
    
    cuotas_totales = prestamo.cuotas_totales
    cuotas_pendientes = sum(1 for c in prestamo.cuotas if c.estado == 'Pendiente')
    cuotas_pagadas = sum(1 for c in prestamo.cuotas if c.estado == 'Pagada')
    
    return render_template(
        'recibo_pago.html', 
        pago=pago, 
        prestamo=prestamo,
        cuotas_pendientes=cuotas_pendientes,
        cuotas_pagadas=cuotas_pagadas,
        cuotas_totales=cuotas_totales
    )


@app.route('/pagos/borrar/<int:id>', methods=['GET', 'POST'])
def borrar_pago(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    pago = Pago.query.get_or_404(id)
    db.session.delete(pago)
    db.session.commit()
    flash('Registro de pago eliminado correctamente.', 'success')
    return redirect(url_for('pagos'))


@app.route('/cobranza')
def cobranza():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    prestamos_activos = Prestamo.query.filter_by(estado='Activo').all()
    return render_template('cobranza.html', prestamos=prestamos_activos)


@app.route('/caja')
def caja():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    prestamos = Prestamo.query.all()
    capital_prestado = sum(p.capital_inicial for p in prestamos)
    
    total_recaudado = 0
    for p in prestamos:
        for pago in p.pagos:
            total_recaudado += pago.total_pago
            
    balance_caja = total_recaudado - capital_prestado
    
    return render_template(
        'caja.html', 
        capital_prestado=capital_prestado,
        total_recaudado=total_recaudado,
        balance_caja=balance_caja
    )


# ==========================================
# MÓDULO DE SOLICITUDES Y PORTAL PÚBLICO
# ==========================================

@app.route('/solicitudes')
def solicitudes():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    estado_filtro = request.args.get('estado', 'Todos')
    if estado_filtro != 'Todos':
        lista_solicitudes = SolicitudPrestamo.query.filter_by(estado=estado_filtro).all()
    else:
        lista_solicitudes = SolicitudPrestamo.query.all()
        
    pendientes = SolicitudPrestamo.query.filter_by(estado='Pendiente').count()
    contactados = SolicitudPrestamo.query.filter_by(estado='Contactados').count()
    en_revision = SolicitudPrestamo.query.filter_by(estado='En Revisión').count()
    aprobados = SolicitudPrestamo.query.filter_by(estado='Aprobados').count()
    rechazados = SolicitudPrestamo.query.filter_by(estado='Rechazados').count()
    convertidos = SolicitudPrestamo.query.filter_by(estado='Convertidos').count()

    return render_template('solicitudes.html', 
                           solicitudes=lista_solicitudes,
                           pendientes=pendientes,
                           contactados=contactados,
                           en_revision=en_revision,
                           aprobados=aprobados,
                           rechazados=rechazados,
                           convertidos=convertidos)


@app.route('/portal/solicitud', methods=['GET', 'POST'])
def portal_solicitud():
    if request.method == 'POST':
        cuotas_raw = request.form.get('cuotas')
        cuotas_val = int(cuotas_raw) if cuotas_raw and cuotas_raw.strip() != '' else None
        
        monto_raw = request.form.get('monto')
        monto_val = float(monto_raw) if monto_raw and monto_raw.strip() != '' else 0.0

        nueva_sol = SolicitudPrestamo(
            nombre=request.form.get('nombre'),
            telefono=request.form.get('telefono'),
            email=request.form.get('email'),
            monto_solicitado=monto_val,
            cuotas=cuotas_val,
            motivo=request.form.get('motivo'),
            estado='Pendiente'
        )
        db.session.add(nueva_sol)
        db.session.commit()
        flash('¡Solicitud enviada con éxito! Nos pondremos en contacto contigo.', 'success')
        return redirect(url_for('portal_solicitud'))
        
    return render_template('portal_solicitud.html')


@app.route('/solicitud/<int:id>/cambiar_estado/<estado>')
def cambiar_estado_solicitud(id, estado):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    sol = SolicitudPrestamo.query.get_or_404(id)
    sol.estado = estado
    db.session.commit()
    flash(f'Estado de la solicitud actualizado a: {estado}', 'success')
    return redirect(url_for('solicitudes'))


@app.route('/solicitudes/borrar/<int:id>', methods=['GET', 'POST'])
def borrar_solicitud(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    sol = SolicitudPrestamo.query.get_or_404(id)
    db.session.delete(sol)
    db.session.commit()
    flash('Solicitud eliminada correctamente.', 'success')
    return redirect(url_for('solicitudes'))


# ==========================================
# MÓDULO DE RUTAS
# ==========================================

@app.route('/rutas', methods=['GET', 'POST'])
def rutas():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        descripcion = request.form.get('descripcion')
        color = request.form.get('color', 'Azul')
        cobrador = request.form.get('cobrador')
        
        if not nombre:
            flash('El nombre de la ruta es obligatorio.', 'error')
            return redirect(url_for('rutas'))
            
        nueva_ruta = Ruta(
            nombre=nombre,
            descripcion=descripcion,
            color=color,
            cobrador=cobrador,
            estado='Activa'
        )
        db.session.add(nueva_ruta)
        db.session.commit()
        flash('Ruta creada exitosamente.', 'success')
        return redirect(url_for('rutas'))
        
    lista_rutas = Ruta.query.all()
    lista_clientes = Cliente.query.all()
    return render_template('rutas.html', rutas=lista_rutas, clientes=lista_clientes)


@app.route('/ruta/<int:id>')
def detalle_ruta(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    ruta = Ruta.query.get_or_404(id)
    clientes_disponibles = Cliente.query.filter((Cliente.ruta_id == None) | (Cliente.ruta_id != id)).all()
    return render_template('detalle_ruta.html', ruta=ruta, clientes_disponibles=clientes_disponibles)


@app.route('/ruta/<int:ruta_id>/asignar_cliente', methods=['POST'])
def asignar_cliente_ruta(ruta_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    cliente_id = request.form.get('cliente_id')
    cliente = Cliente.query.get_or_404(cliente_id)
    cliente.ruta_id = ruta_id
    db.session.commit()
    flash('Cliente agregado a la ruta correctamente.', 'success')
    return redirect(url_for('detalle_ruta', id=ruta_id))


@app.route('/ruta/remover_cliente/<int:cliente_id>', methods=['GET', 'POST'])
def remover_cliente_ruta(cliente_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    cliente = Cliente.query.get_or_404(cliente_id)
    ruta_id = cliente.ruta_id
    cliente.ruta_id = None
    db.session.commit()
    flash('Cliente retirado de la ruta.', 'success')
    return redirect(url_for('detalle_ruta', id=ruta_id))


@app.route('/rutas/borrar/<int:id>', methods=['GET', 'POST'])
def borrar_ruta(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    ruta = Ruta.query.get_or_404(id)
    db.session.delete(ruta)
    db.session.commit()
    flash('Ruta eliminada correctamente.', 'success')
    return redirect(url_for('rutas'))


@app.route('/prestamos/borrar/<int:id>', methods=['GET', 'POST'], endpoint='eliminar_prestamo')
@app.route('/prestamos/eliminar/<int:id>', methods=['GET', 'POST'], endpoint='eliminar_prestamo_alt')
def borrar_prestamo(id):
    app.logger.info("Eliminando préstamo con ID %s", id)
    if 'user_id' not in session:
        return redirect(url_for('login'))
    prestamo = Prestamo.query.get_or_404(id)
    db.session.delete(prestamo)
    db.session.commit()
    flash('Préstamo eliminado correctamente.', 'success')
    return redirect(url_for('prestamos'))


@app.route('/contratos', methods=['GET'])
def contratos():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    prestamo_id = request.args.get('prestamo_id')
    tipo_contrato = request.args.get('tipo', 'prestamo')
    
    prestamo = None
    if prestamo_id:
        prestamo = Prestamo.query.get_or_404(prestamo_id)
        
    lista_prestamos = Prestamo.query.all()
    return render_template('contratos.html', prestamo=prestamo, lista_prestamos=lista_prestamos, tipo=tipo_contrato)


@app.route('/reportes')
def reportes():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('reportes.html')


# ==========================================
# RUTAS DE EXPORTACIÓN A EXCEL
# ==========================================

@app.route('/exportar-cartera-excel')
def exportar_cartera_excel():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    flash('Módulo de exportación de cartera en desarrollo.', 'info')
    return redirect(url_for('reportes'))


@app.route('/exportar-pagos-excel')
def exportar_pagos_excel():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    flash('Módulo de exportación de pagos en desarrollo.', 'info')
    return redirect(url_for('reportes'))


@app.route('/exportar-morosos-excel')
def exportar_morosos_excel():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    flash('Módulo de exportación de morosos en desarrollo.', 'info')
    return redirect(url_for('reportes'))


# ==========================================
# EJECUCIÓN DE LA APLICACIÓN
# ==========================================

if __name__ == '__main__':
    app.run(debug=True)
