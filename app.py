from datetime import date, datetime, timedelta
import os
import random
from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_mail import Mail, Message
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash
import sqlalchemy

app = Flask(__name__)
app.config['SECRET_KEY'] = 'clave_secreta_super_segura'

# Ajuste seguro de la ruta de la base de datos para entornos en la nube (Render)
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'prestamos.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configuración de Correo (Opcional)
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'tu_correo@gmail.com'
app.config['MAIL_PASSWORD'] = 'tu_contrasena_de_aplicacion'
app.config['MAIL_DEFAULT_SENDER'] = 'tu_correo@gmail.com'

db = SQLAlchemy(app)
mail = Mail(app)


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
    cuotas_totales = db.Column(db.Integer, nullable=False)
    modalidad = db.Column(db.String(50), default='MENSUAL')
    tipo_amortizacion = db.Column(db.String(50), default='CAPITAL AL FINAL')
    porcentaje_mora = db.Column(db.Float, default=0.0)
    porcentaje_comision = db.Column(db.Float, default=0.0)
    
    # Datos del Codeudor
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
    cuotas = db.Column(db.Integer, nullable=False)
    motivo = db.Column(db.String(250), nullable=True)
    estado = db.Column(db.String(30), default='Pendiente')
    fecha_solicitud = db.Column(db.String(20), default=lambda: date.today().strftime('%Y-%m-%d'))


# ==========================================
# INICIALIZACIÓN Y MIGRACIONES AUTOMÁTICAS
# ==========================================

with app.app_context():
    db.create_all()
    with db.engine.connect() as conn:
        for col_def in [
            ("capital_actual", "FLOAT DEFAULT 0.0"),
            ("tipo_amortizacion", "VARCHAR(50) DEFAULT 'CAPITAL AL FINAL'"),
            ("porcentaje_mora", "FLOAT DEFAULT 0.0"),
            ("porcentaje_comision", "FLOAT DEFAULT 0.0"),
            ("codeudor_nombre", "VARCHAR(100)"),
            ("codeudor_identificacion", "VARCHAR(50)"),
            ("codeudor_telefono", "VARCHAR(30)"),
            ("codeudor_direccion", "VARCHAR(200)")
        ]:
            try:
                conn.execute(sqlalchemy.text(f"ALTER TABLE prestamo ADD COLUMN {col_def[0]} {col_def[1]}"))
                conn.commit()
            except Exception:
                pass
                
        for col_cliente in [
            ("ruta_id", "INTEGER"),
            ("orden_ruta", "INTEGER DEFAULT 0")
        ]:
            try:
                conn.execute(sqlalchemy.text(f"ALTER TABLE cliente ADD COLUMN {col_cliente[0]} {col_cliente[1]}"))
                conn.commit()
            except Exception:
                pass


# ==========================================
# FUNCIONES AUXILIARES
# ==========================================

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
# RUTAS DE AUTENTICACIÓN
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
        email = request.form['email']
        password = request.form['password']

        error_pwd = validar_password(password)
        if error_pwd:
            flash(error_pwd, 'error')
            return redirect(url_for('registro'))

        user_exist = Usuario.query.filter_by(email=email).first()
        if user_exist:
            flash('Este correo ya está registrado.', 'error')
            return redirect(url_for('registro'))

        hashed_password = generate_password_hash(password)

        nuevo_usuario = Usuario(
            email=email,
            password=hashed_password
        )
        db.session.add(nuevo_usuario)
        db.session.commit()

        flash('¡Registro exitoso! Ya puedes iniciar sesión.', 'success')
        return redirect(url_for('login'))

    return render_template('registro.html')


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
    total_interes_proyectado = sum(p.capital_inicial * (p.tasa_interes / 100.0) * p.cuotas_totales for p in prestamos_activos_lista)

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
        telefono = request.form.get('telefono')
        
        if not nombre or not telefono:
            flash('El nombre y el teléfono son obligatorios.', 'error')
            return redirect(url_for('agregar_cliente'))
            
        cliente_existente = Cliente.query.filter_by(telefono=telefono).first()
        if cliente_existente:
            flash('Ya existe un cliente registrado con ese número de teléfono.', 'error')
            return redirect(url_for('agregar_cliente'))
            
        nuevo_cliente = Cliente(nombre=nombre, telefono=telefono)
        db.session.add(nuevo_cliente)
        db.session.commit()
        
        flash('Cliente registrado exitosamente.', 'success')
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

    if cliente_id:
        cliente = Cliente.query.get(cliente_id)
        if not cliente:
            flash('El cliente seleccionado no existe.', 'error')
            return redirect(url_for('dashboard'))
    elif nombre and telefono:
        cliente = Cliente.query.filter_by(telefono=telefono).first()
        if not cliente:
            cliente = Cliente(nombre=nombre, telefono=telefono)
            db.session.add(cliente)
            db.session.commit()
    else:
        flash('Debe seleccionar o registrar un cliente.', 'error')
        return redirect(url_for('dashboard'))

    capital = float(request.form.get('capital', 0))
    tasa = float(request.form.get('tasa', 0))
    cuotas_cant = int(request.form.get('cuotas', 1))
    modalidad = request.form.get('modalidad', 'MENSUAL')
    tipo_amortizacion = request.form.get('tipo_amortizacion', 'CAPITAL AL FINAL')
    proximo_pago = request.form.get('proximo_pago')
    
    porcentaje_mora = float(request.form.get('mora', 0.0))
    porcentaje_comision = float(request.form.get('comision', 0.0))

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
    interes_por_cuota = capital * (tasa / 100.0)

    for i in range(1, cuotas_cant + 1):
        if modalidad == 'MENSUAL':
            mes = fecha_base.month - 1 + i
            anio = fecha_base.year + mes // 12
            mes = mes % 12 + 1
            dia = min(fecha_base.day, [31, 29 if anio % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mes-1])
            fecha_venc = date(anio, mes, dia).strftime('%Y-%m-%d')
        else:
            fecha_venc = (fecha_base + timedelta(days=7 * i)).strftime('%Y-%m-%d')

        cap_cuota = (capital / cuotas_cant) if tipo_amortizacion == 'FIJA' else (capital if i == cuotas_cant else 0.0)
        val_cuota = interes_por_cuota + cap_cuota

        nueva_cuota = CuotaPrestamo(
            prestamo_id=prestamo.id,
            numero_cuota=i,
            fecha_vencimiento=fecha_venc,
            valor_cuota=val_cuota,
            interes_esperado=interes_por_cuota,
            capital_esperado=cap_cuota,
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
    total_intereses_esperados = prestamo.capital_inicial * (prestamo.tasa_interes / 100.0) * prestamo.cuotas_totales
    total_abonado = sum(p.total_pago for p in prestamo.pagos)
    
    return render_template(
        'detalle_prestamo.html', 
        prestamo=prestamo,
        total_intereses=total_intereses_esperados,
        total_abonado=total_abonado
    )


@app.route('/prestamo/<int:id>/abonar', methods=['POST'])
def registrar_abono(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    prestamo = Prestamo.query.get_or_404(id)
    
    concepto = request.form.get('concepto', 'Abono / Pago')
    total_pago = float(request.form.get('total_pago', 0))
    capital_abonado = float(request.form.get('capital', 0))
    interes_abonado = float(request.form.get('interes', 0))
    mora_abonada = float(request.form.get('mora', 0))
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

    db.session.commit()
    flash('Pago y abono registrado correctamente.', 'success')
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
    return render_template('recibo_pago.html', pago=pago)


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
        nueva_sol = SolicitudPrestamo(
            nombre=request.form.get('nombre'),
            telefono=request.form.get('telefono'),
            email=request.form.get('email'),
            monto_solicitado=float(request.form.get('monto', 0)),
            cuotas=int(request.form.get('cuotas', 1)),
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
# EJECUCIÓN DE LA APLICACIÓN
# ==========================================

if __name__ == '__main__':
    app.run(debug=True)
